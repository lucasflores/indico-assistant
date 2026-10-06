"""LLM Service - Main service class for LLM interactions.

This module provides the LLMService class which handles all LLM
provider interactions using the Instructor library.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Type, TypeVar

from celery.exceptions import SoftTimeLimitExceeded
from pydantic import BaseModel

from indico_assistant.services.analytics import recorder

from indico_assistant.services.llm.errors import LLMError, ErrorType, _map_exception_to_error
from indico_assistant.services.llm.models import LLMResponse, HealthStatus

_CLIENT_SETTINGS = ("provider", "model", "base_url", "api_key", "ibis_mode")  # what the client is built from

# Completion records of the generate() call running in this thread/task. Instructor calls hooks in the
# calling thread, so concurrent calls on one shared client each see only their own completions.
# Holds (records, response model name, requested model).
_current_calls: contextvars.ContextVar[tuple | None] = contextvars.ContextVar("llm_current_calls", default=None)

# The open collect_calls() lists (outermost first): every record goes to all of them.
_request_calls: contextvars.ContextVar[tuple] = contextvars.ContextVar("llm_request_calls", default=())

CALL_LOG_MAX = 1000  # the shared call_log keeps only the most recent records


# The time (time.monotonic) by which model calls in this context must be done: a tool's, inside a turn (spec 025).
_until: contextvars.ContextVar[float | None] = contextvars.ContextVar("llm_until", default=None)


@contextlib.contextmanager
def until(deadline: float | None):
    """Model calls inside the block end by ``deadline`` (``time.monotonic``); one that would start after it fails as
    a timeout. A tool the turn started late (NL2SQL, the guide, the planner) can't keep the turn's own answer from
    being written before the worker's time limit (review of #22)."""
    token = _until.set(deadline)
    try:
        yield
    finally:
        _until.reset(token)


@contextlib.contextmanager
def collect_calls():
    """Collect the completion records of every LLM call made inside the block, in this thread/task.

    Thread-safe per-request cost accounting (one chat question makes several generate() calls):
    ``with collect_calls() as calls: pipeline work...`` then ``calls`` holds them all.
    Blocks nest: a caller can collect around a pipeline that collects for itself, and both see the
    records (the outer one even if the inner code raises).
    """
    calls: list[dict[str, Any]] = []
    token = _request_calls.set(_request_calls.get() + (calls,))
    try:
        yield calls
    finally:
        _request_calls.reset(token)


if TYPE_CHECKING:
    from indico_assistant.plugin import AssistantPlugin


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _fill_step(step: Any, calls: list[dict[str, Any]]) -> None:
    """The analytics step of one generate() call, from its completion records (each attempt was billed)."""
    step.prompt_tokens = _known_sum(c.get("prompt_tokens") for c in calls)
    step.completion_tokens = _known_sum(c.get("completion_tokens") for c in calls)
    costs = [amount for c in calls if (amount := recorder.cost(c.get("cost_usd"))) is not None]
    step.cost_usd = sum(costs) if costs else None  # unknown, never estimated (spec 024 FR-005)
    step.attempts = len(calls) or None
    if calls:
        last = calls[-1]
        step.served_model, step.ibis_chosen, step.ibis_dial = (last.get("served_model"), last.get("ibis_chosen"),
                                                               last.get("ibis_dial"))


def _soft_limit_in(error: BaseException) -> SoftTimeLimitExceeded | None:
    """The worker's SoftTimeLimitExceeded somewhere in an exception's causes, if any."""
    seen = set()
    while error is not None and id(error) not in seen:
        if isinstance(error, SoftTimeLimitExceeded):
            return error
        seen.add(id(error))
        error = error.__cause__ or error.__context__
    return None


