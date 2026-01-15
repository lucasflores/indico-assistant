"""Unit tests for LLM error handling and exception mapping.

These tests verify that provider exceptions are correctly mapped
to structured LLMError objects.
"""

import pytest
from unittest.mock import Mock

from indico_assistant.services.llm.errors import (
    LLMError,
    ErrorType,
    _map_exception_to_error,
)


class MockOpenAIException(Exception):
    """Base mock for OpenAI exceptions."""
    pass


class MockAPITimeoutError(MockOpenAIException):
    """Mock OpenAI timeout error."""
    __module__ = "openai"
    

class MockAPIConnectionError(MockOpenAIException):
    """Mock OpenAI connection error."""
    __module__ = "openai"


class MockRateLimitError(MockOpenAIException):
    """Mock OpenAI rate limit error."""
    __module__ = "openai"
    
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class MockAuthenticationError(MockOpenAIException):
    """Mock OpenAI authentication error."""
    __module__ = "openai"


class MockInstructorRetryException(Exception):
    """Mock Instructor retry exhausted exception."""
    __module__ = "instructor.exceptions"


class MockPydanticValidationError(Exception):
    """Mock Pydantic validation error."""
    __module__ = "pydantic"


class TestTimeoutErrorMapping:
    """Tests for timeout error mapping."""
    
    def test_openai_timeout_maps_correctly(self):
        """OpenAI APITimeoutError maps to TIMEOUT."""
        exc = MockAPITimeoutError("Request timed out")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.TIMEOUT
        assert "timed out" in error.message.lower()
        assert error.details is not None
    
    def test_generic_timeout_in_message(self):
        """Exception with 'timeout' in message maps to TIMEOUT."""
        exc = Exception("Connection timeout after 30s")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.TIMEOUT
    
    def test_generic_timeout_type_name(self):
        """Exception with 'Timeout' in type name maps to TIMEOUT."""
        class CustomTimeoutError(Exception):
            __module__ = "custom"
        
        exc = CustomTimeoutError("Request failed")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.TIMEOUT


class TestConnectionErrorMapping:
    """Tests for connection error mapping."""
    
    def test_openai_connection_error_maps_correctly(self):
        """OpenAI APIConnectionError maps to CONNECTION_ERROR."""
        exc = MockAPIConnectionError("Connection refused")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.CONNECTION_ERROR
        assert "connect" in error.message.lower()
    
    def test_generic_connection_in_message(self):
        """Exception with 'connection' in message maps to CONNECTION_ERROR."""
        exc = Exception("Failed to establish connection")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.CONNECTION_ERROR
    
    def test_generic_connection_type_name(self):
        """Exception with 'Connection' in type name maps to CONNECTION_ERROR."""
        class CustomConnectionError(Exception):
            __module__ = "custom"
        
        exc = CustomConnectionError("Host unreachable")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.CONNECTION_ERROR


class TestRateLimitErrorMapping:
    """Tests for rate limit error mapping."""
    
    def test_openai_rate_limit_maps_correctly(self):
        """OpenAI RateLimitError maps to RATE_LIMIT."""
        exc = MockRateLimitError("Rate limit exceeded")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.RATE_LIMIT
    
    def test_rate_limit_extracts_retry_after(self):
        """Rate limit error extracts retry-after from response headers."""
        mock_response = Mock()
        mock_response.headers = {"retry-after": "30"}
        
        exc = MockRateLimitError("Rate limit exceeded", response=mock_response)
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.RATE_LIMIT
        assert error.retry_after == 30
    
    def test_rate_limit_handles_missing_retry_after(self):
        """Rate limit error handles missing retry-after header."""
        mock_response = Mock()
        mock_response.headers = {}
        
        exc = MockRateLimitError("Rate limit exceeded", response=mock_response)
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.RATE_LIMIT
        assert error.retry_after is None


class TestAuthenticationErrorMapping:
    """Tests for authentication error mapping."""
    
    def test_openai_auth_error_maps_correctly(self):
        """OpenAI AuthenticationError maps to AUTHENTICATION_ERROR."""
        exc = MockAuthenticationError("Invalid API key")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.AUTHENTICATION_ERROR
        # API key should not be in error message
        assert "sk-" not in error.message
        assert "hf_" not in error.message
    
    def test_auth_error_message_is_safe(self):
        """Authentication error message does not leak credentials."""
        exc = MockAuthenticationError("API key sk-abc123xyz is invalid")
        error = _map_exception_to_error(exc)
        
        # The mapped error should have a generic message
        assert error.error_type == ErrorType.AUTHENTICATION_ERROR
        assert "configuration" in error.message.lower() or "failed" in error.message.lower()


class TestValidationErrorMapping:
    """Tests for validation error mapping."""
    
    def test_instructor_retry_exception_maps_correctly(self):
        """Instructor retry exception maps to VALIDATION_ERROR."""
        exc = MockInstructorRetryException("Max retries exceeded")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.VALIDATION_ERROR
        assert "validation" in error.message.lower() or "retries" in error.message.lower()
    
    def test_pydantic_validation_error_maps_correctly(self):
        """Pydantic ValidationError maps to VALIDATION_ERROR."""
        exc = MockPydanticValidationError("1 validation error for Model")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.VALIDATION_ERROR


class TestUnknownErrorMapping:
    """Tests for unknown/generic error mapping."""
    
    def test_generic_exception_maps_to_unknown(self):
        """Generic exception without specific markers maps to UNKNOWN_ERROR."""
        exc = RuntimeError("Something went wrong")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.UNKNOWN_ERROR
        assert "RuntimeError" in error.details.get("exception", "")
    
    def test_unknown_error_includes_exception_type(self):
        """Unknown error includes the original exception type."""
        class CustomException(Exception):
            __module__ = "custom.module"
        
        exc = CustomException("Custom error")
        error = _map_exception_to_error(exc)
        
        assert error.error_type == ErrorType.UNKNOWN_ERROR
        assert "CustomException" in error.details.get("exception", "")


class TestErrorMessageSafety:
    """Tests ensuring error messages don't leak sensitive data."""
    
    def test_no_api_key_in_error_message(self):
        """Error messages should not contain API keys."""
        test_cases = [
            MockAuthenticationError("Invalid key: sk-abc123"),
            MockAuthenticationError("Invalid key: hf_xyz789"),
            MockAPIConnectionError("Failed with key: api-key-secret"),
        ]
        
        for exc in test_cases:
            error = _map_exception_to_error(exc)
            # The mapped message should be generic, not contain the original
            assert "sk-" not in error.message
            assert "hf_" not in error.message
            assert "api-key" not in error.message.lower()
    
    def test_details_dont_contain_sensitive_data(self):
        """Error details should not contain full API keys."""
        exc = MockAuthenticationError("API key sk-abc123xyz is invalid")
        error = _map_exception_to_error(exc)
        
        # Details may contain exception type but not the full message with key
        if error.details and "message" in error.details:
            assert "sk-abc123xyz" not in error.details["message"]
