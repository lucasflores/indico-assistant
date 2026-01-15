"""Observability models for Langfuse metrics storage.

Feature: 005-langfuse-observability
Tasks: T003, T004, T005, T006

These models store locally cached observability metrics synced from Langfuse.
They support the admin dashboard API and ensure metrics availability when
Langfuse is unreachable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from indico.core.db import db
from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

if TYPE_CHECKING:
    from indico_assistant.models.session import ChatSession


class ObservabilityErrorType(str, Enum):
    """Error type classification for observability tracking.
    
    Task: T003
    """
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    LLM_VALIDATION = "LLM_VALIDATION"
    LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
    SQL_SYNTAX_ERROR = "SQL_SYNTAX_ERROR"
    SQL_EXECUTION_ERROR = "SQL_EXECUTION_ERROR"
    SQL_TIMEOUT = "SQL_TIMEOUT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class SyncStatus(str, Enum):
    """Status values for metrics sync jobs."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PeriodType(str, Enum):
    """Aggregation period types for usage statistics."""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class UsageStats(db.Model):
    """Stores aggregated usage statistics for configurable time periods.
    
    Feature: 005-langfuse-observability
    Task: T004
    
    Attributes:
        id: Unique identifier (UUID)
        period_type: Aggregation period ('day', 'week', 'month')
        period_start: Start of the period (UTC)
        total_queries: Total queries in period
        successful_queries: Queries that completed without error
        avg_latency_ms: Average response latency
        p95_latency_ms: 95th percentile latency
        error_count: Total errors in period
        queries_by_intent: JSON breakdown by query intent
        total_input_tokens: Sum of input tokens
        total_output_tokens: Sum of output tokens
        last_synced_at: When this record was last updated from Langfuse
        created_at: Record creation timestamp
    """
    
    __tablename__ = 'observability_usage_stats'
    __table_args__ = (
        UniqueConstraint('period_type', 'period_start', name='uq_usage_stats_period'),
        CheckConstraint("period_type IN ('day', 'week', 'month')", name='ck_usage_stats_period_type'),
        {'schema': 'plugin_assistant'}
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    period_type = Column(String(20), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    total_queries = Column(Integer, nullable=False, default=0)
    successful_queries = Column(Integer, nullable=False, default=0)
    avg_latency_ms = Column(Float, nullable=True)
    p95_latency_ms = Column(Float, nullable=True)
    error_count = Column(Integer, nullable=False, default=0)
    queries_by_intent = Column(JSON, nullable=True)
    total_input_tokens = Column(Integer, nullable=False, default=0)
    total_output_tokens = Column(Integer, nullable=False, default=0)
    last_synced_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # Indexes defined via Index objects for complex indexes
    __table_args__ = (
        UniqueConstraint('period_type', 'period_start', name='uq_usage_stats_period'),
        CheckConstraint("period_type IN ('day', 'week', 'month')", name='ck_usage_stats_period_type'),
        {'schema': 'plugin_assistant'}
    )

    @property
    def error_rate(self) -> float:
        """Calculate error rate as error_count / total_queries."""
        if self.total_queries == 0:
            return 0.0
        return self.error_count / self.total_queries

    def __repr__(self) -> str:
        return (
            f"<UsageStats(id={self.id}, period_type={self.period_type}, "
            f"period_start={self.period_start}, total_queries={self.total_queries})>"
        )


class ErrorRecord(db.Model):
    """Stores recent errors for debugging (rolling 7-day window).
    
    Feature: 005-langfuse-observability
    Task: T005
    
    Attributes:
        id: Unique identifier (UUID)
        correlation_id: Request correlation ID for tracing
        timestamp: When error occurred (UTC)
        error_type: Error classification from ObservabilityErrorType
        error_message: Human-readable error description
        stack_trace: Full stack trace (only at "full" privacy level)
        user_id_hash: SHA-256 hash of user ID (for correlation, not PII)
        session_id: Associated chat session if available
        langfuse_trace_id: Link to Langfuse trace for detailed view
        created_at: Record creation timestamp
    """
    
    __tablename__ = 'observability_error_records'
    __table_args__ = {'schema': 'plugin_assistant'}

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    correlation_id = Column(String(64), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    error_type = Column(String(100), nullable=False, index=True)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    user_id_hash = Column(String(64), nullable=True)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey('plugin_assistant.chat_sessions.id', ondelete='SET NULL'),
        nullable=True
    )
    langfuse_trace_id = Column(String(64), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    session: Optional["ChatSession"] = relationship(
        'ChatSession',
        foreign_keys=[session_id],
        lazy='joined'
    )

    def __repr__(self) -> str:
        return (
            f"<ErrorRecord(id={self.id}, error_type={self.error_type}, "
            f"timestamp={self.timestamp})>"
        )


class MetricsSyncLog(db.Model):
    """Tracks synchronization jobs from Langfuse to local storage.
    
    Feature: 005-langfuse-observability
    Task: T006
    
    Attributes:
        id: Unique identifier (UUID)
        started_at: When sync job started
        completed_at: When sync job completed (NULL if running/failed)
        period_start: Start of period being synced
        period_end: End of period being synced
        traces_processed: Number of Langfuse traces processed
        stats_updated: Number of UsageStats records updated
        errors_recorded: Number of ErrorRecord records created
        status: Sync job status ('running', 'completed', 'failed')
        error_message: Error message if status=failed
    """
    
    __tablename__ = 'observability_sync_log'
    __table_args__ = (
        CheckConstraint("status IN ('running', 'completed', 'failed')", name='ck_sync_log_status'),
        {'schema': 'plugin_assistant'}
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    traces_processed = Column(Integer, nullable=False, default=0)
    stats_updated = Column(Integer, nullable=False, default=0)
    errors_recorded = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default=SyncStatus.RUNNING.value, index=True)
    error_message = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<MetricsSyncLog(id={self.id}, status={self.status}, "
            f"started_at={self.started_at})>"
        )

    def mark_completed(self, traces: int, stats: int, errors: int) -> None:
        """Mark the sync job as completed successfully.
        
        Args:
            traces: Number of traces processed
            stats: Number of stats records updated
            errors: Number of error records created
        """
        self.status = SyncStatus.COMPLETED.value
        self.completed_at = datetime.now(timezone.utc)
        self.traces_processed = traces
        self.stats_updated = stats
        self.errors_recorded = errors

    def mark_failed(self, error_message: str) -> None:
        """Mark the sync job as failed.
        
        Args:
            error_message: Description of the failure
        """
        self.status = SyncStatus.FAILED.value
        self.completed_at = datetime.now(timezone.utc)
        self.error_message = error_message
