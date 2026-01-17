# Data Model: Vector Search RAG

**Feature**: 006-vector-search-rag  
**Date**: 2026-01-16

## Overview

This feature introduces a new PostgreSQL table for storing extracted document chunks with vector embeddings, enabling semantic similarity search across event attachments. The table uses the pgvector extension for efficient vector storage and similarity operations.

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Indico Core                                   │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    │
│  │ Event       │───►│ Attachment   │───►│ File Storage    │    │
│  │ (events.*)  │    │ Folder/File  │    │ (filesystem)    │    │
│  └─────────────┘    └──────────────┘    └─────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
        │                    │
        │                    │ Reference (event_id, attachment_id)
        ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                plugin_assistant schema                           │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ExtractedDocument                                         │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ id (PK, UUID)                                             │  │
│  │ event_id (INT, NOT NULL, INDEX)                          │  │
│  │ attachment_id (INT, NOT NULL, INDEX)                     │  │
│  │ chunk_index (INT, NOT NULL)                              │  │
│  │ content_text (TEXT, NOT NULL)                            │  │
│  │ content_hash (VARCHAR(64), NOT NULL)                     │  │
│  │ embedding (VECTOR(384), NULLABLE)                        │  │
│  │ metadata_json (JSONB)                                     │  │
│  │ extraction_status (VARCHAR(20))                          │  │
│  │ error_message (TEXT, NULLABLE)                           │  │
│  │ created_at (TIMESTAMPTZ)                                 │  │
│  │ updated_at (TIMESTAMPTZ)                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ DocumentSyncLog                                           │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ id (PK, UUID)                                             │  │
│  │ event_id (INT, NULLABLE)                                  │  │
│  │ started_at (TIMESTAMPTZ)                                  │  │
│  │ completed_at (TIMESTAMPTZ, NULLABLE)                     │  │
│  │ documents_processed (INT)                                 │  │
│  │ chunks_created (INT)                                      │  │
│  │ errors_count (INT)                                        │  │
│  │ status (VARCHAR(20))                                      │  │
│  │ error_message (TEXT, NULLABLE)                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Existing Tables:                                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ ChatSession     │  │ ChatMessage     │  │ FeedbackEntry   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Entities

### ExtractedDocument

Stores document chunks with embeddings for similarity search.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Unique chunk identifier |
| event_id | Integer | NOT NULL, INDEX | Indico event ID reference |
| attachment_id | Integer | NOT NULL, INDEX | Indico attachment ID reference |
| chunk_index | Integer | NOT NULL | Position within document (0-based) |
| content_text | Text | NOT NULL | Extracted text content of chunk |
| content_hash | String(64) | NOT NULL | SHA-256 hash for change detection |
| embedding | Vector(384) | NULLABLE, INDEX (HNSW) | Semantic embedding vector |
| metadata_json | JSONB | NULLABLE | Additional metadata (see below) |
| extraction_status | String(20) | NOT NULL, DEFAULT 'pending' | Status: pending, completed, failed |
| error_message | Text | NULLABLE | Error details if extraction failed |
| created_at | DateTime | NOT NULL, DEFAULT now() | Record creation timestamp |
| updated_at | DateTime | NOT NULL, DEFAULT now() | Last update timestamp |

**Indexes**:
- `ix_extracted_documents_event` on (event_id)
- `ix_extracted_documents_attachment` on (attachment_id)
- `ix_extracted_documents_event_attachment` on (event_id, attachment_id) UNIQUE with chunk_index
- `ix_extracted_documents_embedding` on (embedding) USING hnsw (vector_cosine_ops)
- `ix_extracted_documents_hash` on (content_hash)

**Unique Constraint**: (event_id, attachment_id, chunk_index)

