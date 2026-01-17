# Feature Specification: Vector Search RAG

**Feature Branch**: `006-vector-search-rag`  
**Created**: 2026-01-16  
**Status**: Ready for Tasks  
**Input**: User description: "Implement vector search capabilities for Retrieval-Augmented Generation over event documents and attachments"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Document Embedding & Storage (Priority: P1)

As a system administrator, I want event documents (PDF, DOCX, TXT, MD attachments) to be automatically processed and indexed so that users can later search them using natural language.

**Why this priority**: This is the foundational capability. Without document ingestion and embedding, vector search cannot function. All other stories depend on documents being available in the vector store.

**Independent Test**: Upload a PDF attachment to an event, trigger indexing, and verify the document chunks appear in the extracted_documents table with embeddings.

**Acceptance Scenarios**:

1. **Given** a new PDF is uploaded to an event, **When** the document sync process runs, **Then** the PDF text is extracted, chunked, embedded, and stored in the extracted_documents table.
2. **Given** a document is updated or replaced, **When** the sync runs again, **Then** existing chunks are replaced with new ones reflecting the updated content.
3. **Given** a document fails text extraction (corrupt file), **When** processing occurs, **Then** the error is logged, the document is marked as failed, and other documents continue processing.
4. **Given** a large document (>100 pages), **When** it is processed, **Then** it is split into manageable chunks with configurable size and overlap.
5. **Given** pgvector extension is not installed, **When** the plugin starts, **Then** a warning is logged and vector features are disabled (SQL-only mode).

---

### User Story 2 - Semantic Similarity Search (Priority: P2)

As an event participant, I want to search event materials using natural language queries so that I can find relevant information across all presentations, papers, and documents without knowing exact keywords.

**Why this priority**: This provides the core user-facing value proposition. Once documents are indexed, users need a way to search them. This is the primary interface for document retrieval.

**Independent Test**: Index several documents, then call the search endpoint with a natural language query, and verify relevant chunks are returned with similarity scores.

**Acceptance Scenarios**:

1. **Given** several documents are indexed, **When** I search for "machine learning applications", **Then** I receive the top-k most semantically similar document chunks.
2. **Given** an event-scoped search, **When** I search within a specific event, **Then** only documents from that event are searched.
3. **Given** a query returns matches, **When** viewing results, **Then** each result includes similarity score, source document reference, and relevant text excerpt.
4. **Given** no documents match above the similarity threshold, **When** searching, **Then** an empty result set is returned with appropriate messaging.
5. **Given** the vector search index is unavailable, **When** searching, **Then** the system falls back gracefully without crashing.

---

### User Story 3 - RAG-Enhanced Chat Responses (Priority: P3)

As an event participant, I want the chat assistant to automatically retrieve relevant document context so that answers include information from presentation slides, papers, and other event materials.

**Why this priority**: This integrates vector search into the main user workflow. Rather than requiring separate search actions, the chat automatically enriches responses with document context when relevant.

**Independent Test**: Ask a question about content in an indexed document, verify the response incorporates information from the document and cites the source.

**Acceptance Scenarios**:

1. **Given** indexed documents contain relevant information, **When** I ask a question, **Then** the assistant retrieves relevant context and includes it in the response.
2. **Given** document context is used in a response, **When** viewing the answer, **Then** sources are cited (e.g., "According to the workshop agenda...").
3. **Given** a question is purely about database data (registrations, events), **When** the assistant responds, **Then** it uses SQL without unnecessary document retrieval.
4. **Given** both SQL data and document context are relevant, **When** answering, **Then** both sources are appropriately combined.
5. **Given** no documents are indexed for an event, **When** RAG is attempted, **Then** the system gracefully proceeds with SQL-only mode.

---

### User Story 4 - Document Sync & Management (Priority: P4)

As a system administrator, I want documents to be automatically synchronized when attachments change so that the search index stays current without manual intervention.

**Why this priority**: Long-term maintainability and freshness of the index. Without sync, the index would become stale. This is important but less critical for initial deployment than core search functionality.

**Independent Test**: Modify an attachment, verify the sync task detects the change and re-indexes the document.

**Acceptance Scenarios**:

1. **Given** an attachment is added to an event, **When** the sync task runs, **Then** the new document is indexed.
2. **Given** an attachment is deleted, **When** the sync task runs, **Then** corresponding document chunks are removed from the index.
3. **Given** an attachment is modified, **When** the sync task runs, **Then** old chunks are replaced with new chunks from the updated content.
4. **Given** many documents need processing, **When** bulk indexing runs, **Then** progress feedback is provided and rate limiting prevents system overload.
5. **Given** a sync task fails partway through, **When** it restarts, **Then** it resumes from where it left off without reprocessing completed items.

---

### Edge Cases

