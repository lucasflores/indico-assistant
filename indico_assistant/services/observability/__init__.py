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


# Configure structured logging for observability module (T015)
logger = logging.getLogger(__name__)

# Set up structured logging format
_handler = logging.StreamHandler()
_handler.setFormatter(
    logging.Formatter(
        fmt='{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
            '"module": "%(name)s", "message": "%(message)s"}',
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    )
)
logger.addHandler(_handler)
logger.setLevel(logging.INFO)


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
    """Factory function to create a LangfuseClient instance.
    
    Args:
        settings: Plugin settings dictionary containing Langfuse configuration
        
    Returns:
        LangfuseClient instance (with graceful degradation if unavailable)
    """
    from indico_assistant.services.observability.client import LangfuseClient
    return LangfuseClient(settings)


__all__ = [
    "get_langfuse_client",
    "get_observability_logger",
    "logger",
]
