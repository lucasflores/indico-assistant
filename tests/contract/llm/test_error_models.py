"""Contract tests for LLMError model validation.

These tests verify that the LLMError model enforces its validation
rules correctly and can be constructed with all valid error types.
"""

import pytest

from indico_assistant.services.llm.errors import LLMError, ErrorType


class TestErrorTypeEnum:
    """Tests for ErrorType enum values."""
    
    def test_all_error_types_exist(self):
        """All expected error types are defined."""
        expected_types = {
            "timeout",
            "connection_error", 
            "rate_limit",
            "authentication_error",
            "validation_error",
            "model_not_found",
            "not_configured",
            "unknown_error",
        }
        actual_types = {e.value for e in ErrorType}
        assert actual_types == expected_types
    
    def test_error_type_is_string_enum(self):
        """ErrorType values are strings."""
        for error_type in ErrorType:
            assert isinstance(error_type.value, str)
            assert error_type == error_type.value


class TestLLMErrorConstruction:
    """Tests for LLMError model construction."""
    
    def test_minimal_error(self):
        """Error can be created with just type and message."""
        error = LLMError(
            error_type=ErrorType.TIMEOUT,
            message="Request timed out"
        )
        assert error.error_type == ErrorType.TIMEOUT
        assert error.message == "Request timed out"
        assert error.details is None
        assert error.retry_after is None
    
    def test_full_error(self):
        """Error can be created with all fields."""
        error = LLMError(
            error_type=ErrorType.RATE_LIMIT,
            message="Too many requests",
            details={"requests_per_minute": 60},
            retry_after=30
        )
        assert error.error_type == ErrorType.RATE_LIMIT
        assert error.message == "Too many requests"
        assert error.details == {"requests_per_minute": 60}
        assert error.retry_after == 30
    
    @pytest.mark.parametrize("error_type", list(ErrorType))
    def test_all_error_types_accepted(self, error_type):
        """All ErrorType values can be used to create an error."""
        error = LLMError(
            error_type=error_type,
            message=f"Test error for {error_type.value}"
        )
        assert error.error_type == error_type


class TestLLMErrorValidation:
    """Tests for LLMError validation rules."""
    
    def test_empty_message_rejected(self):
        """Empty message string is rejected."""
        with pytest.raises(ValueError, match="at least 1 character"):
            LLMError(
                error_type=ErrorType.TIMEOUT,
                message=""
            )
    
    def test_whitespace_only_message_rejected(self):
        """Whitespace-only message is rejected."""
        with pytest.raises(ValueError, match="cannot be empty or whitespace"):
            LLMError(
                error_type=ErrorType.TIMEOUT,
                message="   "
            )
    
    def test_retry_after_must_be_positive(self):
        """retry_after must be greater than 0."""
        with pytest.raises(ValueError, match="greater than 0"):
            LLMError(
                error_type=ErrorType.RATE_LIMIT,
                message="Rate limited",
                retry_after=0
            )
    
    def test_retry_after_negative_rejected(self):
        """Negative retry_after is rejected."""
        with pytest.raises(ValueError, match="greater than 0"):
            LLMError(
                error_type=ErrorType.RATE_LIMIT,
                message="Rate limited",
                retry_after=-5
            )
    
    def test_invalid_error_type_rejected(self):
        """Invalid error type string is rejected."""
        with pytest.raises(ValueError):
            LLMError(
                error_type="invalid_type",  # type: ignore
                message="Test error"
            )


class TestLLMErrorSerialization:
    """Tests for LLMError serialization."""
    
    def test_to_dict(self):
        """Error can be serialized to dict."""
        error = LLMError(
            error_type=ErrorType.CONNECTION_ERROR,
            message="Connection failed",
            details={"host": "localhost"}
        )
        data = error.model_dump()
        assert data["error_type"] == "connection_error"
        assert data["message"] == "Connection failed"
        assert data["details"] == {"host": "localhost"}
        assert data["retry_after"] is None
    
    def test_from_dict(self):
        """Error can be deserialized from dict."""
        data = {
            "error_type": "validation_error",
            "message": "Invalid response",
            "details": {"field": "name"},
        }
        error = LLMError.model_validate(data)
        assert error.error_type == ErrorType.VALIDATION_ERROR
        assert error.message == "Invalid response"
        assert error.details == {"field": "name"}
