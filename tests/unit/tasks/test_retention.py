"""Retention deletes old rows in batches; messages go with their session."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from indico_assistant.models.message import ChatMessage
from indico_assistant.models.session import ChatSession
from indico_assistant.tasks.cleanup import RETENTION, purge


def test_old_sessions_and_their_messages_are_purged_in_batches(db):
    now = datetime.now(timezone.utc)
    old = [ChatSession(user_id=1, updated_at=now - timedelta(days=91)) for _ in range(3)]
    recent = ChatSession(user_id=1, updated_at=now - timedelta(days=5))
    db.session.add_all([*old, recent])
    db.session.flush()
    db.session.add_all([ChatMessage(session_id=s.id, role='user', content='hi') for s in [*old, recent]])
    db.session.flush()
    old_ids = [s.id for s in old]

    assert purge('plugin_assistant.chat_sessions', 'updated_at', 90, batch_size=2) == 3
    db.session.expire_all()
    assert ChatSession.query.filter(ChatSession.id.in_(old_ids)).count() == 0
    assert ChatMessage.query.filter(ChatMessage.session_id.in_(old_ids)).count() == 0
    assert ChatSession.query.get(recent.id) is not None


def test_every_growing_table_has_a_retention_rule():
    tables = {table for table, _, _ in RETENTION}
    assert {'plugin_assistant.chat_sessions', 'plugin_assistant.query_audit_log',
            'plugin_assistant.observability_error_records'} <= tables
