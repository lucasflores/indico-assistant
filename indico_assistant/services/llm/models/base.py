"""Base response models for LLM service.

This module contains the core response wrapper models used by the
LLM service to return structured results.
"""

from __future__ import annotations

from typing import Generic, TypeVar, Literal

from pydantic import BaseModel, Field, model_validator

from indico_assistant.services.llm.errors import LLMError


T = TypeVar("T", bound=BaseModel)


class LLMResponse(BaseModel, Generic[T]):
    """Generic response wrapper for LLM calls.
    
    This model wraps all LLM call results, ensuring callers receive
    either a validated response or a structured error, never an
    exception.
    
    Attributes:
        success: Whether the LLM call succeeded.
        result: The validated response model (if success=True).
        error: The structured error (if success=False).
        latency_ms: Call duration in milliseconds.
        retries: Number of retry attempts made.
    
    Invariants:
        - If success=True: result is not None, error is None
        - If success=False: result is None, error is not None
    
    Example:
        >>> response = LLMResponse[QueryClassification](
        ...     success=True,
        ...     result=QueryClassification(intent="search"),
        ...     latency_ms=150,
        ...     retries=0
        ... )
    """
    success: bool
    result: T | None = None
    error: LLMError | None = None
    latency_ms: int = Field(ge=0)
    retries: int = Field(ge=0, default=0)
    
    model_config = {"arbitrary_types_allowed": True}
    
    @model_validator(mode="after")
    def check_consistency(self) -> "LLMResponse[T]":
        """Validate response consistency invariants."""
        if self.success and self.result is None:
            raise ValueError("success=True requires result to be present")
        if not self.success and self.error is None:
            raise ValueError("success=False requires error to be present")
        if self.success and self.error is not None:
            raise ValueError("success=True cannot have an error")
        if not self.success and self.result is not None:
            raise ValueError("success=False cannot have a result")
        return self
    
    @classmethod
    def success_response(
        cls,
        result: T,
        latency_ms: int,
        retries: int = 0
    ) -> "LLMResponse[T]":
        """Create a successful response.
        
        Args:
            result: The validated response model.
            latency_ms: Call duration in milliseconds.
            retries: Number of retry attempts made.
            
        Returns:
            An LLMResponse with success=True.
        """
        return cls(
            success=True,
            result=result,
            latency_ms=latency_ms,
            retries=retries
        )
    
    @classmethod
    def error_response(
        cls,
        error: LLMError,
        latency_ms: int,
        retries: int = 0
    ) -> "LLMResponse[T]":
        """Create an error response.
        
        Args:
            error: The structured error.
            latency_ms: Call duration in milliseconds.
            retries: Number of retry attempts made.
            
        Returns:
            An LLMResponse with success=False.
        """
        return cls(
            success=False,
            error=error,
            latency_ms=latency_ms,
            retries=retries
        )


class HealthStatus(BaseModel):
    """Health check result for LLM provider.
    
    This model represents the result of an LLM health check,
    providing connectivity status and latency information.
    
    Attributes:
        status: Provider status ("connected", "unavailable", "timeout", "not_configured").
        latency_ms: Response time in milliseconds (if connected).
        provider: Configured provider name.
        model: Configured model name.
        error: Error message (if not connected).
    
    Example:
        >>> status = HealthStatus(
        ...     status="connected",
        ...     latency_ms=150,
        ...     provider="ollama",
        ...     model="llama3.2"
        ... )
    """
    status: Literal["connected", "unavailable", "timeout", "not_configured"]
    latency_ms: int | None = Field(default=None, ge=0)
    provider: str
    model: str
    error: str | None = None
    
    @model_validator(mode="after")
    def check_consistency(self) -> "HealthStatus":
        """Validate health status consistency."""
        if self.status == "connected" and self.latency_ms is None:
            raise ValueError("connected status requires latency_ms")
        if self.status != "connected" and self.status != "not_configured" and self.error is None:
            raise ValueError(f"status '{self.status}' should have an error message")
        return self
