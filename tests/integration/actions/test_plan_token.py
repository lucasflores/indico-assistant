"""POST /plans/<id>/token (spec 020 R10): a plan card shown again after navigating gets its confirm token. The
same one every time, so a second tab's buttons keep working (review, PR #5); every spec 019 guarantee stays
(single use, expiry, supersession)."""

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


def test_the_token_is_the_same_in_every_tab_and_confirms_once(reissue, shown, dummy_user):
    plan, first_tab = shown
    status, body = reissue(plan.id)  # another page, or another tab
    assert status == 200 and body['id'] == str(plan.id) and body['token'] == first_tab
    assert reissue(plan.id)[1]['token'] == first_tab
    assert body['steps'] == [{'n': 1, 'description': 'Create “Sync”', 'side_effects': []}]
    assert executor.confirm(plan.id, dummy_user, 'guessed') == 'invalid_token'
    assert executor.confirm(plan.id, dummy_user, first_tab) == 'confirmed'
    assert executor.confirm(plan.id, dummy_user, body['token']) == 'not_confirmable'


def test_a_plan_saved_with_a_random_token_keeps_it(reissue, shown, dummy_user):
    # (plans waiting when this is deployed: the old buttons keep working until the plan expires; the card drawn
    # again carries the derived token, which works too. Nothing is written: review, PR #5)
    plan, _ = shown
    plan.token_hash = executor._hash('random-from-before')
    assert executor.confirm(plan.id, dummy_user, 'random-from-before') == 'confirmed'


def test_the_derived_token_confirms_a_plan_saved_before(reissue, shown, dummy_user):
    plan, _ = shown
    plan.token_hash = executor._hash('random-from-before')
    token = reissue(plan.id)[1]['token']
    assert plan.token_hash == executor._hash('random-from-before')  # (not rewritten)
    assert executor.confirm(plan.id, dummy_user, token) == 'confirmed'


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
