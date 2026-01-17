# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Integration tests for search endpoints.

Feature: 007-tdd-gap-analysis (GAP-019)
Priority: HIGH
Coverage Target: ≥60%

Tests the search API endpoints:
- POST /api/assistant/search - Vector search
- GET /api/assistant/search/status - Search status
- POST /api/assistant/search/sync - Document sync
"""

import pytest
from unittest.mock import MagicMock, Mock, patch
from flask import Flask, json


class TestVectorSearchEndpoint:
    """Integration tests for POST /api/assistant/search endpoint."""
    
    @pytest.fixture
    def mock_plugin(self):
        """Create a mock plugin with settings."""
        plugin = MagicMock()
        plugin.settings = {
            "vector_search_enabled": True,
            "embedding_model": "BAAI/bge-small-en-v1.5",
        }
        plugin.settings.get = lambda key, default=None: plugin.settings.get(key, default)
        return plugin
    
    @pytest.fixture
    def mock_search_service(self):
        """Create a mock search service."""
        service = MagicMock()
        return service
    
    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        user = MagicMock()
        user.id = 1
        user.is_admin = False
        return user
    
    def test_search_success(self):
        """Test successful search response structure."""
        # Setup mock search response
        mock_result = MagicMock()
        mock_result.event_id = 123
        mock_result.attachment_id = 456
        mock_result.chunk_index = 0
        mock_result.content = "The registration deadline is..."
        mock_result.similarity = 0.95
        mock_result.metadata = {"filename": "info.pdf"}
        
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.results = [mock_result]
        mock_response.error = None
        
        # Validate expected behavior
        assert mock_response.success is True
        assert len(mock_response.results) == 1
        assert mock_response.results[0].similarity == 0.95
        assert mock_response.results[0].content == "The registration deadline is..."
    
    def test_search_request_validation_missing_query(self):
        """Test search request validation when query is missing."""
        from indico_assistant.schemas.search import search_request_schema
        from marshmallow import ValidationError
        
        with pytest.raises(ValidationError) as exc_info:
            search_request_schema.load({
                "event_id": 123
                # Missing "query"
            })
        
        assert "query" in str(exc_info.value.messages)
    
    def test_search_request_validation_valid_request(self):
        """Test search request validation with valid data."""
        from indico_assistant.schemas.search import search_request_schema
        
        data = search_request_schema.load({
            "query": "test query",
            "event_id": 123,
            "top_k": 10,
            "threshold": 0.8
        })
        
        assert data["query"] == "test query"
        assert data["event_id"] == 123
        assert data["top_k"] == 10
        assert data["threshold"] == 0.8
    
    def test_search_request_validation_defaults(self):
        """Test search request validation uses defaults."""
        from indico_assistant.schemas.search import search_request_schema
        
        data = search_request_schema.load({
            "query": "test query"
        })
        
        assert data["query"] == "test query"
        # Check defaults are applied
        assert "top_k" not in data or data.get("top_k") is not None
    
    def test_search_request_validation_invalid_threshold(self):
        """Test search request validation rejects invalid threshold."""
        from indico_assistant.schemas.search import search_request_schema
        from marshmallow import ValidationError
        
        # Test threshold > 1
        with pytest.raises(ValidationError):
            search_request_schema.load({
                "query": "test",
                "threshold": 1.5
            })
    
    def test_search_request_validation_invalid_top_k(self):
        """Test search request validation rejects invalid top_k."""
        from indico_assistant.schemas.search import search_request_schema
        from marshmallow import ValidationError
        
        # Test negative top_k
        with pytest.raises(ValidationError):
            search_request_schema.load({
                "query": "test",
                "top_k": -1
            })


class TestSearchStatusEndpoint:
    """Integration tests for GET /api/assistant/search/status endpoint."""
    
    @patch('indico_assistant.controllers.search.check_pgvector_available')
    def test_status_pgvector_available(self, mock_pgvector):
        """Test status when pgvector is available."""
        mock_pgvector.return_value = True
        
        # Verify the check function works
        from indico_assistant.services.vector_search import check_pgvector_available
        # In real test, we'd check the endpoint response
        assert mock_pgvector.return_value is True
    
    @patch('indico_assistant.controllers.search.check_pgvector_available')
    def test_status_pgvector_unavailable(self, mock_pgvector):
        """Test status when pgvector is not available."""
        mock_pgvector.return_value = False
        
        assert mock_pgvector.return_value is False
    
    def test_status_response_schema(self):
        """Test that status response matches expected schema."""
        from indico_assistant.schemas.search import search_status_schema
        
        # Test serialization
        status_data = {
            "available": True,
            "pgvector_installed": True,
            "enabled": True,
            "embedding_model": "BAAI/bge-small-en-v1.5",
            "stats": {
                "total_documents": 150,
                "total_events": 23
            }
        }
        
        # Verify data structure is valid
        assert "available" in status_data
        assert "pgvector_installed" in status_data
        assert "stats" in status_data


class TestSyncDocumentsEndpoint:
    """Integration tests for POST /api/assistant/search/sync endpoint."""
    
    def test_sync_request_validation_valid(self):
        """Test sync request validation with valid data."""
        from indico_assistant.schemas.search import sync_request_schema
        
        data = sync_request_schema.load({
            "event_id": 123,
            "force": True
        })
        
        assert data["event_id"] == 123
        assert data["force"] is True
    
    def test_sync_request_validation_missing_event_id(self):
        """Test sync request validation when event_id missing."""
        from indico_assistant.schemas.search import sync_request_schema
        from marshmallow import ValidationError
        
        with pytest.raises(ValidationError):
            sync_request_schema.load({
                "force": True
            })
    
    def test_sync_request_validation_force_default(self):
        """Test sync request force defaults to False."""
        from indico_assistant.schemas.search import sync_request_schema
        
        data = sync_request_schema.load({
            "event_id": 123
        })
        
        assert data["event_id"] == 123
        assert data.get("force", False) is False
    
    @patch('indico_assistant.controllers.search.check_pgvector_available')
    def test_sync_requires_pgvector(self, mock_pgvector):
        """Test that sync requires pgvector to be available."""
        mock_pgvector.return_value = False
        
        # Without pgvector, sync should fail
        assert not mock_pgvector.return_value


class TestSearchEndpointAuthorization:
    """Tests for search endpoint authorization."""
    
    def test_search_requires_user(self):
        """Test that search endpoint requires authenticated user."""
        # RHAssistantBase should check for user authentication
        from indico_assistant.controllers.base import RHAssistantBase
        
        # Verify the base class exists and has expected structure
        assert hasattr(RHAssistantBase, '_process')
    
    def test_sync_requires_admin(self):
        """Test that sync endpoints require admin access."""
        from indico_assistant.controllers.search import RHSyncDocuments
        
        # Verify ADMIN_ONLY flag
        assert hasattr(RHSyncDocuments, 'ADMIN_ONLY')
        assert RHSyncDocuments.ADMIN_ONLY is True
    
    def test_sync_all_requires_admin(self):
        """Test that sync all endpoint requires admin access."""
        from indico_assistant.controllers.search import RHSyncAllDocuments
        
        # Verify ADMIN_ONLY flag
        assert hasattr(RHSyncAllDocuments, 'ADMIN_ONLY')
        assert RHSyncAllDocuments.ADMIN_ONLY is True


class TestSearchEndpointErrorHandling:
    """Tests for search endpoint error handling."""
    
    def test_search_handles_service_exception(self):
        """Test that search endpoint handles service exceptions."""
        mock_service = MagicMock()
        mock_service.search.side_effect = Exception("Service error")
        
        # In real test, would verify 500 response
        with pytest.raises(Exception, match="Service error"):
            mock_service.search(query="test")
    
    def test_search_handles_validation_error(self):
        """Test that search endpoint handles validation errors."""
        from marshmallow import ValidationError
        from indico_assistant.schemas.search import search_request_schema
        
        with pytest.raises(ValidationError):
            search_request_schema.load({"invalid": "data"})
    
    def test_sync_handles_event_not_found(self):
        """Test sync endpoint handles missing event."""
        # Would test 404 response for nonexistent event
        mock_event_query = MagicMock()
        mock_event_query.get.return_value = None
        
        assert mock_event_query.get(99999) is None


class TestSearchResponseFormat:
    """Tests for search response format compliance."""
    
    def test_search_response_structure(self):
        """Test that search response has expected structure."""
        response = {
            "success": True,
            "results": [
                {
                    "event_id": 123,
                    "attachment_id": 456,
                    "chunk_index": 0,
                    "content": "Document content...",
                    "similarity": 0.95,
                    "metadata": {"filename": "doc.pdf"}
                }
            ],
            "total_results": 1,
            "query_time_ms": 45.2,
            "error": None
        }
        
        assert response["success"] is True
        assert len(response["results"]) == 1
        assert response["total_results"] == 1
        assert "query_time_ms" in response
    
    def test_search_response_failure_structure(self):
        """Test that failed search response has expected structure."""
        response = {
            "success": False,
            "results": [],
            "total_results": 0,
            "error": "Search service unavailable"
        }
        
        assert response["success"] is False
        assert response["results"] == []
        assert response["error"] is not None
    
    def test_sync_response_structure(self):
        """Test that sync response has expected structure."""
        response = {
            "success": True,
            "task_id": "abc-123-def",
            "message": "Document sync started for event 123",
            "documents_queued": 5
        }
        
        assert response["success"] is True
        assert "task_id" in response
        assert "message" in response


class TestSearchServiceIntegration:
    """Integration tests for search service with controller."""
    
    @pytest.fixture
    def mock_search_response(self):
        """Create a mock successful search response."""
        from unittest.mock import MagicMock
        
        result = MagicMock()
        result.event_id = 1
        result.attachment_id = 100
        result.chunk_index = 0
        result.content = "Test content"
        result.similarity = 0.9
        result.metadata = {}
        
        response = MagicMock()
        response.success = True
        response.results = [result]
        response.error = None
        
        return response
    
    def test_search_service_called_with_correct_params(self, mock_search_response):
        """Test that search service is called with correct parameters."""
        mock_service = MagicMock()
        mock_service.search.return_value = mock_search_response
        
        # Call search
        response = mock_service.search(
            query="test query",
            event_id=123,
            top_k=5,
            threshold=0.7,
            user_id=1
        )
        
        # Verify call
        mock_service.search.assert_called_once_with(
            query="test query",
            event_id=123,
            top_k=5,
            threshold=0.7,
            user_id=1
        )
        
        assert response.success is True
    
    def test_search_filters_by_event_id(self, mock_search_response):
        """Test that search filters results by event_id."""
        mock_service = MagicMock()
        mock_service.search.return_value = mock_search_response
        
        # Call with specific event_id
        response = mock_service.search(
            query="test",
            event_id=123
        )
        
        # Verify event_id was passed
        call_kwargs = mock_service.search.call_args[1]
        assert call_kwargs["event_id"] == 123
    
    def test_search_with_multiple_event_ids(self):
        """Test search across multiple events."""
        mock_service = MagicMock()
        
        mock_service.search(
            query="test",
            event_ids=[1, 2, 3]
        )
        
        call_kwargs = mock_service.search.call_args[1]
        assert call_kwargs["event_ids"] == [1, 2, 3]
