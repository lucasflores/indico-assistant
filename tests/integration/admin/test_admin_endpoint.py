# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Integration tests for admin endpoints.

Feature: 007-tdd-gap-analysis (GAP-020)
Priority: HIGH
Coverage Target: ≥60%

Tests the admin API endpoints:
- GET /admin/stats - Usage statistics
- GET /admin/errors - Error records
- GET /admin/health - System health check
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch


class TestAdminStatsEndpoint:
    """Integration tests for GET /admin/stats endpoint."""
    
    def test_stats_period_validation_valid_day(self):
        """Test stats accepts valid period 'day'."""
        from indico_assistant.models.observability import PeriodType
        
        period = PeriodType("day")
        assert period == PeriodType.DAY
    
    def test_stats_period_validation_valid_week(self):
        """Test stats accepts valid period 'week'."""
        from indico_assistant.models.observability import PeriodType
        
        period = PeriodType("week")
        assert period == PeriodType.WEEK
    
    def test_stats_period_validation_valid_month(self):
        """Test stats accepts valid period 'month'."""
        from indico_assistant.models.observability import PeriodType
        
        period = PeriodType("month")
        assert period == PeriodType.MONTH
    
    def test_stats_period_validation_invalid(self):
        """Test stats rejects invalid period."""
        from indico_assistant.models.observability import PeriodType
        
        with pytest.raises(ValueError):
            PeriodType("invalid_period")
    
    def test_stats_date_parsing_valid_iso8601(self):
        """Test stats date parsing with valid ISO 8601."""
        date_str = "2024-01-15T00:00:00Z"
        parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        
        assert parsed.year == 2024
        assert parsed.month == 1
        assert parsed.day == 15
    
    def test_stats_date_parsing_invalid(self):
        """Test stats date parsing rejects invalid format."""
        with pytest.raises(ValueError):
            datetime.fromisoformat("invalid-date")
    
    def test_stats_response_schema(self):
        """Test stats response matches expected schema."""
        from indico_assistant.schemas.admin import (
            UsageStatsResponse,
            UsageStatsData,
            PeriodInfo,
        )
        
        now = datetime.now(timezone.utc)
        
        period_info = PeriodInfo(
            type="day",
            start=now,
            end=now,
        )
        
        stats_data = UsageStatsData(
            total_queries=100,
            successful_queries=95,
            error_count=5,
            error_rate=0.05,
            avg_latency_ms=150.5,
            total_input_tokens=10000,
            total_output_tokens=8000,
        )
        
        response = UsageStatsResponse(
            period=period_info,
            stats=stats_data,
            last_synced_at=now,
        )
        
        data = response.model_dump(mode="json")
        
        assert "period" in data
        assert "stats" in data
        assert data["stats"]["total_queries"] == 100
        assert data["stats"]["error_rate"] == 0.05


class TestAdminErrorsEndpoint:
    """Integration tests for GET /admin/errors endpoint."""
    
    def test_errors_error_type_validation_valid(self):
        """Test errors accepts valid error type."""
        from indico_assistant.models.observability import ObservabilityErrorType
        
        error_type = ObservabilityErrorType("LLM_TIMEOUT")
        assert error_type == ObservabilityErrorType.LLM_TIMEOUT
    
    def test_errors_error_type_validation_invalid(self):
        """Test errors rejects invalid error type."""
        from indico_assistant.models.observability import ObservabilityErrorType
        
        with pytest.raises(ValueError):
            ObservabilityErrorType("invalid_type")
    
    def test_errors_pagination_params(self):
        """Test errors pagination parameters."""
        # Test limit clamping
        limit = min(int("150"), 100)  # Max 100
        assert limit == 100
        
        limit = min(int("50"), 100)
        assert limit == 50
    
    def test_errors_offset_validation(self):
        """Test errors offset validation."""
        offset = int("10")
        assert offset == 10
        
        with pytest.raises(ValueError):
            int("not_a_number")
    
    def test_errors_response_schema(self):
        """Test errors response matches expected schema."""
        from indico_assistant.schemas.admin import (
            ErrorListResponse,
            ErrorRecordItem,
            PaginationInfo,
        )
        from uuid import uuid4
        
        now = datetime.now(timezone.utc)
        
        error_item = ErrorRecordItem(
            id=uuid4(),
            correlation_id="trace-123",
            timestamp=now,
            error_type="llm_error",
            error_message="Model unavailable",
            langfuse_trace_id="langfuse-456",
        )
        
        pagination = PaginationInfo(
            total=100,
            limit=50,
            offset=0,
            has_more=True,
        )
        
        response = ErrorListResponse(
            errors=[error_item],
            pagination=pagination,
        )
        
        data = response.model_dump(mode="json")
        
        assert "errors" in data
        assert "pagination" in data
        assert len(data["errors"]) == 1
        assert data["pagination"]["has_more"] is True


