"""Controllers package for indico_assistant Chat API.

Provides request handlers (controllers) for all API endpoints.

Feature: 001-plugin-foundation (health)
Feature: 004-chat-api
"""

from indico_assistant.controllers.base import RHChatBase, RHAssistantBase
from indico_assistant.controllers.health import RHHealth

__all__ = [
    "RHChatBase",
    "RHAssistantBase",
    "RHHealth",
]
