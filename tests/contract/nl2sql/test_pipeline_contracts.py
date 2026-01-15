"""Contract tests for NL2SQL pipeline (T057).

Tests verify PipelineResult contract compliance per spec/contracts.
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


class TestPipelineResultContract:
    """Test PipelineResult contract compliance."""

    def test_success_result_has_answer(self) -> None:
        """Successful result MUST have answer field."""
        result = PipelineResult(
            success=True,
            answer="Found 10 events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        assert result.success is True
        assert result.answer is not None
        assert len(result.answer) > 0

    def test_success_result_has_generated_sql(self) -> None:
        """Successful result MUST have generated_sql field."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        assert result.generated_sql is not None

    def test_success_result_has_tables_accessed(self) -> None:
        """Successful result MUST have tables_accessed list."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        assert isinstance(result.tables_accessed, list)

    def test_success_result_has_row_count(self) -> None:
        """Successful result MUST have row_count."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        assert result.row_count is not None
        assert result.row_count >= 0

    def test_success_result_has_total_time_ms(self) -> None:
        """Successful result MUST have total_time_ms."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        assert result.total_time_ms is not None
        assert result.total_time_ms >= 0

    def test_failed_result_has_error(self) -> None:
        """Failed result MUST have error field."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.CLASSIFICATION_FAILED,
                message="Classification failed",
                user_message="I couldn't understand your question.",
            ),
            total_time_ms=50,
        )

        assert result.success is False
        assert result.error is not None

    def test_result_confidence_is_optional(self) -> None:
        """Confidence field should be optional."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        # Should not raise - confidence is optional
        assert result.confidence is None or isinstance(result.confidence, float)

    def test_result_from_cache_is_optional(self) -> None:
        """from_cache field should default to False."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        assert result.from_cache is False

    def test_result_corrected_is_optional(self) -> None:
        """corrected field should default to False."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        assert result.corrected is False

    def test_result_correction_attempts_defaults_to_zero(self) -> None:
        """correction_attempts field should default to 0."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        assert result.correction_attempts == 0


class TestPipelineResultTimingFields:
    """Test PipelineResult timing field contracts."""

    def test_classification_time_ms_optional(self) -> None:
        """classification_time_ms should be optional."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        # Should not raise
        _ = result.classification_time_ms

    def test_generation_time_ms_optional(self) -> None:
        """generation_time_ms should be optional."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        # Should not raise
        _ = result.generation_time_ms

    def test_execution_time_ms_optional(self) -> None:
        """execution_time_ms should be optional."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        # Should not raise
        _ = result.execution_time_ms

    def test_total_time_includes_all_phases(self) -> None:
        """total_time_ms should be >= sum of phase times."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=300,
            classification_time_ms=50,
            generation_time_ms=100,
            execution_time_ms=100,
        )

        phase_sum = (
            (result.classification_time_ms or 0)
            + (result.generation_time_ms or 0)
            + (result.execution_time_ms or 0)
        )

        assert result.total_time_ms >= phase_sum


class TestPipelineResultSerializability:
    """Test PipelineResult serialization contract."""

    def test_result_is_json_serializable(self) -> None:
        """PipelineResult should be JSON serializable via model_dump."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        serialized = result.model_dump()

        assert isinstance(serialized, dict)
        assert serialized["success"] is True
        assert serialized["answer"] == "Found events"

    def test_error_result_is_json_serializable(self) -> None:
        """Error PipelineResult should be JSON serializable."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.EXECUTION_FAILED,
                message="Connection timeout",
                user_message="Query took too long",
            ),
            total_time_ms=30000,
        )

        serialized = result.model_dump()

        assert isinstance(serialized, dict)
        assert serialized["success"] is False
        assert serialized["error"] is not None

    def test_result_can_be_copied(self) -> None:
        """PipelineResult should support model_copy for caching."""
        result = PipelineResult(
            success=True,
            answer="Found events",
            generated_sql="SELECT * FROM events",
            tables_accessed=["events"],
            row_count=10,
            total_time_ms=150,
        )

        copied = result.model_copy()

        assert copied.success == result.success
        assert copied.answer == result.answer
        assert copied is not result


class TestPipelineErrorContract:
    """Test PipelineError contract compliance."""

    def test_error_has_error_type(self) -> None:
        """PipelineError MUST have error_type."""
        error = PipelineError(
            error_type=PipelineErrorType.VALIDATION_FAILED,
            message="DDL not allowed",
            user_message="Invalid query",
        )

        assert error.error_type is not None
        assert isinstance(error.error_type, PipelineErrorType)

    def test_error_has_message(self) -> None:
        """PipelineError MUST have internal message."""
        error = PipelineError(
            error_type=PipelineErrorType.VALIDATION_FAILED,
            message="DDL not allowed",
            user_message="Invalid query",
        )

        assert error.message is not None
        assert len(error.message) > 0

    def test_error_has_user_message(self) -> None:
        """PipelineError MUST have user-friendly message."""
        error = PipelineError(
            error_type=PipelineErrorType.VALIDATION_FAILED,
            message="DDL not allowed",
            user_message="Invalid query",
        )

        assert error.user_message is not None
        assert len(error.user_message) > 0


class TestPipelineErrorTypeContract:
    """Test PipelineErrorType enumeration contract."""

    def test_classification_failed_exists(self) -> None:
        """CLASSIFICATION_FAILED should exist."""
        assert hasattr(PipelineErrorType, "CLASSIFICATION_FAILED")

    def test_generation_failed_exists(self) -> None:
        """GENERATION_FAILED should exist."""
        assert hasattr(PipelineErrorType, "GENERATION_FAILED")

    def test_validation_failed_exists(self) -> None:
        """VALIDATION_FAILED should exist."""
        assert hasattr(PipelineErrorType, "VALIDATION_FAILED")

    def test_execution_failed_exists(self) -> None:
        """EXECUTION_FAILED should exist."""
        assert hasattr(PipelineErrorType, "EXECUTION_FAILED")

    def test_out_of_scope_exists(self) -> None:
        """OUT_OF_SCOPE should exist."""
        assert hasattr(PipelineErrorType, "OUT_OF_SCOPE")

    def test_correction_exhausted_exists(self) -> None:
        """CORRECTION_EXHAUSTED should exist."""
        assert hasattr(PipelineErrorType, "CORRECTION_EXHAUSTED")
