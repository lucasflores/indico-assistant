# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Unit tests for NL2SQL pipeline models.

Feature: 007-tdd-gap-analysis (GAP-012)
Priority: HIGH
Coverage Target: ≥80%

Tests the Pydantic models for NL2SQL pipeline:
- PipelineResult
- PipelineError
- ValidationResult
- ExecutionResult
- CachedResult
"""

import pytest
from datetime import datetime, timedelta
from pydantic import ValidationError

from indico_assistant.services.nl2sql.models import (
    PipelineErrorType,
    PipelineError,
    PipelineResult,
    ValidationResult,
    ExecutionResult,
    CachedResult,
)


class TestPipelineErrorType:
    """Tests for PipelineErrorType enum."""
    
    def test_error_type_values(self):
        """Test that all expected error types exist."""
        assert PipelineErrorType.CLASSIFICATION_FAILED.value == "classification_failed"
        assert PipelineErrorType.OUT_OF_SCOPE.value == "out_of_scope"
        assert PipelineErrorType.GENERATION_FAILED.value == "generation_failed"
        assert PipelineErrorType.VALIDATION_FAILED.value == "validation_failed"
        assert PipelineErrorType.EXECUTION_FAILED.value == "execution_failed"
        assert PipelineErrorType.TIMEOUT.value == "timeout"
        assert PipelineErrorType.PERMISSION_DENIED.value == "permission_denied"
        assert PipelineErrorType.CORRECTION_EXHAUSTED.value == "correction_exhausted"
    
    def test_error_type_from_string(self):
        """Test creating error type from string value."""
        assert PipelineErrorType("classification_failed") == PipelineErrorType.CLASSIFICATION_FAILED
        assert PipelineErrorType("timeout") == PipelineErrorType.TIMEOUT


class TestPipelineError:
    """Tests for PipelineError model."""
    
    def test_create_basic_error(self):
        """Test creating a basic pipeline error."""
        error = PipelineError(
            error_type=PipelineErrorType.VALIDATION_FAILED,
            message="SQL validation failed",
            user_message="Unable to process your query."
        )
        
        assert error.error_type == PipelineErrorType.VALIDATION_FAILED
        assert error.message == "SQL validation failed"
        assert error.user_message == "Unable to process your query."
        assert error.details is None
    
    def test_create_error_with_details(self):
        """Test creating error with additional details."""
        error = PipelineError(
            error_type=PipelineErrorType.EXECUTION_FAILED,
            message="Database error",
            user_message="Query could not be executed.",
            details={"sql_error": "relation not found", "table": "nonexistent"}
        )
        
        assert error.details is not None
        assert error.details["sql_error"] == "relation not found"
        assert error.details["table"] == "nonexistent"
    
    def test_error_missing_required_fields(self):
        """Test that required fields are enforced."""
        with pytest.raises(ValidationError):
            PipelineError(
                error_type=PipelineErrorType.TIMEOUT
                # Missing message and user_message
            )
    
    def test_error_type_from_string_value(self):
        """Test creating error with string error type."""
        error = PipelineError(
            error_type="out_of_scope",  # String value
            message="Query is out of scope",
            user_message="I can only answer questions about events."
        )
        
        assert error.error_type == PipelineErrorType.OUT_OF_SCOPE


class TestPipelineResult:
    """Tests for PipelineResult model."""
    
    def test_create_successful_result(self):
        """Test creating a successful pipeline result."""
        result = PipelineResult(
            success=True,
            answer="There are 150 participants.",
            confidence=0.95,
            generated_sql="SELECT COUNT(*) FROM registrations WHERE event_id = 1",
            tables_accessed=["registrations"],
            row_count=1,
            total_time_ms=250
        )
        
        assert result.success is True
        assert result.answer == "There are 150 participants."
        assert result.confidence == 0.95
        assert result.generated_sql is not None
        assert "registrations" in result.tables_accessed
        assert result.error is None
    
    def test_create_failed_result(self):
        """Test creating a failed pipeline result."""
        error = PipelineError(
            error_type=PipelineErrorType.CLASSIFICATION_FAILED,
            message="Could not classify query",
            user_message="Unable to understand your question."
        )
        
        result = PipelineResult(
            success=False,
            error=error
        )
        
        assert result.success is False
        assert result.error is not None
        assert result.error.error_type == PipelineErrorType.CLASSIFICATION_FAILED
        assert result.answer is None
    
    def test_result_default_values(self):
        """Test that defaults are applied correctly."""
        result = PipelineResult(success=True)
        
        assert result.answer is None
        assert result.confidence is None
        assert result.generated_sql is None
        assert result.tables_accessed == []
        assert result.row_count == 0
        assert result.total_time_ms == 0
        assert result.classification_time_ms == 0
        assert result.generation_time_ms == 0
        assert result.execution_time_ms == 0
        assert result.error is None
        assert result.correction_attempts == 0
        assert result.corrected is False
        assert result.from_cache is False
    
    def test_result_with_timing_metrics(self):
        """Test result with detailed timing metrics."""
        result = PipelineResult(
            success=True,
            answer="Result",
            total_time_ms=500,
            classification_time_ms=50,
            generation_time_ms=200,
            execution_time_ms=250
        )
        
        assert result.total_time_ms == 500
        assert result.classification_time_ms == 50
        assert result.generation_time_ms == 200
        assert result.execution_time_ms == 250
    
    def test_result_with_correction_info(self):
        """Test result with error correction information."""
        result = PipelineResult(
            success=True,
            answer="Corrected result",
            correction_attempts=2,
            corrected=True
        )
        
        assert result.correction_attempts == 2
        assert result.corrected is True
    
    def test_result_from_cache(self):
        """Test result served from cache."""
        result = PipelineResult(
            success=True,
            answer="Cached answer",
            from_cache=True,
            total_time_ms=5  # Fast due to cache
        )
        
        assert result.from_cache is True
    
    def test_confidence_validation_range(self):
        """Test that confidence must be between 0 and 1."""
        # Valid values
        result = PipelineResult(success=True, confidence=0.0)
        assert result.confidence == 0.0
        
        result = PipelineResult(success=True, confidence=1.0)
        assert result.confidence == 1.0
        
        result = PipelineResult(success=True, confidence=0.5)
        assert result.confidence == 0.5
        
        # Invalid values
        with pytest.raises(ValidationError):
            PipelineResult(success=True, confidence=-0.1)
        
        with pytest.raises(ValidationError):
            PipelineResult(success=True, confidence=1.1)


class TestValidationResult:
    """Tests for ValidationResult model."""
    
    def test_create_valid_result(self):
        """Test creating a valid validation result."""
        result = ValidationResult(
            valid=True,
            sql="SELECT * FROM events WHERE id = 1",
            tables=["events"],
            sanitized_sql="SELECT * FROM events WHERE id = $1"
        )
        
        assert result.valid is True
        assert result.sql == "SELECT * FROM events WHERE id = 1"
        assert result.tables == ["events"]
        assert result.violations == []
        assert result.sanitized_sql is not None
    
    def test_create_invalid_result(self):
        """Test creating an invalid validation result."""
        result = ValidationResult(
            valid=False,
            sql="DROP TABLE events",
            tables=["events"],
            violations=["DDL statements not allowed", "Table modification not allowed"]
        )
        
        assert result.valid is False
        assert len(result.violations) == 2
        assert "DDL statements not allowed" in result.violations
    
    def test_validation_default_values(self):
        """Test default values for validation result."""
        result = ValidationResult(valid=True, sql="SELECT 1")
        
        assert result.tables == []
        assert result.violations == []
        assert result.sanitized_sql is None
    
    def test_validation_multiple_tables(self):
        """Test validation result with multiple tables."""
        result = ValidationResult(
            valid=True,
            sql="SELECT * FROM events e JOIN categories c ON e.category_id = c.id",
            tables=["events", "categories"]
        )
        
        assert len(result.tables) == 2
        assert "events" in result.tables
        assert "categories" in result.tables


class TestExecutionResult:
    """Tests for ExecutionResult model."""
    
    def test_create_successful_execution(self):
        """Test creating a successful execution result."""
        result = ExecutionResult(
            success=True,
            rows=[
                {"id": 1, "title": "Event 1"},
                {"id": 2, "title": "Event 2"}
            ],
            row_count=2,
            columns=["id", "title"],
            execution_time_ms=50
        )
        
        assert result.success is True
        assert len(result.rows) == 2
        assert result.row_count == 2
        assert result.columns == ["id", "title"]
        assert result.error_message is None
        assert result.truncated is False
    
    def test_create_failed_execution(self):
        """Test creating a failed execution result."""
        result = ExecutionResult(
            success=False,
            error_message="relation \"nonexistent\" does not exist",
            execution_time_ms=10
        )
        
        assert result.success is False
        assert result.error_message is not None
        assert result.rows == []
        assert result.row_count == 0
    
    def test_execution_truncated_results(self):
        """Test execution result with truncated data."""
        result = ExecutionResult(
            success=True,
            rows=[{"id": i} for i in range(1000)],
            row_count=1000,
            columns=["id"],
            truncated=True
        )
        
        assert result.truncated is True
        assert len(result.rows) == 1000
    
    def test_execution_default_values(self):
        """Test default values for execution result."""
        result = ExecutionResult(success=True)
        
        assert result.rows == []
        assert result.row_count == 0
        assert result.columns == []
        assert result.execution_time_ms == 0
        assert result.error_message is None
        assert result.truncated is False
    
    def test_execution_with_complex_rows(self):
        """Test execution result with complex row data."""
        result = ExecutionResult(
            success=True,
            rows=[
                {
                    "id": 1,
                    "data": {"nested": "value"},
                    "tags": ["tag1", "tag2"],
                    "count": 42
                }
            ],
            row_count=1,
            columns=["id", "data", "tags", "count"]
        )
        
        assert result.rows[0]["data"]["nested"] == "value"
        assert result.rows[0]["tags"] == ["tag1", "tag2"]


class TestCachedResult:
    """Tests for CachedResult model."""
    
    def test_create_cached_result(self):
        """Test creating a cached result."""
        pipeline_result = PipelineResult(
            success=True,
            answer="Cached answer"
        )
        
        now = datetime.utcnow()
        expires = now + timedelta(hours=1)
        
        cached = CachedResult(
            result=pipeline_result,
            cached_at=now,
            expires_at=expires,
            cache_key="query_hash_abc123"
        )
        
        assert cached.result.success is True
        assert cached.result.answer == "Cached answer"
        assert cached.cache_key == "query_hash_abc123"
        assert cached.cached_at == now
        assert cached.expires_at == expires
    
    def test_cached_result_expiration(self):
        """Test cached result expiration time."""
        result = PipelineResult(success=True)
        
        cached_at = datetime(2024, 1, 1, 12, 0, 0)
        expires_at = datetime(2024, 1, 1, 12, 10, 0)  # 10 minutes later
        
        cached = CachedResult(
            result=result,
            cached_at=cached_at,
            expires_at=expires_at,
            cache_key="test_key"
        )
        
        # Calculate TTL
        ttl = (cached.expires_at - cached.cached_at).total_seconds()
        assert ttl == 600  # 10 minutes
    
    def test_cached_result_required_fields(self):
        """Test that all fields are required."""
        with pytest.raises(ValidationError):
            CachedResult(
                result=PipelineResult(success=True)
                # Missing cached_at, expires_at, cache_key
            )


class TestModelSerialization:
    """Tests for model serialization/deserialization."""
    
    def test_pipeline_result_to_dict(self):
        """Test converting PipelineResult to dict."""
        result = PipelineResult(
            success=True,
            answer="Test answer",
            confidence=0.9,
            tables_accessed=["events"]
        )
        
        data = result.model_dump()
        
        assert data["success"] is True
        assert data["answer"] == "Test answer"
        assert data["confidence"] == 0.9
        assert data["tables_accessed"] == ["events"]
    
    def test_pipeline_result_from_dict(self):
        """Test creating PipelineResult from dict."""
        data = {
            "success": True,
            "answer": "From dict",
            "confidence": 0.85,
            "row_count": 10
        }
        
        result = PipelineResult(**data)
        
        assert result.success is True
        assert result.answer == "From dict"
        assert result.confidence == 0.85
        assert result.row_count == 10
    
    def test_nested_error_serialization(self):
        """Test serialization of result with nested error."""
        result = PipelineResult(
            success=False,
            error=PipelineError(
                error_type=PipelineErrorType.TIMEOUT,
                message="Query timed out",
                user_message="Query took too long.",
                details={"timeout_ms": 30000}
            )
        )
        
        data = result.model_dump()
        
        assert data["error"]["error_type"] == "timeout"
        assert data["error"]["details"]["timeout_ms"] == 30000
    
    def test_execution_result_json_round_trip(self):
        """Test ExecutionResult JSON serialization round-trip."""
        original = ExecutionResult(
            success=True,
            rows=[{"id": 1, "name": "Test"}],
            row_count=1,
            columns=["id", "name"],
            execution_time_ms=25
        )
        
        json_str = original.model_dump_json()
        restored = ExecutionResult.model_validate_json(json_str)
        
        assert restored.success == original.success
        assert restored.rows == original.rows
        assert restored.row_count == original.row_count


class TestModelEdgeCases:
    """Tests for edge cases in model validation."""
    
    def test_empty_tables_accessed(self):
        """Test result with empty tables accessed."""
        result = PipelineResult(
            success=True,
            answer="No tables needed",
            tables_accessed=[]
        )
        
        assert result.tables_accessed == []
    
    def test_zero_confidence(self):
        """Test result with zero confidence."""
        result = PipelineResult(
            success=True,
            answer="Low confidence answer",
            confidence=0.0
        )
        
        assert result.confidence == 0.0
    
    def test_validation_empty_violations(self):
        """Test valid result with explicit empty violations."""
        result = ValidationResult(
            valid=True,
            sql="SELECT 1",
            violations=[]
        )
        
        assert len(result.violations) == 0
    
    def test_execution_empty_rows(self):
        """Test execution with empty result set."""
        result = ExecutionResult(
            success=True,
            rows=[],
            row_count=0,
            columns=["id", "name"]
        )
        
        assert result.success is True
        assert len(result.rows) == 0
    
    def test_very_long_sql(self):
        """Test handling of very long SQL strings."""
        # Generate SQL with 200 columns to exceed 1000 chars
        long_sql = "SELECT " + ", ".join([f"column_{i}" for i in range(200)]) + " FROM events"
        
        result = ValidationResult(
            valid=True,
            sql=long_sql
        )
        
        assert len(result.sql) > 1000
    
    def test_special_characters_in_answer(self):
        """Test answer with special characters."""
        result = PipelineResult(
            success=True,
            answer="The café has 150 résumés on file. Cost: €500."
        )
        
        assert "café" in result.answer
        assert "€" in result.answer
    
    def test_null_vs_missing_optional_fields(self):
        """Test distinction between null and missing optional fields."""
        # With explicit None
        result1 = PipelineResult(success=True, answer=None)
        assert result1.answer is None
        
        # Without field (default to None)
        result2 = PipelineResult(success=True)
        assert result2.answer is None
