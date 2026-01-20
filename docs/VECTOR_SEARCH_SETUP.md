# Vector Search Setup Guide

This guide explains how to set up and configure vector search capabilities for the Indico Assistant plugin, enabling vector similarity search over event documents.

## Prerequisites

### PostgreSQL with pgvector

The vector search feature requires the `pgvector` extension for PostgreSQL. This extension enables storing and querying vector embeddings efficiently.

#### Installing pgvector

**Ubuntu/Debian:**
```bash
# PostgreSQL 15+
sudo apt install postgresql-15-pgvector

# Or build from source
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

**macOS (Homebrew):**
```bash
brew install pgvector
```

**Docker:**
```dockerfile
# Use the official postgres image with pgvector
FROM pgvector/pgvector:pg16
```

#### Enabling pgvector

After installation, enable the extension in your Indico database:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

> **Note**: The plugin will gracefully degrade if pgvector is not installed. Vector search will be disabled, but all other features will continue to work.

### Python Dependencies

The vector search feature requires additional Python packages. These are automatically installed when you install the plugin:

- `sentence-transformers>=2.2.0` - Embedding model support
- `PyPDF2>=3.0.0` - PDF text extraction
- `python-docx>=0.8.11` - DOCX text extraction
- `pgvector>=0.2.0` - PostgreSQL vector operations

To manually install:
```bash
pip install sentence-transformers PyPDF2 python-docx pgvector
```

## Configuration

### Plugin Settings

Configure vector search in your Indico configuration or through the admin interface:

```python
# indico.conf

# Enable/disable vector search (default: True)
ASSISTANT_VECTOR_SEARCH_ENABLED = True

# Embedding model (default: 'BAAI/bge-small-en-v1.5')
# Other options: 'sentence-transformers/all-MiniLM-L6-v2'
ASSISTANT_EMBEDDING_MODEL = 'BAAI/bge-small-en-v1.5'

# Vector dimension (must match model output, default: 384)
ASSISTANT_EMBEDDING_DIMENSION = 384

# Document chunking settings
ASSISTANT_CHUNK_SIZE = 1000      # Characters per chunk
ASSISTANT_CHUNK_OVERLAP = 200   # Overlap between chunks

# Search settings
ASSISTANT_MAX_SEARCH_RESULTS = 5
ASSISTANT_SIMILARITY_THRESHOLD = 0.7
```

### Environment Variables

Alternative configuration via environment variables:

```bash
export ASSISTANT_VECTOR_SEARCH_ENABLED=true
export ASSISTANT_EMBEDDING_MODEL="BAAI/bge-small-en-v1.5"
export ASSISTANT_CHUNK_SIZE=1000
export ASSISTANT_SIMILARITY_THRESHOLD=0.7
```

## Database Migration

Run the migration to create the required tables:

```bash
indico db upgrade --plugin assistant
```

This creates:
- `extracted_documents` - Stores document chunks and embeddings
- `document_sync_log` - Tracks synchronization history

## Pre-downloading the Embedding Model

To avoid download delays during first use, pre-download the model:

```python
from sentence_transformers import SentenceTransformer

# Download and cache the model
model = SentenceTransformer('BAAI/bge-small-en-v1.5')
print(f"Model downloaded to: {model._model_path}")
```

Or via the command line:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
```

## Usage

### Automatic Document Indexing

Documents are automatically indexed when:
1. An attachment is uploaded to an event
2. The document sync task runs (periodic)
3. An admin triggers manual sync

### Manual Sync via API

**Sync a single event:**
```bash
curl -X POST "https://your-indico/api/assistant/search/sync" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"event_id": 123, "force": false}'
```

**Sync all events:**
```bash
curl -X POST "https://your-indico/api/assistant/search/sync/all" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"force": false}'
```

### Searching Documents

```bash
curl -X POST "https://your-indico/api/assistant/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "query": "What is the registration deadline?",
    "event_id": 123,
    "top_k": 5,
    "threshold": 0.7
  }'
```

Response:
```json
{
  "success": true,
  "results": [
    {
      "event_id": 123,
      "attachment_id": 456,
      "chunk_index": 2,
      "content": "Registration closes on December 15th...",
      "similarity": 0.89,
      "metadata": {
        "filename": "event_details.pdf",
        "page_number": 3
      }
    }
  ],
  "total_results": 1,
  "query_time_ms": 45.2
}
```

### Chat with Document Search

When using the chat endpoint, document content queries are handled by NL2SQL-generated SQL using pgvector similarity (`:query_vector`) instead of a separate RAG step:

```bash
curl -X POST "https://your-indico/api/assistant/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "message": "What does the presentation say about quantum computing?",
    "event_id": 123
  }'
```

The response will include citations:
```json
{
  "response": "According to the presentation, quantum computing uses qubits...\n\nSources:\n- quantum_intro.pdf (page 5)",
  "metadata": {
    "rag_enabled": true,
    "rag_sources": [{"filename": "quantum_intro.pdf", "page": 5}],
    "query_type": "document"
  }
}
```

## Monitoring

### Health Check

```bash
curl "https://your-indico/api/assistant/admin/health" \
  -H "Authorization: Bearer <admin-token>"
```

Response includes vector search status:
```json
{
  "status": "healthy",
  "vector_search": {
    "enabled": true,
    "available": true,
    "pgvector_installed": true,
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "stats": {
      "total_documents": 150,
      "total_events": 23
    }
  }
}
```

### Search Status

```bash
curl "https://your-indico/api/assistant/search/status" \
  -H "Authorization: Bearer <token>"
```

## Troubleshooting

### pgvector Not Found

**Symptom:** Vector search disabled, health shows `pgvector_installed: false`

**Solution:**
1. Install pgvector extension (see Prerequisites)
2. Enable in database: `CREATE EXTENSION vector;`
3. Restart Indico

### Embedding Model Download Fails

**Symptom:** First search is slow or fails with network error

**Solution:**
1. Pre-download the model (see above)
2. Ensure network access to Hugging Face
3. Consider using a local model cache

### Search Returns No Results

**Symptom:** Search returns empty results

**Possible causes:**
1. Documents not yet indexed - trigger sync
2. Similarity threshold too high - lower `threshold` parameter
3. Query not matching content - try different phrasing
4. Event has no attachments

### Memory Issues with Large Documents

**Symptom:** OOM errors during document processing

**Solution:**
1. Reduce `ASSISTANT_CHUNK_SIZE`
2. Process documents in batches
3. Increase server memory

## Supported File Types

| Extension | Support | Notes |
|-----------|---------|-------|
| `.pdf` | ✅ Full | Extracts text from all pages |
| `.docx` | ✅ Full | Extracts paragraphs |
| `.txt` | ✅ Full | Direct text |
| `.md` | ✅ Full | Markdown as plain text |
| `.doc` | ❌ | Use .docx conversion |
| `.pptx` | ❌ | Planned for future |

## Performance Considerations

### Index Size

- Each chunk stores ~384 floats (1.5 KB per embedding)
- Typical document: 5-20 chunks
- 1000 documents ≈ 15-30 MB index size

### Search Latency

- Target: <500ms for top-5 search
- Factors: index size, database performance, network
- HNSW index provides O(log n) search

### Embedding Generation

- First load: 2-5 seconds (model initialization)
- Per chunk: ~10-50ms
- Batch processing recommended for large documents

## Security

### Access Control

- Search results are filtered by user permissions
- Users only see documents from events they can access
- Admin endpoints require admin permission

### Data Privacy

- Embeddings are stored locally in your database
- No data sent to external services (except model download)
- Content hashes used for change detection only
