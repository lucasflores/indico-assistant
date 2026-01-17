"""Search controller for vector search endpoints.

Feature: 006-vector-search-rag
Tasks: T031, T047, T048

Handles search and sync API requests.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from flask import jsonify, request
from marshmallow import ValidationError

from indico.core.db import db
from indico.modules.events.models.events import Event

from indico_assistant.controllers.base import RHAssistantBase
from indico_assistant.schemas.search import (
    search_request_schema,
    search_response_schema,
    search_status_schema,
    sync_request_schema,
    sync_response_schema,
)
from indico_assistant.services.vector_search import (
    check_pgvector_available,
    SearchService,
)

if TYPE_CHECKING:
    from flask import Response

logger = logging.getLogger(__name__)


class RHSearchBase(RHAssistantBase):
    """Base class for search endpoints."""
    
    def _get_search_service(self) -> SearchService:
        """Get configured search service."""
        from indico_assistant.services.vector_search.search import create_search_service
        return create_search_service(self.plugin)


class RHVectorSearch(RHSearchBase):
    """Handler for POST /api/assistant/search.
    
    Performs semantic search over indexed event documents.
    
    Request:
        {
            "query": "registration deadline",
            "event_id": 123,
            "top_k": 5,
            "threshold": 0.7
        }
        
    Response:
        {
            "success": true,
            "results": [...],
            "total_results": 3,
            "query_time_ms": 45.2
        }
    """
    
    def _process(self) -> "Response":
        """Process search request."""
        # Validate request
        try:
            data = search_request_schema.load(request.get_json() or {})
        except ValidationError as e:
            return jsonify({
                "success": False,
                "error": str(e.messages),
                "results": [],
                "total_results": 0
            }), 400
        
        # Check if search is available
        if not self.plugin.settings.get("vector_search_enabled", True):
            return jsonify({
                "success": False,
                "error": "Vector search is disabled",
                "results": [],
                "total_results": 0
            }), 503
        
        # Perform search
        search_service = self._get_search_service()
        start_time = time.time()
        
        try:
            response = search_service.search(
                query=data["query"],
                event_id=data.get("event_id"),
                event_ids=data.get("event_ids"),
                top_k=data.get("top_k", 5),
                threshold=data.get("threshold", 0.7),
                user_id=self.user.id if self.user else None
            )
        except Exception as e:
            logger.exception("Search failed")
            return jsonify({
                "success": False,
                "error": f"Search error: {str(e)}",
                "results": [],
                "total_results": 0
            }), 500
        
        query_time_ms = (time.time() - start_time) * 1000
        
        # Format results
        results = []
        if response.success and response.results:
            for r in response.results:
                result = {
                    "event_id": r.event_id,
                    "attachment_id": r.attachment_id,
                    "chunk_index": r.chunk_index,
                    "content": r.content,
                    "similarity": round(r.similarity, 4),
                }
                if data.get("include_metadata", True):
                    result["metadata"] = r.metadata
                results.append(result)
        
        return jsonify({
            "success": response.success,
            "results": results,
            "total_results": len(results),
            "query_time_ms": round(query_time_ms, 2),
            "error": response.error
        })


class RHSearchStatus(RHSearchBase):
    """Handler for GET /api/assistant/search/status.
    
    Returns vector search availability and statistics.
    
    Response:
        {
            "available": true,
            "pgvector_installed": true,
            "enabled": true,
            "embedding_model": "BAAI/bge-small-en-v1.5",
            "stats": {
                "total_documents": 150,
                "total_events": 23
            }
        }
    """
    
    def _process(self) -> "Response":
        """Get search status."""
        # Check pgvector availability
        pgvector_available = check_pgvector_available()
        
        # Check settings
        enabled = self.plugin.settings.get("vector_search_enabled", True)
        
        # Get stats if available
        stats = {}
        if pgvector_available and enabled:
            search_service = self._get_search_service()
            stats = search_service.get_stats() or {}
        
        # Get model name
        embedding_model = self.plugin.settings.get(
            "embedding_model",
            "BAAI/bge-small-en-v1.5"
        )
        
        return jsonify({
            "available": pgvector_available and enabled,
            "pgvector_installed": pgvector_available,
            "enabled": enabled,
            "embedding_model": embedding_model if enabled else None,
            "stats": stats
        })


class RHSyncDocuments(RHSearchBase):
    """Handler for POST /api/assistant/search/sync.
    
    Triggers document synchronization for an event.
    
    Request:
        {
            "event_id": 123,
            "force": false
        }
        
    Response:
        {
            "success": true,
            "task_id": "abc-123",
            "message": "Sync task started",
            "documents_queued": 5
        }
    """
    
    ADMIN_ONLY = True  # Require admin access
    
    def _process(self) -> "Response":
        """Trigger document sync."""
        # Validate request
        try:
            data = sync_request_schema.load(request.get_json() or {})
        except ValidationError as e:
            return jsonify({
                "success": False,
                "error": str(e.messages)
            }), 400
        
        event_id = data["event_id"]
        force = data.get("force", False)
        
        # Verify event exists
        event = Event.query.get(event_id)
        if not event:
            return jsonify({
                "success": False,
                "error": f"Event {event_id} not found"
            }), 404
        
        # Check if search is available
        if not check_pgvector_available():
            return jsonify({
                "success": False,
                "error": "Vector search is not available (pgvector not installed)"
            }), 503
        
        if not self.plugin.settings.get("vector_search_enabled", True):
            return jsonify({
                "success": False,
                "error": "Vector search is disabled"
            }), 503
        
        # Queue sync task
        try:
            from indico_assistant.tasks.sync import sync_event_documents
            
            result = sync_event_documents.delay(
                event_id=event_id,
                force=force
            )
            
            return jsonify({
                "success": True,
                "task_id": result.id,
                "message": f"Document sync started for event {event_id}",
                "documents_queued": None  # Will be determined by task
            })
            
        except Exception as e:
            logger.exception(f"Failed to queue sync task for event {event_id}")
            return jsonify({
                "success": False,
                "error": f"Failed to start sync: {str(e)}"
            }), 500


class RHSyncAllDocuments(RHSearchBase):
    """Handler for POST /api/assistant/search/sync/all.
    
    Triggers document synchronization for all events with attachments.
    Admin only endpoint.
    
    Response:
        {
            "success": true,
            "task_id": "abc-123",
            "message": "Full sync started"
        }
    """
    
    ADMIN_ONLY = True
    
    def _process(self) -> "Response":
        """Trigger full document sync."""
        # Check if search is available
        if not check_pgvector_available():
            return jsonify({
                "success": False,
                "error": "Vector search is not available (pgvector not installed)"
            }), 503
        
        if not self.plugin.settings.get("vector_search_enabled", True):
            return jsonify({
                "success": False,
                "error": "Vector search is disabled"
            }), 503
        
        force = request.get_json().get("force", False) if request.get_json() else False
        
        # Queue full sync task
        try:
            from indico_assistant.tasks.sync import sync_all_documents
            
            result = sync_all_documents.delay(force=force)
            
            return jsonify({
                "success": True,
                "task_id": result.id,
                "message": "Full document sync started"
            })
            
        except Exception as e:
            logger.exception("Failed to queue full sync task")
            return jsonify({
                "success": False,
                "error": f"Failed to start sync: {str(e)}"
            }), 500