def _known_sum(values: Any) -> int | None:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def completion_record(stage: str, requested_model: str | None, completion: Any) -> dict[str, Any]:
    """Summarise one raw chat completion (one HTTP call, including retries).

    ``served_model`` is the model that actually answered; for the ibis router
    ``requested_model`` is ``ibis/<dial>`` and the pick comes back in the
    ``ibis`` extension. ``cost_usd`` is the provider's own bill: ibis's exact
    decimal string, or OpenRouter's ``usage.cost``; other providers leave it None,
    and nothing estimates it (spec 024 FR-005).
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
        "cost_usd": usage_extra.get("cost_usd") if usage_extra.get("cost_usd") is not None else usage_extra.get("cost"),
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
        self._client_lock = threading.Lock()
        self._client_key: tuple | None = None
        self._logger = logger
        # Recent completion_record()s across all calls in this process, for debugging. Bounded (the
        # service lives as long as the process) and mixed across threads: per-call records are on each
        # LLMResponse (.calls), per-request ones come from collect_calls() (e.g. PipelineResult.llm_calls).
        self.call_log: deque[dict[str, Any]] = deque(maxlen=CALL_LOG_MAX)
    
    def _record_completion(self, completion: Any) -> None:
        current = _current_calls.get()
        if current is None:  # a completion made outside generate()/health_check()
            return
        calls, stage, model = current
        self._store(calls, completion_record(stage, model, completion))

    def _record_failed_attempt(self, error: Exception, **_: Any) -> None:
        """An attempt that failed leaves no completion, but the router may still have run and billed it: record it
        with unknown cost. That's a timeout or a dropped connection, or (spec 024) a rate limit or server error the
        SDK gave up on. Validation failures are already recorded through their completion."""
        import openai

        current = _current_calls.get()
        if current is None or not isinstance(error, openai.APIError):  # connection, timeout, status errors
            return
        calls, stage, model = current
        self._store(calls, {"stage": stage, "requested_model": model, "served_model": None,
                            "prompt_tokens": None, "completion_tokens": None, "cost_usd": None,
                            "error": type(error).__name__})

    def _store(self, calls: list[dict[str, Any]], record: dict[str, Any]) -> None:
        calls.append(record)
        self.call_log.append(record)
        for request in _request_calls.get():
            request.append(record)

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
            # Only the ibis client reads it, so only an ibis client is rebuilt when it changes.
            "ibis_mode": settings.get("llm_ibis_mode") if settings.get("llm_provider") == "ibis" else None,
            "timeout_seconds": settings.get("timeout_seconds", 30),
            "max_tokens": settings.get("max_tokens", 2048),
            "max_retries": settings.get("max_retries", 2),
        }
    
    def _create_client(self, settings: dict[str, Any]):
        """Create an Instructor client based on current settings.
        
        Returns:
            Configured Instructor client.
            
        Raises:
            This method should not raise - errors should be caught
            and converted to LLMError in the calling method.
        """
        from indico_assistant.services.llm.factory import create_instructor_client
        
        return create_instructor_client(
            provider=settings["provider"],
            model=settings["model"],
            base_url=settings["base_url"],
            api_key=settings["api_key"],
            ibis_mode=settings["ibis_mode"],
        )
    
    def _ensure_client(self, settings: dict[str, Any] | None = None) -> tuple[Any | None, LLMError | None]:
        """The client for the current settings, (re)built when provider, model, URL or key change.

        Returns:
            Tuple of (client, error). If client is None, error is set.
        """
        settings = settings or self._get_settings()
        key = tuple(settings[k] for k in _CLIENT_SETTINGS)
        if self._client is not None and self._client_key == key:
            return self._client, None
        with self._client_lock:  # first calls from several threads build one client, not one each
            if self._client is not None and self._client_key == key:
                return self._client, None
            return self._create_client_locked(settings, key)

    def _create_client_locked(self, settings: dict[str, Any], key: tuple) -> tuple[Any | None, LLMError | None]:
        if not settings["provider"]:
            return None, LLMError(
                error_type=ErrorType.NOT_CONFIGURED,
                message="LLM provider not configured"
            )
        
        try:
            client = self._create_client(settings)
            # Hooks for the client's lifetime; they record into the calling generate()'s own list.
            # Registered before the client is cached: a client without them would never record costs.
            client.on("completion:response", self._record_completion)
            client.on("completion:error", self._record_failed_attempt)
            self._client, self._client_key = client, key
            return client, None
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
        messages: list[dict[str, str]] | None = None,
        model: str | None = None,
    ) -> LLMResponse[T]:
        """Generate a structured LLM response.
        
        Args:
            prompt: The user prompt to send to the LLM.
            response_model: A Pydantic BaseModel class defining the expected response schema.
            system_prompt: Optional system prompt (defaults to plugin setting).
            max_retries: Override default max_retries from settings.
            timeout: Override default timeout from settings.
            messages: Earlier conversation turns ({"role": "user"|"assistant", "content": ...}), sent between
                the system prompt and ``prompt`` (the chat-action planner passes the chat this way).
            model: A model for this call instead of the setting's (spec 025: a turn pinned to ibis's first pick).
        
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
        
        # The task's soft time limit (spec 024): the SDK may have swallowed the worker's own signal in a retry, so
        # no call starts past it, and none may run beyond it.
        left = recorder.time_left()
        if left is not None:
            if left <= 0:
                raise SoftTimeLimitExceeded()
            effective_timeout = min(effective_timeout, left)
        if (deadline := _until.get()) is not None:  # (a tool's call, inside a turn)
            left = deadline - time.monotonic()
            if left <= 0:
                error = LLMError(error_type=ErrorType.TIMEOUT, message="The turn has no time left for this call")
                return LLMResponse.error_response(error=error, latency_ms=0, retries=0)
            effective_timeout = min(effective_timeout, left)

        # Ensure client is ready
        client, error = self._ensure_client(settings)
        if error is not None:
            latency_ms = int((time.time() - start_time) * 1000)
            return LLMResponse.error_response(error=error, latency_ms=latency_ms, retries=0)
        
        # Build messages
        history = [{"role": m["role"], "content": m["content"]} for m in messages or ()
                   if m.get("role") in ("user", "assistant")]
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        
        # Every raw completion is recorded, including instructor's validation retries and attempts that
        # end in failure (each one is billed), by the client's one hook (_record_completion) into this
        # call's own list.
        calls: list[dict[str, Any]] = []
        requested = model or settings["model"]
        context_token = _current_calls.set((calls, response_model.__name__, requested))
        # one analytics step per call (spec 024), with its text: the whole conversation sent, and what came back
        with recorder.step("llm", response_model.__name__) as step:
            step.requested_model = requested
            recorder.text(step, "prompt", messages)
            try:
                result = client.chat.completions.create(
                    messages=messages,
                    model=requested,
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
                        "retries": max(len(calls) - 1, 0),
                        "response_model": response_model.__name__,
                        "served_model": calls[-1]["served_model"] if calls else None,
                    }
                )

                recorder.text(step, "response", result.model_dump_json() if hasattr(result, "model_dump_json")
                              else str(result))
                return LLMResponse.success_response(
                    result=result,
                    latency_ms=latency_ms,
                    retries=max(len(calls) - 1, 0),  # every attempt after the first leaves a record
                    calls=calls,
                )

            except SoftTimeLimitExceeded:  # the worker's time limit, not a model error: the task reports it (audit #1)
                raise
            except Exception as e:
                if limit := _soft_limit_in(e):  # (the SDK wraps it as a connection error)
                    raise limit from e
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
                step.ok, step.error_code = False, error.error_type.value  # returned, not raised (FR-003)
                recorder.text(step, "response", error.message)

                return LLMResponse.error_response(
                    error=error,
                    latency_ms=latency_ms,
                    retries=max(len(calls) - 1, 0),  # every attempt after the first leaves a record
                    calls=calls,
                )
            finally:
                _fill_step(step, calls)
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
        client, error = self._ensure_client(settings)
        if error is not None:
            return HealthStatus(
                status="unavailable",
                provider=provider,
                model=model,
                error=error.message
            )
        
        # The health check is a billed completion too: recorded in call_log under its own stage
        context_token = _current_calls.set(([], "health_check", settings["model"]))
        try:
            # Minimal health check model
            class HealthCheckResponse(BaseModel):
                status: str = "ok"
            
            # Make minimal LLM call
            client.chat.completions.create(
                messages=[{"role": "user", "content": "Reply with exactly: ok"}],
                model=settings["model"],
                response_model=HealthCheckResponse,
                timeout=settings["timeout_seconds"],  # a routed call can take longer than a fixed 5 s
                # Never an uncapped completion for a probe, but room for one: a reasoning model spends
                # tokens before it answers, and at 16 a healthy gateway read as unavailable (measured
                # 2026-09-29 on gpt-oss-120b and GPT-5-mini in both modes, and ibis/Balanced in tools).
                # 256 still missed once on GPT-5-mini, whose reasoning length varies call to call.
                max_tokens=512,
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
        finally:
            _current_calls.reset(context_token)


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
