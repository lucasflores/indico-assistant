# Feature Specification: Real-Time Document Indexing via Attachment Signals

**Feature Branch**: `011-realtime-attachment-indexing`  
**Created**: January 18, 2026  
**Status**: Draft  
**Input**: User description: "Real-time document indexing via Indico attachment signals for automatic RAG pipeline processing"

## Clarifications

### Session 2026-01-18

- Q: File Size Limit Enforcement - Edge cases mention "50MB limit" and risks suggest rejecting files >50MB, but FR-004 only specifies performance for files "<10MB". What happens between 10-50MB and above 50MB? → A: Tiered approach: <10MB fast-track, 10-50MB slower indexing with warning, >50MB rejected
- Q: Retry Strategy for Failed Indexing - Edge cases mention "retry with exponential backoff, max 3 attempts" and Open Questions propose "3 retries with exponential backoff", but this isn't specified in functional requirements. What is the exact retry behavior? → A: 3 automatic retries with exponential backoff (1min, 5min, 15min) then manual sync required
- Q: Modified Document Re-Indexing Behavior - User Story 3 mentions document modification behavior. How does the system identify a "modified version" vs. a different document with the same filename? → A: Content hash defines document identity - different hash = new document (both versions coexist), same hash = skip (duplicate), no automatic deletion or replacement

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Immediate Document Search After Upload (Priority: P1)

A conference organizer uploads a speaker's presentation PDF to an event. Within seconds, attendees can search the document's content through the assistant chat interface to find specific information (e.g., "What time is the keynote?").

**Why this priority**: This is the core value proposition - making uploaded documents immediately searchable eliminates the current hours-long delay that frustrates users and reduces the assistant's usefulness.

**Independent Test**: Upload a PDF with known content to an event, wait 10 seconds, then search for that content via the search API. The document should appear in results with relevant text chunks.

**Acceptance Scenarios**:

1. **Given** an event with no attachments, **When** a user uploads "schedule.pdf" containing "Registration starts at 9:00 AM", **Then** within 10 seconds, searching for "registration time" returns chunks from the uploaded document.
2. **Given** vector search is enabled, **When** multiple users upload different PDFs to the same event simultaneously, **Then** all documents are indexed without data corruption or lost uploads.
3. **Given** a document is uploaded, **When** indexing completes, **Then** the document status shows "indexed" with timestamp and chunk count.

---

### User Story 2 - Graceful Handling of Unsupported Files (Priority: P2)

A user uploads various file types (images, videos, spreadsheets) to an event. The system silently ignores unsupported formats without errors, only indexing PDFs, DOCX, TXT, and MD files.

**Why this priority**: Prevents user confusion and system errors when mixed file types are uploaded, ensuring reliability without requiring users to know which formats are supported.

**Independent Test**: Upload a JPG image to an event, verify no error messages are shown to the user, and confirm no extraction attempts or database entries are created for that file.

**Acceptance Scenarios**:

1. **Given** an event, **When** a user uploads "photo.jpg", **Then** the upload succeeds, no indexing errors occur, and no chunks are created in the database.
2. **Given** an event, **When** a user uploads both "document.pdf" and "image.png" together, **Then** only the PDF is indexed while the image is ignored.
3. **Given** an unsupported file is uploaded, **When** an admin checks system logs, **Then** no error logs related to that file appear.

---

### User Story 3 - Duplicate Detection Prevents Re-Indexing (Priority: P2)

A user uploads the same document twice (either intentionally or by mistake). The system detects the duplicate content using hash comparison and skips re-indexing, saving computational resources and avoiding duplicate search results.

**Why this priority**: Improves system efficiency and prevents search result pollution from duplicate content, particularly important for large conferences with many documents.

**Independent Test**: Upload a document, verify it's indexed, then upload the exact same file again. Confirm chunk count doesn't increase and the last_synced timestamp is updated but no new embedding computations occur.

**Acceptance Scenarios**:

1. **Given** "report.pdf" is already indexed for Event 123, **When** the same file (identical content hash) is uploaded again, **Then** the system returns status "skipped" and no new chunks are created.
2. **Given** "report.pdf" is indexed, **When** a different file with modified content (different content hash) is uploaded with the same filename, **Then** the new file is indexed as a separate document with its own chunks. Both versions coexist in search results.
3. **Given** the same document (identical hash) exists in two different events, **When** it's uploaded to both, **Then** it's indexed separately for each event to maintain event-specific search boundaries.

