"""The Celery half of chat actions: run the confirmed plan, tell the chat what happened."""

from unittest.mock import patch

import pytest

from indico_assistant.models import ChatMessage, ChatSession
from indico_assistant.services.actions import executor
from indico_assistant.tasks.actions import execute_plan


@pytest.fixture(autouse=True)
def all_enabled(monkeypatch):
    from indico_assistant.tasks import actions
    monkeypatch.setattr(actions, '_enabled_actions', lambda: frozenset({'create_event'}))


@pytest.fixture
def confirmed(db, dummy_user):
    chat = ChatSession(user_id=dummy_user.id)
    db.session.add(chat)
    db.session.flush()
    plan, token = executor.create_plan(dummy_user, chat.id, summary='x',
                                       steps=[{'n': 1, 'action': 'create_event', 'args': {}, 'description': 'Create “Sync”'}])
    executor.confirm(plan.id, dummy_user, token)
    return plan


def test_runs_as_a_request_context_task_on_the_chat_queue():
    assert execute_plan.queue == 'assistant' and execute_plan.request_context and execute_plan.plugin == 'assistant'


@pytest.mark.parametrize(('status', 'error', 'reply'), [
    ('done', None, 'Done:\n- Create “Sync”'),
    ('refused', 'You cannot create events here', 'I did not change anything: You cannot create events here'),
    ('failed', executor.FAILED_MESSAGE, executor.FAILED_MESSAGE),
])
def test_outcome_goes_to_the_chat_and_the_job(confirmed, status, error, reply):
    def fake_run(plan_id, enabled=None):
        assert enabled == {'create_event'}  # the admin's switches as they are now
        confirmed.status, confirmed.error = status, error
        return confirmed

    with patch.object(executor, 'run', fake_run), patch('indico_assistant.services.chat.jobs.finish') as finish, \
            patch('indico_assistant.services.chat.jobs.start'):
        execute_plan.run('job1', confirmed.id)
    kwargs = finish.call_args.kwargs
    assert kwargs['status'] == 'done' and kwargs['response'] == reply and kwargs['plan']['status'] == status
    message = ChatMessage.query.get(kwargs['message_id'])
    assert message.content == reply and message.metadata_json == {'plan_id': str(confirmed.id), 'plan_status': status}


def test_an_unconfirmed_plan_fails_the_job(confirmed):
    with patch.object(executor, 'run', side_effect=executor.NotConfirmed(confirmed.id)), \
            patch('indico_assistant.services.chat.jobs.finish') as finish, patch('indico_assistant.services.chat.jobs.start'):
        execute_plan.run('job1', confirmed.id)
    assert finish.call_args.kwargs['error'] == 'PLAN_NOT_CONFIRMABLE'


def test_the_reply_links_to_the_created_event(confirmed, dummy_event):
    from indico_assistant.tasks.actions import outcome_message
    confirmed.status, confirmed.result = 'done', [{'n': 1, 'action': 'create_event', 'created': {'event_id': dummy_event.id}}]
    assert f'[Open “{dummy_event.title}” in Indico]({dummy_event.external_url})' in outcome_message(confirmed)


def test_a_skipped_step_is_not_reported_as_done(confirmed):
    # (Copilot review, PR #3) a reminder that was too late to send is said so
    from indico_assistant.tasks.actions import outcome_message
    confirmed.status, confirmed.result = 'done', [
        {'n': 1, 'action': 'add_reminder', 'created': None, 'skipped': 'the meeting starts too soon for a reminder'}]
    assert outcome_message(confirmed) == 'Done:\n- Create “Sync” (not done: the meeting starts too soon for a reminder)'
