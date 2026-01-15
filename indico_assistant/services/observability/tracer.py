"""Trace and span context managers for observability.

Feature: 005-langfuse-observability
Tasks: T016, T017, T018, T019, T020, T021, T024, T030, T050, T051

This module provides context managers for:
- Creating root traces for user requests
- Creating generation spans for LLM calls
- Creating nested spans for pipeline stages
- Privacy level handling (metadata/masked/full)
- Correlation ID generation and propagation
"""

from __future__ import annotations

import hashlib
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Generator, Optional

from indico_assistant.services.observability import get_observability_logger
from indico_assistant.services.observability.privacy import mask_pii

if TYPE_CHECKING:
    from indico_assistant.services.observability.client import LangfuseClient

logger = get_observability_logger("tracer")


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for request tracing (T020).
    
    Returns:
        Hex string correlation ID (32 characters)
    """
    return uuid.uuid4().hex


def hash_user_id(user_id: int) -> str:
    """Hash user ID for privacy-safe correlation (T019).
    
    At metadata level, we don't capture actual user IDs but need
    correlation capability. SHA-256 hash provides this safely.
    
    Args:
        user_id: Indico user ID
        
    Returns:
        SHA-256 hash of user ID (64 hex characters)
    """
    return hashlib.sha256(str(user_id).encode()).hexdigest()


class Tracer:
    """High-level tracing interface with privacy controls.
    
    Tasks: T016, T017, T018, T019, T020, T024, T030, T050, T051
    
    Provides context managers for creating traces and spans with
    automatic privacy filtering based on configured level.
    
    Privacy levels:
    - metadata: Only timing, status, and hashed identifiers captured
    - masked: Content captured with PII redacted
    - full: Complete content captured
    
    Attributes:
        client: Underlying LangfuseClient instance
    """

    def __init__(self, client: "LangfuseClient") -> None:
        """Initialize tracer with Langfuse client.
        
        Args:
            client: LangfuseClient instance for actual tracing
        """
        self._client = client
        self._correlation_id: Optional[str] = None

    @property
    def correlation_id(self) -> Optional[str]:
        """Get current correlation ID."""
        return self._correlation_id

    @property
    def privacy_level(self) -> str:
        """Get current privacy level from client."""
        return self._client.privacy_level

    def _apply_privacy(
        self,
        content: Optional[str],
        force_level: Optional[str] = None
    ) -> Optional[str]:
        """Apply privacy filtering to content (T050, T051).
        
        Args:
            content: Text content to filter
            force_level: Override privacy level (for testing)
            
        Returns:
            Filtered content based on privacy level, or None
        """
        level = force_level or self.privacy_level
        
        # T051: metadata level captures NO content
        if level == "metadata":
            return None
        
        # T050: masked level applies PII redaction
        if level == "masked":
            return mask_pii(content)
        
        # full level: return unchanged
        return content

    @contextmanager
    def trace(
        self,
        name: str,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        event_id: Optional[int] = None,
        **kwargs: Any
    ) -> Generator[Any, None, None]:
        """Create a root trace for a user request (T016).
        
        This is the top-level trace that contains all nested spans
        for a single user interaction.
        
        Args:
            name: Trace name (e.g., 'chat-request')
            user_id: Indico user ID (will be hashed at metadata level)
            session_id: Chat session UUID for correlation
            event_id: Indico event ID for context
            **kwargs: Additional trace attributes
            
        Yields:
            Trace span with update() method
        """
        # Store tracer in Flask g context for request teardown (T023)
        try:
            from flask import g
            g._observability_tracer = self
        except (ImportError, RuntimeError):
            # Not in Flask context - skip
            pass
        
        # Generate correlation ID for this request (T020)
        self._correlation_id = generate_correlation_id()
        
        # Hash user ID for privacy (T019)
        user_id_for_trace = None
        if user_id is not None:
            if self.privacy_level == "full":
                user_id_for_trace = str(user_id)
            else:
                user_id_for_trace = hash_user_id(user_id)

        # Convert session_id to string if UUID
        session_str = str(session_id) if session_id else None

        metadata = {
            "correlation_id": self._correlation_id,
            "privacy_level": self.privacy_level,
            **kwargs.get("metadata", {})
        }
        if event_id is not None:
            metadata["event_id"] = event_id

        try:
            with self._client.trace(
                name=name,
                user_id=user_id_for_trace,
                session_id=session_str,
                metadata=metadata,
                **{k: v for k, v in kwargs.items() if k != "metadata"}
            ) as span:
                yield TracerSpan(span, self)
        finally:
            self._correlation_id = None

    @contextmanager
    def generation(
        self,
        name: str,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs: Any
    ) -> Generator["TracerGeneration", None, None]:
        """Create a generation span for LLM calls (T017).
        
        This captures LLM-specific metrics like model, tokens,
        and optionally prompt/response content based on privacy level.
        
        Args:
            name: Generation name (e.g., 'llm-call', 'sql-generation')
            model: Model identifier
            prompt: Input prompt (filtered by privacy level)
            **kwargs: Additional generation attributes
            
        Yields:
            TracerGeneration with update() method for setting response
        """
        # Apply privacy to prompt (T018)
        filtered_prompt = self._apply_privacy(prompt)

        with self._client.generation(
            name=name,
            model=model,
            **kwargs
        ) as gen:
            gen_wrapper = TracerGeneration(gen, self, filtered_prompt)
            yield gen_wrapper

    @contextmanager
    def span(
        self,
        name: str,
        **kwargs: Any
    ) -> Generator["TracerSpan", None, None]:
        """Create a nested span for pipeline stages (T024).
        
        Used for tracking individual stages of the NL2SQL pipeline:
        - query_classification
        - sql_generation
        - sql_execution
        - sql_correction
        - response_summarization
        
        Args:
            name: Span name
            **kwargs: Additional span attributes
            
        Yields:
            TracerSpan with update() and error() methods
        """
        with self._client.span(name=name, **kwargs) as s:
            yield TracerSpan(s, self)

    def flush(self) -> None:
        """Flush pending traces to Langfuse."""
        self._client.flush()


class TracerSpan:
    """Wrapper for trace/span with privacy-aware updates.
    
    Task: T030 - Error status capture
    """

    def __init__(self, span: Any, tracer: Tracer) -> None:
        """Initialize span wrapper.
        
        Args:
            span: Underlying Langfuse span
            tracer: Parent tracer for privacy settings
        """
        self._span = span
        self._tracer = tracer
        self._start_time = datetime.now(timezone.utc)

    def update(
        self,
        output: Optional[str] = None,
        status: Optional[str] = None,
        **kwargs: Any
    ) -> "TracerSpan":
        """Update span with output and status.
        
        Args:
            output: Output content (filtered by privacy level)
            status: Status string (e.g., 'success', 'error')
            **kwargs: Additional attributes
            
        Returns:
            Self for method chaining
        """
        updates = {}
        
        if output is not None:
            updates["output"] = self._tracer._apply_privacy(output)
        
        if status is not None:
            updates["status_message"] = status
            
        updates.update(kwargs)
        
        self._span.update(**updates)
        return self

    def error(
        self,
        error: Exception,
        include_trace: bool = False
    ) -> "TracerSpan":
        """Record error on span (T030).
        
        Args:
            error: Exception that occurred
            include_trace: Include stack trace (only at 'full' privacy level)
            
        Returns:
            Self for method chaining
        """
        import traceback
        
        error_details = {
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        
        # Only include stack trace at full privacy level
        if include_trace and self._tracer.privacy_level == "full":
            error_details["stack_trace"] = traceback.format_exc()
        
        self._span.update(
            status_message="error",
            level="ERROR",
            metadata=error_details
        )
        return self

    def __enter__(self) -> "TracerSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class TracerGeneration(TracerSpan):
    """Wrapper for generation span with LLM-specific methods.
    
    Tasks: T017, T018
    """

    def __init__(
        self,
        generation: Any,
        tracer: Tracer,
        filtered_prompt: Optional[str]
    ) -> None:
        """Initialize generation wrapper.
        
        Args:
            generation: Underlying Langfuse generation
            tracer: Parent tracer for privacy settings
            filtered_prompt: Privacy-filtered input prompt
        """
        super().__init__(generation, tracer)
        self._filtered_prompt = filtered_prompt
        
        # Set input if available
        if filtered_prompt is not None:
            self._span.update(input={"prompt": filtered_prompt})

    def complete(
        self,
        response: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        latency_ms: Optional[float] = None,
        **kwargs: Any
    ) -> "TracerGeneration":
        """Mark generation complete with response and usage.
        
        Args:
            response: LLM response (filtered by privacy level)
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            latency_ms: Response latency in milliseconds
            **kwargs: Additional attributes
            
        Returns:
            Self for method chaining
        """
        updates: dict[str, Any] = {}
        
        # Filter response content (T018)
        if response is not None:
            filtered_response = self._tracer._apply_privacy(response)
            if filtered_response is not None:
                updates["output"] = filtered_response
        
        # Token usage is always captured
        usage = {}
        if input_tokens is not None:
            usage["input"] = input_tokens
        if output_tokens is not None:
            usage["output"] = output_tokens
        if usage:
            updates["usage"] = usage
        
        # Latency metadata
        if latency_ms is not None:
            updates["metadata"] = {
                **(updates.get("metadata") or {}),
                "latency_ms": latency_ms
            }
        
        updates.update(kwargs)
        
        self._span.update(**updates)
        return self


# Module-level tracer factory
def create_tracer(client: "LangfuseClient") -> Tracer:
    """Create a Tracer instance from a LangfuseClient.
    
    Args:
        client: LangfuseClient instance
        
    Returns:
        Configured Tracer instance
    """
    return Tracer(client)


__all__ = [
    "Tracer",
    "TracerSpan",
    "TracerGeneration",
    "create_tracer",
    "generate_correlation_id",
    "hash_user_id",
]
