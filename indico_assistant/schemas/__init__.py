"""Pydantic schemas package for indico_assistant Chat API.

Provides request/response validation schemas for all API endpoints.

Feature: 004-chat-api
"""

from indico_assistant.schemas.chat import ChatRequest, ChatResponse
from indico_assistant.schemas.errors import (
    ErrorCode,
    ErrorResponse,
    create_error_response,
)
from indico_assistant.schemas.feedback import FeedbackRequest, FeedbackResponse
from indico_assistant.schemas.session import (
    MessageItem,
    SessionDetailResponse,
    SessionListItem,
    SessionListQueryParams,
    SessionListResponse,
)

__all__ = [
    # Chat
    "ChatRequest",
    "ChatResponse",
    # Session
    "SessionListItem",
    "SessionListResponse",
    "MessageItem",
    "SessionDetailResponse",
    "SessionListQueryParams",
    # Feedback
    "FeedbackRequest",
    "FeedbackResponse",
    # Errors
    "ErrorResponse",
    "ErrorCode",
    "create_error_response",
]