**metadata_json Schema**:
```json
{
  "filename": "presentation.pdf",
  "file_type": "pdf",
  "file_size": 1024000,
  "page_number": 5,
  "total_pages": 20,
  "total_chunks": 15,
  "char_start": 4500,
  "char_end": 5500,
  "extraction_method": "pypdf2",
  "model_name": "BAAI/bge-small-en-v1.5"
}
```

### DocumentSyncLog

Tracks document synchronization and indexing jobs.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, default uuid4 | Unique sync job identifier |
| event_id | Integer | NULLABLE, INDEX | Event scope (NULL = all events) |
| started_at | DateTime | NOT NULL | When sync job started |
| completed_at | DateTime | NULLABLE | When sync job completed |
| documents_processed | Integer | NOT NULL, DEFAULT 0 | Number of attachments processed |
| chunks_created | Integer | NOT NULL, DEFAULT 0 | Total chunks generated |
| errors_count | Integer | NOT NULL, DEFAULT 0 | Number of extraction errors |
| status | String(20) | NOT NULL, CHECK | Status: running, completed, failed |
| error_message | Text | NULLABLE | Error message if status=failed |

**Indexes**:
- `ix_document_sync_log_started` on (started_at DESC)
- `ix_document_sync_log_event` on (event_id)

## Enums

### ExtractionStatus

```python
class ExtractionStatus(str, Enum):
    PENDING = "pending"      # Queued for processing
    PROCESSING = "processing"  # Currently being processed
    COMPLETED = "completed"  # Successfully extracted and embedded
    FAILED = "failed"        # Extraction or embedding failed
    SKIPPED = "skipped"      # Unsupported file type or empty content
```

### SyncStatus

```python
class SyncStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

## SQLAlchemy Model Definition

```python
"""ExtractedDocument model for vector search.

Feature: 006-vector-search-rag
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from indico.core.db import db
from sqlalchemy import Column, DateTime, Integer, Text, Index, text
from sqlalchemy.dialects.postgresql import UUID, JSONB


class ExtractionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExtractedDocument(db.Model):
    """Represents a document chunk with vector embedding.
    
    Each row stores a chunk of text extracted from an Indico attachment,
    along with its semantic embedding for similarity search.
    """
    
    __tablename__ = 'extracted_documents'
    __table_args__ = (
        Index('ix_extracted_documents_event_attachment_chunk', 
              'event_id', 'attachment_id', 'chunk_index', unique=True),
        {'schema': 'plugin_assistant'}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(Integer, nullable=False, index=True)
    attachment_id = Column(Integer, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content_text = Column(Text, nullable=False)
    content_hash = Column(db.String(64), nullable=False, index=True)
    # Note: Vector column added via migration with pgvector
    # embedding = Column(Vector(384))  
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
```

## Migration Script

```python
"""Create extracted_documents table for vector search.

Feature: 006-vector-search-rag
Revision ID: 004_create_extracted_documents
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '004_create_extracted_documents'
down_revision = '003_create_observability_tables'
branch_labels = None
depends_on = None


