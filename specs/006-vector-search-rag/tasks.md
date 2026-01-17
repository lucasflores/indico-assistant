# Tasks: Vector Search RAG

**Feature**: 006-vector-search-rag  
**Input**: Design documents from `/specs/006-vector-search-rag/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Not explicitly requested in specification. Test tasks NOT included (can be added later if needed).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1-US4) - Setup/Foundational phases have no story label

---

## Phase 1: Setup

**Purpose**: Project initialization, settings, dependencies, and database schema

- [X] T001 Add vector search dependencies (sentence-transformers, PyPDF2, python-docx, pgvector) to pyproject.toml
- [X] T002 [P] Add vector search settings to indico_assistant/default_settings.py
- [X] T003 [P] Create ExtractionStatus enum in indico_assistant/models/document.py
- [X] T004 Create ExtractedDocument model in indico_assistant/models/document.py
- [X] T005 [P] Create DocumentSyncLog model in indico_assistant/models/document.py
- [X] T006 Export new models from indico_assistant/models/__init__.py
- [X] T007 Create migration 004_create_extracted_documents.py with pgvector detection

**Checkpoint**: Database schema ready, settings available ✅

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T008 Create embedding service package structure indico_assistant/services/embedding/__init__.py
- [X] T009 Implement EmbeddingService class with model loading in indico_assistant/services/embedding/service.py
- [X] T010 Add batch embedding method to EmbeddingService in indico_assistant/services/embedding/service.py
- [X] T011 Implement embedding cache by content hash in indico_assistant/services/embedding/cache.py
- [X] T012 Create pgvector availability check utility in indico_assistant/services/vector_search/__init__.py
- [X] T013 Create document service package structure indico_assistant/services/document/__init__.py
- [X] T014 Create vector_search service package structure indico_assistant/services/vector_search/__init__.py
- [X] T015 Create search Pydantic schemas (SearchRequest, SearchResponse, SearchResult) in indico_assistant/schemas/search.py

**Checkpoint**: Foundation ready - user story implementation can begin ✅

---

## Phase 3: User Story 1 - Document Embedding & Storage (Priority: P1) 🎯 MVP

**Goal**: Enable document extraction, chunking, and embedding storage

**Independent Test**: Upload a PDF, trigger indexing, verify chunks in database with embeddings

### Implementation for User Story 1

- [X] T016 [US1] Implement PDF text extraction in indico_assistant/services/document/extractor.py
- [X] T017 [P] [US1] Implement DOCX text extraction in indico_assistant/services/document/extractor.py
- [X] T018 [P] [US1] Implement TXT/MD text extraction in indico_assistant/services/document/extractor.py
- [X] T019 [US1] Implement unified extract_text() dispatcher in indico_assistant/services/document/extractor.py
- [X] T020 [US1] Implement document chunking with overlap in indico_assistant/services/document/chunker.py
- [X] T021 [US1] Implement chunk metadata generation in indico_assistant/services/document/chunker.py
- [X] T022 [US1] Implement DocumentProcessor orchestrator in indico_assistant/services/document/processor.py
- [X] T023 [US1] Implement content hash computation for change detection in indico_assistant/services/document/processor.py
- [X] T024 [US1] Implement VectorStore.insert_chunks() for batch storage in indico_assistant/services/vector_search/store.py
- [X] T025 [US1] Implement VectorStore.delete_attachment() for cleanup in indico_assistant/services/vector_search/store.py
- [X] T026 [US1] Add error handling for extraction failures in indico_assistant/services/document/processor.py

**Checkpoint**: Documents can be extracted, chunked, embedded, and stored. ✅

---

## Phase 4: User Story 2 - Semantic Similarity Search (Priority: P2)

**Goal**: Enable natural language search across indexed documents

**Independent Test**: Index documents, call search endpoint, verify relevant results with scores

### Implementation for User Story 2

- [X] T027 [US2] Implement VectorStore.similarity_search() in indico_assistant/services/vector_search/store.py
- [X] T028 [US2] Implement SearchService.search() with embedding generation in indico_assistant/services/vector_search/search.py
- [X] T029 [US2] Add event_id filtering to similarity search in indico_assistant/services/vector_search/store.py
- [X] T030 [US2] Add similarity threshold filtering in indico_assistant/services/vector_search/search.py
- [X] T031 [US2] Create RHSearch controller for POST /search in indico_assistant/controllers/search.py
- [X] T032 [US2] Register search route in blueprint.py in indico_assistant/blueprint.py
- [X] T033 [US2] Add graceful degradation when pgvector unavailable in indico_assistant/services/vector_search/search.py
- [X] T034 [US2] Add permission filtering for search results in indico_assistant/services/vector_search/search.py

**Checkpoint**: Users can search documents using natural language. ✅

---

## Phase 5: User Story 3 - RAG-Enhanced Chat Responses (Priority: P3)

**Goal**: Automatically enrich chat responses with document context

**Independent Test**: Ask question about indexed document, verify response includes document content and citation

### Implementation for User Story 3

- [X] T035 [US3] Implement query intent detection for document queries in indico_assistant/services/vector_search/rag.py
- [X] T036 [US3] Implement RAGService.get_context() for document retrieval in indico_assistant/services/vector_search/rag.py
- [X] T037 [US3] Implement context formatting for LLM prompt in indico_assistant/services/vector_search/rag.py
- [X] T038 [US3] Implement source citation generation in indico_assistant/services/vector_search/rag.py
- [X] T039 [US3] Integrate RAG into chat pipeline in indico_assistant/services/chat/service.py
- [X] T040 [US3] Add RAG context to LLM prompt template in indico_assistant/services/chat/service.py
- [X] T041 [US3] Handle hybrid queries (SQL + document) in indico_assistant/services/vector_search/rag.py
- [X] T042 [US3] Add fallback to SQL-only when no documents indexed in indico_assistant/services/vector_search/rag.py

**Checkpoint**: Chat responses automatically include relevant document context with citations. ✅

---

## Phase 6: User Story 4 - Document Sync & Management (Priority: P4)

**Goal**: Keep document index synchronized with Indico attachments

**Independent Test**: Modify attachment, verify sync task re-indexes the document

### Implementation for User Story 4

- [X] T043 [US4] Create Celery task for single document processing in indico_assistant/tasks/document_sync.py
- [X] T044 [US4] Create Celery task for event document sync in indico_assistant/tasks/document_sync.py
- [X] T045 [US4] Implement incremental sync (skip unchanged documents) in indico_assistant/tasks/document_sync.py
- [X] T046 [US4] Implement bulk sync with progress tracking in indico_assistant/tasks/document_sync.py
- [X] T047 [US4] Create RHDocumentSync controller for POST /documents/sync in indico_assistant/controllers/search.py
- [X] T048 [US4] Create RHDocumentStatus controller for GET /documents/status in indico_assistant/controllers/search.py
- [X] T049 [US4] Register document management routes in blueprint.py in indico_assistant/blueprint.py
- [X] T050 [US4] Implement sync logging to DocumentSyncLog in indico_assistant/tasks/document_sync.py
- [X] T051 [US4] Add rate limiting for bulk processing in indico_assistant/tasks/sync.py
- [X] T052 [US4] Implement cleanup of orphaned chunks (deleted attachments) in indico_assistant/tasks/document_sync.py

**Checkpoint**: Documents are automatically synchronized, admin can trigger manual sync. ✅

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final integration, documentation, and validation

- [X] T053 [P] Document vector search setup in docs/VECTOR_SEARCH_SETUP.md
- [X] T054 [P] Add environment variable documentation for embedding model
- [X] T055 Update services/__init__.py to export embedding, document, vector_search modules
- [X] T056 Add vector search status to admin health endpoint in indico_assistant/controllers/admin.py
- [X] T057 Verify graceful degradation by testing with pgvector disabled (validation.py)
- [X] T058 Performance validation: measure search latency (<500ms target) (validation.py)
- [X] T059 Run quickstart.md validation scenarios (validation.py)

**Checkpoint**: Documents are automatically synchronized, admin can trigger manual sync. ✅

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final integration, documentation, and validation

- [X] T053 [P] Document vector search setup in docs/VECTOR_SEARCH_SETUP.md
- [X] T054 [P] Add environment variable documentation for embedding model
- [X] T055 Update services/__init__.py to export embedding, document, vector_search modules
- [X] T056 Add vector search status to admin health endpoint in indico_assistant/controllers/admin.py
- [X] T057 Verify graceful degradation by testing with pgvector disabled (validation.py)
- [X] T058 Performance validation: measure search latency (<500ms target) (validation.py)
- [X] T059 Run quickstart.md validation scenarios (validation.py)

**Checkpoint**: All implementation complete. Manual testing/validation remaining. ✅

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) ──► Phase 2 (Foundational) ──┬──► Phase 3 (US1: Document Storage) ──► US1 Complete
                                             │
                                             └──► Phase 4 (US2: Search) ──► US2 Complete
                                                          │
                                                          └──► Phase 5 (US3: RAG) ──► US3 Complete
                                             
Phase 3 ──► Phase 6 (US4: Sync) ──► US4 Complete

All User Stories ──► Phase 7 (Polish)
```

