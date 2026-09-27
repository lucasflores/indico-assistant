"""Vector store for document chunks and embeddings.

Feature: 006-vector-search-rag
Tasks: T024, T025

Provides storage and retrieval of document chunks with pgvector embeddings.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import text

from indico.core.db import db
from indico_assistant.models.document import ExtractedDocument, ExtractionStatus
from indico_assistant.services.nl2sql import readonly_db
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
    
    def insert_chunks(self, chunks: list[dict[str, Any]], commit: bool = True) -> int:
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
        # One multi-row INSERT with the vector bound (it used to be INSERT + flush + UPDATE per chunk,
        # i.e. two statements and a dead tuple for every row).
        embedding_sql = "CAST(:embedding AS vector)" if self._pgvector_available else "NULL"
        embedding_col = ", embedding" if self._pgvector_available else ""
        rows = [{
            "id": str(uuid.uuid4()),
            "event_id": c["event_id"],
            "attachment_id": c["attachment_id"],
            "chunk_index": c["chunk_index"],
            "content_text": c["content_text"],
            "content_hash": c["content_hash"],
            "metadata": json.dumps(c.get("metadata")),
            "embedding": "[" + ",".join(str(float(x)) for x in c["embedding"]) + "]" if c.get("embedding") else None,
        } for c in chunks]
        db.session.execute(text(f"""
            INSERT INTO plugin_assistant.extracted_documents
                (id, event_id, attachment_id, chunk_index, content_text, content_hash, metadata_json,
                 extraction_status, created_at, updated_at{embedding_col})
            VALUES (CAST(:id AS uuid), :event_id, :attachment_id, :chunk_index, :content_text, :content_hash,
                    CAST(:metadata AS jsonb), 'completed', now(), now(){', ' + embedding_sql if embedding_col else ''})
        """), rows)
        if commit:
            db.session.commit()
        logger.debug(f"Inserted {len(rows)} chunks")
        return len(rows)

    def replace_attachment_chunks(self, attachment_id: int, chunks: list[dict[str, Any]]) -> int:
        """Swap an attachment's chunks in one transaction: search never sees it missing or half-done."""
        self.delete_attachment_chunks(attachment_id, commit=False)
        count = self.insert_chunks(chunks, commit=False)
        db.session.commit()
        return count

    def copy_chunks(self, source_attachment_id: int, attachment_id: int, event_id: int,
                    metadata: dict[str, Any]) -> int:
        """Give ``attachment_id`` the chunks (and embeddings) of an attachment with identical text.

        Cloned events and re-uploads carry the same documents; copying skips the embedding work.
        """
        self.delete_attachment_chunks(attachment_id, commit=False)
        embedding_col = ", embedding" if self._pgvector_available else ""
        count = db.session.execute(text(f"""
            INSERT INTO plugin_assistant.extracted_documents
                (id, event_id, attachment_id, chunk_index, content_text, content_hash, metadata_json,
                 extraction_status, created_at, updated_at{embedding_col})
            SELECT gen_random_uuid(), :event_id, :attachment_id, chunk_index, content_text, content_hash,
                   metadata_json || CAST(:metadata AS jsonb), extraction_status, now(), now(){embedding_col}
            FROM plugin_assistant.extracted_documents WHERE attachment_id = :source
        """), {"event_id": event_id, "attachment_id": attachment_id, "source": source_attachment_id,
              "metadata": json.dumps(metadata)}).rowcount
        db.session.commit()
        return count

    def find_attachment_with_hash(self, content_hash: str, exclude_attachment_id: int) -> Optional[int]:
        """Another attachment already indexed with this exact text (content_hash is indexed)."""
        return db.session.execute(text("""
            SELECT attachment_id FROM plugin_assistant.extracted_documents
            WHERE content_hash = :hash AND attachment_id <> :exclude LIMIT 1
        """), {"hash": content_hash, "exclude": exclude_attachment_id}).scalar()

    def is_current(self, attachment_id: int, file_id: int) -> bool:
        """Chunks exist for this version of the file (Indico file rows are immutable per version)."""
        return db.session.execute(text("""
            SELECT 1 FROM plugin_assistant.extracted_documents
            WHERE attachment_id = :attachment_id AND metadata_json->>'file_id' = :file_id LIMIT 1
        """), {"attachment_id": attachment_id, "file_id": str(file_id)}).scalar() is not None

    def update_attachment_metadata(self, attachment_id: int, metadata: dict[str, Any]) -> None:
        """Record a new file version whose text did not change (no re-embedding needed)."""
        db.session.execute(text("""
            UPDATE plugin_assistant.extracted_documents
            SET metadata_json = coalesce(metadata_json, '{}'::jsonb) || CAST(:metadata AS jsonb)
            WHERE attachment_id = :attachment_id
        """), {"attachment_id": attachment_id, "metadata": json.dumps(metadata)})
        db.session.commit()

    def delete_attachment_chunks(self, attachment_id: int, commit: bool = True) -> int:
        """Delete all chunks for an attachment.
        
        Args:
            attachment_id: Indico attachment ID.
            commit: False when part of a larger transaction (e.g. the request deleting the file).
            
        Returns:
            Number of chunks deleted.
        """
        result = ExtractedDocument.query.filter_by(
            attachment_id=attachment_id
        ).delete(synchronize_session=False)
        if commit:
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
    
    def check_duplicate_by_hash(
        self, 
        event_id: int, 
        content_hash: str
    ) -> Optional[dict[str, Any]]:
        """Check if document with given hash already exists for event.
        
        Feature: 011-realtime-attachment-indexing
        Task: T009
        
        Args:
            event_id: Indico event ID to scope search.
            content_hash: SHA256 hash of document content (64 hex chars).
            
        Returns:
            Dictionary with existing document info if duplicate found:
                - attachment_id: Existing attachment ID
                - chunk_count: Number of chunks for this document
                - content_hash: The matching hash
            None if no duplicate found.
            
        Example:
            >>> store = VectorStore()
            >>> result = store.check_duplicate_by_hash(123, "abc123...")
            >>> if result:
            ...     print(f"Duplicate: {result['chunk_count']} chunks")
            
        Contract:
            See contracts/indexing_task.yaml step 3_check_duplicate
        """
        # Query for any chunk with matching event_id and content_hash
        doc = ExtractedDocument.query.filter_by(
            event_id=event_id,
            content_hash=content_hash
        ).first()
        
        if not doc:
            return None
        
        # Count total chunks for this attachment
        chunk_count = ExtractedDocument.query.filter_by(
            event_id=event_id,
            attachment_id=doc.attachment_id
        ).count()
        
        return {
            "attachment_id": doc.attachment_id,
            "chunk_count": chunk_count,
            "content_hash": content_hash
        }
    
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
        context: "readonly_db.QueryContext",
        event_id: Optional[int] = None,
        event_ids: Optional[list[int]] = None,
        top_k: int = 5,
        threshold: float = 0.7
    ) -> list[dict[str, Any]]:
        """Find most similar document chunks.
        
        Args:
            query_embedding: Query embedding vector.
            context: Whose search this is; runs as the read-only role, so the row
                policies drop chunks of events and attachments the user cannot see.
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
        
        params: dict[str, Any] = {
            "top_k": top_k,
            "threshold": threshold,
            "embedding": "[" + ",".join(str(float(x)) for x in query_embedding) + "]",
        }
        event_filter = ""
        if event_id is not None:
            event_ids = [event_id]
        if event_ids:
            event_filter = "AND event_id = ANY(:event_ids)"
            params["event_ids"] = [int(e) for e in event_ids]
        
        query = text(f"""
            SELECT 
                id, event_id, attachment_id, chunk_index,
                content_text, metadata_json,
                1 - (embedding <=> CAST(:embedding AS vector)) as similarity
            FROM plugin_assistant.extracted_documents
            WHERE extraction_status = 'completed'
            AND embedding IS NOT NULL
            {event_filter}
            AND 1 - (embedding <=> CAST(:embedding AS vector)) >= :threshold
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """)
        
        with readonly_db.scoped_connection(context) as conn:
            result = conn.execute(query, params).fetchall()
        
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
        # One pass over the table (it used to be 8 separate COUNT(*) scans).
        indexed = "count(embedding)" if self._pgvector_available else "0"  # no column without pgvector
        rows = db.session.execute(text(f"""
            SELECT extraction_status, count(*) AS chunks,
                   count(DISTINCT attachment_id) AS documents, {indexed} AS indexed
            FROM plugin_assistant.extracted_documents
            WHERE (CAST(:event_id AS integer) IS NULL OR event_id = :event_id)
            GROUP BY ROLLUP (extraction_status)
        """), {"event_id": event_id}).fetchall()
        totals = next((r for r in rows if r.extraction_status is None), None)
        status_counts = {r.extraction_status: r.chunks for r in rows if r.extraction_status is not None}
        total_chunks = totals.chunks if totals else 0
        total_documents = totals.documents if totals else 0
        indexed_count = totals.indexed if totals else 0
        
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
