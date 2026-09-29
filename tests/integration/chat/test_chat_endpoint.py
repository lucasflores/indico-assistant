"""POST /chat queues the answer in Celery; GET /chat/jobs/<job_id> returns it.

Feature: 004-chat-api (queued since the scalability audit, Phase 1)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from werkzeug.exceptions import TooManyRequests

import indico_assistant.controllers.chat as chat_module
from indico_assistant.controllers.chat import RHChat, RHChatJob
from indico_assistant.services.chat import EventAccessDeniedError, SessionAccessDeniedError, SessionNotFoundError


USER = MagicMock(id=123, is_admin=False)


def _controller(cls):
    controller = cls.__new__(cls)
    controller._user = USER
    return controller


@pytest.fixture
def request_(monkeypatch):
    req = MagicMock()
    monkeypatch.setattr(chat_module, 'request', req)
    return req


@pytest.fixture
def service():
    with patch('indico_assistant.controllers.chat.get_chat_service') as get:
        yield get.return_value


@pytest.fixture
def jobs():
    store = {}
    with patch.object(chat_module.jobs, 'create', side_effect=lambda user_id, session_id: 'job1') as create, \
            patch.object(chat_module.jobs, 'get', side_effect=store.get), \
            patch.object(chat_module.jobs, 'finish') as finish:
        yield store, create, finish


@pytest.fixture
def answer_task():
    with patch('indico_assistant.tasks.chat.answer_chat') as task:
        yield task


class TestPostChat:
    def test_queues_the_answer(self, request_, service, jobs, answer_task):
        session_id = uuid4()
        request_.get_json.return_value = {"message": "What events are tomorrow?", "event_id": 7}
        service.submit_message.return_value = (session_id, True, 'q1')

        response, status = _controller(RHChat)._process()

        assert status == 202
        assert response.get_json() == {"job_id": "job1", "session_id": str(session_id),
                                       "created_session": True, "status": "pending"}
        service.submit_message.assert_called_once_with(user=USER, message="What events are tomorrow?",
                                                       session_id=None, event_id=7, uploads=[], answer_id=None)
        jobs[1].assert_called_once_with(123, session_id)
        answer_task.delay.assert_called_once_with("job1", 123, session_id, "What events are tomorrow?", 'q1')

    def test_broker_down_fails_the_job(self, request_, service, jobs, answer_task):
        request_.get_json.return_value = {"message": "hi"}
        service.submit_message.return_value = (uuid4(), False, uuid4())
        answer_task.delay.side_effect = ConnectionError('broker down')

        response, status = _controller(RHChat)._process()

        assert (status, response.get_json()["error"]) == (503, "QUEUE_UNAVAILABLE")
        assert jobs[2].call_args.kwargs['status'] == 'failed'

    @pytest.mark.parametrize('body', [{}, {"message": ""}])
    def test_validation(self, request_, service, body):
        request_.get_json.return_value = body
        response, status = _controller(RHChat)._process()
        assert status == 422
        service.submit_message.assert_not_called()

    @pytest.mark.parametrize(('error', 'status', 'code'), [
        (SessionNotFoundError('x'), 404, 'SESSION_NOT_FOUND'),
        (SessionAccessDeniedError('x'), 403, 'ACCESS_DENIED'),
        (EventAccessDeniedError(7), 403, 'ACCESS_DENIED'),
    ])
    def test_refusals_queue_nothing(self, request_, service, answer_task, error, status, code):
        request_.get_json.return_value = {"message": "hi", "session_id": str(uuid4())}
        service.submit_message.side_effect = error
        response, got = _controller(RHChat)._process()
        assert (got, response.get_json()["error"]) == (status, code)
        answer_task.delay.assert_not_called()


class TestChatJob:
    def _get(self, request_, job_id='job1'):
        request_.view_args = {'job_id': job_id}
        return _controller(RHChatJob)._process()

    def test_pending(self, request_, jobs):
        jobs[0]['job1'] = {'status': 'pending', 'user_id': 123, 'session_id': 's'}
        response, status = self._get(request_)
        assert status == 202 and response.get_json()['status'] == 'pending'

    def test_done_returns_the_answer(self, request_, jobs):
        session_id, message_id = uuid4(), uuid4()
        jobs[0]['job1'] = {'status': 'done', 'user_id': 123, 'session_id': str(session_id),
                           'message_id': str(message_id), 'response': 'Three events.',
                           'metadata': {'sql_generated': 'SELECT 1', 'pipeline_error': None, 'internal': 'x'}}
        response, status = self._get(request_)
        data = response.get_json()
        assert status == 200
        assert (data['status'], data['response'], data['session_id']) == ('done', 'Three events.', str(session_id))
        assert data['metadata'] == {'sql_generated': 'SELECT 1'}

    def test_done_with_a_plan(self, request_, jobs):
        plan = {'id': str(uuid4()), 'status': 'shown', 'expires_at': '2026-09-28T12:30:00+00:00', 'token': 't0k',
                'summary': 'Create “Sync”', 'steps': [{'n': 1, 'description': 'Create “Sync”', 'side_effects': []}],
                'questions': [], 'suggestions': [], 'can_confirm': True, 'error': None}
        jobs[0]['job1'] = {'status': 'done', 'user_id': 123, 'session_id': str(uuid4()), 'message_id': str(uuid4()),
                           'response': 'Here is the plan.', 'metadata': {}, 'plan': plan}
        response, status = self._get(request_)
        body = response.get_json()
        assert status == 200 and body['plan']['token'] == 't0k' and body['plan']['steps'][0]['n'] == 1

    @pytest.mark.parametrize(('error', 'expected'), [
        ('TIMEOUT', 504), ('ACCESS_DENIED', 403), ('QUEUE_UNAVAILABLE', 503), ('INTERNAL_ERROR', 500),
    ])
    def test_failed(self, request_, jobs, error, expected):
        jobs[0]['job1'] = {'status': 'failed', 'user_id': 123, 'session_id': 's', 'error': error,
                           'message': 'Too long'}
        response, status = self._get(request_)
        assert status == expected and response.get_json()['error'] == error

    def test_polling_counts_against_the_read_limit(self):
        with patch('indico_assistant.controllers.base.RHAssistantBase._check_access'), patch('indico_assistant.controllers.base.get_rate_limiter') as limiter:
            limiter.return_value.check_rate.return_value = MagicMock(allowed=False, retry_after=5)
            with pytest.raises(TooManyRequests):
                _controller(RHChatJob)._check_access()
        limiter.return_value.check_rate.assert_called_once_with(123, 'read')

    @pytest.mark.parametrize('job', [None, {'status': 'done', 'user_id': 999, 'session_id': 's'}])
    def test_unknown_or_someone_elses_job(self, request_, jobs, job):
        if job:
            jobs[0]['job1'] = job
        response, status = self._get(request_)
        assert status == 404
