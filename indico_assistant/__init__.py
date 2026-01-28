"""Indico Assistant Plugin - AI-powered assistant for Indico events.

This plugin provides natural language query capabilities for Indico events,
leveraging LLM providers to answer questions about event data.
"""

__version__ = "0.1.0"

from indico_assistant.version import check_indico_version

# Fail fast if Indico version is incompatible
check_indico_version()

from indico_assistant.plugin import AssistantPlugin

# Import tasks to register them with Celery
# This ensures Celery workers can discover and execute these tasks
from indico_assistant.tasks import cleanup, indexing, sync  # noqa: F401

__all__ = ["AssistantPlugin", "__version__"]