- What happens when embedding model is unavailable? System logs error, continues without embedding new documents, existing vectors remain searchable.
- What happens with very long documents? Documents are chunked with configurable size (default 1000 chars) and overlap (default 200 chars).
- What happens with unsupported file types? File is logged as unsupported and skipped; only PDF, DOCX, TXT, MD processed.
- How are embeddings cached? Document content hash is stored; if content unchanged, embedding is reused.
- What happens if vector search returns low-relevance results? Results below configurable similarity threshold are filtered out.
- How does the system handle concurrent document updates? Database-level locking prevents duplicate processing.

## Requirements *(mandatory)*

### Functional Requirements

**Embedding Service**
- **FR-001**: System MUST support generating embeddings using sentence-transformers library.
- **FR-002**: System MUST use BAAI/bge-small-en-v1.5 as the default embedding model.
- **FR-003**: System MUST allow configuring alternative embedding models via plugin settings.
- **FR-004**: System MUST support batch embedding for efficiency (process multiple texts at once).
- **FR-005**: System MUST cache embeddings based on content hash to avoid recomputation.

**Document Storage**
- **FR-006**: System MUST store extracted documents in plugin_assistant.extracted_documents table.
- **FR-007**: System MUST use pgvector extension for vector storage when available.
- **FR-008**: System MUST store: id, event_id, attachment_id, content_text, embedding, metadata_json, content_hash.
- **FR-009**: System MUST create appropriate vector indexes (HNSW or IVFFlat) for similarity search.
- **FR-010**: System MUST gracefully degrade to SQL-only mode when pgvector is unavailable.

**Document Extraction**
- **FR-011**: System MUST extract text from PDF files using appropriate library (PyPDF2/pdfplumber).
- **FR-012**: System MUST extract text from DOCX files using python-docx library.
- **FR-013**: System MUST extract text from plain text files (TXT, MD).
- **FR-014**: System MUST chunk long documents into segments with configurable size and overlap.
- **FR-015**: System MUST store chunk position metadata (start/end, chunk index) for context.
- **FR-016**: System MUST handle extraction errors gracefully (skip unprocessable, log errors).

**Similarity Search**
- **FR-017**: System MUST accept query text and generate query embedding.
- **FR-018**: System MUST find top-k most similar document chunks using cosine similarity.
- **FR-019**: System MUST support filtering by event_id for event-scoped searches.
- **FR-020**: System MUST return chunks with similarity scores and source metadata.
- **FR-021**: System MUST support configurable similarity threshold for filtering results.

**RAG Integration**
- **FR-022**: System MUST automatically determine when document context would benefit a query.
- **FR-023**: System MUST include relevant document chunks in LLM prompt as context.
- **FR-024**: System MUST cite sources in responses when document context is used.
- **FR-025**: System MUST support combining SQL results with document context when appropriate.

**Document Sync**
- **FR-026**: System MUST detect new/updated attachments for processing.
- **FR-027**: System MUST queue documents for background processing via Celery.
- **FR-028**: System MUST handle extraction errors gracefully (skip, log, continue).
- **FR-029**: System MUST provide progress feedback for bulk operations.
- **FR-030**: System MUST support incremental sync (only process changed documents).

### Non-Functional Requirements

**Performance**
- **NFR-001**: Embedding generation MUST support batch processing for efficiency.
- **NFR-002**: Similarity search MUST return results within 500ms for typical queries.
- **NFR-003**: Document extraction MUST process at least 10 pages per second.
- **NFR-004**: Vector index MUST support at least 100,000 document chunks.

**Reliability**
- **NFR-005**: System MUST continue functioning if embedding service fails (SQL-only mode).
- **NFR-006**: System MUST continue functioning if pgvector is unavailable.
- **NFR-007**: System MUST recover gracefully from interrupted sync operations.

**Privacy & Security**
- **NFR-008**: System MUST respect Indico's attachment access permissions.
- **NFR-009**: System MUST not index documents the user cannot access.
- **NFR-010**: Embeddings MUST be stored securely within the plugin schema.

## Success Criteria *(mandatory)*

1. **Document Indexing**: ≥90% of supported document types (PDF, DOCX, TXT, MD) are successfully extracted and indexed.
2. **Search Quality**: Users can find relevant documents using natural language queries with ≥80% relevance (measured via feedback).
3. **Response Latency**: Similarity search returns results within 500ms for 95% of queries.
4. **RAG Enhancement**: Chat responses citing document context receive positive feedback ≥70% of the time.
5. **Graceful Degradation**: System continues to function in SQL-only mode when vector features unavailable.
6. **Sync Reliability**: Document sync completes successfully ≥99% of the time.

## Out of Scope

- OCR for scanned PDF images (would require Tesseract integration)
- Real-time embedding generation during file upload (uses background processing)
- Cross-event document search (search is event-scoped by default)
- Custom embedding model fine-tuning
- Document preview/viewer functionality
- Attachment upload functionality (relies on existing Indico features)
