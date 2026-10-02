"""The analytics tables (spec 024, T003): a turn, its steps and their text."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from indico_assistant.models import Turn, TurnStep, TurnText


def turn(**fields):
    return Turn(**{'job_id': uuid4().hex, 'session_id': uuid4(), 'message_id': uuid4(),
                   'started_at': datetime.now(UTC), **fields})


def test_deleting_a_turn_deletes_its_steps_and_text(db):
    row = turn()
    db.session.add(row)
    db.session.flush()
    db.session.add_all([TurnStep(turn_id=row.id, seq=1, kind='llm', stage='QueryClassification'),
                        TurnText(turn_id=row.id, seq=1, kind='prompt', text='what is on today?')])
    db.session.flush()
    db.session.execute(Turn.__table__.delete().where(Turn.id == row.id))  # as the retention purge does: in SQL
    assert TurnStep.query.filter_by(turn_id=row.id).count() == 0
    assert TurnText.query.filter_by(turn_id=row.id).count() == 0


def test_a_new_turn_is_running_public_and_unrated(db):
    row = turn()
    db.session.add(row)
    db.session.flush()
    assert row.finished_at is None and row.outcome is None and row.private is False and row.rating is None


def test_a_step_number_is_used_once_per_turn(db):
    row = turn()
    db.session.add(row)
    db.session.flush()
    db.session.add(TurnStep(turn_id=row.id, seq=1, kind='llm'))
    db.session.flush()
    with pytest.raises(IntegrityError), db.session.begin_nested():
        db.session.add(TurnStep(turn_id=row.id, seq=1, kind='sql'))
        db.session.flush()


def test_one_turn_per_job(db):
    first = turn()
    db.session.add(first)
    db.session.flush()
    with pytest.raises(IntegrityError), db.session.begin_nested():
        db.session.add(turn(job_id=first.job_id))
        db.session.flush()
