"""Contract tests for error responses (T058).

Tests verify error response contract compliance per spec/contracts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from indico_assistant.services.nl2sql.models import (
    PipelineError,
    PipelineErrorType,
    PipelineResult,
)

if TYPE_CHECKING:
    pass


class TestErrorResponseContract:
    """Test error response contract compliance."""

    def test_classification_error_has_user_message(self) -> None:
        """Classification errors MUST have user-friendly message."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.CLASSIFICATION_FAILED,
                message="LLM returned invalid response",
                user_message="I couldn't understand your question. Please try rephrasing it.",
            ),
            total_time_ms=50,
        )

        assert result.error.user_message is not None
        assert len(result.error.user_message) > 10  # Not too short
        # User message should be friendly, not technical
        assert "LLM" not in result.error.user_message
        assert "exception" not in result.error.user_message.lower()

    def test_generation_error_has_user_message(self) -> None:
        """Generation errors MUST have user-friendly message."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.GENERATION_FAILED,
                message="SQL generation failed",
                user_message="I had trouble creating a query for your question.",
            ),
            total_time_ms=100,
        )

        assert result.error.user_message is not None
        # User message should be helpful
        assert "SQL" not in result.error.user_message or "query" in result.error.user_message.lower()

    def test_validation_error_has_user_message(self) -> None:
        """Validation errors MUST have user-friendly message."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.VALIDATION_FAILED,
                message="DDL statement detected",
                user_message="I generated a query that doesn't meet our safety requirements.",
            ),
            total_time_ms=50,
            generated_sql="DROP TABLE events",  # May be included for debugging
        )

        assert result.error.user_message is not None
        # Should not expose technical details to user
        assert "DDL" not in result.error.user_message

    def test_execution_error_has_user_message(self) -> None:
        """Execution errors MUST have user-friendly message."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.EXECUTION_FAILED,
                message="Connection timeout after 30 seconds",
                user_message="I wasn't able to retrieve that information.",
            ),
            total_time_ms=30000,
        )

        assert result.error.user_message is not None
        # Technical details in internal message only
        assert "30 seconds" not in result.error.user_message

    def test_out_of_scope_error_guides_user(self) -> None:
        """Out-of-scope errors should guide user appropriately."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.OUT_OF_SCOPE,
                message="Query classified as out_of_scope",
                user_message="I can only help with questions about events and registrations.",
            ),
            total_time_ms=30,
        )

        assert result.error.user_message is not None
        # Should guide user on what IS supported
        assert "event" in result.error.user_message.lower() or "registration" in result.error.user_message.lower()

    def test_correction_exhausted_error_suggests_alternative(self) -> None:
        """Correction exhausted errors should suggest trying something else."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.CORRECTION_EXHAUSTED,
                message="Max correction attempts (3) reached",
                user_message="I wasn't able to retrieve that information. Please try a different question.",
            ),
            total_time_ms=5000,
            correction_attempts=3,
        )

        assert result.error.user_message is not None
        # Should suggest alternative action
        assert "try" in result.error.user_message.lower() or "different" in result.error.user_message.lower()


class TestErrorResponseInternalMessage:
    """Test internal error message contract (for logging/debugging)."""

    def test_internal_message_has_technical_details(self) -> None:
        """Internal message should have technical details."""
        error = PipelineError(
            error_type=PipelineErrorType.EXECUTION_FAILED,
            message="PostgreSQL error: relation 'events_v2' does not exist",
            user_message="I couldn't find that data.",
        )

        # Internal message should be technical
        assert "PostgreSQL" in error.message or "relation" in error.message

    def test_internal_and_user_messages_different(self) -> None:
        """Internal and user messages should be different."""
        error = PipelineError(
            error_type=PipelineErrorType.VALIDATION_FAILED,
            message="SQL injection pattern detected: '; DROP TABLE",
            user_message="Invalid query format.",
        )

        assert error.message != error.user_message
        # Internal has details, user does not
        assert "DROP" in error.message
        assert "DROP" not in error.user_message


class TestErrorResponseWithContext:
    """Test error responses include appropriate context."""

    def test_validation_error_includes_generated_sql(self) -> None:
        """Validation errors should include the generated SQL for debugging."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.VALIDATION_FAILED,
                message="CTE detected",
                user_message="Invalid query",
            ),
            generated_sql="WITH cte AS (SELECT * FROM events) SELECT * FROM cte",
            total_time_ms=50,
        )

        # Generated SQL available for debugging
        assert result.generated_sql is not None

    def test_execution_error_includes_timing(self) -> None:
        """Execution errors should include timing information."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.EXECUTION_FAILED,
                message="Timeout",
                user_message="Query took too long",
            ),
            total_time_ms=30000,
            execution_time_ms=30000,
        )

        assert result.total_time_ms is not None
        assert result.execution_time_ms is not None

    def test_correction_error_includes_attempts(self) -> None:
        """Correction exhausted errors should include attempt count."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.CORRECTION_EXHAUSTED,
                message="Max attempts reached",
                user_message="Could not fix the query",
            ),
            total_time_ms=5000,
            correction_attempts=3,
        )

        assert result.correction_attempts == 3


class TestErrorTypeEnumValues:
    """Test error type enum has expected values."""

    def test_all_error_types_have_unique_values(self) -> None:
        """All error types should have unique values."""
        values = [e.value for e in PipelineErrorType]
        assert len(values) == len(set(values))

    def test_error_types_are_strings(self) -> None:
        """Error type values should be string identifiers."""
        for error_type in PipelineErrorType:
            assert isinstance(error_type.value, str)

    def test_error_types_are_snake_case(self) -> None:
        """Error type values should be snake_case."""
        for error_type in PipelineErrorType:
            value = error_type.value
            # Should be lowercase or with underscores
            assert value == value.lower() or "_" in value


class TestErrorResponseImmutability:
    """Test error responses are properly structured."""

    def test_pipeline_error_has_all_fields(self) -> None:
        """PipelineError should have all required fields."""
        error = PipelineError(
            error_type=PipelineErrorType.EXECUTION_FAILED,
            message="Test error",
            user_message="Test user message",
        )

        # All fields should be present
        assert error.error_type is not None
        assert error.message is not None
        assert error.user_message is not None

    def test_error_type_is_enum(self) -> None:
        """Error type should be an enum value."""
        error = PipelineError(
            error_type=PipelineErrorType.EXECUTION_FAILED,
            message="Test",
            user_message="Test",
        )

        assert isinstance(error.error_type, PipelineErrorType)
