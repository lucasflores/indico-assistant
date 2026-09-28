"""Retention deletes old rows in batches; messages go with their session."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from indico_assistant.models.message import ChatMessage
from indico_assistant.models.session import ChatSession
from unittest.mock import patch

from indico_assistant.default_settings import DEFAULT_SETTINGS
from indico_assistant.tasks.cleanup import RETENTION, apply_retention, purge


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


def _sessions(db, *ages_days):
    now = datetime.now(timezone.utc)
    sessions = [ChatSession(user_id=1, updated_at=now - timedelta(days=age)) for age in ages_days]
    db.session.add_all(sessions)
    db.session.flush()
    return sessions


def test_retention_follows_the_admin_settings(db):
    old_id, recent_id = (s.id for s in _sessions(db, 40, 5))
    # only chats: the test database has no audit-log table (that model is not registered with Indico's)
    settings = {**DEFAULT_SETTINGS, **{setting: 0 for _, _, setting in RETENTION}, 'retention_chat_days': 30}
    with patch('indico_assistant.tasks.cleanup.purge', wraps=purge) as spy:
        apply_retention.run(settings)
    db.session.expire_all()
    assert ChatSession.query.get(old_id) is None and ChatSession.query.get(recent_id) is not None
    assert ('plugin_assistant.chat_sessions', 'updated_at', 30) in [c.args for c in spy.call_args_list]


def test_zero_keeps_forever(db):
    (ancient,) = _sessions(db, 3650)
    settings = {**DEFAULT_SETTINGS, **{setting: 0 for _, _, setting in RETENTION}}
    with patch('indico_assistant.tasks.cleanup.purge') as spy:
        assert apply_retention.run(settings) == {}
    spy.assert_not_called()
    assert ChatSession.query.get(ancient.id) is not None


def test_every_growing_table_has_a_retention_rule():
    tables = {table for table, _, _ in RETENTION}
    assert {'plugin_assistant.chat_sessions', 'plugin_assistant.query_audit_log',
            'plugin_assistant.observability_error_records', 'plugin_assistant.action_plans'} <= tables
    assert all(setting in DEFAULT_SETTINGS for _, _, setting in RETENTION)
