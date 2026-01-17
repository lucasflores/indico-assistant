"""Pydantic schemas for vector search API.

Feature: 006-vector-search-rag
Tasks: T015

Defines request/response models for the search endpoint.
"""

from __future__ import annotations

from typing import Any, Optional

from marshmallow import Schema, fields, validate, post_load


class SearchRequestSchema(Schema):
    """Schema for search requests.
    
    Example:
        {
            "query": "What is the registration deadline?",
            "event_id": 123,
            "top_k": 5,
            "threshold": 0.7
        }
    """
    
    query = fields.Str(
        required=True,
        validate=validate.Length(min=3, max=1000),
        metadata={"description": "Search query text"}
    )
    
    event_id = fields.Int(
        load_default=None,
        metadata={"description": "Single event ID to search within"}
    )
    
    event_ids = fields.List(
        fields.Int(),
        load_default=None,
        metadata={"description": "List of event IDs to search within"}
    )
    
    top_k = fields.Int(
        load_default=5,
        validate=validate.Range(min=1, max=20),
        metadata={"description": "Maximum number of results to return"}
    )
    
    threshold = fields.Float(
        load_default=0.7,
        validate=validate.Range(min=0.0, max=1.0),
        metadata={"description": "Minimum similarity score threshold"}
    )
    
    include_metadata = fields.Bool(
        load_default=True,
        metadata={"description": "Whether to include document metadata"}
    )


class SearchResultSchema(Schema):
    """Schema for individual search results.
    
    Example:
        {
            "event_id": 123,
            "attachment_id": 456,
            "chunk_index": 0,
            "content": "Registration deadline is December 15th...",
            "similarity": 0.89,
            "metadata": {
                "filename": "event_details.pdf",
                "page_number": 2
            }
        }
    """
    
    event_id = fields.Int(
        required=True,
        metadata={"description": "Event ID the document belongs to"}
    )
    
    attachment_id = fields.Int(
        required=True,
        metadata={"description": "Attachment ID in Indico"}
    )
    
    chunk_index = fields.Int(
        required=True,
        metadata={"description": "Index of this chunk within the document"}
    )
    
    content = fields.Str(
        required=True,
        metadata={"description": "Text content of the chunk"}
    )
    
    similarity = fields.Float(
        required=True,
        metadata={"description": "Similarity score (0-1)"}
    )
    
    metadata = fields.Dict(
        load_default=dict,
        metadata={"description": "Additional document metadata"}
    )


class SearchResponseSchema(Schema):
    """Schema for search response.
    
    Example:
        {
            "success": true,
            "results": [...],
            "total_results": 3,
            "query_time_ms": 45.2
        }
    """
    
    success = fields.Bool(
        required=True,
        metadata={"description": "Whether the search succeeded"}
    )
    
    results = fields.List(
        fields.Nested(SearchResultSchema),
        load_default=list,
        metadata={"description": "List of search results"}
    )
    
    total_results = fields.Int(
        required=True,
        metadata={"description": "Total number of results returned"}
    )
    
    query_time_ms = fields.Float(
        load_default=None,
        metadata={"description": "Search execution time in milliseconds"}
    )
    
    error = fields.Str(
        load_default=None,
        metadata={"description": "Error message if search failed"}
    )


class SearchStatusSchema(Schema):
    """Schema for vector search status response.
    
    Example:
        {
            "available": true,
            "pgvector_installed": true,
            "enabled": true,
            "stats": {
                "total_documents": 150,
                "total_events": 23
            }
        }
    """
    
    available = fields.Bool(
        required=True,
        metadata={"description": "Whether vector search is fully available"}
    )
    
    pgvector_installed = fields.Bool(
        required=True,
        metadata={"description": "Whether pgvector extension is installed"}
    )
    
    enabled = fields.Bool(
        required=True,
        metadata={"description": "Whether vector search is enabled in settings"}
    )
    
    embedding_model = fields.Str(
        load_default=None,
        metadata={"description": "Name of the embedding model being used"}
    )
    
    stats = fields.Dict(
        load_default=dict,
        metadata={"description": "Document statistics"}
    )


class SyncRequestSchema(Schema):
    """Schema for document sync requests.
    
    Example:
        {
            "event_id": 123,
            "force": false
        }
    """
    
    event_id = fields.Int(
        required=True,
        metadata={"description": "Event ID to sync documents for"}
    )
    
    force = fields.Bool(
        load_default=False,
        metadata={"description": "Force re-extraction of all documents"}
    )


class SyncResponseSchema(Schema):
    """Schema for sync response.
    
    Example:
        {
            "success": true,
            "task_id": "abc-123",
            "message": "Sync task started"
        }
    """
    
    success = fields.Bool(
        required=True,
        metadata={"description": "Whether sync was started successfully"}
    )
    
    task_id = fields.Str(
        load_default=None,
        metadata={"description": "Celery task ID for tracking"}
    )
    
    message = fields.Str(
        load_default=None,
        metadata={"description": "Status message"}
    )
    
    documents_queued = fields.Int(
        load_default=None,
        metadata={"description": "Number of documents queued for processing"}
    )


# Schema instances for validation
search_request_schema = SearchRequestSchema()
search_response_schema = SearchResponseSchema()
search_result_schema = SearchResultSchema()
search_status_schema = SearchStatusSchema()
sync_request_schema = SyncRequestSchema()
sync_response_schema = SyncResponseSchema()
