"""A thumbs vote is copied onto the turn (spec 024, T011, FR-007), so satisfaction outlives the chat."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from indico.core.db import db

from indico_assistant.models import ChatMessage, ChatSession, Turn
from indico_assistant.services.feedback.service import FeedbackService


@pytest.fixture
def answered(create_user):
    user = create_user(40)
    session = ChatSession(user_id=user.id)
    db.session.add(session)
    db.session.flush()
    answer = ChatMessage(session_id=session.id, role='assistant', content='Two events today.')
    db.session.add(answer)
    db.session.flush()
    turn = Turn(job_id=uuid4().hex, session_id=session.id, message_id=uuid4(), answer_id=answer.id,
                started_at=datetime.now(UTC))
    db.session.add(turn)
    db.session.flush()
    return user, answer, turn


def rating_of(turn):
    db.session.expire(turn)
    return turn.rating


def test_thumbs_set_switch_and_withdraw_the_rating(answered):
    user, answer, turn = answered
    service = FeedbackService()
    service.submit_feedback(user.id, answer.id, 'thumbs_up')
    assert rating_of(turn) == 1
    entry = service.submit_feedback(user.id, answer.id, 'thumbs_down', thumb_comment='wrong year')
    assert rating_of(turn) == -1
    assert service.withdraw_feedback(user.id, entry.id) is True
    assert rating_of(turn) is None


def test_a_comment_alone_changes_no_rating(answered):
    user, answer, turn = answered
    FeedbackService().submit_feedback(user.id, answer.id, 'comment', comment='nice')
    assert rating_of(turn) is None


def test_withdrawing_by_the_comments_id_still_clears_the_rating(answered):
    user, answer, turn = answered
    service = FeedbackService()
    service.submit_feedback(user.id, answer.id, 'thumbs_down', thumb_comment='wrong year')
    from indico_assistant.models import FeedbackEntry
    comment = FeedbackEntry.query.filter_by(message_id=answer.id, feedback_type='comment').one()
    assert service.withdraw_feedback(user.id, comment.id) is True
    assert rating_of(turn) is None
