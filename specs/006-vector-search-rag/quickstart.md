# Quickstart: Vector Search RAG

**Feature**: 006-vector-search-rag  
**Date**: 2026-01-16

## Prerequisites

1. Indico instance running with assistant plugin installed
2. PostgreSQL with pgvector extension (optional but recommended)
3. Admin access to Indico
4. Python 3.11+ environment

## Setup Steps

### 1. Install pgvector Extension

pgvector must be installed in PostgreSQL for vector search to work. Without it, the system falls back to SQL-only mode.

```bash
# For Debian/Ubuntu with PostgreSQL packages
sudo apt-get install postgresql-15-pgvector

# Or compile from source
git clone --branch v0.5.1 https://github.com/pgvector/pgvector.git
cd pgvector
make
make install

# Then in PostgreSQL (as superuser)
CREATE EXTENSION vector;
```

### 2. Install Python Dependencies

```bash
pip install sentence-transformers>=2.2.0
pip install PyPDF2>=3.0.0
pip install python-docx>=0.8.11
pip install pgvector>=0.2.0
```

### 3. Configure Plugin Settings

In Indico admin panel → Plugins → Indico Assistant:

```yaml
# Vector Search Settings
vector_search_enabled: true
embedding_model: "BAAI/bge-small-en-v1.5"
embedding_dimensions: 384
chunk_size: 1000
chunk_overlap: 200
similarity_threshold: 0.7
max_search_results: 5
embedding_batch_size: 32
supported_extensions:
  - ".pdf"
  - ".docx"
  - ".doc"
  - ".txt"
  - ".md"
```

### 4. Run Database Migration

```bash
cd /path/to/indico
indico db --plugin assistant migrate
```

This creates the tables:
- `plugin_assistant.extracted_documents` (with vector column if pgvector available)
- `plugin_assistant.document_sync_log`

### 5. Download Embedding Model (First Time)

The embedding model is downloaded on first use. To pre-download:

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
```

### 6. Verify Setup

#### Check Vector Search Status

```bash
# Via CLI (if implemented)
indico assistant check-vector-search

# Expected output:
# ✓ pgvector extension available
# ✓ Embedding model loaded (BAAI/bge-small-en-v1.5)
# ✓ extracted_documents table exists
# ○ 0 documents indexed
```

#### Check Search Endpoint

```bash
curl -X POST "http://localhost:8000/api/assistant/search" \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your-session-cookie>" \
  -d '{"query": "test search", "event_id": 123}'
```

Expected response:
```json
{
  "success": true,
  "results": [],
  "total": 0,
  "query": "test search"
}
```

## Validation Tests

### Test 1: Document Indexing (US1)

**Goal**: Verify documents can be extracted and indexed

1. Upload a PDF to an event:
   - Go to Event → Material → Add files
   - Upload a PDF document

2. Trigger document sync:
```bash
# Via Celery task
indico assistant sync-documents --event-id 123

# Or wait for automatic sync (if configured)
```

3. Verify indexing:
```bash
# Check database
SELECT COUNT(*) FROM plugin_assistant.extracted_documents 
WHERE event_id = 123;

# Check via API
curl "http://localhost:8000/api/assistant/admin/documents?event_id=123"
```

Expected: Document chunks appear in database with embeddings.

---

### Test 2: Semantic Search (US2)

**Goal**: Verify similarity search returns relevant results

1. Ensure documents are indexed (Test 1)

2. Perform search:
```bash
curl -X POST "http://localhost:8000/api/assistant/search" \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<cookie>" \
  -d '{
    "query": "What are the main topics discussed?",
    "event_id": 123,
    "top_k": 5
  }'
