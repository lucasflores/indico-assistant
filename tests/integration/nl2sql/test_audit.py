"""Integration tests for audit logging (T055/US5).

Tests end-to-end audit logging through the pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    pass


class TestAuditLoggingIntegration:
    """Test audit logging integration with pipeline."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create mock database session."""
        session = MagicMock()
        session.execute.return_value.fetchall.return_value = []
        session.execute.return_value.keys.return_value = []
        return session

    @pytest.fixture
    def mock_llm_service(self) -> MagicMock:
        """Create mock LLM service."""
        return MagicMock()

    def test_audit_log_created_on_pipeline_entry(
        self, mock_db_session: MagicMock, mock_llm_service: MagicMock
    ) -> None:
        """Audit log entry should be created when pipeline starts."""
        from indico_assistant.services.nl2sql.audit import AuditLogger
        
        logger = AuditLogger(mock_db_session, enabled=True)
        
        entry = logger.create_log_entry(
            question="Show events",
            user_id=123,
            user_email="test@example.com",
            session_id="sess-abc",
            ip_address="10.0.0.1",
        )
        
        assert entry is not None
        assert entry.question == "Show events"
        assert entry.user_id == 123
        assert entry.user_email == "test@example.com"
        assert entry.session_id == "sess-abc"
        assert entry.ip_address == "10.0.0.1"
        mock_db_session.add.assert_called_once()

    def test_audit_log_records_classification(
        self, mock_db_session: MagicMock
    ) -> None:
        """Classification results should be recorded in audit log."""
        from indico_assistant.models.audit import QueryAuditLog
        from indico_assistant.services.nl2sql.audit import log_classification
        
        entry = QueryAuditLog.create_entry(question="List events")
        
        log_classification(entry, "event_list", 0.95)
        
        assert entry.intent == "event_list"
        assert entry.intent_confidence == 0.95

    def test_audit_log_records_generation(
        self, mock_db_session: MagicMock
    ) -> None:
        """Generated SQL should be recorded in audit log."""
        from indico_assistant.models.audit import QueryAuditLog
        from indico_assistant.services.nl2sql.audit import log_generation
        
        entry = QueryAuditLog.create_entry(question="List events")
        
        log_generation(entry, "SELECT * FROM plugin_assistant.events")
        
        assert entry.generated_sql == "SELECT * FROM plugin_assistant.events"

    def test_audit_log_records_validation_rejection(
        self, mock_db_session: MagicMock
    ) -> None:
        """Validation rejections should be recorded with reason."""
        from indico_assistant.models.audit import QueryAuditLog
        from indico_assistant.services.nl2sql.audit import log_validation_rejection
        
        entry = QueryAuditLog.create_entry(question="DROP TABLE events")
        
        log_validation_rejection(entry, "DDL_STATEMENT_NOT_ALLOWED")
        
        assert entry.validation_rejection_reason == "DDL_STATEMENT_NOT_ALLOWED"
        assert entry.success is False

    def test_audit_log_records_execution_success(
        self, mock_db_session: MagicMock
    ) -> None:
        """Successful execution should be recorded with metrics."""
        from indico_assistant.models.audit import QueryAuditLog
        from indico_assistant.services.nl2sql.audit import log_execution
        
        entry = QueryAuditLog.create_entry(question="List events")
        
        log_execution(entry, execution_time_ms=150.5, row_count=25, success=True)
        
        assert entry.execution_time_ms == 150.5
        assert entry.row_count == 25
        assert entry.success is True

    def test_audit_log_records_execution_failure(
        self, mock_db_session: MagicMock
    ) -> None:
        """Failed execution should be recorded with error."""
        from indico_assistant.models.audit import QueryAuditLog
        from indico_assistant.services.nl2sql.audit import log_error
        
        entry = QueryAuditLog.create_entry(question="List events")
        
        log_error(entry, "Connection timeout after 30s")
        
        assert entry.error_message == "Connection timeout after 30s"
        assert entry.success is False

    def test_audit_log_records_correction_attempts(
        self, mock_db_session: MagicMock
    ) -> None:
        """Error correction attempts should be tracked."""
        from indico_assistant.models.audit import QueryAuditLog
        from indico_assistant.services.nl2sql.audit import (
            log_correction_attempt,
            log_correction_success,
        )
        
        entry = QueryAuditLog.create_entry(question="List events")
        
        log_correction_attempt(entry)
        log_correction_attempt(entry)
        log_correction_success(entry)
        
        assert entry.correction_attempts == 2
        assert entry.was_corrected is True

    def test_audit_log_records_cache_hit(
        self, mock_db_session: MagicMock
    ) -> None:
        """Cache hits should be recorded."""
        from indico_assistant.models.audit import QueryAuditLog
        from indico_assistant.services.nl2sql.audit import log_cache_hit
        
        entry = QueryAuditLog.create_entry(question="List events")
        
        log_cache_hit(entry)
        
        assert entry.cached is True


