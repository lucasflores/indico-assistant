# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Unit tests for QueryExecutor component."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from indico_assistant.services.nl2sql.executor import QueryExecutor


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock database session."""
    session = MagicMock()
    return session


@pytest.fixture
def mock_result() -> MagicMock:
    """Create a mock query result."""
    result = MagicMock()
    result.keys.return_value = ["id", "title", "created_at"]
    result.fetchall.return_value = [
        (1, "Event 1", "2024-01-01"),
        (2, "Event 2", "2024-01-02"),
        (3, "Event 3", "2024-01-03"),
    ]
    return result


@pytest.fixture
def db_session_factory(mock_session: MagicMock, mock_result: MagicMock):
    """Create a mock database session factory."""
    mock_session.execute.return_value = mock_result

    def factory():
        return mock_session

    return factory


@pytest.fixture
def executor(db_session_factory) -> QueryExecutor:
    """Create an executor instance."""
    return QueryExecutor(
        db_session_factory=db_session_factory,
        max_rows=1000,
        timeout_seconds=30,
    )


class TestQueryExecutorBasicExecution:
    """Test basic query execution."""

    def test_execute_returns_success_result(
        self, executor: QueryExecutor
    ) -> None:
        """Successful execution should return success=True."""
        result = executor.execute("SELECT * FROM events.events")

        assert result.success is True
        assert result.error_message is None

    def test_execute_returns_rows(
        self, executor: QueryExecutor
    ) -> None:
        """Should return fetched rows as list of dicts."""
        result = executor.execute("SELECT * FROM events.events")

        assert len(result.rows) == 3
        assert result.rows[0]["id"] == 1
        assert result.rows[0]["title"] == "Event 1"

    def test_execute_returns_columns(
        self, executor: QueryExecutor
    ) -> None:
        """Should return column names."""
        result = executor.execute("SELECT * FROM events.events")

        assert result.columns == ["id", "title", "created_at"]

    def test_execute_returns_row_count(
        self, executor: QueryExecutor
    ) -> None:
        """Should return correct row count."""
        result = executor.execute("SELECT * FROM events.events")

        assert result.row_count == 3

    def test_execute_with_parameters(
        self,
        db_session_factory,
        mock_session: MagicMock,
    ) -> None:
        """Should pass parameters to query execution."""
        executor = QueryExecutor(db_session_factory=db_session_factory)
        params = {"event_id": 123}

        executor.execute(
            "SELECT * FROM events.events WHERE id = :event_id",
            params=params,
        )

        # Second call is the actual query (first is SET statement_timeout)
        calls = mock_session.execute.call_args_list
        query_call = calls[1]
        assert query_call[0][1] == params


class TestQueryExecutorTimeout:
    """Test query timeout enforcement (FR-025)."""

    def test_sets_statement_timeout(
        self,
        db_session_factory,
        mock_session: MagicMock,
    ) -> None:
        """Should set PostgreSQL statement timeout."""
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            timeout_seconds=30,
        )

        executor.execute("SELECT * FROM events.events")

        # First execute call should be the timeout setting
        first_call = mock_session.execute.call_args_list[0]
        timeout_sql = str(first_call[0][0])
        assert "statement_timeout" in timeout_sql.lower()
        assert "30000" in timeout_sql  # 30 * 1000 ms

    def test_custom_timeout_value(
        self,
        db_session_factory,
        mock_session: MagicMock,
    ) -> None:
        """Custom timeout should be applied."""
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            timeout_seconds=60,
        )

        executor.execute("SELECT * FROM events.events")

        first_call = mock_session.execute.call_args_list[0]
        timeout_sql = str(first_call[0][0])
        assert "60000" in timeout_sql  # 60 * 1000 ms

    def test_timeout_property(self, db_session_factory) -> None:
        """timeout_seconds property should return configured value."""
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            timeout_seconds=45,
        )

        assert executor.timeout_seconds == 45

    def test_timeout_error_handled(
        self,
        db_session_factory,
        mock_session: MagicMock,
    ) -> None:
        """Timeout errors should be converted to friendly message."""
        mock_session.execute.side_effect = SQLAlchemyError(
            "statement timeout"
        )
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            timeout_seconds=30,
        )

        result = executor.execute("SELECT * FROM events.events")

        assert result.success is False
        assert "timed out" in result.error_message.lower()
        assert "30 seconds" in result.error_message


class TestQueryExecutorRowLimit:
    """Test row limit enforcement (FR-024)."""

    def test_adds_limit_when_missing(
        self,
        db_session_factory,
        mock_session: MagicMock,
        mock_result: MagicMock,
    ) -> None:
        """Should add LIMIT clause when not present."""
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            max_rows=1000,
        )

        executor.execute("SELECT * FROM events.events")

        # Second execute call is the query
        query_call = mock_session.execute.call_args_list[1]
        sql = str(query_call[0][0])
        assert "LIMIT 1000" in sql.upper()

    def test_preserves_existing_limit(
        self,
        db_session_factory,
        mock_session: MagicMock,
    ) -> None:
        """Should not modify query with existing LIMIT."""
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            max_rows=1000,
        )
        sql = "SELECT * FROM events.events LIMIT 10"

        executor.execute(sql)

        query_call = mock_session.execute.call_args_list[1]
        executed_sql = str(query_call[0][0])
        # Should not add another LIMIT
        assert executed_sql.upper().count("LIMIT") == 1

    def test_truncated_flag_when_at_limit(
        self,
        db_session_factory,
        mock_session: MagicMock,
        mock_result: MagicMock,
    ) -> None:
        """truncated should be True when rows equal max_rows."""
        mock_result.fetchall.return_value = [(i,) for i in range(10)]
        mock_result.keys.return_value = ["id"]
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            max_rows=10,
        )

        result = executor.execute("SELECT id FROM events.events")

        assert result.truncated is True

    def test_not_truncated_when_under_limit(
        self, executor: QueryExecutor
    ) -> None:
        """truncated should be False when rows under max_rows."""
        result = executor.execute("SELECT * FROM events.events")

        # 3 rows returned, max is 1000
        assert result.truncated is False

    def test_max_rows_property(self, db_session_factory) -> None:
        """max_rows property should return configured value."""
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            max_rows=500,
        )

        assert executor.max_rows == 500

    def test_rows_truncated_to_max(
        self,
        db_session_factory,
        mock_session: MagicMock,
        mock_result: MagicMock,
    ) -> None:
        """Rows exceeding max should be truncated."""
        mock_result.fetchall.return_value = [(i,) for i in range(20)]
        mock_result.keys.return_value = ["id"]
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            max_rows=10,
        )

        result = executor.execute("SELECT id FROM events.events")

        assert result.row_count == 10
        assert result.truncated is True

    def test_handles_semicolon_when_adding_limit(
        self,
        db_session_factory,
        mock_session: MagicMock,
    ) -> None:
        """Should handle trailing semicolon when adding LIMIT."""
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            max_rows=100,
        )

        executor.execute("SELECT * FROM events.events;")

        query_call = mock_session.execute.call_args_list[1]
        sql = str(query_call[0][0])
        # Should not have ;LIMIT
        assert "LIMIT 100" in sql.upper()


class TestQueryExecutorErrorHandling:
    """Test error handling."""

    def test_sqlalchemy_error_returns_failure(
        self,
        db_session_factory,
        mock_session: MagicMock,
    ) -> None:
        """SQLAlchemy errors should return failure result."""
        mock_session.execute.side_effect = SQLAlchemyError("Database error")
        executor = QueryExecutor(db_session_factory=db_session_factory)

        result = executor.execute("SELECT * FROM events.events")

        assert result.success is False
        assert "Database error" in result.error_message

    def test_generic_error_returns_failure(
        self,
        db_session_factory,
        mock_session: MagicMock,
    ) -> None:
        """Generic errors should return failure result."""
        mock_session.execute.side_effect = Exception("Unexpected error")
        executor = QueryExecutor(db_session_factory=db_session_factory)

        result = executor.execute("SELECT * FROM events.events")

        assert result.success is False
        assert "Unexpected error" in result.error_message

    def test_error_returns_empty_rows(
        self,
        db_session_factory,
        mock_session: MagicMock,
    ) -> None:
        """Error results should have empty rows."""
        mock_session.execute.side_effect = SQLAlchemyError("Error")
        executor = QueryExecutor(db_session_factory=db_session_factory)

        result = executor.execute("SELECT * FROM events.events")

        assert result.rows == []
        assert result.row_count == 0
        assert result.columns == []


class TestQueryExecutorExecutionTime:
    """Test execution time tracking."""

    def test_records_execution_time(
        self, executor: QueryExecutor
    ) -> None:
        """Should record execution time in milliseconds."""
        result = executor.execute("SELECT * FROM events.events")

        assert result.execution_time_ms >= 0

    def test_execution_time_on_error(
        self,
        db_session_factory,
        mock_session: MagicMock,
    ) -> None:
        """Should record execution time even on error."""
        mock_session.execute.side_effect = SQLAlchemyError("Error")
        executor = QueryExecutor(db_session_factory=db_session_factory)

        result = executor.execute("SELECT * FROM events.events")

        assert result.execution_time_ms >= 0


class TestQueryExecutorDefaultParams:
    """Test default parameter handling."""

    def test_none_params_converted_to_empty_dict(
        self,
        db_session_factory,
        mock_session: MagicMock,
    ) -> None:
        """None params should be converted to empty dict."""
        executor = QueryExecutor(db_session_factory=db_session_factory)

        executor.execute("SELECT * FROM events.events", params=None)

        # Second call is the query
        query_call = mock_session.execute.call_args_list[1]
        # Params should be empty dict, not None
        assert query_call[0][1] == {}


class TestQueryExecutorEmptyResult:
    """Test handling of empty results."""

    def test_empty_result_returns_success(
        self,
        db_session_factory,
        mock_session: MagicMock,
        mock_result: MagicMock,
    ) -> None:
        """Empty result set should still be successful."""
        mock_result.fetchall.return_value = []
        mock_result.keys.return_value = ["id", "title"]
        executor = QueryExecutor(db_session_factory=db_session_factory)

        result = executor.execute("SELECT * FROM events.events WHERE 1=0")

        assert result.success is True
        assert result.rows == []
        assert result.row_count == 0
        assert result.columns == ["id", "title"]

    def test_empty_result_not_truncated(
        self,
        db_session_factory,
        mock_session: MagicMock,
        mock_result: MagicMock,
    ) -> None:
        """Empty result should not be marked truncated."""
        mock_result.fetchall.return_value = []
        mock_result.keys.return_value = ["id"]
        executor = QueryExecutor(db_session_factory=db_session_factory)

        result = executor.execute("SELECT * FROM events.events WHERE 1=0")

        assert result.truncated is False


class TestQueryExecutorEnsureLimit:
    """Test _ensure_limit helper method."""

    def test_ensure_limit_adds_limit(self, db_session_factory) -> None:
        """Should add LIMIT to query without one."""
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            max_rows=100,
        )

        result = executor._ensure_limit("SELECT * FROM events")

        assert "LIMIT 100" in result.upper()

    def test_ensure_limit_preserves_existing(self, db_session_factory) -> None:
        """Should not modify query with LIMIT."""
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            max_rows=100,
        )
        sql = "SELECT * FROM events LIMIT 50"

        result = executor._ensure_limit(sql)

        assert result == sql

    def test_ensure_limit_case_insensitive(self, db_session_factory) -> None:
        """Should detect LIMIT regardless of case."""
        executor = QueryExecutor(
            db_session_factory=db_session_factory,
            max_rows=100,
        )

        result = executor._ensure_limit("SELECT * FROM events limit 50")

        assert result == "SELECT * FROM events limit 50"
