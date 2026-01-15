"""Langfuse client wrapper with graceful degradation.

Feature: 005-langfuse-observability
Tasks: T010, T011, T012, T021, T022, T053

This module provides a LangfuseClient wrapper that:
- Validates credentials on initialization
- Returns no-op spans when Langfuse is unavailable
- Never fails user requests due to tracing errors
- Supports runtime privacy level configuration
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator, Optional

from indico_assistant.services.observability import get_observability_logger

if TYPE_CHECKING:
    from langfuse import Langfuse

logger = get_observability_logger("client")


class NoOpSpan:
    """No-operation span for graceful degradation.
    
    Task: T010
    
    Used when Langfuse is disabled or unavailable. All methods are no-ops
    that silently succeed, ensuring user requests never fail due to tracing.
    """

    def __init__(self, name: str = "noop") -> None:
        """Initialize no-op span.
        
        Args:
            name: Span name (ignored)
        """
        self._name = name

    def update(self, **kwargs: Any) -> "NoOpSpan":
        """No-op update method.
        
        Args:
            **kwargs: Ignored keyword arguments
            
        Returns:
            Self for method chaining
        """
        return self

    def end(self, **kwargs: Any) -> None:
        """No-op end method.
        
        Args:
            **kwargs: Ignored keyword arguments
        """
        pass

    def __enter__(self) -> "NoOpSpan":
        """Enter context manager."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager."""
        pass