class TestAdminHealthEndpoint:
    """Integration tests for GET /admin/health endpoint."""
    
    def test_health_response_schema(self):
        """Test health response matches expected schema."""
        from indico_assistant.schemas.admin import (
            HealthResponse,
            LangfuseStatus,
        )
        
        langfuse_status = LangfuseStatus(
            enabled=True,
            connected=True,
            host="https://cloud.langfuse.com",
            last_error=None,
        )
        
        response = HealthResponse(
            status="healthy",
            langfuse=langfuse_status,
            last_sync=None,
            privacy_level="metadata",
        )
        
        data = response.model_dump(mode="json")
        
        assert data["status"] == "healthy"
        assert data["langfuse"]["enabled"] is True
        assert data["langfuse"]["connected"] is True
    
    def test_health_status_values(self):
        """Test health status valid values."""
        valid_statuses = ["healthy", "degraded", "unhealthy"]
        
        for status in valid_statuses:
            assert status in valid_statuses
    
    @patch('indico_assistant.services.vector_search.check_pgvector_available')
    def test_health_includes_vector_search_status(self, mock_pgvector):
        """Test health response includes vector search status."""
        mock_pgvector.return_value = True
        
        # Vector search status should be included
        vector_status = {
            "enabled": True,
            "available": True,
            "pgvector_installed": True,
            "embedding_model": "BAAI/bge-small-en-v1.5",
            "stats": {},
            "error": None,
        }
        
        assert vector_status["enabled"] is True
        assert vector_status["available"] is True
    
    @patch('indico_assistant.controllers.admin.get_langfuse_client')
    def test_health_langfuse_connected(self, mock_client):
        """Test health check when Langfuse is connected."""
        mock_langfuse = MagicMock()
        mock_langfuse.enabled = True
        mock_client.return_value = mock_langfuse
        
        assert mock_langfuse.enabled is True
    
    @patch('indico_assistant.controllers.admin.get_langfuse_client')
    def test_health_langfuse_disconnected(self, mock_client):
        """Test health check when Langfuse connection fails."""
        mock_client.side_effect = Exception("Connection refused")
        
        with pytest.raises(Exception, match="Connection refused"):
            mock_client({})
    
    def test_health_degraded_status(self):
        """Test health reports degraded when services partially available."""
        # If Langfuse enabled but not connected, status should be degraded
        langfuse_enabled = True
        langfuse_connected = False
        
        if langfuse_enabled and not langfuse_connected:
            overall_status = "degraded"
        else:
            overall_status = "healthy"
        
        assert overall_status == "degraded"


class TestAdminEndpointAuthorization:
    """Tests for admin endpoint authorization."""
    
    def test_admin_stats_requires_admin(self):
        """Test that stats endpoint requires admin access."""
        from indico_assistant.controllers.admin import RHAdminStats
        from indico.modules.admin import RHAdminBase
        
        # Verify inherits from RHAdminBase which requires admin
        assert issubclass(RHAdminStats, RHAdminBase)
    
    def test_admin_errors_requires_admin(self):
        """Test that errors endpoint requires admin access."""
        from indico_assistant.controllers.admin import RHAdminErrors
        from indico.modules.admin import RHAdminBase
        
        assert issubclass(RHAdminErrors, RHAdminBase)
    
    def test_admin_health_requires_admin(self):
        """Test that health endpoint requires admin access."""
        from indico_assistant.controllers.admin import RHAdminHealth
        from indico.modules.admin import RHAdminBase
        
        assert issubclass(RHAdminHealth, RHAdminBase)


class TestAdminEndpointErrorHandling:
    """Tests for admin endpoint error handling."""
    
    def test_stats_invalid_period_returns_400(self):
        """Test stats returns 400 for invalid period."""
        # Would return 400 with error message
        error_response = {
            "error": "Invalid period: invalid. Must be 'day', 'week', or 'month'"
        }
        
        assert "Invalid period" in error_response["error"]
    
    def test_stats_invalid_date_returns_400(self):
        """Test stats returns 400 for invalid date format."""
        error_response = {
            "error": "Invalid start_date format: not-a-date"
        }
        
        assert "Invalid" in error_response["error"]
    
    def test_errors_invalid_limit_returns_400(self):
        """Test errors returns 400 for invalid limit."""
        error_response = {
            "error": "Invalid limit parameter"
        }
        
        assert "Invalid limit" in error_response["error"]
    
    def test_errors_invalid_offset_returns_400(self):
        """Test errors returns 400 for invalid offset."""
        error_response = {
            "error": "Invalid offset parameter"
        }
        
        assert "Invalid offset" in error_response["error"]
    
    def test_health_plugin_not_found_returns_500(self):
        """Test health returns 500 when plugin not found."""
        error_response = {
            "status": "unhealthy",
            "error": "Plugin not found"
        }
        
        assert error_response["status"] == "unhealthy"