---

### User Story 4 - System Degradation When Vector Search Unavailable (Priority: P3)

When pgvector extension is not installed or vector search is explicitly disabled, document uploads continue to work normally without triggering indexing. Users receive no errors, and the system logs appropriate informational messages.

**Why this priority**: Ensures the plugin doesn't break core Indico functionality when optional vector search features are unavailable, maintaining system stability.

**Independent Test**: Disable vector search in plugin settings, upload a document, and verify the upload succeeds with no indexing attempts or error messages visible to users.

**Acceptance Scenarios**:

1. **Given** `ASSISTANT_VECTOR_SEARCH_ENABLED` is set to `False`, **When** a user uploads "document.pdf", **Then** the file is stored normally but no indexing task is queued.
2. **Given** pgvector extension is not installed in the database, **When** a document is uploaded, **Then** the signal handler detects unavailability and skips indexing gracefully.
3. **Given** vector search is disabled, **When** an admin re-enables it later, **Then** existing unindexed documents can be processed via the manual sync API.

---

### Edge Cases

- What happens when a document larger than 50MB is uploaded? (System rejects indexing with error message: "Document exceeds 50MB size limit and cannot be indexed")
- What happens when a document between 10MB and 50MB is uploaded? (System indexes with reduced performance guarantees; logs warning about large file; no strict time SLA)
- How does the system handle partial upload failures where the file is stored but indexing fails? (Task automatically retries 3 times with exponential backoff: 1 minute, 5 minutes, 15 minutes. After 3 failures, requires manual sync via API)
- What if the Celery worker queue is full or workers are down? (Tasks are queued and processed when workers become available; signal handler never blocks)
- How are documents handled when an attachment is deleted from an event? (Existing cleanup tasks handle removal; this feature doesn't change that behavior)
- What if two workers try to index the same document simultaneously? (Content hash check prevents duplicates; database constraints ensure atomicity)
- How does the system behave during database connection failures during indexing? (Task fails, logs error with full context, and can be retried via manual sync)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST queue an asynchronous indexing task within 1 second when a supported document (PDF, DOCX, TXT, MD) is attached to an event.
- **FR-002**: System MUST check if vector search is enabled before triggering indexing tasks, skipping indexing when disabled.
- **FR-003**: System MUST validate file type using file extension before queueing indexing tasks. Documents between 10-50MB are indexed with best effort (no time guarantee). Documents over 50MB are rejected with clear error message.
- **FR-004**: System MUST extract text content, chunk it into overlapping segments, generate embeddings, and store in vector database within 30 seconds for documents under 10MB.
- **FR-005**: System MUST compute and store a SHA256 content hash for each indexed document to enable duplicate detection.
- **FR-006**: System MUST skip re-indexing when an uploaded document's content hash matches an existing indexed document for the same event. Different content (different hash) is treated as a new document regardless of filename.
- **FR-007**: System MUST log indexing failures with event_id, attachment_id, and error details to enable debugging.
- **FR-009**: System MUST complete signal handler execution in under 100ms to avoid blocking Indico's attachment upload workflow.
- **FR-010**: System MUST handle concurrent document uploads to the same event without race conditions or data corruption.
- **FR-011**: System MUST fail gracefully when pgvector extension is unavailable, logging warnings without raising errors.
- **FR-012**: System MUST ignore unsupported file types (images, videos, spreadsheets) without triggering errors or indexing attempts.
- **FR-013**: System MUST connect to Indico's `attachment_created` signal during plugin initialization.
- **FR-014**: System MUST disconnect signal handlers when the plugin is disabled or unloaded.
- **FR-015**: Indexing tasks MUST respect Indico's event permission model, only processing attachments from accessible events.
- **FR-015**: System MUST retry failed indexing tasks automatically 3 times with delays of 60 seconds, 300 seconds, and 900 seconds before marking as permanently failed and requiring manual sync.
- **FR-016**: System MUST treat each unique content hash as a distinct document identity. When Indico attachment is updated with different content, both old and new versions coexist in search results unless explicitly deleted.

### Key Entities

- **Attachment Signal Event**: Represents the Indico signal event fired when an attachment is created, containing attachment object, event context, and upload metadata.
- **Indexing Task**: Asynchronous Celery task that orchestrates extraction, chunking, embedding, and storage for a single attachment.
- **Document Chunk**: Text segment extracted from a document with associated embedding vector, stored in `extracted_documents` table with event_id, attachment_id, chunk_index, content, embedding, and content_hash fields.
- **Content Hash**: SHA256 hash of the complete document content used as the unique document identity for duplicate detection. Documents with the same hash within an event are considered identical and not re-indexed. Different hashes = different documents, even with the same filename.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 90% of uploaded documents under 10MB become searchable within 10 seconds of upload completion. Documents 10-50MB are indexed without time guarantees. Documents over 50MB are rejected before indexing.
- **SC-002**: Signal handler execution completes in under 100ms for 99% of attachment creations, ensuring no upload workflow blocking.
- **SC-003**: Indexing tasks complete successfully for 99% of supported document uploads under normal system load.
- **SC-004**: Duplicate documents are detected and skipped with 100% accuracy, preventing unnecessary re-indexing.
- **SC-005**: System handles 50 concurrent document uploads across multiple events without race conditions or data corruption.
- **SC-006**: When vector search is disabled or unavailable, 100% of document uploads proceed without errors or user-visible failures.
- **SC-007**: Search latency for newly indexed documents is within 500ms for 95% of queries, matching existing indexed document performance.
- **SC-008**: Failed indexing tasks log sufficient diagnostic information (event_id, attachment_id, error traceback) in 100% of failure cases.

## Scope & Boundaries *(mandatory)*

### In Scope

- Automatic indexing triggered by `attachment_created` signal
- Support for PDF, DOCX, TXT, and MD file formats
- Asynchronous processing via Celery background tasks
- Duplicate detection using content hash comparison
- Graceful degradation when vector search is disabled or unavailable
- Error logging with contextual information for debugging
- Integration tests verifying end-to-end indexing workflow

### Out of Scope

- Real-time re-indexing when attachments are updated (handled by existing periodic sync)
- Progress indicators or status notifications during indexing (covered by existing task monitoring)
- Optimization for bulk document uploads (periodic sync is better suited for this)
- Support for additional file formats beyond PDF/DOCX/TXT/MD
- Search result caching or performance optimization (separate feature)
- User-facing controls to disable auto-indexing per event (may be added in future)
- Attachment deletion signal handling (existing cleanup tasks handle this)

## Assumptions *(mandatory)*

1. **Celery Infrastructure**: Indico instance has Celery workers configured and running to process asynchronous tasks.
2. **Database Access**: Plugin has sufficient database permissions to insert/query `extracted_documents` table.
3. **Signal Availability**: Indico's `attachment_created` signal is stable and reliably fired for all attachment uploads.
4. **File Access**: Attachment files are accessible via Indico's file storage system when indexing tasks execute.
5. **Network Stability**: Embedding service (local or remote) is reachable when indexing tasks run.
6. **Storage Capacity**: Database has sufficient storage for embedding vectors (384 dimensions per chunk).
7. **Performance Baseline**: Existing extraction, chunking, and embedding services meet performance requirements (<30s for 10MB files).
8. **Concurrent Safety**: PostgreSQL's MVCC ensures safe concurrent writes to `extracted_documents` table.

## Dependencies *(mandatory)*

### Internal Dependencies

- **Document Extractor** (`services/document/extractor.py`): Extracts text from PDF/DOCX/TXT/MD files.
- **Document Chunker** (`services/document/chunker.py`): Splits text into overlapping segments for embedding.
- **Embedding Service** (`services/embedding/service.py`): Generates 384-dimensional vectors using sentence-transformers.
- **Vector Store** (`services/vector_search/store.py`): Provides `insert_chunks()` and duplicate detection logic.
- **Extracted Documents Model** (`models/document.py`): Database model for storing document chunks and embeddings.

### External Dependencies

- **Indico Attachment Signals**: `indico.modules.attachments.signals.attachment_created` signal for event notification.
- **Celery**: Asynchronous task processing framework for background indexing.
- **PostgreSQL with pgvector**: Database extension for vector storage and similarity search.
- **Indico ORM**: Database access layer for fetching attachment objects and file content.

### Configuration Dependencies

- `ASSISTANT_VECTOR_SEARCH_ENABLED`: Plugin setting controlling whether indexing is active.
- `CELERY_BROKER_URL`: Celery message broker configuration.
- `CELERY_RESULT_BACKEND`: Celery result storage configuration.

## Risks & Mitigations *(mandatory)*

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| High upload volume overwhelms Celery queue | Tasks delayed, users experience long indexing times | Medium | Implement task rate limiting (max 10/sec per event) and priority queues; monitor queue depth |
| Large documents (>50MB) cause OOM errors in workers | Worker crashes, incomplete indexing | Medium | Add file size check in signal handler; reject >50MB files with clear error message; document limit |
| Signal handler blocks Indico request cycle | Slow upload experience, potential timeouts | Low | Keep handler logic minimal (<50 lines, <50ms); defer ALL processing to async task; add performance monitoring |
| Race condition when same document uploaded twice quickly | Duplicate chunks created despite hash check | Low | Use database unique constraint on (event_id, attachment_id, chunk_index); implement optimistic locking |
| Celery workers down/unavailable when uploads occur | Tasks queued but not processed | Medium | Implement task visibility monitoring; alert admins; provide manual sync fallback; set task expiry |
| pgvector extension unavailable after feature deployed | Indexing fails for all documents | Low | Add availability check in signal handler; fail gracefully; log warnings; document setup requirements |
| Attachment deleted before indexing task executes | Task fails with attachment not found error | Low | Add existence check in task; skip silently if attachment missing; log info message |
| Network failure during embedding generation | Indexing fails mid-process | Medium | Automatic retry with exponential backoff (1min, 5min, 15min for 3 attempts); log failures; manual sync available after exhausting retries |

## Open Questions *(optional)*

1. Should we add a plugin setting to disable real-time indexing per event or globally? (Default: enabled for all events)
2. Should we emit a notification event when indexing completes for UI progress indicators? (Defer to future feature)
3. How should we handle documents that fail extraction (corrupted PDFs, password-protected files)? (Log error, mark as "failed", allow manual retry)

## Non-Functional Requirements *(optional)*

### Performance

- **NFR-001**: Signal handler execution MUST complete in <100ms (99th percentile) to avoid blocking uploads.
- **NFR-002**: Indexing tasks MUST process documents <10MB within 30 seconds (90th percentile).
- **NFR-003**: System MUST handle 50 concurrent uploads without degradation in indexing time.
- **NFR-004**: Duplicate detection hash comparison MUST complete in <10ms.

### Reliability

- **NFR-005**: Indexing task success rate MUST exceed 99% for supported file formats.
- **NFR-006**: System MUST recover gracefully from transient failures (network, database) via retry logic.
- **NFR-007**: Failed indexing MUST NOT prevent document uploads or corrupt existing data.

### Observability

- **NFR-008**: All indexing failures MUST be logged with full context (event_id, attachment_id, error traceback, file size, file type).
- **NFR-009**: Successful indexing MUST log summary statistics (chunks created, processing time, embedding generation time).
- **NFR-010**: Signal handler performance MUST be measurable via timing logs for monitoring.

### Security

- **NFR-011**: Indexing MUST respect Indico's event access permissions - only process attachments from events the system can access.
- **NFR-012**: Content hashes MUST use cryptographically secure SHA256 algorithm to prevent hash collisions.
- **NFR-013**: Celery tasks MUST NOT expose sensitive document content in task arguments or logs beyond metadata.

## User Experience Considerations *(optional)*

1. **Transparency**: Users should have visibility into whether their documents are indexed. Consider adding an "Indexing Status" indicator in the attachment list (future enhancement).

2. **Feedback Loop**: When a document fails to index, administrators should receive clear error messages with actionable remediation steps (e.g., "PDF is password-protected and cannot be indexed").

3. **Performance Expectations**: Document in user guides that search availability typically takes 5-10 seconds after upload, with longer times for large files or high system load.

4. **Format Support**: Clearly communicate supported file formats (PDF, DOCX, TXT, MD) in documentation and potentially in the upload interface.

5. **Duplicate Handling**: If the same document is uploaded multiple times, users should understand that search results won't be duplicated (this is a feature, not a bug).