def check_pgvector():
    """Check if pgvector extension is available."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
    ))
    return result.scalar()


def upgrade():
    # Try to create pgvector extension (may require superuser)
    try:
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')
        has_pgvector = True
    except Exception:
        has_pgvector = check_pgvector()
    
    # Create extracted_documents table
    op.create_table(
        'extracted_documents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('event_id', sa.Integer, nullable=False),
        sa.Column('attachment_id', sa.Integer, nullable=False),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('content_text', sa.Text, nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('metadata_json', JSONB, nullable=True),
        sa.Column('extraction_status', sa.String(20), nullable=False, 
                  server_default='pending'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        schema='plugin_assistant'
    )
    
    # Add vector column if pgvector available
    if has_pgvector:
        op.execute('''
            ALTER TABLE plugin_assistant.extracted_documents 
            ADD COLUMN embedding vector(384)
        ''')
        
        # Create HNSW index for similarity search
        op.execute('''
            CREATE INDEX ix_extracted_documents_embedding 
            ON plugin_assistant.extracted_documents 
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        ''')
    
    # Create other indexes
    op.create_index(
        'ix_extracted_documents_event', 
        'extracted_documents', ['event_id'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_extracted_documents_attachment', 
        'extracted_documents', ['attachment_id'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_extracted_documents_hash', 
        'extracted_documents', ['content_hash'],
        schema='plugin_assistant'
    )
    op.create_index(
        'ix_extracted_documents_event_attachment_chunk',
        'extracted_documents',
        ['event_id', 'attachment_id', 'chunk_index'],
        unique=True,
        schema='plugin_assistant'
    )
    
    # Create document_sync_log table
    op.create_table(
        'document_sync_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('event_id', sa.Integer, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('documents_processed', sa.Integer, nullable=False, 
                  server_default='0'),
        sa.Column('chunks_created', sa.Integer, nullable=False, 
                  server_default='0'),
        sa.Column('errors_count', sa.Integer, nullable=False, 
                  server_default='0'),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error_message', sa.Text, nullable=True),
        schema='plugin_assistant'
    )
    
    op.create_index(
        'ix_document_sync_log_started',
        'document_sync_log', ['started_at'],
        schema='plugin_assistant'
    )


def downgrade():
    op.drop_table('document_sync_log', schema='plugin_assistant')
    op.drop_table('extracted_documents', schema='plugin_assistant')
```

## Query Patterns

### Insert Document Chunk

```python
def insert_chunk(
    event_id: int,
    attachment_id: int,
    chunk_index: int,
    content: str,
    embedding: list[float] | None,
    metadata: dict
) -> ExtractedDocument:
    """Insert a new document chunk with embedding."""
    doc = ExtractedDocument(
        event_id=event_id,
        attachment_id=attachment_id,
        chunk_index=chunk_index,
        content_text=content,
        content_hash=compute_hash(content),
        metadata_json=metadata,
        extraction_status=ExtractionStatus.COMPLETED.value
    )
    db.session.add(doc)
    
    # Set embedding via raw SQL for pgvector
    if embedding:
        db.session.flush()
        db.session.execute(text("""
            UPDATE plugin_assistant.extracted_documents 
            SET embedding = :embedding 
            WHERE id = :id
        """), {"embedding": str(embedding), "id": doc.id})
    
    return doc
```

### Similarity Search

```python
def search_similar(
    query_embedding: list[float],
    event_id: int | None = None,
    top_k: int = 5,
    threshold: float = 0.7
) -> list[dict]:
    """Find most similar document chunks."""
    result = db.session.execute(text("""
        SELECT 
            id, event_id, attachment_id, chunk_index,
            content_text, metadata_json,
            1 - (embedding <=> :query_embedding) as similarity
        FROM plugin_assistant.extracted_documents
        WHERE extraction_status = 'completed'
        AND embedding IS NOT NULL
        AND (:event_id IS NULL OR event_id = :event_id)
        AND 1 - (embedding <=> :query_embedding) >= :threshold
        ORDER BY embedding <=> :query_embedding
        LIMIT :top_k
    """), {
        "query_embedding": str(query_embedding),
        "event_id": event_id,
        "top_k": top_k,
        "threshold": threshold
    })
    return [dict(row._mapping) for row in result]
```

### Delete Document Chunks

```python
def delete_attachment_chunks(attachment_id: int) -> int:
    """Delete all chunks for an attachment."""
    result = ExtractedDocument.query.filter_by(
        attachment_id=attachment_id
    ).delete()
    return result
```

### Check Content Changed

```python
def content_changed(attachment_id: int, new_hash: str) -> bool:
    """Check if document content has changed."""
    existing = ExtractedDocument.query.filter_by(
        attachment_id=attachment_id,
        chunk_index=0  # Check first chunk
    ).first()
    
    if not existing:
        return True  # New document
    
    return existing.content_hash != new_hash
```
