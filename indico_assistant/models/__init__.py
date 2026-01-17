"""Models package for indico_assistant.

Provides SQLAlchemy models for the Indico Assistant plugin.

Feature: 004-chat-api (T009)
Feature: 005-langfuse-observability (T007)
Feature: 006-vector-search-rag (T006)
"""

from indico_assistant.models.audit import QueryAuditLog
from indico_assistant.models.document import (
    DocumentSyncLog,
    ExtractedDocument,
    ExtractionStatus,
    SyncStatus as DocumentSyncStatus,
)
from indico_assistant.models.feedback import FeedbackEntry
from indico_assistant.models.message import ChatMessage
from indico_assistant.models.observability import (
    ErrorRecord,
    MetricsSyncLog,
    ObservabilityErrorType,
    PeriodType,
    SyncStatus,
    UsageStats,
)
from indico_assistant.models.session import ChatSession

__all__ = [
    "QueryAuditLog",
    "ChatSession",
    "ChatMessage",
    "FeedbackEntry",
    # Observability models (Feature 005)
    "UsageStats",
    "ErrorRecord",
    "MetricsSyncLog",
    "ObservabilityErrorType",
    "PeriodType",
    "SyncStatus",
    # Document models (Feature 006)
    "ExtractedDocument",
    "DocumentSyncLog",
    "ExtractionStatus",
    "DocumentSyncStatus",
]
