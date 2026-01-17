# Research: Vector Search RAG

**Feature**: 006-vector-search-rag  
**Date**: 2026-01-16

## Research Tasks Completed

### 1. Embedding Model Selection

**Decision**: Use sentence-transformers library with BAAI/bge-small-en-v1.5 as default

**Rationale**:
- BAAI/bge-small-en-v1.5 provides excellent quality-to-size ratio (33M params, 384 dimensions)
- Fast inference suitable for batch processing
- Well-supported by sentence-transformers library
- Open source, no API costs
- Configurable to allow alternatives (e.g., OpenAI embeddings) via settings

**Alternatives Considered**:
- OpenAI ada-002: Excellent quality but requires API, costs per token, latency
- all-MiniLM-L6-v2: Smaller but lower quality for technical content
- Instructor embeddings: More complex setup for minimal benefit

**Key API Patterns**:
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('BAAI/bge-small-en-v1.5')

# Batch embedding for efficiency
texts = ["document chunk 1", "document chunk 2", "document chunk 3"]
embeddings = model.encode(texts, normalize_embeddings=True)
# Returns numpy array of shape (3, 384)
```

### 2. Vector Storage with pgvector

**Decision**: Use pgvector PostgreSQL extension with HNSW index

**Rationale**:
- PostgreSQL already used by Indico - no new infrastructure
- pgvector is mature, well-documented, actively maintained
- HNSW provides excellent search quality with good performance
- IVFFlat available as fallback for very large datasets
- Cosine similarity via `<=>` operator

**Schema Design**:
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE plugin_assistant.extracted_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id INTEGER NOT NULL,
    attachment_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    content_text TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    embedding vector(384),  -- 384 dims for bge-small
    metadata_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast similarity search
CREATE INDEX ON plugin_assistant.extracted_documents 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

**Graceful Degradation**:
```python
def check_pgvector_available():
    """Check if pgvector extension is available."""
    try:
        db.session.execute(text("SELECT 'vector'::regtype"))
        return True
    except Exception:
        return False
```

### 3. Document Text Extraction

**Decision**: Use PyPDF2 for PDF, python-docx for DOCX, built-in for text

**Rationale**:
- PyPDF2: Lightweight, pure Python, handles most PDFs
- python-docx: Standard library for DOCX, well-maintained
- Plain text: Built-in Python file handling
- Fallback to pdfplumber for complex PDFs if needed

**Extraction Patterns**:
```python
# PDF extraction
from PyPDF2 import PdfReader

def extract_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

# DOCX extraction  
from docx import Document

def extract_docx(file_path: str) -> str:
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs)

# Text files
def extract_text(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()
```

### 4. Document Chunking Strategy

**Decision**: Use recursive character splitting with configurable size and overlap

**Rationale**:
- Preserves semantic coherence by respecting sentence boundaries
- Overlap ensures context continuity between chunks
- Configurable for different use cases
- Simple, predictable, debuggable

**Default Parameters**:
- Chunk size: 1000 characters
- Overlap: 200 characters
- Separators: ["\n\n", "\n", ". ", " ", ""]

**Implementation Pattern**:
```python
def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[dict]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    chunk_index = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence end within last 100 chars
            for sep in [". ", ".\n", "\n\n", "\n"]:
                pos = text.rfind(sep, start + chunk_size - 100, end)
                if pos > start:
                    end = pos + len(sep)
                    break
        
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                "text": chunk_text,
                "start": start,
                "end": end,
                "chunk_index": chunk_index
            })
            chunk_index += 1
        
        start = end - overlap
    
    return chunks
```

### 5. Similarity Search Implementation

**Decision**: Use pgvector's cosine distance operator with optional filtering

**Rationale**:
- Native PostgreSQL query with vector operations
- Can combine with WHERE clauses for filtering
- Index-accelerated search
- Returns distance that can be converted to similarity

**Query Pattern**:
```python
def similarity_search(
    query_embedding: list[float],
    event_id: int | None = None,
    top_k: int = 5,
    threshold: float = 0.7
) -> list[dict]:
    """Find most similar document chunks."""
    query = text("""
        SELECT 
            id, event_id, attachment_id, chunk_index,
            content_text, metadata_json,
            1 - (embedding <=> :query_embedding) as similarity
        FROM plugin_assistant.extracted_documents
        WHERE 1=1
        AND (:event_id IS NULL OR event_id = :event_id)
        AND 1 - (embedding <=> :query_embedding) >= :threshold
        ORDER BY embedding <=> :query_embedding
        LIMIT :top_k
    """)
    
    result = db.session.execute(query, {
        "query_embedding": str(query_embedding),
        "event_id": event_id,
        "top_k": top_k,
        "threshold": threshold
    })
    return [dict(row) for row in result]
