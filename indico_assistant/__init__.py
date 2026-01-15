"""Indico Assistant Plugin - AI-powered assistant for Indico events.

This plugin provides natural language query capabilities for Indico events,
leveraging LLM providers to answer questions about event data.
"""

__version__ = "0.1.0"

from indico_assistant.version import check_indico_version

# Fail fast if Indico version is incompatible
check_indico_version()

from indico_assistant.plugin import AssistantPlugin

__all__ = ["AssistantPlugin", "__version__"]
