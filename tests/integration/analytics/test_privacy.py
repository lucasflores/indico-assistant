"""What happens to turns when chats and users go (spec 024, T010, FR-011, FR-012): the numbers stay, the text goes."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from indico.core.db import db

from indico_assistant.models import ChatSession, Turn, TurnStep, TurnText
from indico_assistant.services.analytics import recorder
from indico_assistant.services.chat.session_manager import SessionManager


def turn_in(session, user):
    row = Turn(job_id=uuid4().hex, session_id=session.id, message_id=uuid4(), user_id=user.id,
               started_at=datetime.now(UTC))
    db.session.add(row)
    db.session.flush()
    db.session.add_all([TurnStep(turn_id=row.id, seq=1, kind='llm'),
                        TurnText(turn_id=row.id, seq=1, kind='prompt', text='my question')])
    db.session.flush()
    return row


@pytest.fixture
def chat(create_user):
    user = create_user(50)
    session = ChatSession(user_id=user.id)
    db.session.add(session)
    db.session.flush()
    return user, session, turn_in(session, user)


def texts(row):
    return TurnText.query.filter_by(turn_id=row.id).count()


def test_deleting_a_chat_takes_its_text_and_keeps_its_turns(chat):
    user, session, row = chat
    assert SessionManager().delete_session(session.id) is True
    db.session.flush()
    assert texts(row) == 0 and Turn.query.get(row.id) is not None
    assert TurnStep.query.filter_by(turn_id=row.id).count() == 1


@pytest.mark.parametrize('signal', ['db_deleted', 'anonymized'])
def test_a_deleted_or_anonymised_user_loses_their_turns_user_and_text(chat, signal):
    from indico_assistant.plugin import _forget_turns

    user, session, row = chat
    _forget_turns(user, flushed=False)  # (before the flush: nothing yet)
    assert texts(row) == 1
    _forget_turns(user, flushed=True)
    db.session.expire_all()
    assert texts(row) == 0 and Turn.query.get(row.id).user_id is None


def test_merged_users_turns_follow_the_account_that_remains(chat, create_user):
    from indico_assistant.plugin import _merge_turns

    user, session, row = chat
    target = create_user(51)
    _merge_turns(target, user)
    db.session.expire_all()
    assert Turn.query.get(row.id).user_id == target.id


def test_the_nightly_task_takes_the_text_of_turns_whose_chat_is_gone(chat):
    user, session, row = chat
    other = turn_in(session, user)
    gone = Turn(job_id=uuid4().hex, session_id=uuid4(), message_id=uuid4(), started_at=datetime.now(UTC))
    db.session.add(gone)
    db.session.flush()
    db.session.add(TurnText(turn_id=gone.id, seq=1, kind='prompt', text='x'))
    db.session.flush()
    assert recorder.forget_orphan_texts() == 1
    assert texts(gone) == 0 and texts(row) == 1 and texts(other) == 1
