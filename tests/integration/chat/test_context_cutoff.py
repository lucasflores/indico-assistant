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


def test_the_connector_sees_only_the_users_messages_and_githubs_answers(db, dummy_user):
    """Spec 023 (Copilot, PR #17): no Indico data in the connector's loop, not even from earlier answers."""
    session = ChatSession(user_id=dummy_user.id)
    db.session.add(session)
    db.session.flush()
    start = datetime.now(timezone.utc)
    turns = [('user', 'when is the sync?', None), ('assistant', 'Thursday at 10, in room 4.', 'data'),
             ('user', 'my open PRs?', None), ('assistant', '#16 and #17.', 'connector'), ('user', 'the oldest?', None)]
    db.session.add_all([ChatMessage(session_id=session.id, role=role, content=text, created_at=start + timedelta(seconds=i),
                                    metadata_json={'route': {'route': route}} if route else None)
                        for i, (role, text, route) in enumerate(turns)])
    db.session.flush()
    from indico_assistant.services.chat.context_builder import HIDDEN

    history = ContextBuilder().connector_history(session.id)
    assert [m['content'] for m in history] == ['when is the sync?', HIDDEN, 'my open PRs?', '#16 and #17.', 'the oldest?']
    assert [m['role'] for m in history] == ['user', 'assistant', 'user', 'assistant', 'user']  # (fresh-review: alternating)