```

### 6. RAG Integration Strategy

**Decision**: Query-aware retrieval with context injection in chat pipeline

**Rationale**:
- Not all queries benefit from document context
- Classifier determines if query is SQL-based or document-based
- Document context added to LLM prompt when relevant
- Citations preserve source traceability

**Integration Pattern**:
```python
def should_use_document_context(question: str, event_id: int) -> bool:
    """Determine if document retrieval would benefit this query."""
    # Use classifier to detect intent
    # Document-related: "what does the presentation say about..."
    # SQL-related: "how many registrations..."
    pass

def build_rag_context(chunks: list[dict]) -> str:
    """Build context string from document chunks."""
    context_parts = []
    for chunk in chunks:
        source = chunk.get("metadata_json", {}).get("filename", "document")
        context_parts.append(f"From {source}:\n{chunk['content_text']}")
    return "\n\n---\n\n".join(context_parts)
```

### 7. Background Processing with Celery

**Decision**: Use existing Celery infrastructure with dedicated task queue

**Rationale**:
- Celery already used by plugin (Feature 004, 005)
- Document processing is CPU-intensive, should not block requests
- Supports retry, progress tracking, rate limiting

**Task Structure**:
```python
@celery_task
def process_attachment(attachment_id: int):
    """Process a single attachment for indexing."""
    # 1. Fetch attachment file
    # 2. Extract text based on file type
    # 3. Chunk text
    # 4. Generate embeddings (batch)
    # 5. Store in database
    pass

@celery_task
def sync_event_documents(event_id: int):
    """Sync all documents for an event."""
    attachments = get_event_attachments(event_id)
    for att in attachments:
        if needs_processing(att):
            process_attachment.delay(att.id)
```

### 8. Caching Strategy

**Decision**: Content-hash based caching to avoid reprocessing

**Rationale**:
- Documents change infrequently
- Embedding generation is expensive
- Hash comparison is cheap
- Store hash in database for comparison

**Implementation**:
```python
import hashlib

def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()

def needs_reprocessing(attachment_id: int, new_content: str) -> bool:
    """Check if document needs reprocessing."""
    existing = ExtractedDocument.query.filter_by(
        attachment_id=attachment_id
    ).first()
    if not existing:
        return True
    return existing.content_hash != compute_content_hash(new_content)
```

### 9. Permission Handling

**Decision**: Filter search results based on user's event access permissions

**Rationale**:
- Indico has existing permission system
- Documents inherit permissions from parent event
- Filter at search time, not index time
- Preserves index for all users while respecting access control

**Implementation**:
```python
def search_with_permissions(
    query_embedding: list[float],
    user_id: int,
    event_id: int | None = None
) -> list[dict]:
    """Search with permission filtering."""
    # Get events user can access
    accessible_events = get_user_accessible_event_ids(user_id)
    
    # Filter search to accessible events
    results = similarity_search(
        query_embedding=query_embedding,
        event_ids=accessible_events if event_id is None else [event_id]
    )
    return results
```

## Dependencies

### Required Python Packages
- `sentence-transformers>=2.2.0` - Embedding generation
- `PyPDF2>=3.0.0` - PDF text extraction
- `python-docx>=0.8.11` - DOCX text extraction
- `pgvector>=0.2.0` - PostgreSQL vector operations (Python client)

### Required PostgreSQL Extensions
- `pgvector>=0.5.0` - Vector storage and similarity search

### Optional Dependencies
- `pdfplumber>=0.9.0` - Alternative PDF extraction for complex layouts

## Configuration Settings

```python
# Vector search settings
VECTOR_SEARCH_SETTINGS = {
    "enabled": True,
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "embedding_dimensions": 384,
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "similarity_threshold": 0.7,
    "max_results": 5,
    "batch_size": 32,
}
```
