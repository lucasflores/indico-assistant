"""LLM Service - Main service class for LLM interactions.

This module provides the LLMService class which handles all LLM
provider interactions using the Instructor library.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Type, TypeVar

from pydantic import BaseModel

from indico_assistant.services.llm.errors import LLMError, ErrorType, _map_exception_to_error
from indico_assistant.services.llm.models import LLMResponse, HealthStatus

if TYPE_CHECKING:
    from indico_assistant.plugin import AssistantPlugin


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMService:
    """Main service class providing LLM interaction capabilities.
    
    This service wraps the Instructor library to provide structured
    LLM outputs with automatic validation and retry logic.
    
    The service is designed for graceful degradation - all errors are
    returned as structured LLMError objects, never raised as exceptions.
    
    Attributes:
        _plugin: Reference to the AssistantPlugin for settings access.
        _client: Lazy-initialized Instructor client.
        _logger: Structured logger for observability.
    
    Example:
        >>> llm = create_llm_service(plugin)
        >>> response = llm.generate("What events?", QueryClassification)
        >>> if response.success:
        ...     print(response.result.intent)
    """
    
    def __init__(self, plugin: "AssistantPlugin") -> None:
        """Initialize LLM service with plugin reference.
        
        Args:
            plugin: The AssistantPlugin instance for settings access.
        
        Note:
            The actual Instructor client is NOT created here.
            It is lazy-initialized on first generate() or health_check() call.
        """
        self._plugin = plugin
        self._client = None
        self._logger = logger
    
    def _get_settings(self) -> dict[str, Any]:
        """Extract LLM configuration from plugin settings.
        
        Returns:
            Dictionary containing LLM settings.
        """
        settings = self._plugin.settings
        return {
            "provider": settings.get("llm_provider"),
            "model": settings.get("llm_model"),
            "base_url": settings.get("llm_base_url"),
            "api_key": settings.get("llm_api_key"),
            "timeout_seconds": settings.get("timeout_seconds", 30),
            "max_tokens": settings.get("max_tokens", 2048),
            "max_retries": settings.get("max_retries", 2),
        }
    
    def _create_client(self):
        """Create an Instructor client based on current settings.
        
        Returns:
            Configured Instructor client.
            
        Raises:
            This method should not raise - errors should be caught
            and converted to LLMError in the calling method.
        """
        from indico_assistant.services.llm.factory import create_instructor_client
        
        settings = self._get_settings()
        return create_instructor_client(
            provider=settings["provider"],
            model=settings["model"],
            base_url=settings["base_url"],
            api_key=settings["api_key"],
        )
    
    def _ensure_client(self) -> tuple[Any | None, LLMError | None]:
        """Ensure client is initialized, returning error if not.
        
        Returns:
            Tuple of (client, error). If client is None, error is set.
        """
        if self._client is not None:
            return self._client, None
        
        settings = self._get_settings()
        if not settings["provider"]:
            return None, LLMError(
                error_type=ErrorType.NOT_CONFIGURED,
                message="LLM provider not configured"
            )
        
        try:
            self._client = self._create_client()
            return self._client, None
        except Exception as e:
            self._logger.warning(
                "Failed to create LLM client",
                extra={"error": str(e), "provider": settings["provider"]}
            )
            return None, _map_exception_to_error(e)
    
    def generate(
        self,
        prompt: str,
        response_model: Type[T],
        *,
        system_prompt: str | None = None,
        max_retries: int | None = None,
        timeout: float | None = None,
    ) -> LLMResponse[T]:
        """Generate a structured LLM response.
        
        Args:
            prompt: The user prompt to send to the LLM.
            response_model: A Pydantic BaseModel class defining the expected response schema.
            system_prompt: Optional system prompt (defaults to plugin setting).
            max_retries: Override default max_retries from settings.
            timeout: Override default timeout from settings.
        
        Returns:
            LLMResponse[T] containing either:
            - success=True, result=T (validated response)
            - success=False, error=LLMError (structured error)
        
        Notes:
            - Never raises exceptions to caller (all errors wrapped in LLMResponse)
            - Logs call metadata but NOT prompt/response content
            - Automatically retries on validation failures
        """
        start_time = time.time()
        retries = 0
        settings = self._get_settings()
        
        # Get effective settings with overrides
        effective_max_retries = max_retries if max_retries is not None else settings["max_retries"]
        effective_timeout = timeout if timeout is not None else settings["timeout_seconds"]
        
        # Ensure client is ready
        client, error = self._ensure_client()
        if error is not None:
            latency_ms = int((time.time() - start_time) * 1000)
            return LLMResponse.error_response(error=error, latency_ms=latency_ms, retries=0)
        
        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            # Make the LLM call with Instructor
            result = client.chat.completions.create(
                messages=messages,
                response_model=response_model,
                max_retries=effective_max_retries,
                timeout=effective_timeout,
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Log metadata (not content)
            self._logger.info(
                "LLM call succeeded",
                extra={
                    "provider": settings["provider"],
                    "model": settings["model"],
                    "latency_ms": latency_ms,
                    "retries": retries,
                    "response_model": response_model.__name__,
                }
            )
            
            return LLMResponse.success_response(
                result=result,
                latency_ms=latency_ms,
                retries=retries
            )
            
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error = _map_exception_to_error(e)
            
            # Log error metadata with validation error details for FR-008
            log_extra = {
                "provider": settings["provider"],
                "model": settings["model"],
                "latency_ms": latency_ms,
                "error_type": error.error_type.value,
                "response_model": response_model.__name__,
            }
            
            # Include validation error details for retry logging (FR-008)
            if error.error_type == ErrorType.VALIDATION_ERROR and error.details:
                log_extra["validation_errors"] = error.details.get("errors", "")
            
            self._logger.warning(
                "LLM call failed",
                extra=log_extra
            )
            
            return LLMResponse.error_response(
                error=error,
                latency_ms=latency_ms,
                retries=retries
            )
    
    def health_check(self) -> HealthStatus:
        """Test LLM provider connectivity.
        
        Returns:
            HealthStatus with:
            - status: "connected" | "unavailable" | "timeout" | "not_configured"
            - latency_ms: Response time in milliseconds (if connected)
            - provider: Configured provider name
            - model: Configured model name
            - error: Error message (if not connected)
        
        Notes:
            - Uses a minimal test prompt to verify full connectivity
            - Respects configured timeout
            - Does not count against rate limits on most providers
        """
        settings = self._get_settings()
        provider = settings["provider"] or "none"
        model = settings["model"] or "none"
        
        if not settings["provider"]:
            return HealthStatus(
                status="not_configured",
                provider=provider,
                model=model
            )
        
        start_time = time.time()
        
        # Ensure client is ready
        client, error = self._ensure_client()
        if error is not None:
            return HealthStatus(
                status="unavailable",
                provider=provider,
                model=model,
                error=error.message
            )
        
        try:
            # Minimal health check model
            class HealthCheckResponse(BaseModel):
                status: str = "ok"
            
            # Make minimal LLM call
            client.chat.completions.create(
                messages=[{"role": "user", "content": "Reply with exactly: ok"}],
                response_model=HealthCheckResponse,
                timeout=5.0,  # Short timeout for health check
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return HealthStatus(
                status="connected",
                latency_ms=latency_ms,
                provider=provider,
                model=model
            )
            
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            mapped_error = _map_exception_to_error(e)
            
            # Determine status based on error type
            if mapped_error.error_type == ErrorType.TIMEOUT:
                status = "timeout"
            else:
                status = "unavailable"
            
            return HealthStatus(
                status=status,
                provider=provider,
                model=model,
                error=mapped_error.message
            )


def create_llm_service(plugin: "AssistantPlugin") -> LLMService:
    """Create an LLM service instance for the plugin.
    
    This is the primary way to obtain an LLMService instance.
    The service maintains a reference to the plugin for settings access.
    
    Args:
        plugin: The AssistantPlugin instance.
    
    Returns:
        Configured LLMService instance.
    
    Example:
        >>> from indico_assistant.services.llm import create_llm_service
        >>> llm = create_llm_service(plugin)
    """
    return LLMService(plugin)
