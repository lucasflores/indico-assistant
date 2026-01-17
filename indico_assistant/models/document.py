"""Document models for vector search.

Feature: 006-vector-search-rag
Tasks: T003, T004, T005
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from indico.core.db import db
from sqlalchemy import Column, DateTime, Integer, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB


class ExtractionStatus(str, Enum):
    """Status of document extraction process."""
    PENDING = "pending"        # Queued for processing
    PROCESSING = "processing"  # Currently being processed
    COMPLETED = "completed"    # Successfully extracted and embedded
    FAILED = "failed"          # Extraction or embedding failed
    SKIPPED = "skipped"        # Unsupported file type or empty content


class SyncStatus(str, Enum):
    """Status of document synchronization job."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractedDocument(db.Model):
    """Represents a document chunk with vector embedding.
    
    Each row stores a chunk of text extracted from an Indico attachment,
    along with its semantic embedding for similarity search.
    
    Attributes:
        id: Unique chunk identifier (UUID)
        event_id: Indico event ID reference
        attachment_id: Indico attachment ID reference
        chunk_index: Position within document (0-based)
        content_text: Extracted text content of chunk
        content_hash: SHA-256 hash for change detection
        embedding: Vector embedding (384 dimensions for bge-small)
                   Note: Actual vector column added via migration with pgvector
        metadata_json: Additional metadata (filename, page, etc.)
        extraction_status: Processing status
        error_message: Error details if extraction failed
        created_at: Record creation timestamp
        updated_at: Last update timestamp
    """
    
    __tablename__ = 'extracted_documents'
    __table_args__ = (
        Index(
            'ix_extracted_documents_event_attachment_chunk', 
            'event_id', 'attachment_id', 'chunk_index', 
            unique=True
        ),
        {'schema': 'plugin_assistant'}
    )

    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    event_id = Column(Integer, nullable=False, index=True)
    attachment_id = Column(Integer, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content_text = Column(Text, nullable=False)
    content_hash = Column(db.String(64), nullable=False, index=True)
    # Note: Vector column 'embedding' added via migration with pgvector
    # Cannot use SQLAlchemy Vector type directly without pgvector installed
    metadata_json = Column(JSONB, nullable=True)
    extraction_status = Column(
        db.String(20), 
        nullable=False, 
        default=ExtractionStatus.PENDING.value
    )
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<ExtractedDocument(id={self.id}, event_id={self.event_id}, "
            f"attachment_id={self.attachment_id}, chunk={self.chunk_index})>"
        )

    @classmethod
    def create(
        cls,
        event_id: int,
        attachment_id: int,
        chunk_index: int,
        content_text: str,
        content_hash: str,
        metadata: Optional[dict] = None,
        status: ExtractionStatus = ExtractionStatus.PENDING
    ) -> "ExtractedDocument":
        """Create a new extracted document chunk.
        
        Args:
            event_id: Indico event ID
            attachment_id: Indico attachment ID
            chunk_index: Position in document
            content_text: Extracted text content
            content_hash: SHA-256 hash of content
            metadata: Additional metadata dict
            status: Extraction status
            
        Returns:
            Newly created ExtractedDocument instance
        """
        doc = cls(
            event_id=event_id,
            attachment_id=attachment_id,
            chunk_index=chunk_index,
            content_text=content_text,
            content_hash=content_hash,
            metadata_json=metadata,
            extraction_status=status.value
        )
        db.session.add(doc)
        db.session.flush()
        return doc

    def update_status(
        self, 
        status: ExtractionStatus, 
        error_message: Optional[str] = None
    ) -> None:
        """Update extraction status.
        
        Args:
            status: New status
            error_message: Optional error message if status is FAILED
        """
        self.extraction_status = status.value
        if error_message:
            self.error_message = error_message
        db.session.flush()


class DocumentSyncLog(db.Model):
    """Tracks document synchronization and indexing jobs.
    
    Attributes:
        id: Unique sync job identifier
        event_id: Event scope (NULL = all events)
        started_at: When sync job started
        completed_at: When sync job completed
        documents_processed: Number of attachments processed
        chunks_created: Total chunks generated
        errors_count: Number of extraction errors
        status: Job status
        error_message: Error message if failed
    """
    
    __tablename__ = 'document_sync_log'
    __table_args__ = {'schema': 'plugin_assistant'}

    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    event_id = Column(Integer, nullable=True, index=True)
    started_at = Column(
        DateTime(timezone=True), 
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    documents_processed = Column(Integer, nullable=False, default=0)
    chunks_created = Column(Integer, nullable=False, default=0)
    errors_count = Column(Integer, nullable=False, default=0)
    status = Column(db.String(20), nullable=False, default=SyncStatus.RUNNING.value)
    error_message = Column(Text, nullable=True)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<DocumentSyncLog(id={self.id}, event_id={self.event_id}, "
            f"status={self.status})>"
        )

    @classmethod
    def start(cls, event_id: Optional[int] = None) -> "DocumentSyncLog":
        """Start a new sync log entry.
        
        Args:
            event_id: Optional event scope
            
        Returns:
            Newly created DocumentSyncLog instance
        """
        log = cls(
            event_id=event_id,
            status=SyncStatus.RUNNING.value
        )
        db.session.add(log)
        db.session.flush()
        return log

    def complete(
        self, 
        documents_processed: int = 0,
        chunks_created: int = 0,
        errors_count: int = 0
    ) -> None:
        """Mark sync job as completed.
        
        Args:
            documents_processed: Total documents processed
            chunks_created: Total chunks created
            errors_count: Number of errors
        """
        self.completed_at = datetime.now(timezone.utc)
        self.documents_processed = documents_processed
        self.chunks_created = chunks_created
        self.errors_count = errors_count
        self.status = SyncStatus.COMPLETED.value
        db.session.flush()

    def fail(self, error_message: str) -> None:
        """Mark sync job as failed.
        
        Args:
            error_message: Error description
        """
        self.completed_at = datetime.now(timezone.utc)
        self.status = SyncStatus.FAILED.value
        self.error_message = error_message
        db.session.flush()
