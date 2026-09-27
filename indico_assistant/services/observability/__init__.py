"""Observability services package for Langfuse integration.

Feature: 005-langfuse-observability
Task: T009, T015

This package provides:
- LangfuseClient: Wrapper with graceful degradation (client.py)
- Tracer: Trace/span context managers (tracer.py)
- Privacy: PII redaction utilities (privacy.py)
- Metrics: Local metrics aggregation (metrics.py)
- Sync: Celery task for Langfuse → PostgreSQL sync (sync.py)

Usage:
    from indico_assistant.services.observability import get_langfuse_client
    
    client = get_langfuse_client(settings)
    with client.trace("chat-request") as trace:
        # ... traced operation
        pass
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from indico_assistant.services.observability.client import LangfuseClient


# Logging goes through Indico's configuration (a handler of our own duplicated every line)
logger = logging.getLogger(__name__)


def get_observability_logger(name: str) -> logging.Logger:
    """Get a child logger for observability components.
    
    Args:
        name: Component name (e.g., 'client', 'tracer', 'privacy')
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(f"{__name__}.{name}")


# Lazy imports to avoid circular dependencies
def get_langfuse_client(settings: dict) -> "LangfuseClient":
    """The per-process LangfuseClient (building one per call meant a network auth check per call)."""
    from indico_assistant.services.observability.client import get_langfuse_client as _get_client
    return _get_client(settings)


__all__ = [
    "get_langfuse_client",
    "get_observability_logger",
    "logger",
]