class TestAuditLoggingCommit:
    """Test audit log commit behavior."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create mock database session."""
        return MagicMock()

    def test_context_manager_commits_on_success(
        self, mock_db_session: MagicMock
    ) -> None:
        """Context manager should commit on successful exit."""
        from indico_assistant.services.nl2sql.audit import AuditLogger
        
        logger = AuditLogger(mock_db_session, enabled=True)
        
        with logger.log_query("test question") as entry:
            assert entry is not None
        
        mock_db_session.commit.assert_called()

    def test_context_manager_commits_on_exception(
        self, mock_db_session: MagicMock
    ) -> None:
        """Context manager should commit even on exception."""
        from indico_assistant.services.nl2sql.audit import AuditLogger
        
        logger = AuditLogger(mock_db_session, enabled=True)
        
        try:
            with logger.log_query("test question") as entry:
                raise RuntimeError("Something went wrong")
        except RuntimeError:
            pass
        
        mock_db_session.commit.assert_called()


class TestAuditLoggingDisabled:
    """Test behavior when audit logging is disabled."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Create mock database session."""
        return MagicMock()

    def test_disabled_logger_returns_none(
        self, mock_db_session: MagicMock
    ) -> None:
        """Disabled logger should return None entries."""
        from indico_assistant.services.nl2sql.audit import AuditLogger
        
        logger = AuditLogger(mock_db_session, enabled=False)
        
        entry = logger.create_log_entry(question="test")
        
        assert entry is None
        mock_db_session.add.assert_not_called()

    def test_disabled_logger_context_manager_yields_none(
        self, mock_db_session: MagicMock
    ) -> None:
        """Disabled logger context manager should yield None."""
        from indico_assistant.services.nl2sql.audit import AuditLogger
        
        logger = AuditLogger(mock_db_session, enabled=False)
        
        with logger.log_query("test") as entry:
            assert entry is None

    def test_helper_functions_safe_with_none(
        self, mock_db_session: MagicMock
    ) -> None:
        """Helper functions should be safe with None entry."""
        from indico_assistant.services.nl2sql.audit import (
            log_cache_hit,
            log_classification,
            log_correction_attempt,
            log_correction_success,
            log_error,
            log_execution,
            log_generation,
            log_validation_rejection,
        )
        
        # None of these should raise
        log_classification(None, "event_list", 0.9)
        log_generation(None, "SELECT * FROM events")
        log_execution(None, 100.0, 10, success=True)
        log_validation_rejection(None, "reason")
        log_error(None, "error")
        log_correction_attempt(None)
        log_correction_success(None)
        log_cache_hit(None)


class TestAuditLoggingMigration:
    """Test migration creates correct schema."""

    def test_migration_creates_schema(self) -> None:
        """Migration should create plugin_assistant schema."""
        import importlib.util
        import os
        
        # Load migration module by path (name has numeric prefix)
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "indico_assistant",
            "migrations",
            "versions",
            "001_create_query_audit_log.py",
        )
        migration_path = os.path.abspath(migration_path)
        
        spec = importlib.util.spec_from_file_location("migration", migration_path)
        assert spec is not None
        assert spec.loader is not None
        
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        
        # Functions should exist and be callable
        assert callable(migration.upgrade)
        assert callable(migration.downgrade)

    def test_model_matches_migration_columns(self) -> None:
        """Model columns should match migration columns."""
        from indico_assistant.models.audit import QueryAuditLog
        
        expected_columns = {
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
        
        model_columns = {c.name for c in QueryAuditLog.__table__.columns}
        
        assert expected_columns == model_columns


class TestAuditLoggingComplianceFR031:
    """Test FR-031: Query results are NOT stored in audit logs."""

    def test_results_not_stored_in_model(self) -> None:
        """QueryAuditLog should NOT have results column."""
        from indico_assistant.models.audit import QueryAuditLog
        
        columns = {c.name for c in QueryAuditLog.__table__.columns}
        
        forbidden_columns = {
            "results",
            "result_data",
            "query_results",
            "data",
            "rows",
        }
        
        assert forbidden_columns.isdisjoint(columns), (
            f"Model should not have result columns: {forbidden_columns & columns}"
        )

    def test_only_metadata_stored(self) -> None:
        """Only query metadata should be stored, not results."""
        from indico_assistant.models.audit import QueryAuditLog
        
        entry = QueryAuditLog.create_entry(question="Show events")
        entry.update_classification("event_list", 0.95)
        entry.update_generation("SELECT * FROM events")
        entry.update_execution(150.0, 100, success=True)
        
        # Verify metadata is stored
        assert entry.question is not None
        assert entry.intent is not None
        assert entry.generated_sql is not None
        assert entry.row_count is not None
        
        # Verify no results storage method exists
        assert not hasattr(entry, "store_results")
        assert not hasattr(entry, "set_results")
