"""An answer's context stops at its own question (real DB)."""

from datetime import datetime, timedelta, timezone

from indico_assistant.models.message import ChatMessage
from indico_assistant.models.session import ChatSession
from indico_assistant.services.chat.context_builder import ContextBuilder


def test_context_stops_at_the_bound_message(db, dummy_user):
    session = ChatSession(user_id=dummy_user.id)
    db.session.add(session)
    db.session.flush()
    start = datetime.now(timezone.utc)
    first, second = (ChatMessage(session_id=session.id, role='user', content=text, created_at=start + timedelta(seconds=i))
                     for i, text in enumerate(('first question', 'second question')))
    db.session.add_all([first, second])
    db.session.flush()

    builder = ContextBuilder()
    assert [m['content'] for m in builder.build_context(session.id, up_to=first.id)] == ['first question']
    assert [m['content'] for m in builder.build_context(session.id)] == ['first question', 'second question']
