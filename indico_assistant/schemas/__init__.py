"""Pydantic schemas package for indico_assistant Chat API.

Provides request/response validation schemas for all API endpoints.

Feature: 004-chat-api
Feature: 005-langfuse-observability (admin schemas)
Feature: 006-vector-search-rag (search schemas)
"""

from indico_assistant.schemas.admin import (
    ErrorListResponse,
    ErrorRecordItem,
    HealthResponse,
    LangfuseStatus,
    PaginationInfo,
    PeriodInfo,
    SyncStatus,
    UsageStatsData,
    UsageStatsResponse,
)
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
from indico_assistant.schemas.search import (
    SearchRequestSchema,
    SearchResponseSchema,
    SearchResultSchema,
    SearchStatusSchema,
    SyncRequestSchema,
    SyncResponseSchema,
    search_request_schema,
    search_response_schema,
    search_result_schema,
    search_status_schema,
    sync_request_schema,
    sync_response_schema,
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
    # Admin (Feature 005)
    "UsageStatsResponse",
    "UsageStatsData",
    "PeriodInfo",
    "ErrorListResponse",
    "ErrorRecordItem",
    "PaginationInfo",
    "HealthResponse",
    "LangfuseStatus",
    "SyncStatus",
    # Search (Feature 006)
    "SearchRequestSchema",
    "SearchResponseSchema",
    "SearchResultSchema",
    "SearchStatusSchema",
    "SyncRequestSchema",
    "SyncResponseSchema",
    "search_request_schema",
    "search_response_schema",
    "search_result_schema",
    "search_status_schema",
    "sync_request_schema",
    "sync_response_schema",
]
