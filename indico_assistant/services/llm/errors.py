"""LLM error types and error handling.

This module defines structured error types for LLM failures,
ensuring all errors are handled gracefully without raising exceptions.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ErrorType(str, Enum):
    """Categorized error types for LLM failures.
    
    These types allow callers to programmatically handle different
    error conditions appropriately.
    """
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION_ERROR = "authentication_error"
    VALIDATION_ERROR = "validation_error"
    MODEL_NOT_FOUND = "model_not_found"
    NOT_CONFIGURED = "not_configured"
    UNKNOWN_ERROR = "unknown_error"


class LLMError(BaseModel):
    """Structured error for LLM failures.
    
    All LLM errors are wrapped in this model rather than being raised
    as exceptions. This ensures callers can handle errors gracefully
    without try/except blocks.
    
    Attributes:
        error_type: Categorized error type for programmatic handling.
        message: Human-readable error description.
        details: Additional error context (optional).
        retry_after: Seconds to wait before retry (for rate_limit).
    
    Example:
        >>> error = LLMError(
        ...     error_type=ErrorType.TIMEOUT,
        ...     message="Request timed out after 30 seconds",
        ...     details={"timeout_seconds": 30}
        ... )
    """
    error_type: ErrorType
    message: str = Field(min_length=1)
    details: dict[str, Any] | None = None
    retry_after: int | None = Field(default=None, gt=0)
    
    @field_validator("message")
    @classmethod
    def validate_message_not_empty(cls, v: str) -> str:
        """Ensure message is not just whitespace."""
        if not v.strip():
            raise ValueError("message cannot be empty or whitespace")
        return v


def _map_exception_to_error(exc: Exception) -> LLMError:
    """Map provider exceptions to LLMError types.
    
    This function converts various provider-specific exceptions into
    structured LLMError objects for consistent error handling.
    
    Args:
        exc: The exception to map.
        
    Returns:
        A structured LLMError with appropriate type and message.
    
    Note:
        API keys and other sensitive information are never included
        in error messages or details.
    """
    exc_type = type(exc).__name__
    exc_module = type(exc).__module__
    
    # ValueError handling (often configuration issues)
    if isinstance(exc, ValueError):
        message = str(exc).strip() or "Invalid LLM configuration"
        lowered = message.lower()
        if "api key" in lowered or "api_key" in lowered:
            return LLMError(
                error_type=ErrorType.AUTHENTICATION_ERROR,
                message=message,
                details={"exception": exc_type}
            )
        if "provider" in lowered or "model" in lowered or "configuration" in lowered:
            return LLMError(
                error_type=ErrorType.NOT_CONFIGURED,
                message=message,
                details={"exception": exc_type}
            )
        return LLMError(
            error_type=ErrorType.UNKNOWN_ERROR,
            message=message,
            details={"exception": exc_type}
        )

    # OpenAI-specific exceptions
    if "openai" in exc_module.lower():
        if "Timeout" in exc_type or "APITimeoutError" in exc_type:
            return LLMError(
                error_type=ErrorType.TIMEOUT,
                message="LLM request timed out",
                details={"exception": exc_type}
            )
        if "Connection" in exc_type or "APIConnectionError" in exc_type:
            return LLMError(
                error_type=ErrorType.CONNECTION_ERROR,
                message="Failed to connect to LLM provider",
                details={"exception": exc_type}
            )
        if "RateLimit" in exc_type:
            # Try to extract retry_after from headers if available
            retry_after = None
            if hasattr(exc, "response") and exc.response is not None:
                retry_header = exc.response.headers.get("retry-after")
                if retry_header and retry_header.isdigit():
                    retry_after = int(retry_header)
            return LLMError(
                error_type=ErrorType.RATE_LIMIT,
                message="Rate limit exceeded",
                details={"exception": exc_type},
                retry_after=retry_after
            )
        if "Authentication" in exc_type or "AuthenticationError" in exc_type:
            return LLMError(
                error_type=ErrorType.AUTHENTICATION_ERROR,
                message="Authentication failed - check API key configuration",
                details={"exception": exc_type}
            )
        if "NotFound" in exc_type:
            return LLMError(
                error_type=ErrorType.MODEL_NOT_FOUND,
                message="Model not found on provider",
                details={"exception": exc_type}
            )
    
    # Instructor-specific exceptions
    if "instructor" in exc_module.lower():
        if "Retry" in exc_type:
            return LLMError(
                error_type=ErrorType.VALIDATION_ERROR,
                message="Response validation failed after max retries",
                details={"exception": exc_type, "original_error": str(exc)}
            )
    
    # Pydantic validation errors
    if "pydantic" in exc_module.lower() or "ValidationError" in exc_type:
        return LLMError(
            error_type=ErrorType.VALIDATION_ERROR,
            message="Response did not match expected schema",
            details={"exception": exc_type, "errors": str(exc)}
        )
    
    # Ollama-specific exceptions
    if "ollama" in exc_module.lower():
        if "ResponseError" in exc_type:
            error_str = str(exc).lower()
            if "not found" in error_str or "doesn't exist" in error_str:
                return LLMError(
                    error_type=ErrorType.MODEL_NOT_FOUND,
                    message="Model not found on Ollama server",
                    details={"exception": exc_type}
                )
            if "connection" in error_str or "connect" in error_str:
                return LLMError(
                    error_type=ErrorType.CONNECTION_ERROR,
                    message="Failed to connect to Ollama server",
                    details={"exception": exc_type}
                )
    
    # Generic timeout handling
    if "Timeout" in exc_type or "timeout" in str(exc).lower():
        return LLMError(
            error_type=ErrorType.TIMEOUT,
            message=f"Request timed out: {exc}",
            details={"exception": exc_type}
        )
    
    # Generic connection error handling
    if "Connection" in exc_type or "connection" in str(exc).lower():
        return LLMError(
            error_type=ErrorType.CONNECTION_ERROR,
            message=f"Connection error: {exc}",
            details={"exception": exc_type}
        )
    
    # Unknown error fallback
    return LLMError(
        error_type=ErrorType.UNKNOWN_ERROR,
        message=f"Unexpected error: {exc_type}: {exc}",
        details={"exception": exc_type, "message": str(exc)}
    )
