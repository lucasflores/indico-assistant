"""Vector store for document chunks and embeddings.

Feature: 006-vector-search-rag
Tasks: T024, T025

Provides storage and retrieval of document chunks with pgvector embeddings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import text

from indico.core.db import db
from indico_assistant.models.document import ExtractedDocument, ExtractionStatus
from indico_assistant.services.vector_search import check_pgvector_available

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class VectorStore:
    """Storage for document chunks with vector embeddings.
    
    Provides methods for inserting, retrieving, and searching
    document chunks using pgvector similarity operations.
    
    Example:
        >>> store = VectorStore()
        >>> store.insert_chunks([{
        ...     "event_id": 123,
        ...     "attachment_id": 456,
        ...     "chunk_index": 0,
        ...     "content_text": "Document text...",
        ...     "content_hash": "abc123...",
        ...     "embedding": [0.1, 0.2, ...],
        ...     "metadata": {"filename": "doc.pdf"}
        ... }])
    """
    
    def __init__(self) -> None:
        """Initialize the vector store."""
        self._pgvector_available = check_pgvector_available()
    
    @property
    def is_available(self) -> bool:
        """Check if vector operations are available."""
        return self._pgvector_available
    
    def insert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Insert document chunks with embeddings.
        
        Args:
            chunks: List of chunk dictionaries with keys:
                - event_id: Indico event ID
                - attachment_id: Indico attachment ID
                - chunk_index: Position in document
                - content_text: Chunk text content
                - content_hash: SHA-256 hash of full document
                - embedding: List of floats (384 dimensions)
                - metadata: Optional metadata dict
                
        Returns:
            Number of chunks inserted.
            
        Note:
            If pgvector is not available, chunks are inserted without
            embeddings (embedding column will be NULL).
        """
        if not chunks:
            return 0
        
        inserted = 0
        
        for chunk in chunks:
            doc = ExtractedDocument(
                event_id=chunk["event_id"],
                attachment_id=chunk["attachment_id"],
                chunk_index=chunk["chunk_index"],
                content_text=chunk["content_text"],
                content_hash=chunk["content_hash"],
                metadata_json=chunk.get("metadata"),
                extraction_status=ExtractionStatus.COMPLETED.value
            )
            db.session.add(doc)
            db.session.flush()  # Get the ID
            
            # Set embedding via raw SQL if pgvector available
            if self._pgvector_available and chunk.get("embedding"):
                self._set_embedding(doc.id, chunk["embedding"])
            
            inserted += 1
        
        db.session.commit()
        logger.debug(f"Inserted {inserted} chunks")
        return inserted
    
    def _set_embedding(self, doc_id: str, embedding: list[float]) -> None:
        """Set embedding for a document chunk via raw SQL.
        
        Args:
            doc_id: UUID of the ExtractedDocument.
            embedding: List of floats representing the embedding.
        """
        # Convert embedding to PostgreSQL array string format
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        
        db.session.execute(text("""
            UPDATE plugin_assistant.extracted_documents 
            SET embedding = :embedding::vector 
            WHERE id = :id
        """), {"embedding": embedding_str, "id": str(doc_id)})
    
    def delete_attachment_chunks(self, attachment_id: int) -> int:
        """Delete all chunks for an attachment.
        
        Args:
            attachment_id: Indico attachment ID.
            
        Returns:
            Number of chunks deleted.
        """
        result = ExtractedDocument.query.filter_by(
            attachment_id=attachment_id
        ).delete()
        db.session.commit()
        logger.debug(f"Deleted {result} chunks for attachment {attachment_id}")
        return result
    
    def delete_event_chunks(self, event_id: int) -> int:
        """Delete all chunks for an event.
        
        Args:
            event_id: Indico event ID.
            
        Returns:
            Number of chunks deleted.
        """
        result = ExtractedDocument.query.filter_by(
            event_id=event_id
        ).delete()
        db.session.commit()
        logger.debug(f"Deleted {result} chunks for event {event_id}")
        return result
    
    def get_content_hash(self, attachment_id: int) -> Optional[str]:
        """Get the content hash for an attachment.
        
        Used to check if document content has changed.
        
        Args:
            attachment_id: Indico attachment ID.
            
        Returns:
            Content hash string, or None if not found.
        """
        doc = ExtractedDocument.query.filter_by(
            attachment_id=attachment_id,
            chunk_index=0  # Check first chunk
        ).first()
        
        return doc.content_hash if doc else None
    
    def get_chunk_count(
        self, 
        event_id: Optional[int] = None,
        attachment_id: Optional[int] = None
    ) -> int:
        """Get count of document chunks.
        
        Args:
            event_id: Optional event ID filter.
            attachment_id: Optional attachment ID filter.
            
        Returns:
            Number of chunks matching filters.
        """
        query = ExtractedDocument.query
        
        if event_id is not None:
            query = query.filter_by(event_id=event_id)
        if attachment_id is not None:
            query = query.filter_by(attachment_id=attachment_id)
        
        return query.count()
    
    def get_document_count(self, event_id: Optional[int] = None) -> int:
        """Get count of unique documents (attachments).
        
        Args:
            event_id: Optional event ID filter.
            
        Returns:
            Number of unique attachment IDs.
        """
        query = db.session.query(
            ExtractedDocument.attachment_id
        ).distinct()
        
        if event_id is not None:
            query = query.filter(ExtractedDocument.event_id == event_id)
        
        return query.count()
    
    def similarity_search(
        self,
        query_embedding: list[float],
        event_id: Optional[int] = None,
        event_ids: Optional[list[int]] = None,
        top_k: int = 5,
        threshold: float = 0.7
    ) -> list[dict[str, Any]]:
        """Find most similar document chunks.
        
        Args:
            query_embedding: Query embedding vector.
            event_id: Optional single event ID filter.
            event_ids: Optional list of event IDs to search in.
            top_k: Maximum number of results.
            threshold: Minimum similarity threshold (0-1).
            
        Returns:
            List of result dictionaries with keys:
                - id: Chunk UUID
                - event_id: Indico event ID
                - attachment_id: Indico attachment ID
                - chunk_index: Position in document
                - content_text: Chunk text
                - metadata_json: Chunk metadata
                - similarity: Cosine similarity score (0-1)
                
        Note:
            Returns empty list if pgvector is not available.
        """
        if not self._pgvector_available:
            logger.warning("pgvector not available, returning empty results")
            return []
        
        # Build event filter
        event_filter = ""
        params: dict[str, Any] = {
            "query_embedding": "[" + ",".join(str(x) for x in query_embedding) + "]",
            "top_k": top_k,
            "threshold": threshold
        }
        
        if event_id is not None:
            event_filter = "AND event_id = :event_id"
            params["event_id"] = event_id
        elif event_ids is not None and event_ids:
            event_filter = "AND event_id = ANY(:event_ids)"
            params["event_ids"] = event_ids
        
        query = text(f"""
            SELECT 
                id, event_id, attachment_id, chunk_index,
                content_text, metadata_json,
                1 - (embedding <=> :query_embedding::vector) as similarity
            FROM plugin_assistant.extracted_documents
            WHERE extraction_status = 'completed'
            AND embedding IS NOT NULL
            {event_filter}
            AND 1 - (embedding <=> :query_embedding::vector) >= :threshold
            ORDER BY embedding <=> :query_embedding::vector
            LIMIT :top_k
        """)
        
        result = db.session.execute(query, params)
        
        rows = []
        for row in result:
            rows.append({
                "id": str(row.id),
                "event_id": row.event_id,
                "attachment_id": row.attachment_id,
                "chunk_index": row.chunk_index,
                "content_text": row.content_text,
                "metadata_json": row.metadata_json,
                "similarity": float(row.similarity)
            })
        
        logger.debug(
            f"Similarity search returned {len(rows)} results "
            f"(threshold={threshold}, top_k={top_k})"
        )
        return rows
    
    def get_stats(self, event_id: Optional[int] = None) -> dict[str, Any]:
        """Get vector store statistics.
        
        Args:
            event_id: Optional event ID filter.
            
        Returns:
            Dictionary with statistics.
        """
        query = ExtractedDocument.query
        if event_id is not None:
            query = query.filter_by(event_id=event_id)
        
        total_chunks = query.count()
        
        # Count by status
        status_counts = {}
        for status in ExtractionStatus:
            count = query.filter_by(extraction_status=status.value).count()
            status_counts[status.value] = count
        
        # Count unique documents
        doc_query = db.session.query(
            ExtractedDocument.attachment_id
        ).distinct()
        if event_id is not None:
            doc_query = doc_query.filter(ExtractedDocument.event_id == event_id)
        total_documents = doc_query.count()
        
        # Count with embeddings (if pgvector available)
        indexed_count = 0
        if self._pgvector_available:
            result = db.session.execute(text("""
                SELECT COUNT(*) FROM plugin_assistant.extracted_documents
                WHERE embedding IS NOT NULL
                AND (:event_id IS NULL OR event_id = :event_id)
            """), {"event_id": event_id})
            indexed_count = result.scalar() or 0
        
        return {
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "indexed": indexed_count,
            "pending": status_counts.get(ExtractionStatus.PENDING.value, 0),
            "completed": status_counts.get(ExtractionStatus.COMPLETED.value, 0),
            "failed": status_counts.get(ExtractionStatus.FAILED.value, 0),
            "skipped": status_counts.get(ExtractionStatus.SKIPPED.value, 0),
            "pgvector_available": self._pgvector_available,
        }
