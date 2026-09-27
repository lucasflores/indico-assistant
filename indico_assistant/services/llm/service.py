"""LLM Service - Main service class for LLM interactions.

This module provides the LLMService class which handles all LLM
provider interactions using the Instructor library.

Feature: 005-langfuse-observability (T019) - Added tracing instrumentation
"""

from __future__ import annotations

import contextvars
import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Optional, Type, TypeVar

from pydantic import BaseModel

from indico_assistant.services.llm.errors import LLMError, ErrorType, _map_exception_to_error
from indico_assistant.services.llm.models import LLMResponse, HealthStatus

# Completion records of the generate() call running in this thread/task. Instructor calls hooks in the
# calling thread, so concurrent calls on one shared client each see only their own completions.
# Holds (records, response model name, requested model).
_current_calls: contextvars.ContextVar[tuple | None] = contextvars.ContextVar("llm_current_calls", default=None)

CALL_LOG_MAX = 1000  # the shared call_log keeps only the most recent records

if TYPE_CHECKING:
    from indico_assistant.plugin import AssistantPlugin
    from indico_assistant.services.observability.tracer import Tracer


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def completion_record(stage: str, requested_model: str | None, completion: Any) -> dict[str, Any]:
    """Summarise one raw chat completion (one HTTP call, including retries).

    ``served_model`` is the model that actually answered; for the ibis router
    ``requested_model`` is ``ibis/<dial>`` and the pick comes back in the
    ``ibis`` extension. ``cost_usd`` is ibis's exact decimal string (the
    provider's bill); other providers leave it None.
    """
    usage = getattr(completion, "usage", None)
    usage_extra = getattr(usage, "model_extra", None) or {}
    ibis = (getattr(completion, "model_extra", None) or {}).get("ibis") or {}
    return {
        "stage": stage,
        "requested_model": requested_model,
        "served_model": getattr(completion, "model", None),
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "cost_usd": usage_extra.get("cost_usd"),
        "ibis_chosen": ibis.get("chosen"),
        "ibis_dial": ibis.get("dial"),
        "ibis_request_id": ibis.get("request_id"),
    }


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
        self._tracer: Optional["Tracer"] = None
        # Recent completion_record()s across calls, for single-threaded callers such as the eval
        # harness (clear, run, read). Bounded: the service lives as long as the process. Per-call
        # records are on each LLMResponse (.calls), which is what concurrent callers should use.
        self.call_log: deque[dict[str, Any]] = deque(maxlen=CALL_LOG_MAX)
    
    def _record_completion(self, completion: Any) -> None:
        current = _current_calls.get()
        if current is None:  # a completion outside generate() (e.g. health_check)
            return
        calls, stage, model = current
        record = completion_record(stage, model, completion)
        calls.append(record)
        self.call_log.append(record)

    def set_tracer(self, tracer: "Tracer") -> None:
        """Set tracer for observability instrumentation (T019).
        
        Args:
            tracer: Tracer instance for LLM call tracing
        """
        self._tracer = tracer
    
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
            # One hook for the client's lifetime; it records into the calling generate()'s own list.
            self._client.on("completion:response", self._record_completion)
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
            - Traces LLM calls if tracer is configured (Feature 005)
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
        
        # Prepare tracing context (T019)
        tracer = self._tracer
        generation_name = f"llm-{response_model.__name__}"

        # Every raw completion is recorded, including instructor's validation retries and attempts that
        # end in failure (each one is billed), by the client's one hook (_record_completion) into this
        # call's own list.
        calls: list[dict[str, Any]] = []
        context_token = _current_calls.set((calls, response_model.__name__, settings["model"]))
        try:
            # Make the LLM call with Instructor, optionally traced
            if tracer is not None:
                with tracer.generation(
                    name=generation_name,
                    model=settings["model"],
                    prompt=prompt,
                ) as gen:
                    result = client.chat.completions.create(
                        messages=messages,
                        model=settings["model"],
                        response_model=response_model,
                        max_retries=effective_max_retries,
                        timeout=effective_timeout,
                        max_tokens=settings["max_tokens"],
                    )
                    
                    latency_ms = int((time.time() - start_time) * 1000)
                    
                    # Complete the generation span with response details
                    response_str = result.model_dump_json() if hasattr(result, 'model_dump_json') else str(result)
                    gen.complete(
                        response=response_str,
                        latency_ms=latency_ms,
                    )
            else:
                # No tracing - original behavior
                result = client.chat.completions.create(
                    messages=messages,
                    model=settings["model"],
                    response_model=response_model,
                    max_retries=effective_max_retries,
                    timeout=effective_timeout,
                    max_tokens=settings["max_tokens"],
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
                    "served_model": calls[-1]["served_model"] if calls else None,
                }
            )

            return LLMResponse.success_response(
                result=result,
                latency_ms=latency_ms,
                retries=retries,
                calls=calls,
            )
            
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error = _map_exception_to_error(e)
            
            # Record error in trace if available (T019)
            if tracer is not None:
                try:
                    with tracer.generation(
                        name=generation_name,
                        model=settings["model"],
                        prompt=prompt,
                    ) as gen:
                        gen.error(e, include_trace=True)
                except Exception:
                    pass  # Tracing errors must not affect main flow
            
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
                retries=retries,
                calls=calls,
            )
        finally:
            _current_calls.reset(context_token)

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
                model=settings["model"],
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
