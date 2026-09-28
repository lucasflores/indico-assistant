"""POST /plans/<id>/token (spec 020 R10): a plan card shown again after navigating gets a fresh confirm token;
the old buttons stop working, and every spec 019 guarantee stays (single use, expiry, supersession)."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

import indico_assistant.controllers.actions as actions_module
from indico_assistant.controllers.actions import RHPlanToken
from indico_assistant.models import ChatSession
from indico_assistant.services.actions import executor


@pytest.fixture
def chat(db, dummy_user):
    session = ChatSession(user_id=dummy_user.id)
    db.session.add(session)
    db.session.flush()
    return session


@pytest.fixture
def shown(chat, dummy_user):
    return executor.create_plan(dummy_user, chat.id, summary='Create a meeting',
                                steps=[{'n': 1, 'action': 'create_event', 'args': {}, 'description': 'Create “Sync”'}])


@pytest.fixture
def reissue(monkeypatch, dummy_user):
    request = MagicMock()
    monkeypatch.setattr(actions_module, 'request', request)

    def _call(plan_id, user=dummy_user):
        request.view_args = {'plan_id': str(plan_id)}
        rh = RHPlanToken.__new__(RHPlanToken)
        rh._user = user
        with patch.object(RHPlanToken, 'plugin', MagicMock()):
            response, status = rh._process()
        return status, response.get_json()
    return _call


def test_the_new_token_confirms_once_and_the_old_one_never(reissue, shown, dummy_user):
    plan, old_token = shown
    status, body = reissue(plan.id)
    assert status == 200 and body['id'] == str(plan.id) and body['token'] and body['token'] != old_token
    assert body['steps'] == [{'n': 1, 'description': 'Create “Sync”', 'side_effects': []}]
    assert executor.confirm(plan.id, dummy_user, old_token) == 'invalid_token'
    assert executor.confirm(plan.id, dummy_user, body['token']) == 'confirmed'
    assert executor.confirm(plan.id, dummy_user, body['token']) == 'not_confirmable'


def test_only_the_owner(reissue, shown, create_user):
    plan, _ = shown
    status, _ = reissue(plan.id, user=create_user(55))
    assert status == 404


@pytest.mark.parametrize('state', ['confirmed', 'superseded', 'expired', 'cancelled'])
def test_only_a_plan_still_waiting(reissue, shown, chat, dummy_user, state):
    plan, token = shown
    if state == 'confirmed':
        executor.confirm(plan.id, dummy_user, token)
    elif state == 'superseded':
        executor.create_plan(dummy_user, chat.id, summary='Revised', steps=[])
    elif state == 'expired':
        plan.expires_at -= timedelta(hours=1)
    else:
        executor.cancel(plan.id, dummy_user)
    status, body = reissue(plan.id)
    assert status == 409 and body['error'] == 'PLAN_NOT_CONFIRMABLE'