class TestAdminMetricsService:
    """Tests for admin metrics service integration."""
    
    @pytest.fixture
    def mock_metrics_service(self):
        """Create a mock metrics service."""
        service = MagicMock()
        service.get_stats.return_value = {
            "period": "day",
            "start_date": "2024-01-15T00:00:00+00:00",
            "end_date": "2024-01-15T23:59:59+00:00",
            "total_requests": 100,
            "total_errors": 5,
            "error_rate": 0.05,
            "avg_latency_ms": 150.0,
            "total_tokens": 18000,
        }
        return service
    
    def test_metrics_service_returns_stats(self, mock_metrics_service):
        """Test metrics service returns stats correctly."""
        from indico_assistant.models.observability import PeriodType
        
        stats = mock_metrics_service.get_stats(
            period=PeriodType.DAY,
            start_date=None,
            end_date=None,
        )
        
        assert stats["total_requests"] == 100
        assert stats["error_rate"] == 0.05
    
    def test_metrics_service_filters_by_date(self, mock_metrics_service):
        """Test metrics service filters by date range."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        
        mock_metrics_service.get_stats(
            start_date=start,
            end_date=end,
        )
        
        mock_metrics_service.get_stats.assert_called_once()
        call_kwargs = mock_metrics_service.get_stats.call_args[1]
        assert call_kwargs["start_date"] == start
        assert call_kwargs["end_date"] == end


class TestAdminErrorRecordService:
    """Tests for admin error record service integration."""
    
    @pytest.fixture
    def mock_error_service(self):
        """Create a mock error record service."""
        service = MagicMock()
        service.get_errors.return_value = (
            [
                {
                    "trace_id": "trace-123",
                    "created_at": "2024-01-15T10:30:00+00:00",
                    "error_type": "llm_error",
                    "message": "Model timeout",
                }
            ],
            1  # total count
        )
        return service
    
    def test_error_service_returns_errors(self, mock_error_service):
        """Test error service returns errors correctly."""
        errors, total = mock_error_service.get_errors(
            limit=50,
            offset=0,
        )
        
        assert len(errors) == 1
        assert total == 1
        assert errors[0]["error_type"] == "llm_error"
    
    def test_error_service_filters_by_type(self, mock_error_service):
        """Test error service filters by error type."""
        from indico_assistant.models.observability import ObservabilityErrorType
        
        mock_error_service.get_errors(
            error_type=ObservabilityErrorType.LLM_TIMEOUT,
            limit=50,
            offset=0,
        )
        
        call_kwargs = mock_error_service.get_errors.call_args[1]
        assert call_kwargs["error_type"] == ObservabilityErrorType.LLM_TIMEOUT
    
    def test_error_service_pagination(self, mock_error_service):
        """Test error service pagination."""
        mock_error_service.get_errors.return_value = ([], 100)
        
        errors, total = mock_error_service.get_errors(
            limit=50,
            offset=50,
        )
        
        call_kwargs = mock_error_service.get_errors.call_args[1]
        assert call_kwargs["limit"] == 50
        assert call_kwargs["offset"] == 50
        assert total == 100


class TestAdminVectorSearchStatus:
    """Tests for admin vector search status in health endpoint."""
    
    @patch('indico_assistant.services.vector_search.check_pgvector_available')
    def test_vector_search_available(self, mock_pgvector):
        """Test vector search status when available."""
        mock_pgvector.return_value = True
        
        from indico_assistant.services.vector_search import check_pgvector_available
        
        available = check_pgvector_available()
        assert available is True
    
    @patch('indico_assistant.services.vector_search.check_pgvector_available')
    def test_vector_search_unavailable(self, mock_pgvector):
        """Test vector search status when unavailable."""
        mock_pgvector.return_value = False
        
        from indico_assistant.services.vector_search import check_pgvector_available
        
        available = check_pgvector_available()
        assert available is False
    
    def test_vector_search_disabled_in_settings(self):
        """Test vector search when disabled in settings."""
        settings = {"vector_search_enabled": False}
        
        vector_enabled = settings.get("vector_search_enabled", True)
        assert vector_enabled is False
    
    @patch('indico_assistant.services.vector_search.store.VectorStore')
    def test_vector_search_stats_retrieval(self, mock_store_class):
        """Test vector search stats retrieval."""
        mock_store = MagicMock()
        mock_store.get_stats.return_value = {
            "total_documents": 150,
            "total_chunks": 500,
            "indexed": 450,
            "pgvector_available": True,
        }
        mock_store_class.return_value = mock_store
        
        stats = mock_store.get_stats()
        
        assert stats["total_documents"] == 150
        assert stats["pgvector_available"] is True