```

3. Expected response:
```json
{
  "success": true,
  "results": [
    {
      "content": "The main topics include...",
      "similarity": 0.85,
      "source": {
        "filename": "presentation.pdf",
        "page": 3,
        "attachment_id": 456
      }
    }
  ],
  "total": 1,
  "query": "What are the main topics discussed?"
}
```

---

### Test 3: RAG-Enhanced Chat (US3)

**Goal**: Verify chat responses incorporate document context

1. Ensure documents are indexed

2. Ask a question via chat:
```bash
curl -X POST "http://localhost:8000/api/assistant/chat" \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<cookie>" \
  -d '{
    "message": "What does the workshop presentation say about machine learning?",
    "event_id": 123
  }'
```

3. Expected response includes document citation:
```json
{
  "success": true,
  "response": "According to the workshop presentation (presentation.pdf), the machine learning section covers...",
  "sources": [
    {
      "type": "document",
      "filename": "presentation.pdf",
      "relevance": 0.87
    }
  ]
}
```

---

### Test 4: Document Sync (US4)

**Goal**: Verify automatic sync detects changes

1. Note current chunk count:
```sql
SELECT COUNT(*) FROM plugin_assistant.extracted_documents WHERE event_id = 123;
```

2. Add new attachment to event

3. Trigger sync or wait for scheduled task:
```bash
indico assistant sync-documents --event-id 123
```

4. Verify chunk count increased:
```sql
SELECT COUNT(*) FROM plugin_assistant.extracted_documents WHERE event_id = 123;
```

---

### Test 5: Graceful Degradation

**Goal**: Verify system works without pgvector

1. Disable vector search:
```yaml
# In plugin settings
vector_search_enabled: false
```

2. Send chat message:
```bash
curl -X POST "http://localhost:8000/api/assistant/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "How many events?", "event_id": null}'
```

3. Expected: Chat works using SQL-only mode, no errors.

## Common Issues

### Issue: "Extension 'vector' is not available"

**Solution**: Install pgvector extension. Vector search requires PostgreSQL superuser to create extension:
```sql
-- As PostgreSQL superuser
CREATE EXTENSION vector;
```

### Issue: Embedding model download fails

**Solution**: Download manually or check network:
```bash
# Manual download
python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('BAAI/bge-small-en-v1.5')
model.save('/path/to/cache')
"
```

### Issue: PDF extraction returns empty text

**Solution**: Some PDFs are scanned images. OCR is out of scope. Check file:
```python
from PyPDF2 import PdfReader
reader = PdfReader("document.pdf")
print(reader.pages[0].extract_text())
```

### Issue: Search returns no results

**Checks**:
1. Documents indexed? `SELECT COUNT(*) FROM plugin_assistant.extracted_documents`
2. Embeddings exist? `SELECT COUNT(*) FROM ... WHERE embedding IS NOT NULL`
3. Threshold too high? Try lowering `similarity_threshold` to 0.5

## Performance Tuning

### For Large Document Collections (>10,000 chunks)

1. Consider IVFFlat index for faster approximate search:
```sql
CREATE INDEX ON plugin_assistant.extracted_documents 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

2. Increase Celery worker concurrency for parallel processing

3. Adjust batch size based on available memory:
```yaml
embedding_batch_size: 64  # Increase if RAM allows
```

### For Faster First Response

1. Pre-download embedding model at startup
2. Keep model in memory (singleton pattern)
3. Use smaller model if quality acceptable

## Monitoring

### Key Metrics

- Documents indexed: `SELECT COUNT(DISTINCT attachment_id) FROM extracted_documents`
- Chunks total: `SELECT COUNT(*) FROM extracted_documents`
- Failed extractions: `SELECT COUNT(*) FROM extracted_documents WHERE extraction_status = 'failed'`
- Average search latency: Monitor via Langfuse (Feature 005)

### Health Check Endpoint

```bash
curl "http://localhost:8000/api/assistant/admin/health"
```

Response includes vector search status:
```json
{
  "components": {
    "vector_search": {
      "status": "healthy",
      "pgvector_available": true,
      "documents_indexed": 1234,
      "model_loaded": true
    }
  }
}
```
