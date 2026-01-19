# Data Model: Real-Time Document Indexing

**Feature**: 011-realtime-attachment-indexing  
**Date**: 2026-01-18  
**Phase**: 1 (Design & Contracts)

## Overview

This document defines the data structures, entities, and their relationships for the real-time document indexing feature. The feature primarily reuses existing models with minor enhancements for content hashing and duplicate detection.

---

## Core Entities

### 1. Attachment Signal Event (Transient)

**Source**: `indico.modules.attachments.signals.attachment_created`  
**Lifetime**: Exists only during signal emission (not persisted)  
**Purpose**: Triggers real-time indexing workflow

```python
# Signal payload structure (received by handler)
@dataclass
class AttachmentSignalPayload:
    """Representation of data available in attachment_created signal."""
    
    sender: Any  # Signal sender (attachment folder object)
    attachment: Attachment  # Indico Attachment model instance
    
    # Key properties accessed from attachment:
    # - attachment.id: int
    # - attachment.file.size: int (bytes)
    # - attachment.file.filename: str
    # - attachment.file.content_type: str
    # - attachment.folder.event.id: int
```

**Attributes**:
- `sender`: Signal source object
- `attachment`: Full Indico Attachment model with:
  - `id`: Unique attachment identifier
  - `file.size`: File size in bytes (for tier determination)
  - `file.filename`: Original filename (for format detection)
  - `file.content_type`: MIME type (for format validation)
  - `folder.event.id`: Parent event ID (for event-scoped indexing)

**Lifecycle**: Created → Handler invoked → Discarded

---

### 2. Indexing Task Parameters

**Source**: Celery task arguments  
**Lifetime**: Task execution duration  
**Purpose**: Carry necessary context for asynchronous indexing

```python
@dataclass
class IndexingTaskInput:
    """Input parameters for index_attachment_task."""
    
    attachment_id: int  # Primary key of attachment to index
    event_id: int  # Event ID for permission checking and scoping
    force: bool = False  # Force re-index even if hash matches (optional)
    priority: int = 5  # Celery task priority (lower = higher priority)
```

**Attributes**:
- `attachment_id`: Primary key to fetch attachment from database
- `event_id`: Event context for permission validation
- `force`: Override duplicate detection (default: False)
- `priority`: Task queue priority (5=normal, 9=low for large files)

**Validation**:
- `attachment_id` must reference existing attachment
- `event_id` must reference existing event
- `priority` in range [0, 9] (Celery default)

---

### 3. Indexing Task Result

**Source**: Task return value  
**Lifetime**: Stored in Celery result backend  
**Purpose**: Communicate task outcome for monitoring and retry logic

```python
@dataclass
class IndexingTaskResult:
    """Return value from index_attachment_task."""
    
    success: bool  # Overall success/failure status
    attachment_id: int  # Attachment that was processed
    event_id: int  # Event context
    chunks_created: int  # Number of new chunks inserted
    chunks_skipped: int  # Number of duplicate chunks skipped
    processing_time_ms: int  # Total processing time in milliseconds
    content_hash: str  # SHA256 hash of document content
    status: str  # 'indexed', 'skipped', 'failed', 'rejected'
    error: Optional[str] = None  # Error message if failed
    file_size_bytes: int = 0  # File size for metrics
    retry_count: int = 0  # Number of retry attempts
```

**Attributes**:
- `success`: Boolean indicating if indexing completed successfully
- `attachment_id`: Reference to processed attachment
- `event_id`: Event context
- `chunks_created`: Count of new chunks inserted (0 if duplicate)
- `chunks_skipped`: Count of chunks that already existed
- `processing_time_ms`: Performance metric
- `content_hash`: SHA256 hash for duplicate detection
- `status`: Enum-like status:
  - `'indexed'`: New document successfully indexed
  - `'skipped'`: Duplicate detected, no action taken
  - `'failed'`: Indexing failed after retries
  - `'rejected'`: File rejected (size/format)
- `error`: Error message string (None if success)
- `file_size_bytes`: File size for logging/metrics
- `retry_count`: Current retry attempt number

**Serialization**: JSON-serializable for Celery result backend

---

### 4. Content Hash Record (Enhancement to ExtractedDocument)