class LangfuseClient:
    """Langfuse client wrapper with graceful degradation.
    
    Tasks: T011, T012, T021, T022, T053
    
    This wrapper ensures:
    - User requests never fail due to tracing errors (Constitution IV)
    - Credentials are validated at startup with clear error logging
    - No-op spans are returned when Langfuse is unavailable
    - Async batching via SDK defaults (FR-017, FR-018)
    - Runtime privacy level configuration (FR-004)
    
    Attributes:
        enabled: Whether Langfuse tracing is active
        privacy_level: Current privacy level ('metadata', 'masked', 'full')
    """

    def __init__(self, settings: dict) -> None:
        """Initialize Langfuse client with graceful degradation.
        
        Args:
            settings: Plugin settings dictionary containing:
                - langfuse_enabled: Whether to enable tracing
                - langfuse_host: Langfuse API host
                - langfuse_public_key: Public API key
                - langfuse_secret_key: Secret API key
                - langfuse_privacy_level: Privacy level setting
        """
        self._client: Optional["Langfuse"] = None
        self._enabled = settings.get("langfuse_enabled", False)
        self._privacy_level = settings.get("langfuse_privacy_level", "metadata")
        
        if not self._enabled:
            logger.info("Langfuse tracing disabled by configuration")
            return

        # Configure Langfuse via environment variables (SDK pattern)
        host = settings.get("langfuse_host", "https://cloud.langfuse.com")
        public_key = settings.get("langfuse_public_key")
        secret_key = settings.get("langfuse_secret_key")

        if not public_key or not secret_key:
            logger.error(
                "Langfuse credentials not configured. "
                "Set langfuse_public_key and langfuse_secret_key in plugin settings."
            )
            self._enabled = False
            return

        try:
            # Set environment variables for SDK (T021 - SDK handles async batching)
            os.environ["LANGFUSE_HOST"] = host
            os.environ["LANGFUSE_PUBLIC_KEY"] = public_key
            os.environ["LANGFUSE_SECRET_KEY"] = secret_key

            from langfuse import Langfuse
            self._client = Langfuse()

            # Validate credentials (T011)
            if not self._client.auth_check():
                logger.error(
                    "Langfuse credentials invalid. "
                    "Verify public_key and secret_key are correct."
                )
                self._enabled = False
                self._client = None
            else:
                logger.info(
                    f"Langfuse initialized successfully (host={host}, "
                    f"privacy_level={self._privacy_level})"
                )
        except ImportError:
            logger.warning(
                "Langfuse package not installed. Install with: pip install langfuse"
            )
            self._enabled = False
        except Exception as e:
            logger.warning(f"Langfuse initialization failed: {e}")
            self._enabled = False

    @property
    def enabled(self) -> bool:
        """Check if Langfuse tracing is enabled and working."""
        return self._enabled and self._client is not None

    @property
    def privacy_level(self) -> str:
        """Get current privacy level."""
        return self._privacy_level

    @privacy_level.setter
    def privacy_level(self, level: str) -> None:
        """Set privacy level at runtime (T053).
        
        Args:
            level: Privacy level ('metadata', 'masked', 'full')
            
        Raises:
            ValueError: If level is not valid
        """
        valid_levels = ("metadata", "masked", "full")
        if level not in valid_levels:
            raise ValueError(f"Invalid privacy level: {level}. Must be one of {valid_levels}")
        self._privacy_level = level
        logger.info(f"Privacy level changed to: {level}")

    @contextmanager
    def trace(
        self,
        name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs: Any
    ) -> Generator[Any, None, None]:
        """Create a trace span with graceful degradation.
        
        Args:
            name: Trace name
            user_id: Optional user identifier (will be hashed at metadata level)
            session_id: Optional session identifier for correlation
            **kwargs: Additional trace attributes
            
        Yields:
            Trace span or NoOpSpan if tracing unavailable
        """
        if not self.enabled:
            yield NoOpSpan(name)
            return

        try:
            with self._client.start_as_current_observation(
                as_type="span",
                name=name,
                user_id=user_id,
                session_id=session_id,
                **kwargs
            ) as span:
                yield span
        except Exception as e:
            logger.warning(f"Tracing error for '{name}': {e}")
            yield NoOpSpan(name)

    @contextmanager
    def generation(
        self,
        name: str,
        model: Optional[str] = None,
        **kwargs: Any
    ) -> Generator[Any, None, None]:
        """Create a generation span for LLM calls.
        
        Args:
            name: Generation name (e.g., 'llm-call')
            model: Model identifier
            **kwargs: Additional generation attributes
            
        Yields:
            Generation span or NoOpSpan if tracing unavailable
        """
        if not self.enabled:
            yield NoOpSpan(name)
            return

        try:
            with self._client.start_as_current_observation(
                as_type="generation",
                name=name,
                model=model,
                **kwargs
            ) as gen:
                yield gen
        except Exception as e:
            logger.warning(f"Generation tracing error for '{name}': {e}")
            yield NoOpSpan(name)

    @contextmanager
    def span(
        self,
        name: str,
        **kwargs: Any
    ) -> Generator[Any, None, None]:
        """Create a nested span for pipeline stages.
        
        Args:
            name: Span name (e.g., 'sql_generation')
            **kwargs: Additional span attributes
            
        Yields:
            Span or NoOpSpan if tracing unavailable
        """
        if not self.enabled:
            yield NoOpSpan(name)
            return

        try:
            with self._client.start_as_current_observation(
                as_type="span",
                name=name,
                **kwargs
            ) as s:
                yield s
        except Exception as e:
            logger.warning(f"Span tracing error for '{name}': {e}")
            yield NoOpSpan(name)

    def flush(self) -> None:
        """Flush pending traces to Langfuse (T022).
        
        Call this in request teardown for critical paths to ensure
        traces are sent before the request completes.
        """
        if not self.enabled:
            return

        try:
            self._client.flush()
        except Exception as e:
            logger.warning(f"Langfuse flush failed: {e}")

    def shutdown(self) -> None:
        """Shutdown the Langfuse client cleanly.
        
        Call this during application shutdown to ensure all pending
        traces are sent.
        """
        if not self.enabled:
            return

        try:
            self._client.shutdown()
            logger.info("Langfuse client shutdown complete")
        except Exception as e:
            logger.warning(f"Langfuse shutdown failed: {e}")


# Module-level client instance (lazy initialization)
_client_instance: Optional[LangfuseClient] = None


def get_langfuse_client(settings: dict) -> LangfuseClient:
    """Get or create a LangfuseClient instance (T012).
    
    This factory function provides a singleton-like pattern for the
    Langfuse client, but allows re-initialization with new settings.
    
    Args:
        settings: Plugin settings dictionary
        
    Returns:
        LangfuseClient instance
    """
    global _client_instance
    
    # Create new instance if none exists or settings changed
    if _client_instance is None:
        _client_instance = LangfuseClient(settings)
    
    return _client_instance


def reset_client() -> None:
    """Reset the global client instance.
    
    Useful for testing and when settings change.
    """
    global _client_instance
    if _client_instance is not None:
        _client_instance.shutdown()
    _client_instance = None
