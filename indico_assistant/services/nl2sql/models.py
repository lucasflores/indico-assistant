# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Pydantic models for the NL2SQL pipeline.

This module defines all data models used throughout the pipeline:
- Response models (PipelineResult, PipelineError)
- Intermediate models (ValidationResult, ExecutionResult)
- Cache models (CachedResult)
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PipelineErrorType(str, Enum):
    """Types of errors that can occur in the pipeline."""

    CLASSIFICATION_FAILED = "classification_failed"
    OUT_OF_SCOPE = "out_of_scope"
    GENERATION_FAILED = "generation_failed"
    VALIDATION_FAILED = "validation_failed"
    EXECUTION_FAILED = "execution_failed"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    CORRECTION_EXHAUSTED = "correction_exhausted"


class PipelineError(BaseModel):
    """Structured error information from the pipeline."""

    error_type: PipelineErrorType = Field(
        description="Type of error that occurred"
    )
    message: str = Field(description="Internal error message for logging")
    details: dict[str, Any] | None = Field(
        default=None, description="Additional error details"
    )
    user_message: str = Field(
        description="User-safe error message to display"
    )


class PipelineResult(BaseModel):
    """Complete result from NL2SQL pipeline execution."""

    success: bool = Field(description="Whether the query was successful")
    answer: str | None = Field(
        default=None, description="Natural language answer to the question"
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score for the answer",
    )
    suggested_followups: list[str] = Field(
        default_factory=list,
        description="Suggested follow-up questions for the user"
    )

    # Query details
    generated_sql: str | None = Field(
        default=None, description="The SQL query that was generated"
    )
    tables_accessed: list[str] = Field(
        default_factory=list, description="Tables accessed by the query"
    )
    row_count: int = Field(default=0, description="Number of rows returned")
    source_event_ids: list[int] = Field(
        default_factory=list,
        description="Event IDs that contributed to the result (Feature 015: citations)"
    )

    # Performance metrics
    total_time_ms: int = Field(
        default=0, description="Total pipeline execution time in milliseconds"
    )
    classification_time_ms: int = Field(
        default=0, description="Time spent on classification in milliseconds"
    )
    generation_time_ms: int = Field(
        default=0, description="Time spent on SQL generation in milliseconds"
    )
    execution_time_ms: int = Field(
        default=0, description="Time spent on query execution in milliseconds"
    )

    # Error handling
    error: PipelineError | None = Field(
        default=None, description="Error information if failed"
    )
    correction_attempts: int = Field(
        default=0, description="Number of error correction attempts"
    )
    corrected: bool = Field(
        default=False, description="Whether the query was corrected"
    )

    # Cache info
    from_cache: bool = Field(
        default=False, description="Whether result was served from cache"
    )


class ValidationResult(BaseModel):
    """Result of SQL validation."""

    valid: bool = Field(description="Whether the SQL is valid")
    sql: str = Field(description="The SQL that was validated")
    tables: list[str] = Field(
        default_factory=list, description="Tables referenced in the SQL"
    )
    violations: list[str] = Field(
        default_factory=list,
        description="List of validation rule violations",
    )
    sanitized_sql: str | None = Field(
        default=None,
        description="Sanitized/parameterized version of the SQL",
    )


class ExecutionResult(BaseModel):
    """Result of SQL query execution."""

    success: bool = Field(description="Whether execution succeeded")
    rows: list[dict[str, Any]] = Field(
        default_factory=list, description="Query result rows"
    )
    row_count: int = Field(default=0, description="Number of rows returned")
    columns: list[str] = Field(
        default_factory=list, description="Column names in result"
    )
    execution_time_ms: int = Field(
        default=0, description="Execution time in milliseconds"
    )
    error_message: str | None = Field(
        default=None, description="Error message if execution failed"
    )
    truncated: bool = Field(
        default=False,
        description="Whether results were truncated due to row limit",
    )


class CachedResult(BaseModel):
    """Wrapper for cached pipeline results."""

    result: PipelineResult = Field(description="The cached pipeline result")
    cached_at: datetime = Field(description="When the result was cached")
    expires_at: datetime = Field(description="When the cache entry expires")
    cache_key: str = Field(description="The cache key used")