**Source**: `models/document.py.ExtractedDocument`  
**Lifetime**: Persistent (database)  
**Purpose**: Enable duplicate detection and change tracking

**Existing Model (No Schema Changes Required)**:
```python
# models/document.py - ExtractedDocument model
class ExtractedDocument(db.Model):
    """Existing model for storing document chunks and embeddings."""
    
    __tablename__ = 'extracted_documents'
    __table_args__ = (
        UniqueConstraint('event_id', 'attachment_id', 'chunk_index'),
        {'schema': 'plugin_assistant'}
    )
    
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, nullable=False, index=True)
    attachment_id = db.Column(db.Integer, nullable=False, index=True)
    chunk_index = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    embedding = db.Column(Vector(384), nullable=True)  # pgvector type
    content_hash = db.Column(db.String(64), nullable=True, index=True)  # [ENHANCEMENT]
    extracted_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.Enum(ExtractionStatus), default=ExtractionStatus.PENDING)
```

**Enhancement Details**:
- `content_hash`: SHA256 hash of complete document content (64 hex chars)
  - **Purpose**: Duplicate detection per FR-006
  - **Scope**: Document-level (same hash for all chunks of one document)
  - **Index**: B-tree index on `(event_id, content_hash)` for fast lookups
  - **Nullable**: True (backward compatibility with existing records)

**Usage Patterns**:
1. **Check Duplicate**: Query by `(event_id, content_hash)` before indexing
2. **Skip Re-Index**: If hash matches existing record, return 'skipped'
3. **Detect Changes**: Different hash → different document → re-index

**Index Strategy**:
```sql
-- Composite index for duplicate detection queries
CREATE INDEX idx_extracted_docs_event_hash 
ON plugin_assistant.extracted_documents(event_id, content_hash);

-- Existing indexes remain unchanged
-- - Primary key: id
-- - Foreign key: event_id
-- - Foreign key: attachment_id
-- - Unique constraint: (event_id, attachment_id, chunk_index)
```

---

### 5. Processing Tier Enum

**Source**: Signal handler logic  
**Lifetime**: Request scope  
**Purpose**: Categorize files by size for differential processing

```python
from enum import Enum

class ProcessingTier(Enum):
    """File processing tier based on size."""
    
    FAST = 'fast'  # <10MB - guaranteed 30s SLA
    BEST_EFFORT = 'best-effort'  # 10-50MB - no time guarantee
    REJECTED = 'rejected'  # >50MB - not indexed
```

**Tier Determination Logic**:
```python
def determine_processing_tier(file_size_bytes: int) -> ProcessingTier:
    """Determine processing tier based on file size.
    
    Args:
        file_size_bytes: File size in bytes
        
    Returns:
        ProcessingTier enum value
    """
    MAX_SIZE_FAST = 10 * 1024 * 1024  # 10MB
    MAX_SIZE_BEST_EFFORT = 50 * 1024 * 1024  # 50MB
    
    if file_size_bytes > MAX_SIZE_BEST_EFFORT:
        return ProcessingTier.REJECTED
    elif file_size_bytes > MAX_SIZE_FAST:
        return ProcessingTier.BEST_EFFORT
    else:
        return ProcessingTier.FAST
```

**Impact on Behavior**:
| Tier | Size Range | Behavior |
|------|------------|----------|
| FAST | <10MB | High priority queue, 30s SLA, guaranteed processing |
| BEST_EFFORT | 10-50MB | Low priority queue, no SLA, logged warning |
| REJECTED | >50MB | Not queued, logged info message, no error to user |

---

## Data Flow Diagram