### User Story Dependencies

| Story | Can Start After | Dependencies on Other Stories |
|-------|-----------------|-------------------------------|
| US1 (Document Storage) | Phase 2 complete | None - MVP standalone |
| US2 (Search) | Phase 2 complete | Uses embedding from Phase 2, can parallelize with US1 |
| US3 (RAG) | US2 complete | Requires search capability from US2 |
| US4 (Sync) | US1 complete | Requires document processing from US1 |

**Recommended Order**: US1 (parallel with US2 start) → US2 → US3 → US4

### Within Each User Story

1. Models/schemas before services
2. Services before controllers
3. Core implementation before integration points
4. Verify independently before moving to next story

### Parallel Opportunities

**Phase 1**:
- T002, T003 can run in parallel
- T004, T005 can run in parallel (same file but different classes)

**Phase 2**:
- T008-T011 (embedding) can run in parallel with T012-T014 (vector_search structure)

**Phase 3 (US1)**:
- T016, T017, T018 (extractors) can run in parallel

**Phase 6 (US4)**:
- T043-T046 (Celery tasks) before T047-T049 (controllers)

---

## Estimated Effort

| Phase | Tasks | Est. Hours |
|-------|-------|------------|
| Phase 1: Setup | 7 | 3 |
| Phase 2: Foundation | 8 | 6 |
| Phase 3: US1 Document Storage | 11 | 10 |
| Phase 4: US2 Search | 8 | 8 |
| Phase 5: US3 RAG | 8 | 10 |
| Phase 6: US4 Sync | 10 | 8 |
| Phase 7: Polish | 7 | 4 |
| **Total** | **59** | **~49 hours** |

---

## Risk Mitigation

| Risk | Task Impact | Mitigation |
|------|-------------|------------|
| pgvector not installed | T007, T024, T027 | Graceful degradation in T033 |
| Large document OOM | T016, T020 | Streaming extraction, chunk limits |
| Slow embedding | T010 | Batch processing, background tasks |
| Model download failure | T009 | Pre-download script in T053 |
