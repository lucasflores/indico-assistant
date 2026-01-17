"""Controllers package for indico_assistant Chat API.

Provides request handlers (controllers) for all API endpoints.

Feature: 001-plugin-foundation (health)
Feature: 004-chat-api
Feature: 006-vector-search-rag (search endpoints)
"""

from indico_assistant.controllers.base import RHChatBase, RHAssistantBase
from indico_assistant.controllers.health import RHHealth
from indico_assistant.controllers.search import (
    RHVectorSearch,
    RHSearchStatus,
    RHSyncDocuments,
    RHSyncAllDocuments,
)

__all__ = [
    "RHChatBase",
    "RHAssistantBase",
    "RHHealth",
    # Search (Feature 006)
    "RHVectorSearch",
    "RHSearchStatus",
    "RHSyncDocuments",
    "RHSyncAllDocuments",
]