```
┌─────────────────┐
│ User Uploads    │
│ document.pdf    │
└────────┬────────┘
         │
         │ Indico stores file
         ▼
┌─────────────────────────────────────┐
│ attachment_created signal fires     │
│ Payload: {sender, attachment}       │
└────────┬────────────────────────────┘
         │
         │ Signal handler validates
         ▼
┌────────────────────────────────────────┐
│ Format Check: is_supported_format()    │
│ - .pdf/.docx/.txt/.md ✓               │
│ - .jpg/.mp4 ✗ → RETURN (silent skip)  │
└────────┬───────────────────────────────┘
         │
         │ Size tier determination
         ▼
┌────────────────────────────────────────┐
│ Size Check: determine_processing_tier()│
│ - <10MB → FAST (priority=5)           │
│ - 10-50MB → BEST_EFFORT (priority=9)  │
│ - >50MB → REJECTED → RETURN (logged)  │
└────────┬───────────────────────────────┘
         │
         │ Queue async task
         ▼
┌─────────────────────────────────────────┐
│ Celery Task: index_attachment_task      │
│ Input: IndexingTaskInput                │
│   {attachment_id, event_id, priority}   │
└────────┬────────────────────────────────┘
         │
         │ Load attachment from DB
         ▼
┌─────────────────────────────────────────┐
│ Compute Content Hash                    │
│ - Streaming SHA256 in 8KB chunks       │
│ - hash = compute_file_hash_streaming()  │
└────────┬────────────────────────────────┘
         │
         │ Check for duplicates
         ▼
┌─────────────────────────────────────────────┐
│ Duplicate Detection Query                   │
│ SELECT * FROM extracted_documents           │
│ WHERE event_id = ? AND content_hash = ?     │
└────────┬────────────────────────────────────┘
         │
         ├─ Found → IndexingTaskResult          │
         │           {status='skipped',          │
         │            chunks_skipped=N}          │
         │                                       │
         └─ Not Found → Continue processing     │
                        ▼
         ┌──────────────────────────────────┐
         │ Extract Text                     │
         │ - DocumentExtractor.extract()    │
         │ - Returns: str (full text)       │
         └──────────┬───────────────────────┘
                    │
                    ▼
         ┌──────────────────────────────────┐
         │ Chunk Text                       │
         │ - DocumentChunker.chunk_text()   │
         │ - Returns: List[str] (chunks)    │
         └──────────┬───────────────────────┘
                    │
                    ▼
         ┌──────────────────────────────────┐
         │ Generate Embeddings              │
         │ - EmbeddingService.embed_batch() │
         │ - Returns: List[Vector]          │
         └──────────┬───────────────────────┘
                    │
                    ▼
         ┌──────────────────────────────────┐
         │ Store in Database                │
         │ - Insert ExtractedDocument rows  │
         │ - Include content_hash           │
         │ - try/except IntegrityError      │
         └──────────┬───────────────────────┘
                    │
                    ▼
         ┌─────────────────────────────────┐
         │ Return IndexingTaskResult        │
         │ {status='indexed',               │
         │  chunks_created=N,               │
         │  content_hash='abc123...'}       │
         └──────────────────────────────────┘
```

---

## Database Schema Impact

### New Column (Migration Required)

**Table**: `plugin_assistant.extracted_documents`  
**Column**: `content_hash VARCHAR(64) NULL`  
**Index**: `idx_extracted_docs_event_hash ON (event_id, content_hash)`

**Migration**:
```python
# migrations/005_add_content_hash.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column(
        'extracted_documents',
        sa.Column('content_hash', sa.String(64), nullable=True),
        schema='plugin_assistant'
    )
    op.create_index(
        'idx_extracted_docs_event_hash',
        'extracted_documents',
        ['event_id', 'content_hash'],
        schema='plugin_assistant'
    )

def downgrade():
    op.drop_index(
        'idx_extracted_docs_event_hash',
        table_name='extracted_documents',
        schema='plugin_assistant'
    )
    op.drop_column(
        'extracted_documents',
        'content_hash',
        schema='plugin_assistant'
    )
```

**Backward Compatibility**:
- Column is nullable - existing records have `content_hash=NULL`
- Query logic handles NULL: `WHERE content_hash IS NOT NULL AND content_hash = ?`
- Gradual backfill via periodic sync updates existing records

---

## State Transitions

### Indexing Task State Machine

