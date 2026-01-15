"""Chat service package for indico_assistant.

Provides services for chat operations including rate limiting,
session management, context building, and orchestration.

Feature: 004-chat-api
"""

from indico_assistant.services.chat.context_builder import (
    ContextBuilder,
    get_context_builder,
)
from indico_assistant.services.chat.rate_limiter import (
    RateLimiter,
    RateLimitResult,
    get_rate_limiter,
)
from indico_assistant.services.chat.service import (
    ChatResult,
    ChatService,
    ChatServiceError,
    EventAccessDeniedError,
    QueryProcessingError,
    SessionAccessDeniedError,
    SessionNotFoundError,
    get_chat_service,
)
from indico_assistant.services.chat.session_manager import (
    SessionManager,
    get_session_manager,
)

__all__ = [
    # Context builder
    "ContextBuilder",
    "get_context_builder",
    # Rate limiter
    "RateLimiter",
    "RateLimitResult",
    "get_rate_limiter",
    # Chat service
    "ChatResult",
    "ChatService",
    "ChatServiceError",
    "EventAccessDeniedError",
    "QueryProcessingError",
    "SessionAccessDeniedError",
    "SessionNotFoundError",
    "get_chat_service",
    # Session manager
    "SessionManager",
    "get_session_manager",
]
