"""Local metrics cache services for admin dashboard.

Feature: 005-langfuse-observability
Tasks: T032, T033, T052

This module provides services for:
- Querying usage statistics from local PostgreSQL cache
- Storing and querying error records
- Supporting admin dashboard API endpoints
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from indico_assistant.models.observability import (
    ErrorRecord,
    ObservabilityErrorType,
    PeriodType,
    UsageStats,
)
from indico_assistant.services.observability import get_observability_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_observability_logger("metrics")


class MetricsService:
    """Service for querying usage statistics from local cache.
    
    Task: T032
    
    Provides methods for:
    - Getting aggregated stats for a time period
    - Filtering by day/week/month periods
    - Computing totals and averages
    """

    def __init__(self, db_session: Session) -> None:
        """Initialize metrics service.
        
        Args:
            db_session: SQLAlchemy database session
        """
        self._session = db_session

    def get_stats(
        self,
        period: PeriodType = PeriodType.DAY,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """Get usage statistics for a time period.
        
        Args:
            period: Time period granularity (day/week/month)
            start_date: Optional start of date range
            end_date: Optional end of date range (defaults to now)
            
        Returns:
            Dictionary with aggregated statistics
        """
        now = datetime.now(timezone.utc)
        end_date = end_date or now
        
        # Default start date based on period
        if start_date is None:
            if period == PeriodType.DAY:
                start_date = end_date - timedelta(days=1)
            elif period == PeriodType.WEEK:
                start_date = end_date - timedelta(weeks=1)
            else:  # MONTH
                start_date = end_date - timedelta(days=30)
        
        # Query aggregated stats
        stmt = select(
            func.sum(UsageStats.total_requests).label("total_requests"),
            func.sum(UsageStats.total_tokens).label("total_tokens"),
            func.sum(UsageStats.total_errors).label("total_errors"),
            func.avg(UsageStats.avg_latency_ms).label("avg_latency_ms"),
        ).where(
            UsageStats.period_type == period,
            UsageStats.period_start >= start_date,
            UsageStats.period_start <= end_date,
        )
        
        result = self._session.execute(stmt).first()
        
        if result is None or result.total_requests is None:
            return {
                "period": period.value,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_requests": 0,
                "total_tokens": 0,
                "total_errors": 0,
                "avg_latency_ms": 0.0,
                "error_rate": 0.0,
            }
        
        total_requests = int(result.total_requests)
        total_errors = int(result.total_errors) if result.total_errors else 0
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0.0
        
        return {
            "period": period.value,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_requests": total_requests,
            "total_tokens": int(result.total_tokens) if result.total_tokens else 0,
            "total_errors": total_errors,
            "avg_latency_ms": float(result.avg_latency_ms) if result.avg_latency_ms else 0.0,
            "error_rate": round(error_rate, 2),
        }

    def get_daily_breakdown(
        self,
        days: int = 7
    ) -> list[dict]:
        """Get daily statistics breakdown.
        
        Args:
            days: Number of days to include
            
        Returns:
            List of daily statistics dictionaries
        """
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=days)
        
        stmt = select(UsageStats).where(
            UsageStats.period_type == PeriodType.DAY,
            UsageStats.period_start >= start_date,
        ).order_by(UsageStats.period_start.desc())
        
        results = self._session.scalars(stmt).all()
        
        return [
            {
                "date": stat.period_start.date().isoformat(),
                "total_requests": stat.total_requests,
                "total_tokens": stat.total_tokens,
                "total_errors": stat.total_errors,
                "avg_latency_ms": stat.avg_latency_ms,
            }
            for stat in results
        ]


class ErrorRecordService:
    """Service for storing and querying error records.
    
    Tasks: T033, T052
    
    Provides methods for:
    - Recording errors from Langfuse sync
    - Querying errors with filtering and pagination
    - Cleaning up old error records
    """

    def __init__(self, db_session: Session) -> None:
        """Initialize error record service.
        
        Args:
            db_session: SQLAlchemy database session
        """
        self._session = db_session

    def record_error(
        self,
        error_type: ObservabilityErrorType,
        message: str,
        trace_id: Optional[str] = None,
        user_id_hash: Optional[str] = None,
        stack_trace: Optional[str] = None,
        privacy_level: str = "metadata",
    ) -> ErrorRecord:
        """Record a new error.
        
        Args:
            error_type: Type of error
            message: Error message
            trace_id: Optional Langfuse trace ID
            user_id_hash: Optional hashed user ID
            stack_trace: Optional stack trace (only stored at 'full' privacy level)
            privacy_level: Current privacy level setting
            
        Returns:
            Created ErrorRecord instance
        """
        # T052: Only store stack_trace at full privacy level
        if privacy_level != "full":
            stack_trace = None
        
        error = ErrorRecord(
            error_type=error_type,
            message=message,
            trace_id=trace_id,
            user_id_hash=user_id_hash,
            stack_trace=stack_trace,
        )
        
        self._session.add(error)
        self._session.flush()
        
        logger.info(
            f"Recorded error: {error_type.value}",
            extra={"error_id": error.id, "trace_id": trace_id}
        )
        
        return error

    def get_errors(
        self,
        error_type: Optional[ObservabilityErrorType] = None,
        limit: int = 50,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[list[dict], int]:
        """Query error records with filtering and pagination.
        
        Args:
            error_type: Optional filter by error type
            limit: Maximum number of records to return
            offset: Offset for pagination
            start_date: Optional start of date range
            end_date: Optional end of date range
            
        Returns:
            Tuple of (list of error dicts, total count)
        """
        # Build base query
        stmt = select(ErrorRecord)
        count_stmt = select(func.count(ErrorRecord.id))
        
        # Apply filters
        if error_type is not None:
            stmt = stmt.where(ErrorRecord.error_type == error_type)
            count_stmt = count_stmt.where(ErrorRecord.error_type == error_type)
        
        if start_date is not None:
            stmt = stmt.where(ErrorRecord.created_at >= start_date)
            count_stmt = count_stmt.where(ErrorRecord.created_at >= start_date)
        
        if end_date is not None:
            stmt = stmt.where(ErrorRecord.created_at <= end_date)
            count_stmt = count_stmt.where(ErrorRecord.created_at <= end_date)
        
        # Get total count
        total = self._session.scalar(count_stmt) or 0
        
        # Apply pagination and ordering
        stmt = stmt.order_by(ErrorRecord.created_at.desc()).limit(limit).offset(offset)
        
        results = self._session.scalars(stmt).all()
        
        errors = [
            {
                "id": error.id,
                "error_type": error.error_type.value,
                "message": error.message,
                "trace_id": error.trace_id,
                "user_id_hash": error.user_id_hash,
                "created_at": error.created_at.isoformat(),
                # Note: stack_trace intentionally excluded from API response
            }
            for error in results
        ]
        
        return errors, total

    def cleanup_old_records(self, days: int = 7) -> int:
        """Clean up error records older than specified days.
        
        Args:
            days: Number of days to retain records
            
        Returns:
            Number of records deleted
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        stmt = select(ErrorRecord).where(ErrorRecord.created_at < cutoff)
        old_records = self._session.scalars(stmt).all()
        
        count = len(old_records)
        for record in old_records:
            self._session.delete(record)
        
        if count > 0:
            logger.info(f"Cleaned up {count} error records older than {days} days")
        
        return count


__all__ = ["MetricsService", "ErrorRecordService"]