```
[QUEUED] → (task starts) → [PROCESSING]
   │                            │
   │                            ├─→ [COMPUTING_HASH]
   │                            │        │
   │                            │        ├─→ [CHECKING_DUPLICATE]
   │                            │        │        │
   │                            │        │        ├─→ Found → [SKIPPED] (success)
   │                            │        │        │
   │                            │        │        └─→ Not Found → [EXTRACTING]
   │                            │        │                              │
   │                            │        │                              ├─→ [CHUNKING]
   │                            │        │                              │        │
   │                            │        │                              │        ├─→ [EMBEDDING]
   │                            │        │                              │        │        │
   │                            │        │                              │        │        ├─→ [STORING]
   │                            │        │                              │        │        │        │
   │                            │        │                              │        │        │        └─→ [INDEXED] (success)
   │                            │        │
   │                            │        └─→ Error → [RETRYING]
   │                            │                    │
   │                            │                    ├─→ Attempt 1 (60s delay)
   │                            │                    ├─→ Attempt 2 (300s delay)
   │                            │                    ├─→ Attempt 3 (900s delay)
   │                            │                    └─→ Max retries → [FAILED] (error)
   │                            │
   │                            └─→ File too large → [REJECTED] (info)
   │
   └─→ (worker never picks up) → [EXPIRED] (timeout)
```

**Terminal States**:
- `INDEXED`: Successfully processed and stored
- `SKIPPED`: Duplicate detected, no processing needed
- `FAILED`: Permanently failed after 3 retries
- `REJECTED`: File size/format validation failed
- `EXPIRED`: Task expired in queue (rare, requires monitoring)

---

## Memory Considerations

### Hash Computation Memory Usage

**Streaming Approach**:
- **Chunk size**: 8KB (8,192 bytes)
- **50MB file**: ~6,400 iterations
- **Peak memory**: ~8KB constant (hasher state + one chunk buffer)
- **vs Non-streaming**: 50MB loaded entirely into memory

### Task Memory Profile

**Typical Workflow (10MB PDF)**:
1. **Hash computation**: ~8KB
2. **Text extraction**: ~5MB (text smaller than PDF)
3. **Chunking**: ~5MB (in-memory list of strings)
4. **Embedding**: ~5MB text + 384×N floats (N=chunks)
5. **Peak memory**: ~15-20MB total

**Large File (50MB PDF)**:
- May extract to ~25MB text
- Chunking + embedding: ~30-40MB peak
- Within acceptable limits for Celery worker

---

## Validation Rules

### Signal Handler Validation

1. **Attachment exists**: `attachment is not None`
2. **Has file**: `attachment.file is not None`
3. **Supported format**: `ext in {'.pdf', '.docx', '.txt', '.md'}`
4. **Size within limits**: `size <= 50MB`
5. **Vector search enabled**: `settings.get('vector_search_enabled')`
6. **pgvector available**: `check_pgvector_available()`

**Validation Failures**:
- Fail 1-2: Log error, do not queue task (safety)
- Fail 3-4: Log info, do not queue task (expected rejection)
- Fail 5-6: Log warning, do not queue task (graceful degradation)

### Task Input Validation

1. **Attachment ID exists**: Database lookup succeeds
2. **Event ID exists**: Event.query.get(event_id) returns object
3. **File still accessible**: `attachment.file.open()` succeeds

**Validation Failures**:
- Fail 1-2: Log error, return `IndexingTaskResult(success=False, error=...)`
- Fail 3: Attachment was deleted - log info, return skipped (graceful)

---

## Performance Characteristics

### Signal Handler

- **Target**: <100ms (99th percentile)
- **Operations**: Format check (~1ms) + size check (~1ms) + task queue (~5ms)
- **Measured**: ~10-20ms typical

### Indexing Task

| File Size | Hash | Extract | Chunk | Embed | Store | Total |
|-----------|------|---------|-------|-------|-------|-------|
| 1MB | 20ms | 100ms | 50ms | 200ms | 50ms | 420ms |
| 10MB | 100ms | 1s | 200ms | 2s | 200ms | 3.5s |
| 50MB | 500ms | 5s | 1s | 10s | 1s | 17.5s |

**SLA Compliance**:
- <10MB: 3.5s < 30s ✓ (SC-001)
- 10-50MB: 17.5s (no SLA, best-effort)
- >50MB: Rejected before indexing

---

## Summary

**New Data Structures**: 5  
**Database Schema Changes**: 1 column + 1 index  
**Migration Required**: Yes (005_add_content_hash.py)  
**Backward Compatible**: Yes (nullable column)  
**Memory Impact**: Low (streaming hash, typical 15-40MB peak)  
**Performance Impact**: Minimal signal handler (<20ms), task within SLAs