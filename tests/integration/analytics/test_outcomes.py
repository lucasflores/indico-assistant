"""Every answer leaves exactly one turn with its outcome (spec 024, T008, SC-001): answer_chat with the real recorder
and database, and a chat service that answers, refuses or fails in each way; and the chat service's own rules."""

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from indico.core.db import db

from indico_assistant.models import ChatMessage, ChatSession, Turn
from indico_assistant.services.analytics import recorder
from indico_assistant.services.chat.service import (ChatResult, EventAccessDeniedError, QueryProcessingError,
                                                     _record_turn)
from indico_assistant.tasks.chat import answer_chat


@pytest.fixture
def question(create_user, create_event):
    user, event = create_user(31, admin=True), create_event(title='Budget review')
    session = ChatSession(user_id=user.id)
    db.session.add(session)
    db.session.flush()
    message = ChatMessage(session_id=session.id, role='user', content='q', metadata_json={'event_id': event.id})
    db.session.add(message)
    db.session.flush()
    return SimpleNamespace(user=user, event=event, session=session, message=message)


def run(question, answer):
    """The worker, with ``answer`` as the chat service's answer (a function, or an exception to raise)."""
    job_id = uuid4().hex

    def service_answer(*args):
        if isinstance(answer, BaseException):
            raise answer
        return answer()

    with patch('indico_assistant.services.chat.jobs.start'), patch('indico_assistant.services.chat.jobs.finish'), \
            patch('indico_assistant.services.chat.get_chat_service') as get:
        get.return_value.answer.side_effect = service_answer
        answer_chat.run(job_id, question.user.id, question.session.id, 'q', question.message.id)
    db.session.expire_all()
    return Turn.query.filter_by(job_id=job_id).one()


def done():
    return ChatResult(response='ok', session_id=uuid4(), message_id=uuid4(), metadata={})


@pytest.mark.parametrize(('error', 'outcome', 'code'), [
    (SoftTimeLimitExceeded(), 'timeout', 'TIMEOUT'),
    (EventAccessDeniedError(1), 'access_denied', 'ACCESS_DENIED'),
    (QueryProcessingError('Unable to process your query'), 'failed', 'QUERY_PROCESSING_ERROR'),
    (RuntimeError('boom'), 'failed', 'INTERNAL_ERROR'),
])
def test_each_failure_leaves_one_turn_with_its_outcome(question, error, outcome, code):
    row = run(question, error)
    assert (row.outcome, row.error_code) == (outcome, code) and row.finished_at is not None
    # who and where come from the start row: a turn that failed before routing has them too (FR-002)
    assert row.is_admin is True and row.event_id == question.event.id and row.user_id == question.user.id
    assert Turn.query.filter_by(session_id=question.session.id).count() == 1


def test_an_answer_is_answered_unless_the_service_says_otherwise(question):
    assert run(question, done).outcome == 'answered'

    def refused():
        recorder.set_outcome('refusal')
        return done()

    assert run(question, refused).outcome == 'refusal'


def describe(metadata, route='data', plan=None, answer=None):
    turn = recorder._Turn(1, text_on=True)
    token = recorder._current.set(turn)
    try:
        _record_turn(uuid4(), route, None, None, {'route': {}, **metadata}, plan, answer)
    finally:
        recorder._current.reset(token)
    return turn


@pytest.mark.parametrize(('route', 'metadata', 'outcome', 'code'), [
    ('refusal', {'problem': 'out_of_scope'}, 'refusal', None),
    ('change', {'cannot_plan': True, 'problem': 'cannot_do'}, 'cannot_plan', None),
    ('change', {'problem': 'not_understood'}, 'cannot_plan', None),
    ('data', {'problem': 'failed', 'pipeline_error': {'error_type': 'execution_failed'}}, 'failed', 'execution_failed'),
    ('knowledge', {'problem': 'failed'}, 'failed', 'model_error'),  # a model call failed, answered politely
    ('data', {}, None, None),  # (the task's default: answered)
])
def test_the_service_sets_the_outcome_of_answers_that_are_not_plain_answers(route, metadata, outcome, code):
    turn = describe(metadata, route)
    assert (turn.outcome, turn.error_code) == (outcome, code)


def test_the_service_describes_the_turn():
    turn = describe({'evidence': {'intent': 'time_range', 'correction_attempts': 1, 'row_count': 4}},
                    plan={'id': str(uuid4())}, answer=SimpleNamespace(tools=[{'name': 'x'}], stop='answered'))
    fields = turn.fields
    assert (fields['route'], fields['decided_by'], fields['intent'], fields['corrections'], fields['row_count']) == (
        'data', 'shortcut', 'time_range', 1, 4)
    assert fields['tool_calls'] == 1 and fields['record']['connector_stop'] == 'answered'
    assert describe({}, plan={'id': 'not-a-uuid'}).fields['plan_id'] is None  # (never an error in an answer)
