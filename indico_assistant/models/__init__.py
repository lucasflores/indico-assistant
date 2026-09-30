"""Models package for indico_assistant.

Provides SQLAlchemy models for the Indico Assistant plugin.

Feature: 004-chat-api (T009)
Feature: 005-langfuse-observability (T007)
Feature: 006-vector-search-rag (T006)
Feature: 019-chat-actions
Feature: 021-issue-reports
"""

from indico_assistant.models.action_plan import ActionPlan
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
from indico_assistant.models.report import IssueReport
from indico_assistant.models.session import ChatSession

__all__ = [
    "ActionPlan",
    "QueryAuditLog",
    "ChatSession",
    "ChatMessage",
    "FeedbackEntry",
    "IssueReport",
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
