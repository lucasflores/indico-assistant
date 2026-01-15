"""Unit tests for audit logging (T053a, T054/US5).

Tests QueryAuditLog model and AuditLogger helper functions.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from indico_assistant.models.audit import QueryAuditLog
from indico_assistant.services.nl2sql.audit import (
    AuditLogger,
    log_cache_hit,
    log_classification,
    log_correction_attempt,
    log_correction_success,
    log_error,
    log_execution,
    log_generation,
    log_validation_rejection,
)

if TYPE_CHECKING:
    pass


class TestQueryAuditLogModel:
    """Test QueryAuditLog SQLAlchemy model."""

    def test_create_entry_sets_question(self) -> None:
        """create_entry should set the question."""
        log = QueryAuditLog.create_entry(question="What events are there?")
        
        assert log.question == "What events are there?"

    def test_create_entry_sets_user_id(self) -> None:
        """create_entry should set user_id when provided."""
        log = QueryAuditLog.create_entry(question="test", user_id=123)
        
        assert log.user_id == 123

    def test_create_entry_sets_user_email(self) -> None:
        """create_entry should set user_email when provided."""
        log = QueryAuditLog.create_entry(
            question="test", user_email="user@example.com"
        )
        
        assert log.user_email == "user@example.com"

    def test_create_entry_sets_session_id(self) -> None:
        """create_entry should set session_id when provided."""
        log = QueryAuditLog.create_entry(question="test", session_id="sess-123")
        
        assert log.session_id == "sess-123"

    def test_create_entry_sets_ip_address(self) -> None:
        """create_entry should set ip_address when provided."""
        log = QueryAuditLog.create_entry(question="test", ip_address="192.168.1.1")
        
        assert log.ip_address == "192.168.1.1"

    def test_create_entry_defaults_success_false(self) -> None:
        """create_entry should default success to False."""
        log = QueryAuditLog.create_entry(question="test")
        
        assert log.success is False

    def test_update_classification_sets_intent(self) -> None:
        """update_classification should set intent."""
        log = QueryAuditLog.create_entry(question="test")
        
        log.update_classification(intent="event_list", confidence=0.95)
        
        assert log.intent == "event_list"

    def test_update_classification_sets_confidence(self) -> None:
        """update_classification should set confidence."""
        log = QueryAuditLog.create_entry(question="test")
        
        log.update_classification(intent="event_list", confidence=0.95)
        
        assert log.intent_confidence == 0.95

    def test_update_generation_sets_sql(self) -> None:
        """update_generation should set generated_sql."""
        log = QueryAuditLog.create_entry(question="test")
        
        log.update_generation(sql="SELECT * FROM events")
        
        assert log.generated_sql == "SELECT * FROM events"

    def test_update_execution_sets_metrics(self) -> None:
        """update_execution should set execution metrics."""
        log = QueryAuditLog.create_entry(question="test")
        
        log.update_execution(execution_time_ms=150.5, row_count=25, success=True)
        
        assert log.execution_time_ms == 150.5
        assert log.row_count == 25
        assert log.success is True

    def test_mark_validation_rejected_sets_reason(self) -> None:
        """mark_validation_rejected should set reason and success=False."""
        log = QueryAuditLog.create_entry(question="test")
        
        log.mark_validation_rejected(reason="DDL_NOT_ALLOWED")
        
        assert log.validation_rejection_reason == "DDL_NOT_ALLOWED"
        assert log.success is False

    def test_mark_error_sets_message(self) -> None:
        """mark_error should set error_message and success=False."""
        log = QueryAuditLog.create_entry(question="test")
        
        log.mark_error(error_message="Connection timeout")
        
        assert log.error_message == "Connection timeout"
        assert log.success is False

    def test_mark_correction_attempt_increments(self) -> None:
        """mark_correction_attempt should increment counter."""
        log = QueryAuditLog.create_entry(question="test")
        
        assert log.correction_attempts == 0
        log.mark_correction_attempt()
        assert log.correction_attempts == 1
        log.mark_correction_attempt()
        assert log.correction_attempts == 2

    def test_mark_corrected_sets_flag(self) -> None:
        """mark_corrected should set was_corrected=True."""
        log = QueryAuditLog.create_entry(question="test")
        
        assert log.was_corrected is False
        log.mark_corrected()
        assert log.was_corrected is True

    def test_mark_cached_sets_flag(self) -> None:
        """mark_cached should set cached=True."""
        log = QueryAuditLog.create_entry(question="test")
        
        assert log.cached is False
        log.mark_cached()
        assert log.cached is True


class TestQueryAuditLogFR031:
    """Test FR-031: Query results NOT stored in audit logs (T053a)."""

    def test_model_has_no_results_column(self) -> None:
        """QueryAuditLog should NOT have a 'results' or 'data' column."""
        log = QueryAuditLog.create_entry(question="test")
        
        # Verify no results/data attributes exist
        assert not hasattr(log, "results")
        assert not hasattr(log, "result_data")
        assert not hasattr(log, "query_results")

    def test_model_only_stores_row_count(self) -> None:
        """Model should only store row_count, not actual results."""
        log = QueryAuditLog.create_entry(question="test")
        log.update_execution(execution_time_ms=100, row_count=50, success=True)
        
        # row_count is stored
        assert log.row_count == 50
        
        # But no actual result data
        columns = [c.name for c in QueryAuditLog.__table__.columns]
        assert "results" not in columns
        assert "result_data" not in columns
        assert "query_results" not in columns

    def test_generated_sql_stored_for_debugging(self) -> None:
        """Generated SQL should be stored for debugging/compliance."""
        log = QueryAuditLog.create_entry(question="test")
        log.update_generation(sql="SELECT id, title FROM events")
        
        # SQL is stored (needed for debugging)
        assert log.generated_sql == "SELECT id, title FROM events"


class TestAuditLoggerHelper:
    """Test AuditLogger helper class."""

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock database session."""
        return MagicMock()

    def test_init_with_enabled_true(self, mock_session: MagicMock) -> None:
        """AuditLogger should be enabled by default."""
        logger = AuditLogger(mock_session)
        
        assert logger.enabled is True

    def test_init_with_enabled_false(self, mock_session: MagicMock) -> None:
        """AuditLogger can be disabled."""
        logger = AuditLogger(mock_session, enabled=False)
        
        assert logger.enabled is False

    def test_create_log_entry_returns_entry_when_enabled(
        self, mock_session: MagicMock
    ) -> None:
        """create_log_entry returns QueryAuditLog when enabled."""
        logger = AuditLogger(mock_session, enabled=True)
        
        entry = logger.create_log_entry(question="test")
        
        assert entry is not None
        assert isinstance(entry, QueryAuditLog)
        mock_session.add.assert_called_once()

    def test_create_log_entry_returns_none_when_disabled(
        self, mock_session: MagicMock
    ) -> None:
        """create_log_entry returns None when disabled."""
        logger = AuditLogger(mock_session, enabled=False)
        
        entry = logger.create_log_entry(question="test")
        
        assert entry is None
        mock_session.add.assert_not_called()

    def test_commit_calls_session_commit(self, mock_session: MagicMock) -> None:
        """commit should call session.commit()."""
        logger = AuditLogger(mock_session)
        
        logger.commit()
        
        mock_session.commit.assert_called_once()


