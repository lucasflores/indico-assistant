"""Celery sync task for fetching Langfuse metrics.

Feature: 005-langfuse-observability
Tasks: T034, T035, T036, T037, T038, T046

This module provides:
- Celery task skeleton for hourly sync
- Langfuse API fetching logic
- Stats aggregation and error extraction
- Automatic cleanup of old records
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

from celery.schedules import crontab

from indico_assistant.services.observability import get_observability_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_observability_logger("sync")


def sync_langfuse_metrics(
    db_session: "Session",
    settings: dict,
) -> dict:
    """Sync metrics from Langfuse to local database (T034).
    
    This is the main entry point called by the Celery task.
    It orchestrates fetching, aggregating, and storing metrics.
    
    Args:
        db_session: SQLAlchemy database session
        settings: Plugin settings dictionary
        
    Returns:
        Dictionary with sync results
    """
    from indico_assistant.models.observability import (
        MetricsSyncLog,
        ObservabilityErrorType,
        PeriodType,
        SyncStatus,
        UsageStats,
    )
    from indico_assistant.services.observability.client import get_langfuse_client
    from indico_assistant.services.observability.metrics import ErrorRecordService
    
    sync_start = datetime.now(timezone.utc)
    sync_log = MetricsSyncLog(
        started_at=sync_start,
        status=SyncStatus.RUNNING,
    )
    db_session.add(sync_log)
    db_session.flush()
    
    try:
        # Get Langfuse client
        client = get_langfuse_client(settings)
        
        if not client.enabled:
            logger.warning("Langfuse not enabled, skipping sync")
            sync_log.status = SyncStatus.SKIPPED
            sync_log.completed_at = datetime.now(timezone.utc)
            db_session.commit()
            return {"status": "skipped", "reason": "langfuse_disabled"}
        
        # Fetch metrics from Langfuse API (T035)
        traces_data = _fetch_langfuse_traces(client, settings)
        
        if traces_data is None:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = "Failed to fetch traces from Langfuse"
            sync_log.completed_at = datetime.now(timezone.utc)
            db_session.commit()
            return {"status": "failed", "reason": "fetch_error"}
        
        # Aggregate stats (T036)
        stats = _aggregate_stats(traces_data)
        
        # Store daily stats
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        existing_stat = db_session.query(UsageStats).filter(
            UsageStats.period_type == PeriodType.DAY,
            UsageStats.period_start == today,
        ).first()
        
        if existing_stat:
            # Update existing record
            existing_stat.total_requests = stats["total_requests"]
            existing_stat.total_tokens = stats["total_tokens"]
            existing_stat.total_errors = stats["total_errors"]
            existing_stat.avg_latency_ms = stats["avg_latency_ms"]
            existing_stat.updated_at = datetime.now(timezone.utc)
        else:
            # Create new record
            new_stat = UsageStats(
                period_type=PeriodType.DAY,
                period_start=today,
                total_requests=stats["total_requests"],
                total_tokens=stats["total_tokens"],
                total_errors=stats["total_errors"],
                avg_latency_ms=stats["avg_latency_ms"],
            )
            db_session.add(new_stat)
        
        # Extract and store errors (T037)
        errors_stored = 0
        error_service = ErrorRecordService(db_session)
        privacy_level = settings.get("langfuse_privacy_level", "metadata")
        
        for error_data in _extract_errors(traces_data):
            error_service.record_error(
                error_type=ObservabilityErrorType.LLM_ERROR,
                message=error_data.get("message", "Unknown error"),
                trace_id=error_data.get("trace_id"),
                user_id_hash=error_data.get("user_id_hash"),
                stack_trace=error_data.get("stack_trace"),
                privacy_level=privacy_level,
            )
            errors_stored += 1
        
        # Cleanup old records (T046)
        cleaned_up = error_service.cleanup_old_records(days=7)
        
        # Update sync log
        sync_log.status = SyncStatus.COMPLETED
        sync_log.completed_at = datetime.now(timezone.utc)
        sync_log.records_synced = stats["total_requests"]
        
        db_session.commit()
        
        logger.info(
            f"Sync completed: {stats['total_requests']} requests, "
            f"{errors_stored} errors stored, {cleaned_up} old records cleaned"
        )
        
        return {
            "status": "completed",
            "stats_synced": stats,
            "errors_stored": errors_stored,
            "cleaned_up": cleaned_up,
        }
        
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        sync_log.status = SyncStatus.FAILED
        sync_log.error_message = str(e)
        sync_log.completed_at = datetime.now(timezone.utc)
        db_session.commit()
        return {"status": "failed", "reason": str(e)}


def _fetch_langfuse_traces(
    client: Any,
    settings: dict,
) -> Optional[list[dict]]:
    """Fetch traces from Langfuse API (T035).
    
    Args:
        client: LangfuseClient instance
        settings: Plugin settings
        
    Returns:
        List of trace data dictionaries, or None on error
    """
    try:
        # The Langfuse SDK provides access to the underlying client
        # for fetching trace data via the API
        langfuse = client._client
        if langfuse is None:
            return None
        
        # Fetch traces from the last hour
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        
        # Use the Langfuse Python SDK to fetch traces
        # Note: The exact API depends on Langfuse SDK version
        # This is a simplified implementation
        traces = langfuse.get_traces(
            limit=1000,
            from_timestamp=one_hour_ago.isoformat(),
        )
        
        if hasattr(traces, 'data'):
            return [t.dict() if hasattr(t, 'dict') else t for t in traces.data]
        return list(traces) if traces else []
        
    except Exception as e:
        logger.warning(f"Failed to fetch Langfuse traces: {e}")
        return None


def _aggregate_stats(traces: list[dict]) -> dict:
    """Aggregate statistics from trace data (T036).
    
    Args:
        traces: List of trace dictionaries
        
    Returns:
        Aggregated statistics dictionary
    """
    if not traces:
        return {
            "total_requests": 0,
            "total_tokens": 0,
            "total_errors": 0,
            "avg_latency_ms": 0.0,
        }
    
    total_requests = len(traces)
    total_tokens = 0
    total_errors = 0
    total_latency = 0.0
    latency_count = 0
    
    for trace in traces:
        # Count tokens from usage data
        usage = trace.get("usage", {}) or {}
        total_tokens += usage.get("total_tokens", 0) or 0
        total_tokens += (usage.get("input", 0) or 0) + (usage.get("output", 0) or 0)
        
        # Count errors
        if trace.get("level") == "ERROR" or trace.get("status_message") == "error":
            total_errors += 1
        
        # Calculate latency
        metadata = trace.get("metadata", {}) or {}
        latency = metadata.get("latency_ms")
        if latency is not None:
            total_latency += float(latency)
            latency_count += 1
    
    avg_latency = total_latency / latency_count if latency_count > 0 else 0.0
    
    return {
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "total_errors": total_errors,
        "avg_latency_ms": round(avg_latency, 2),
    }


def _extract_errors(traces: list[dict]) -> list[dict]:
    """Extract error records from trace data (T037).
    
    Args:
        traces: List of trace dictionaries
        
    Returns:
        List of error data dictionaries
    """
    errors = []
    
    for trace in traces:
        if trace.get("level") == "ERROR" or trace.get("status_message") == "error":
            metadata = trace.get("metadata", {}) or {}
            errors.append({
                "trace_id": trace.get("id"),
                "user_id_hash": trace.get("user_id"),
                "message": metadata.get("error_message") or trace.get("output", "Unknown error"),
                "stack_trace": metadata.get("stack_trace"),
            })
    
    return errors


# Celery task registration (T038)
def register_celery_tasks(celery_app: Any) -> None:
    """Register sync task with Celery.
    
    Args:
        celery_app: Celery application instance
    """
    @celery_app.task(name="indico_assistant.sync_langfuse_metrics")
    def sync_task():
        """Celery task to sync Langfuse metrics hourly."""
        from indico.core.plugins import plugin_engine
        from indico.core.db import db
        
        plugin = plugin_engine.get_active_plugins().get("assistant")
        if plugin is None:
            logger.warning("Assistant plugin not found")
            return
        
        settings = dict(plugin.settings.get_all())
        
        with db.session.begin_nested():
            result = sync_langfuse_metrics(db.session, settings)
        
        return result
    
    # Register hourly schedule
    celery_app.conf.beat_schedule["sync_langfuse_metrics"] = {
        "task": "indico_assistant.sync_langfuse_metrics",
        "schedule": crontab(minute=0),  # Run at the start of every hour
    }


__all__ = ["sync_langfuse_metrics", "register_celery_tasks"]
