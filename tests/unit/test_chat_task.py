"""The Celery half of chat: the worker answers and records the outcome for the polling client."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from indico_assistant.services.chat.service import ChatResult, QueryProcessingError
from indico_assistant.tasks.chat import CHAT_QUEUE, answer_chat


@pytest.fixture
def finish():
    with patch('indico_assistant.services.chat.jobs.finish') as finish:
        yield finish


@pytest.fixture
def service():
    with patch('indico_assistant.services.chat.get_chat_service') as get:
        yield get.return_value


def test_runs_on_its_own_queue_with_a_time_limit():
    assert answer_chat.queue == CHAT_QUEUE
    assert answer_chat.soft_time_limit and answer_chat.time_limit > answer_chat.soft_time_limit


def test_done(finish, service):
    session_id, message_id = uuid4(), uuid4()
    service.answer.return_value = ChatResult(response='Hi', session_id=session_id, message_id=message_id,
                                             metadata={'confidence': 0.9})
    answer_chat.run('job1', 7, session_id, 'hello')
    service.answer.assert_called_once_with(7, session_id, 'hello')
    finish.assert_called_once_with('job1', status='done', message_id=str(message_id), response='Hi',
                                   metadata={'confidence': 0.9})


@pytest.mark.parametrize(('error', 'code'), [
    (SoftTimeLimitExceeded(), 'TIMEOUT'),
    (QueryProcessingError('Unable to process your query'), 'QUERY_PROCESSING_ERROR'),
    (RuntimeError('boom'), 'INTERNAL_ERROR'),
])
def test_failures_are_recorded_not_raised(finish, service, error, code):
    service.answer.side_effect = error
    with patch('indico_assistant.tasks.chat.db') as db:
        answer_chat.run('job1', 7, uuid4(), 'hello')
    db.session.rollback.assert_called_once()
    assert finish.call_args.kwargs['status'] == 'failed' and finish.call_args.kwargs['error'] == code
    assert 'boom' not in finish.call_args.kwargs['message']  # internals never reach the user
