"""Semantic search service for document retrieval.

Feature: 006-vector-search-rag
Tasks: T027, T028, T029, T030, T033, T034

Provides high-level search interface with embedding generation and filtering.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from indico_assistant.services.vector_search import check_pgvector_available
from indico_assistant.services.vector_search.store import VectorStore

if TYPE_CHECKING:
    from indico_assistant.services.embedding import EmbeddingService
    from indico_assistant.plugin import AssistantPlugin

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result.
    
    Attributes:
        content: The matching text content.
        similarity: Cosine similarity score (0-1).
        event_id: Indico event ID.
        attachment_id: Indico attachment ID.
        chunk_index: Position in document.
        metadata: Additional metadata.
    """
    content: str
    similarity: float
    event_id: int
    attachment_id: int
    chunk_index: int
    metadata: dict


@dataclass
class SearchResponse:
    """Response from a search operation.
    
    Attributes:
        success: Whether search completed successfully.
        results: List of search results.
        total: Total number of results.
        query: Original query string.
        search_time_ms: Time taken in milliseconds.
        error: Error message if search failed.
    """
    success: bool
    results: list[SearchResult]
    total: int
    query: str
    search_time_ms: float
    error: Optional[str] = None


class SearchService:
    """High-level service for semantic document search.
    
    Combines embedding generation with vector store queries to provide
    a simple search interface.
    
    Attributes:
        _embedding_service: Service for generating query embeddings.
        _vector_store: Storage for document vectors.
        _default_top_k: Default number of results.
        _default_threshold: Default similarity threshold.
    
    Example:
        >>> service = SearchService(embedding_svc, store)
        >>> response = service.search("machine learning applications", event_id=123)
        >>> for result in response.results:
        ...     print(f"[{result.similarity:.2f}] {result.content[:100]}...")
    """
    
    def __init__(
        self,
        embedding_service: "EmbeddingService",
        vector_store: Optional[VectorStore] = None,
        default_top_k: int = 5,
        default_threshold: float = 0.7
    ) -> None:
        """Initialize the search service.
        
        Args:
            embedding_service: Service for generating embeddings.
            vector_store: Vector storage. Created if not provided.
            default_top_k: Default maximum results.
            default_threshold: Default similarity threshold.
        """
        self._embedding_service = embedding_service
        self._vector_store = vector_store or VectorStore()
        self._default_top_k = default_top_k
        self._default_threshold = default_threshold
    
    @property
    def is_available(self) -> bool:
        """Check if search is available.
        
        Returns:
            True if both embedding service and vector store are available.
        """
        return (
            self._embedding_service.is_enabled and 
            self._vector_store.is_available
        )
    
    def search(
        self,
        query: str,
        event_id: Optional[int] = None,
        event_ids: Optional[list[int]] = None,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
        user_id: Optional[int] = None
    ) -> SearchResponse:
        """Search for similar document chunks.
        
        Args:
            query: Natural language search query.
            event_id: Optional single event ID to search in.
            event_ids: Optional list of event IDs to search in.
            top_k: Maximum number of results (default: 5).
            threshold: Minimum similarity threshold (default: 0.7).
            user_id: Optional user ID for permission filtering.
            
        Returns:
            SearchResponse with results or error.
        """
        start_time = time.time()
        
        if not query or not query.strip():
            return SearchResponse(
                success=False,
                results=[],
                total=0,
                query=query,
                search_time_ms=0,
                error="Query cannot be empty"
            )
        
        # Check availability
        if not self.is_available:
            return SearchResponse(
                success=False,
                results=[],
                total=0,
                query=query,
                search_time_ms=0,
                error="Vector search is not available"
            )
        
        top_k = top_k or self._default_top_k
        threshold = threshold or self._default_threshold
        
        try:
            # Generate query embedding
            logger.debug(f"Generating embedding for query: {query[:50]}...")
            query_embedding = self._embedding_service.embed_text(query)
            
            # Apply permission filtering if user_id provided
            if user_id is not None and event_ids is None and event_id is None:
                event_ids = self._get_accessible_event_ids(user_id)
                if not event_ids:
                    # User has no accessible events
                    elapsed = (time.time() - start_time) * 1000
                    return SearchResponse(
                        success=True,
                        results=[],
                        total=0,
                        query=query,
                        search_time_ms=elapsed
                    )
            
            # Search vector store
            raw_results = self._vector_store.similarity_search(
                query_embedding=query_embedding,
                event_id=event_id,
                event_ids=event_ids,
                top_k=top_k,
                threshold=threshold
            )
            
            # Convert to SearchResult objects
            results = [
                SearchResult(
                    content=r["content_text"],
                    similarity=r["similarity"],
                    event_id=r["event_id"],
                    attachment_id=r["attachment_id"],
                    chunk_index=r["chunk_index"],
                    metadata=r.get("metadata_json") or {}
                )
                for r in raw_results
            ]
            
            elapsed = (time.time() - start_time) * 1000
            
            logger.info(
                f"Search completed: {len(results)} results in {elapsed:.1f}ms"
            )
            
            return SearchResponse(
                success=True,
                results=results,
                total=len(results),
                query=query,
                search_time_ms=elapsed
            )
            
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Search failed: {e}", exc_info=True)
            return SearchResponse(
                success=False,
                results=[],
                total=0,
                query=query,
                search_time_ms=elapsed,
                error=str(e)
            )
    
    def _get_accessible_event_ids(self, user_id: int) -> list[int]:
        """Get event IDs accessible to a user.
        
        This is a placeholder that should integrate with Indico's
        permission system.
        
        Args:
            user_id: Indico user ID.
            
        Returns:
            List of accessible event IDs.
        """
        # Import here to avoid circular imports
        try:
            from indico_assistant.services.nl2sql.permissions import (
                get_user_accessible_event_ids
            )
            return get_user_accessible_event_ids(user_id)
        except ImportError:
            logger.warning(
                "Permission service not available, "
                "returning empty event list"
            )
            return []
    
    def get_stats(self, event_id: Optional[int] = None) -> dict[str, Any]:
        """Get search service statistics.
        
        Args:
            event_id: Optional event ID filter.
            
        Returns:
            Dictionary with service statistics.
        """
        store_stats = self._vector_store.get_stats(event_id)
        embedding_health = self._embedding_service.health_check()
        
        return {
            "available": self.is_available,
            "embedding_service": embedding_health,
            "vector_store": store_stats,
        }


def create_search_service(plugin: "AssistantPlugin") -> SearchService:
    """Factory function to create a SearchService.
    
    Args:
        plugin: The AssistantPlugin instance.
        
    Returns:
        Configured SearchService instance.
    """
    from indico_assistant.services.embedding import EmbeddingService
    
    embedding_service = EmbeddingService(plugin)
    vector_store = VectorStore()
    
    return SearchService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        default_top_k=plugin.settings.get("max_search_results", 5),
        default_threshold=plugin.settings.get("similarity_threshold", 0.7)
    )
