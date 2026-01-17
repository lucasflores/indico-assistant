# Implementation Plan: Vector Search RAG

**Branch**: `006-vector-search-rag` | **Date**: 2026-01-16 | **Spec**: [spec.md](spec.md)

## Summary

Implement vector search capabilities for Retrieval-Augmented Generation (RAG) over event documents and attachments. This includes an embedding service using sentence-transformers, document extraction pipeline for PDF/DOCX/TXT/MD files, pgvector-backed similarity search, and integration with the chat pipeline for context-aware responses with source citations.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: sentence-transformers, PyPDF2, python-docx, pgvector  
**Storage**: PostgreSQL with pgvector extension (plugin_assistant schema)  
**Testing**: pytest with indico fixtures, mocked embedding model  
**Target Platform**: Indico plugin (Flask-based)  
**Project Type**: Single plugin with vector search services  
**Performance Goals**: <500ms similarity search, batch embedding for throughput  
**Constraints**: Must gracefully degrade if pgvector unavailable; embedding can be slow  
**Scale/Scope**: Support ~100k document chunks, incremental sync

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Official Indico Plugin Architecture | ✅ PASS | Uses IndicoPluginBlueprint, RH handlers, plugin settings |
| II. API-First Design | ✅ PASS | Search API endpoint for testing before UI |
| III. LLM Provider Abstraction | ✅ PASS | Embedding model configurable, RAG uses existing LLMService |
| IV. Graceful Degradation | ✅ PASS | Core requirement: FR-010, NFR-005, NFR-006 |
| V. Configuration Hierarchy | ✅ PASS | Plugin settings for model, chunk size, thresholds |
| VI. Test-First Development | ✅ PASS | Unit tests for services, integration for pipeline |

## Project Structure

### Documentation (this feature)

```text
specs/006-vector-search-rag/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI for search endpoint)
│   └── openapi.yaml
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
indico_assistant/
├── services/
│   ├── embedding/                    # NEW: Embedding generation
│   │   ├── __init__.py
│   │   ├── service.py               # EmbeddingService class
│   │   └── cache.py                 # Embedding cache by content hash
│   ├── document/                     # NEW: Document extraction
│   │   ├── __init__.py
│   │   ├── extractor.py             # Text extraction (PDF, DOCX, TXT, MD)
│   │   ├── chunker.py               # Document chunking with overlap
│   │   └── processor.py             # Document processing orchestrator
│   ├── vector_search/               # NEW: Vector search
│   │   ├── __init__.py
│   │   ├── store.py                 # pgvector storage operations
│   │   ├── search.py                # Similarity search service
│   │   └── rag.py                   # RAG context builder
│   ├── chat/
│   │   └── service.py               # MODIFY: Add RAG integration
│   └── nl2sql/
│       └── classifier.py            # MODIFY: Add document intent detection
├── models/
│   ├── document.py                  # NEW: ExtractedDocument model
│   └── __init__.py                  # MODIFY: Export new model
├── controllers/
│   └── search.py                    # NEW: Search endpoint controller
├── schemas/
│   └── search.py                    # NEW: Search request/response schemas
├── migrations/versions/
│   └── 004_create_extracted_documents.py  # NEW: pgvector table
├── tasks/
│   └── document_sync.py             # NEW: Celery tasks for sync
├── default_settings.py              # MODIFY: Add vector search settings
└── blueprint.py                     # MODIFY: Register search routes

tests/
├── unit/services/
│   ├── embedding/
│   │   ├── test_service.py
│   │   └── test_cache.py
│   ├── document/
│   │   ├── test_extractor.py
│   │   └── test_chunker.py
│   └── vector_search/
│       ├── test_store.py
│       ├── test_search.py
│       └── test_rag.py
├── integration/
│   └── test_document_pipeline.py
└── contract/
    └── test_search_api.py
```

**Structure Decision**: New service packages under `services/` for embedding, document, and vector_search. Follows existing modular structure from Features 004 and 005.

**Path Note**: All paths are relative to `indico_assistant/` package root.

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Chat Controller                             │
│                    (RHChat - existing)                          │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RAG Integration                               │
│              (services/vector_search/rag.py)                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. Classify query (document vs SQL)                      │   │
│  │ 2. If document: similarity search → context              │   │
│  │ 3. Add context to LLM prompt                             │   │
│  │ 4. Generate response with citations                      │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────┬──────────────────────────────────────┬───────────────┘
           │                                       │
           ▼                                       ▼
┌──────────────────────┐              ┌──────────────────────────┐
│ Similarity Search    │              │ NL2SQL Pipeline          │
│ (search.py)          │              │ (existing)               │
└──────────┬───────────┘              └──────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Vector Store (store.py)                       │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ extracted_documents table with pgvector                     │ │
│  │ - HNSW index for cosine similarity                         │ │
│  │ - Filtered by event_id for scoping                         │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                Document Processing Pipeline                       │
│              (Background - Celery tasks)                         │
│                                                                  │
│  ┌─────────────┐    ┌────────────┐    ┌─────────────────────┐  │
│  │ Attachment  │───►│ Extractor  │───►│ Chunker             │  │
│  │ (PDF/DOCX)  │    │            │    │ (1000 chars, 200    │  │
│  └─────────────┘    └────────────┘    │  overlap)           │  │
│                                        └──────────┬──────────┘  │
│                                                   │              │
│                                                   ▼              │
│  ┌─────────────┐    ┌────────────┐    ┌─────────────────────┐  │
│  │ Vector      │◄───│ Embedding  │◄───│ Batch Processing    │  │
│  │ Store       │    │ Service    │    │                     │  │
│  └─────────────┘    └────────────┘    └─────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Embedding Model Loading
- Load model once at startup, reuse for all embeddings
- Use lazy loading to avoid startup delay if vector search disabled
- Model stored in service singleton

### 2. pgvector Detection
- Check for extension availability at startup
- Set feature flag for graceful degradation
- Log warning if unavailable

### 3. Chunking Strategy
- Fixed size with overlap preserves context
- Sentence boundary detection for cleaner breaks
- Metadata tracks position for reconstruction

### 4. RAG Query Classification
- Extend existing QueryClassifier
- New intent: "document_query"
- Hybrid queries use both SQL and documents

### 5. Citation Format
- Include source filename in response
- Format: "According to [filename]..."
- Track which chunks contributed to response

## Dependencies

### New Python Packages
```toml
# pyproject.toml additions
dependencies = [
    "sentence-transformers>=2.2.0",
    "PyPDF2>=3.0.0",
    "python-docx>=0.8.11",
    "pgvector>=0.2.0",
]
```

### PostgreSQL Requirements
- pgvector extension >= 0.5.0
- Must be installed in database

## Migration Strategy

1. Check pgvector availability before creating table
2. Create table with vector column only if extension present
3. Fallback schema without embedding column for graceful degradation

## Configuration

```python
# default_settings.py additions
DEFAULT_SETTINGS = {
    # ... existing settings ...
    
    # Vector Search Settings (Feature 006)
    "vector_search_enabled": True,
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "embedding_dimensions": 384,
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "similarity_threshold": 0.7,
    "max_search_results": 5,
    "embedding_batch_size": 32,
    "supported_extensions": [".pdf", ".docx", ".doc", ".txt", ".md"],
}
```

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| pgvector not installed | Graceful degradation to SQL-only mode |
| Large documents OOM | Streaming extraction, chunk limits |
| Slow embedding | Background processing, batch operations |
| Model download on first use | Document in setup, provide pre-download script |
| Search returns irrelevant results | Configurable threshold, user feedback loop |