class TestAuditLoggerContextManager:
    """Test AuditLogger context manager."""

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock database session."""
        return MagicMock()

    def test_log_query_yields_entry_when_enabled(
        self, mock_session: MagicMock
    ) -> None:
        """log_query should yield entry when enabled."""
        logger = AuditLogger(mock_session, enabled=True)
        
        with logger.log_query("test question") as entry:
            assert entry is not None
            assert entry.question == "test question"

    def test_log_query_yields_none_when_disabled(
        self, mock_session: MagicMock
    ) -> None:
        """log_query should yield None when disabled."""
        logger = AuditLogger(mock_session, enabled=False)
        
        with logger.log_query("test question") as entry:
            assert entry is None

    def test_log_query_commits_on_success(
        self, mock_session: MagicMock
    ) -> None:
        """log_query should commit session on normal exit."""
        logger = AuditLogger(mock_session, enabled=True)
        
        with logger.log_query("test"):
            pass
        
        mock_session.commit.assert_called()

    def test_log_query_commits_on_exception(
        self, mock_session: MagicMock
    ) -> None:
        """log_query should still commit on exception."""
        logger = AuditLogger(mock_session, enabled=True)
        
        try:
            with logger.log_query("test"):
                raise ValueError("test error")
        except ValueError:
            pass
        
        mock_session.commit.assert_called()


class TestAuditHelperFunctions:
    """Test standalone audit helper functions."""

    @pytest.fixture
    def log_entry(self) -> QueryAuditLog:
        """Create test log entry."""
        return QueryAuditLog.create_entry(question="test")

    def test_log_classification_updates_entry(
        self, log_entry: QueryAuditLog
    ) -> None:
        """log_classification should update intent and confidence."""
        log_classification(log_entry, "event_list", 0.9)
        
        assert log_entry.intent == "event_list"
        assert log_entry.intent_confidence == 0.9

    def test_log_classification_safe_with_none(self) -> None:
        """log_classification should be safe with None entry."""
        # Should not raise
        log_classification(None, "event_list", 0.9)

    def test_log_generation_updates_entry(
        self, log_entry: QueryAuditLog
    ) -> None:
        """log_generation should update generated_sql."""
        log_generation(log_entry, "SELECT * FROM events")
        
        assert log_entry.generated_sql == "SELECT * FROM events"

    def test_log_generation_safe_with_none(self) -> None:
        """log_generation should be safe with None entry."""
        log_generation(None, "SELECT * FROM events")

    def test_log_execution_updates_entry(
        self, log_entry: QueryAuditLog
    ) -> None:
        """log_execution should update execution metrics."""
        log_execution(log_entry, 200.0, 50, success=True)
        
        assert log_entry.execution_time_ms == 200.0
        assert log_entry.row_count == 50
        assert log_entry.success is True

    def test_log_execution_safe_with_none(self) -> None:
        """log_execution should be safe with None entry."""
        log_execution(None, 200.0, 50, success=True)

    def test_log_validation_rejection_updates_entry(
        self, log_entry: QueryAuditLog
    ) -> None:
        """log_validation_rejection should update reason."""
        log_validation_rejection(log_entry, "DDL_NOT_ALLOWED")
        
        assert log_entry.validation_rejection_reason == "DDL_NOT_ALLOWED"
        assert log_entry.success is False

    def test_log_validation_rejection_safe_with_none(self) -> None:
        """log_validation_rejection should be safe with None entry."""
        log_validation_rejection(None, "DDL_NOT_ALLOWED")

    def test_log_error_updates_entry(self, log_entry: QueryAuditLog) -> None:
        """log_error should update error_message."""
        log_error(log_entry, "Connection failed")
        
        assert log_entry.error_message == "Connection failed"
        assert log_entry.success is False

    def test_log_error_safe_with_none(self) -> None:
        """log_error should be safe with None entry."""
        log_error(None, "Connection failed")

    def test_log_correction_attempt_increments(
        self, log_entry: QueryAuditLog
    ) -> None:
        """log_correction_attempt should increment counter."""
        log_correction_attempt(log_entry)
        log_correction_attempt(log_entry)
        
        assert log_entry.correction_attempts == 2

    def test_log_correction_attempt_safe_with_none(self) -> None:
        """log_correction_attempt should be safe with None entry."""
        log_correction_attempt(None)

    def test_log_correction_success_sets_flag(
        self, log_entry: QueryAuditLog
    ) -> None:
        """log_correction_success should set was_corrected."""
        log_correction_success(log_entry)
        
        assert log_entry.was_corrected is True

    def test_log_correction_success_safe_with_none(self) -> None:
        """log_correction_success should be safe with None entry."""
        log_correction_success(None)

    def test_log_cache_hit_sets_flag(self, log_entry: QueryAuditLog) -> None:
        """log_cache_hit should set cached flag."""
        log_cache_hit(log_entry)
        
        assert log_entry.cached is True

    def test_log_cache_hit_safe_with_none(self) -> None:
        """log_cache_hit should be safe with None entry."""
        log_cache_hit(None)


class TestQueryAuditLogTableSchema:
    """Test QueryAuditLog table schema."""

    def test_tablename_is_query_audit_log(self) -> None:
        """Table name should be query_audit_log."""
        assert QueryAuditLog.__tablename__ == "query_audit_log"

    def test_schema_is_plugin_assistant(self) -> None:
        """Schema should be plugin_assistant."""
        assert QueryAuditLog.__table_args__["schema"] == "plugin_assistant"

    def test_has_required_columns(self) -> None:
        """Model should have all required columns."""
        columns = {c.name for c in QueryAuditLog.__table__.columns}
        
        required = {
            "id",
            "created_at",
            "user_id",
            "user_email",
            "session_id",
            "question",
            "intent",
            "intent_confidence",
            "generated_sql",
            "execution_time_ms",
            "row_count",
            "success",
            "error_message",
            "validation_rejection_reason",
            "correction_attempts",
            "was_corrected",
            "cached",
            "ip_address",
        }
        
        assert required.issubset(columns)

    def test_question_is_not_nullable(self) -> None:
        """Question column should not be nullable."""
        question_col = QueryAuditLog.__table__.c.question
        assert question_col.nullable is False

    def test_success_is_not_nullable(self) -> None:
        """Success column should not be nullable."""
        success_col = QueryAuditLog.__table__.c.success
        assert success_col.nullable is False
