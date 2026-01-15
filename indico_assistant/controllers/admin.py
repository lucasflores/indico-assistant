"""Admin API controllers for observability dashboard.

Feature: 005-langfuse-observability
Tasks: T039, T040, T041, T042, T044, T045

This module provides REST API handlers for:
- GET /admin/stats - Usage statistics
- GET /admin/errors - Error records
- GET /admin/health - System health check
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from flask import jsonify, request
from indico.core.db import db
from indico.core.plugins import plugin_engine
from indico.modules.admin import RHAdminBase

from indico_assistant.models.observability import (
    ObservabilityErrorType,
    PeriodType,
)
from indico_assistant.schemas.admin import (
    ErrorListResponse,
    ErrorRecordItem,
    HealthResponse,
    LangfuseStatus,
    PaginationInfo,
    PeriodInfo,
    SyncStatus as SyncStatusSchema,
    UsageStatsData,
    UsageStatsResponse,
)
from indico_assistant.services.observability.client import get_langfuse_client
from indico_assistant.services.observability.metrics import (
    ErrorRecordService,
    MetricsService,
)


class RHAdminStats(RHAdminBase):
    """Handler for GET /admin/stats endpoint.
    
    Tasks: T039, T042, T044
    
    Returns usage statistics with optional period filtering.
    Requires admin permission (inherited from RHAdminBase).
    """

    def _process(self):
        """Process the stats request.
        
        Query params:
            period: 'day', 'week', or 'month' (default: 'day')
            start_date: ISO 8601 date string (optional)
            end_date: ISO 8601 date string (optional)
            
        Returns:
            JSON response with usage statistics
        """
        # Parse query parameters (T044)
        period_str = request.args.get("period", "day")
        try:
            period = PeriodType(period_str)
        except ValueError:
            return jsonify({
                "error": f"Invalid period: {period_str}. Must be 'day', 'week', or 'month'"
            }), 400
        
        start_date = None
        end_date = None
        
        start_str = request.args.get("start_date")
        if start_str:
            try:
                start_date = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": f"Invalid start_date format: {start_str}"}), 400
        
        end_str = request.args.get("end_date")
        if end_str:
            try:
                end_date = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": f"Invalid end_date format: {end_str}"}), 400
        
        # Get metrics
        metrics_service = MetricsService(db.session())
        stats = metrics_service.get_stats(
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
        
        # Build response matching schema
        now = datetime.now(timezone.utc)
        period_info = PeriodInfo(
            type=stats["period"],
            start=datetime.fromisoformat(stats["start_date"]),
            end=datetime.fromisoformat(stats["end_date"]),
        )
        
        stats_data = UsageStatsData(
            total_queries=stats["total_requests"],
            successful_queries=stats["total_requests"] - stats["total_errors"],
            error_count=stats["total_errors"],
            error_rate=stats["error_rate"],
            avg_latency_ms=stats["avg_latency_ms"],
            total_input_tokens=stats["total_tokens"] // 2,  # Approximate split
            total_output_tokens=stats["total_tokens"] // 2,
        )
        
        response = UsageStatsResponse(
            period=period_info,
            stats=stats_data,
            last_synced_at=now,  # TODO: Get from sync log
        )
        
        return jsonify(response.model_dump(mode="json"))


class RHAdminErrors(RHAdminBase):
    """Handler for GET /admin/errors endpoint.
    
    Tasks: T040, T042, T045
    
    Returns error records with filtering and pagination.
    Requires admin permission (inherited from RHAdminBase).
    """

    def _process(self):
        """Process the errors request.
        
        Query params:
            error_type: Filter by error type (optional)
            limit: Max records to return (default: 50, max: 100)
            offset: Pagination offset (default: 0)
            start_date: ISO 8601 date string (optional)
            end_date: ISO 8601 date string (optional)
            
        Returns:
            JSON response with error records
        """
        # Parse query parameters (T045)
        error_type = None
        error_type_str = request.args.get("error_type")
        if error_type_str:
            try:
                error_type = ObservabilityErrorType(error_type_str)
            except ValueError:
                return jsonify({
                    "error": f"Invalid error_type: {error_type_str}"
                }), 400
        
        try:
            limit = min(int(request.args.get("limit", 50)), 100)
        except ValueError:
            return jsonify({"error": "Invalid limit parameter"}), 400
        
        try:
            offset = int(request.args.get("offset", 0))
        except ValueError:
            return jsonify({"error": "Invalid offset parameter"}), 400
        
        start_date = None
        end_date = None
        
        start_str = request.args.get("start_date")
        if start_str:
            try:
                start_date = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": f"Invalid start_date format: {start_str}"}), 400
        
        end_str = request.args.get("end_date")
        if end_str:
            try:
                end_date = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": f"Invalid end_date format: {end_str}"}), 400
        
        # Get errors
        error_service = ErrorRecordService(db.session())
        errors, total = error_service.get_errors(
            error_type=error_type,
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
        )
        
        # Convert to schema format
        error_items = [
            ErrorRecordItem(
                id=uuid4(),  # Generate ID since original may not be UUID
                correlation_id=err.get("trace_id", "unknown"),
                timestamp=datetime.fromisoformat(err["created_at"]),
                error_type=err["error_type"],
                error_message=err["message"],
                langfuse_trace_id=err.get("trace_id"),
            )
            for err in errors
        ]
        
        # Build response
        pagination = PaginationInfo(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        )
        
        response = ErrorListResponse(
            errors=error_items,
            pagination=pagination,
        )
        
        return jsonify(response.model_dump(mode="json"))


class RHAdminHealth(RHAdminBase):
    """Handler for GET /admin/health endpoint.
    
    Tasks: T041, T042
    
    Returns system health status including Langfuse connectivity.
    Requires admin permission (inherited from RHAdminBase).
    """

    def _process(self):
        """Process the health check request.
        
        Returns:
            JSON response with health status
        """
        # Get plugin settings
        plugin = plugin_engine.get_active_plugins().get("assistant")
        if plugin is None:
            return jsonify({
                "status": "unhealthy",
                "error": "Plugin not found"
            }), 500
        
        settings = dict(plugin.settings.get_all())
        
        # Check Langfuse connection
        langfuse_enabled = settings.get("langfuse_enabled", False)
        langfuse_connected = False
        langfuse_error = None
        langfuse_host = settings.get("langfuse_host", "https://cloud.langfuse.com")
        
        if langfuse_enabled:
            try:
                client = get_langfuse_client(settings)
                langfuse_connected = client.enabled
                if not langfuse_connected:
                    langfuse_error = "Client initialization failed"
            except Exception as e:
                langfuse_error = str(e)
        
        # Overall status
        overall_status = "healthy"
        if langfuse_enabled and not langfuse_connected:
            overall_status = "degraded"
        
        # Build response
        langfuse_status = LangfuseStatus(
            enabled=langfuse_enabled,
            connected=langfuse_connected,
            host=langfuse_host if langfuse_enabled else None,
            last_error=langfuse_error,
        )
        
        response = HealthResponse(
            status=overall_status,
            langfuse=langfuse_status,
            last_sync=None,  # TODO: Get from MetricsSyncLog
            privacy_level=settings.get("langfuse_privacy_level", "metadata"),
        )
        
        return jsonify(response.model_dump(mode="json"))


__all__ = ["RHAdminStats", "RHAdminErrors", "RHAdminHealth"]
