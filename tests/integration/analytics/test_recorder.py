"""The recorder (spec 024, T007): a turn, its steps and their text, written at the start and the end."""

import logging
from decimal import Decimal
from uuid import uuid4

import pytest

from indico.core.db import db

from indico_assistant.models import ChatMessage, ChatSession, FeedbackEntry, Turn, TurnStep, TurnText
from indico_assistant.services.analytics import recorder


@pytest.fixture
def question(db, create_user, create_event):
    """A user's question on an event page, as the chat's web half saves it."""
    user = create_user(30, admin=True)
    event = create_event(title='Budget review')
    session = ChatSession(user_id=user.id)
    db.session.add(session)
    db.session.flush()
    message = ChatMessage(session_id=session.id, role='user', content='what is on today?',
                          metadata_json={'event_id': event.id})
    db.session.add(message)
    db.session.flush()
    return {'user': user, 'event': event, 'session': session, 'message': message}


def run_turn(question, body=lambda turn: None):
    job_id = uuid4().hex
    with recorder.turn(job_id, question['user'].id, question['session'].id, question['message'].id) as turn:
        body(turn)
    db.session.expire_all()  # (the end write is SQL: the session's objects don't see it)
    return Turn.query.filter_by(job_id=job_id).one()


def test_the_start_row_stamps_who_and_where(question):
    seen = {}

    def body(turn):
        seen.update(Turn.query.get(turn.id).__dict__)  # the row exists while the answer runs

    row = run_turn(question, body)
    assert seen['finished_at'] is None and seen['started_at'] is not None
    assert seen['is_admin'] is True and seen['event_id'] == question['event'].id
    assert seen['category_id'] == question['event'].category_id
    assert seen['queued_at'] == question['message'].created_at
    assert row.finished_at is not None and row.outcome == 'answered' and row.user_id == question['user'].id


def test_steps_nest_time_and_fail(question):
    def body(turn):
        with recorder.step('llm', 'QueryClassification') as classify:
            classify.prompt_tokens, classify.completion_tokens, classify.cost_usd = 100, 10, Decimal('0.001')
        with recorder.step('sql', 'topic_search') as query:
            with pytest.raises(ValueError), recorder.step('llm', 'SQLCorrection') as correction:
                correction.prompt_tokens = 50  # (unpriced)
                raise ValueError('boom')
            query.row_count = 3
        with recorder.step('llm', 'ResponseSummary') as formatter:
            formatter.ok, formatter.error_code = False, 'rate_limit'  # failed without raising

    row = run_turn(question, body)
    steps = TurnStep.query.filter_by(turn_id=row.id).order_by(TurnStep.seq).all()
    assert [(s.seq, s.parent_seq, s.kind, s.stage) for s in steps] == [
        (1, None, 'llm', 'QueryClassification'), (2, None, 'sql', 'topic_search'), (3, 2, 'llm', 'SQLCorrection'),
        (4, None, 'llm', 'ResponseSummary')]
    assert (steps[2].ok, steps[2].error_code) == (False, 'ValueError')
    assert (steps[3].ok, steps[3].error_code) == (False, 'rate_limit')
    assert steps[1].row_count == 3 and all(s.duration_ms is not None and s.offset_ms is not None for s in steps)
    # totals are sums over the steps; model calls are llm and jev steps
    assert (row.llm_calls, row.prompt_tokens, row.completion_tokens) == (3, 150, 10)
    assert (row.cost_usd, row.unpriced_calls) == (Decimal('0.001000'), 2)


def test_text_is_kept_cut_and_dropped_when_private(question):
    def body(turn):
        with recorder.step('llm', 'ChatAnswer') as step:
            recorder.text(step, 'prompt', 'x' * (recorder.TEXT_LIMIT + 5))
            recorder.text(step, 'response', {'answer': 'hello'})

    row = run_turn(question, body)
    texts = {t.kind: t for t in TurnText.query.filter_by(turn_id=row.id)}
    assert len(texts['prompt'].text) == recorder.TEXT_LIMIT and texts['prompt'].cut is True
    assert texts['response'].text == '{"answer": "hello"}' and texts['response'].cut is False

    def private(turn):
        with recorder.step('llm', 'QueryClassification') as step:
            recorder.text(step, 'prompt', 'collected before the route was known')
        recorder.private()
        with recorder.step('tool', 'github', 'list_pull_requests') as step:
            recorder.text(step, 'response', 'secret')

    row = run_turn(question, private)
    assert row.private is True and TurnText.query.filter_by(turn_id=row.id).count() == 0
    assert TurnStep.query.filter_by(turn_id=row.id).count() == 2


def test_no_text_when_the_setting_is_off(question, monkeypatch):
    monkeypatch.setattr(recorder, '_text_on', lambda: False)

    def body(turn):
        with recorder.step('llm', 'ChatAnswer') as step:
            recorder.text(step, 'prompt', 'hello')

    row = run_turn(question, body)
    assert row.private is False and TurnText.query.filter_by(turn_id=row.id).count() == 0


def test_outcome_fields_and_the_rating_read_at_the_end(question, db):
    answer = ChatMessage(session_id=question['session'].id, role='assistant', content='Nothing today.')
    db.session.add(answer)
    db.session.flush()

    def body(turn):
        recorder.update(answer_id=answer.id, route='data', intent='time_range', record={'a': 1})
        recorder.update(record={'b': 2}, not_a_column=1)  # an unknown field is ignored, never raised
        # a vote that lands before the end write (FR-007)
        db.session.add(FeedbackEntry(message_id=answer.id, user_id=question['user'].id, feedback_type='thumbs_down',
                                     value='true'))
        db.session.flush()
        recorder.set_outcome('refusal')

    row = run_turn(question, body)
    assert (row.outcome, row.route, row.intent, row.rating) == ('refusal', 'data', 'time_range', -1)
    assert row.record == {'a': 1, 'b': 2}


def test_a_failing_write_is_logged_and_never_raises(question, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError('the database is down')

    monkeypatch.setattr(recorder, '_write_end', broken)
    with caplog.at_level(logging.ERROR, logger=recorder.logger.name):
        run_turn(question)  # (no exception)
    assert 'could not record' in caplog.text


def test_outside_a_turn_everything_is_a_no_op():
    with recorder.step('llm', 'ChatAnswer') as step:
        recorder.text(step, 'prompt', 'hello')
        step.prompt_tokens = 5
    recorder.update(route='chat')
    recorder.set_outcome('failed')
    recorder.private()
    assert recorder.current_step() is None
