"""Models package for indico_assistant.

Provides SQLAlchemy models for the Indico Assistant plugin.

Feature: 004-chat-api (T009)
Feature: 006-vector-search-rag (T006)
Feature: 019-chat-actions
Feature: 021-issue-reports
Feature: 023-github-connector
Feature: 024-assistant-analytics
"""

from indico_assistant.models.action_plan import ActionPlan
from indico_assistant.models.analytics import Turn, TurnStep, TurnText
from indico_assistant.models.audit import QueryAuditLog
from indico_assistant.models.connection import Connection
from indico_assistant.models.document import (
    DocumentSyncLog,
    ExtractedDocument,
    ExtractionStatus,
    SyncStatus as DocumentSyncStatus,
)
from indico_assistant.models.feedback import FeedbackEntry
from indico_assistant.models.message import ChatMessage
from indico_assistant.models.report import IssueReport
from indico_assistant.models.session import ChatSession

__all__ = [
    "ActionPlan",
    "QueryAuditLog",
    "Connection",
    "ChatSession",
    "ChatMessage",
    "FeedbackEntry",
    "IssueReport",
    # Analytics (spec 024)
    "Turn",
    "TurnStep",
    "TurnText",
    # Document models (Feature 006)
    "ExtractedDocument",
    "DocumentSyncLog",
    "ExtractionStatus",
    "DocumentSyncStatus",
]
