"""Pydantic schemas for admin API endpoints.

Feature: 005-langfuse-observability
Task: T014

Schemas for:
- GET /api/assistant/admin/stats → UsageStatsResponse
- GET /api/assistant/admin/errors → ErrorListResponse
- GET /api/assistant/admin/health → HealthResponse
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PeriodInfo(BaseModel):
    """Period information for stats response."""
    
    type: str = Field(..., description="Period type: day, week, month, or custom")
    start: datetime = Field(..., description="Period start timestamp (UTC)")
    end: datetime = Field(..., description="Period end timestamp (UTC)")


class UsageStatsData(BaseModel):
    """Aggregated usage statistics."""
    
    total_queries: int = Field(..., description="Total queries in period")
    successful_queries: int = Field(..., description="Queries completed without error")
    error_count: int = Field(..., description="Total errors in period")
    error_rate: float = Field(..., description="Error rate (error_count / total_queries)")
    avg_latency_ms: Optional[float] = Field(None, description="Average response latency")
    p95_latency_ms: Optional[float] = Field(None, description="95th percentile latency")
    total_input_tokens: int = Field(0, description="Sum of input tokens")
    total_output_tokens: int = Field(0, description="Sum of output tokens")
    queries_by_intent: Optional[dict[str, int]] = Field(
        None, 
        description="Breakdown by query intent"
    )


class UsageStatsResponse(BaseModel):
    """Response schema for GET /api/assistant/admin/stats.
    
    Conforms to OpenAPI spec in contracts/openapi.yaml.
    """
    
    model_config = ConfigDict(from_attributes=True)
    
    period: PeriodInfo = Field(..., description="Period information")
    stats: UsageStatsData = Field(..., description="Aggregated statistics")
    last_synced_at: datetime = Field(..., description="When data was last synced from Langfuse")


class ErrorRecordItem(BaseModel):
    """Single error record for errors list."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(..., description="Unique error identifier")
    correlation_id: str = Field(..., description="Request correlation ID")
    timestamp: datetime = Field(..., description="When error occurred")
    error_type: str = Field(..., description="Error classification")
    error_message: str = Field(..., description="Human-readable error description")
    langfuse_trace_id: Optional[str] = Field(
        None, 
        description="Link to Langfuse trace"
    )


class PaginationInfo(BaseModel):
    """Pagination metadata for list responses."""
    
    total: int = Field(..., description="Total number of records")
    limit: int = Field(..., description="Maximum records per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more records exist")


class ErrorListResponse(BaseModel):
    """Response schema for GET /api/assistant/admin/errors.
    
    Conforms to OpenAPI spec in contracts/openapi.yaml.
    """
    
    errors: list[ErrorRecordItem] = Field(..., description="List of error records")
    pagination: PaginationInfo = Field(..., description="Pagination metadata")


class LangfuseStatus(BaseModel):
    """Langfuse connectivity status."""
    
    enabled: bool = Field(..., description="Whether Langfuse is enabled")
    connected: bool = Field(..., description="Whether Langfuse is reachable")
    host: Optional[str] = Field(None, description="Langfuse host URL")
    last_error: Optional[str] = Field(None, description="Last connection error if any")


class SyncStatus(BaseModel):
    """Last sync job status."""
    
    status: str = Field(..., description="Last sync status: running, completed, failed")
    started_at: Optional[datetime] = Field(None, description="When last sync started")
    completed_at: Optional[datetime] = Field(None, description="When last sync completed")
    traces_processed: int = Field(0, description="Traces processed in last sync")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class HealthResponse(BaseModel):
    """Response schema for GET /api/assistant/admin/health.
    
    Conforms to OpenAPI spec in contracts/openapi.yaml.
    """
    
    status: str = Field(..., description="Overall health status: healthy, degraded, unhealthy")
    langfuse: LangfuseStatus = Field(..., description="Langfuse connectivity status")
    last_sync: Optional[SyncStatus] = Field(None, description="Last sync job status")
    privacy_level: str = Field(..., description="Current privacy level setting")


__all__ = [
    "UsageStatsResponse",
    "UsageStatsData",
    "PeriodInfo",
    "ErrorListResponse",
    "ErrorRecordItem",
    "PaginationInfo",
    "HealthResponse",
    "LangfuseStatus",
    "SyncStatus",
]
