"""Indico Assistant services package.

This package contains service classes that encapsulate business logic
for the Indico Assistant plugin.
"""

from indico_assistant.services.llm import LLMService, create_llm_service

__all__ = ["LLMService", "create_llm_service"]
