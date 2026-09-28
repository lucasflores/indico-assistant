"""GET /plans/<id>, POST /plans/<id>/confirm and /cancel (contracts/api.md)."""

from unittest.mock import MagicMock, patch

import pytest

import indico_assistant.controllers.actions as actions_module
from indico_assistant.controllers.actions import RHPlan, RHPlanCancel, RHPlanConfirm
from indico_assistant.models import ActionPlan, ChatSession
from indico_assistant.services.actions import executor


@pytest.fixture
def plan_and_token(db, dummy_user):
    chat = ChatSession(user_id=dummy_user.id)
    db.session.add(chat)
    db.session.flush()
    return executor.create_plan(dummy_user, chat.id, summary='Create a meeting',
                                steps=[{'n': 1, 'action': 'create_event', 'args': {'secret': 'x'},
                                        'description': 'Create “Sync”', 'side_effects': ['Emails the managers']}])


@pytest.fixture
def call(monkeypatch, dummy_user):
    request = MagicMock()
    monkeypatch.setattr(actions_module, 'request', request)
    plugin = MagicMock()
    plugin.settings.get_all.return_value = {'actions_enabled': True, 'actions_allowed': ['create_event']}

    def _call(cls, plan_id, body=None, user=dummy_user, settings=None):
        if settings is not None:
            plugin.settings.get_all.return_value = settings
        request.view_args = {'plan_id': str(plan_id)}
        request.get_json.return_value = body
        rh = cls.__new__(cls)
        rh._user = user
        with patch.object(cls, 'plugin', plugin):
            response, status = rh._process()
        return status, response.get_json()
    return _call


@pytest.fixture
def queued():
    with patch('indico_assistant.tasks.actions.execute_plan') as task:
        yield task.delay


def test_get_hides_arguments_and_token(call, plan_and_token):
    plan, _ = plan_and_token
    status, body = call(RHPlan, plan.id)
    assert status == 200
    assert body['steps'] == [{'n': 1, 'description': 'Create “Sync”', 'side_effects': ['Emails the managers']}]
    assert 'token' not in body and 'secret' not in str(body)


def test_confirm_queues_once(call, plan_and_token, queued):
    plan, token = plan_and_token
    status, body = call(RHPlanConfirm, plan.id, {'token': token})
    assert status == 202 and body['status'] == 'confirmed'
    queued.assert_called_once_with(body['job_id'], plan.id)
    status, body = call(RHPlanConfirm, plan.id, {'token': token})  # double click
    assert (status, body['error'], body['details']['status']) == (409, 'PLAN_NOT_CONFIRMABLE', 'confirmed')
    queued.assert_called_once()


@pytest.mark.parametrize(('case', 'expected'), [
    ('wrong_token', (403, 'INVALID_TOKEN')),
    ('no_token', (422, 'VALIDATION_ERROR')),
    ('other_user', (404, 'NOT_FOUND')),
    ('bad_id', (404, 'NOT_FOUND')),
    ('disabled', (403, 'ACTIONS_DISABLED')),
])
def test_confirm_refusals(call, plan_and_token, queued, create_user, case, expected):
    plan, token = plan_and_token
    kwargs = {'body': {'token': token}}
    plan_id = plan.id
    if case == 'wrong_token':
        kwargs['body'] = {'token': 'guess'}
    elif case == 'no_token':
        kwargs['body'] = {}
    elif case == 'other_user':
        kwargs['user'] = create_user(2)
    elif case == 'bad_id':
        plan_id = 'not-a-uuid'
    elif case == 'disabled':
        kwargs['settings'] = {'actions_enabled': False}
    status, body = call(RHPlanConfirm, plan_id, **kwargs)
    assert (status, body['error']) == expected
    queued.assert_not_called()
    assert ActionPlan.query.get(plan.id).status == 'shown'


def test_queue_outage_leaves_the_plan_confirmable(call, plan_and_token, queued):
    plan, token = plan_and_token
    queued.side_effect = ConnectionError('broker down')
    status, body = call(RHPlanConfirm, plan.id, {'token': token})
    assert (status, body['error']) == (503, 'QUEUE_UNAVAILABLE')
    assert ActionPlan.query.get(plan.id).status == 'shown'


def test_cancel(call, plan_and_token, queued):
    plan, token = plan_and_token
    assert call(RHPlanCancel, plan.id)[0] == 200
    status, body = call(RHPlanConfirm, plan.id, {'token': token})
    assert (status, body['details']['status']) == (409, 'cancelled')
    assert call(RHPlanCancel, plan.id)[0] == 409


def test_endpoints_count_against_the_read_limit(dummy_user):
    from werkzeug.exceptions import TooManyRequests

    from indico_assistant.controllers.base import RHChatBase
    rh = RHPlanConfirm.__new__(RHPlanConfirm)
    rh._user = dummy_user
    with patch.object(RHChatBase, '_check_access'), patch.object(actions_module, 'get_rate_limiter') as limiter:
        limiter.return_value.check_rate.return_value = MagicMock(allowed=False, retry_after=3)
        with pytest.raises(TooManyRequests):
            rh._check_access()
    limiter.return_value.check_rate.assert_called_once_with(dummy_user.id, 'read')
