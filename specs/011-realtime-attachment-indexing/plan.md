# Implementation Plan: Real-Time Document Indexing via Attachment Signals

**Branch**: `011-realtime-attachment-indexing` | **Date**: 2026-01-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/011-realtime-attachment-indexing/spec.md`

## Summary

Implement automatic document indexing when files are uploaded to Indico events by connecting to Indico's `attachment_created` signal. When a supported document (PDF, DOCX, TXT, MD) is attached to an event, the system queues an asynchronous Celery task that extracts text, generates embeddings, and stores vectors in PostgreSQL for RAG-based search. The feature includes file size tiers (<10MB fast, 10-50MB best-effort, >50MB rejected), duplicate detection via SHA256 content hashing, automatic retry logic (3 attempts with exponential backoff), and graceful degradation when vector search is unavailable.

## Technical Context

**Language/Version**: Python 3.11+ (matching Indico requirements)  
**Primary Dependencies**: 
- Indico signals framework (`indico.modules.attachments.signals`)
- Celery for asynchronous task processing
- Existing document services (extractor, chunker, embedding, vector store)
- PostgreSQL with pgvector extension for vector storage  

**Storage**: PostgreSQL (`extracted_documents` table with event_id, attachment_id, content_hash, embeddings)  
**Testing**: pytest with Indico fixtures (`pytest_plugins = ('indico',)`)  
**Target Platform**: Linux server running Indico instance  
**Project Type**: Single project (Indico plugin)  
**Performance Goals**: 
- Signal handler <100ms (99th percentile)
- Indexing <30 seconds for documents <10MB (90th percentile)
- 99% task success rate for supported formats  

**Constraints**: 
- File size: <10MB guaranteed fast, 10-50MB best-effort, >50MB rejected
- No blocking of Indico's attachment upload workflow
- Must respect Indico event permissions
- Graceful degradation when pgvector unavailable  

**Scale/Scope**: 
- Handle 50 concurrent uploads across multiple events
- Support 4 file formats (PDF, DOCX, TXT, MD)
- 3 retry attempts with exponential backoff (1min, 5min, 15min)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Official Indico Plugin Architecture ✅ PASS
- ✅ Uses Indico's signals framework (`attachment_created` signal)
- ✅ Celery tasks use `indico.core.celery.celery` decorator
- ✅ Database access via Indico's `db` instance
- ✅ Plugin initialization connects signals in `AssistantPlugin.init()`
- ✅ No routes or UI components (signal-driven background processing only)

### II. API-First Design with Optional UI ✅ PASS  
- ✅ No API endpoints added (uses existing `/search/sync` for manual fallback)
- ✅ Feature operates via background signals, not HTTP requests
- ⚠️ Note: This is a background automation feature, not an API feature

### III. LLM Provider Abstraction ✅ PASS (N/A)
- ✅ Feature does not use LLM services
- ✅ Only uses document extraction and embedding services

### IV. Graceful Degradation ✅ PASS
- ✅ Checks `ASSISTANT_VECTOR_SEARCH_ENABLED` setting before processing
- ✅ Checks pgvector availability via `check_pgvector_available()`
- ✅ Logs warnings without raising exceptions when unavailable
- ✅ Signal handler never blocks; all work deferred to async task
- ✅ Failed tasks don't prevent document uploads

### V. Configuration Hierarchy ✅ PASS
- ✅ Uses existing global setting `ASSISTANT_VECTOR_SEARCH_ENABLED`
- ✅ File size limits configurable (implementation will add settings)
- ✅ No sensitive data involved (operates on existing attachments)

### VI. Test-First Development ✅ PASS (Planned)
- ✅ Unit tests planned for signal handler (≥80% coverage)
- ✅ Unit tests planned for indexing task logic
- ✅ Integration tests planned for end-to-end flow
- ✅ Uses pytest with Indico fixtures

**GATE RESULT**: ✅ **ALL GATES PASS** - Ready for Phase 0

## Project Structure

### Documentation (this feature)

```text
specs/011-realtime-attachment-indexing/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
├── checklists/
│   └── requirements.md  # Specification validation checklist
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
indico_assistant/
├── plugin.py                          # [MODIFY] Connect attachment signal
├── tasks/
│   ├── __init__.py                    # [MODIFY] Export new task
│   ├── sync.py                        # [EXISTING] Periodic sync tasks
│   └── indexing.py                    # [NEW] Real-time indexing task
├── services/
│   ├── document/
│   │   ├── extractor.py               # [EXISTING] Text extraction
│   │   └── chunker.py                 # [EXISTING] Text chunking
│   ├── embedding/
│   │   └── service.py                 # [EXISTING] Embedding generation
│   └── vector_search/
│       └── store.py                   # [MODIFY] Add duplicate detection
├── models/
│   └── document.py                    # [EXISTING] ExtractedDocument model
└── default_settings.py                # [MODIFY] Add file size limit setting

tests/
├── unit/
│   └── tasks/
│       └── test_indexing.py           # [NEW] Indexing task unit tests
├── integration/
│   └── test_realtime_indexing.py      # [NEW] End-to-end integration tests
└── services/
    └── test_signal_handlers.py        # [NEW] Signal handler tests
```

**Structure Decision**: Single project structure. Feature adds signal handler to existing plugin, creates new Celery task module, and extends existing vector store with duplicate detection logic.

## Phases

### Phase 0: Research & Technical Discovery

**Goal**: Resolve all NEEDS CLARIFICATION items and research best practices.

#### Research Topics

1. **Indico Attachment Signals API**
   - Research: Document the exact signature of `attachment_created` signal
   - Research: What data is available in signal payload (attachment object, event context)
   - Research: Signal timing relative to file storage (is file guaranteed accessible?)
   - Research: Best practices for signal handler performance (what operations are safe?)

2. **Celery Retry Patterns**
   - Research: Exponential backoff implementation in Celery
   - Research: How to configure retry delays (1min, 5min, 15min)
   - Research: Task state management for failed/retrying tasks
   - Research: Best practices for idempotent task design

3. **Content Hash-Based Duplicate Detection**
   - Research: SHA256 hashing for large files (memory-efficient streaming)
   - Research: Database index strategy for (event_id, content_hash) lookups
   - Research: How to handle hash collisions (probability, mitigation)

4. **File Size Checking**
   - Research: How to get file size from Indico Attachment object
   - Research: Where to enforce size limits (signal handler vs. task)
   - Research: User feedback mechanism for rejected files

5. **Concurrent Upload Race Conditions**
   - Research: PostgreSQL unique constraints on (event_id, attachment_id, chunk_index)
   - Research: Transaction isolation for duplicate detection queries
   - Research: Celery task deduplication strategies

**Output**: `research.md` with findings and decisions for each topic

### Phase 1: Design & Contracts

**Goal**: Define data structures, API contracts, and component interfaces.

#### Artifacts to Create

1. **data-model.md**: Document data structures
   - IndexingTaskResult: Task return value schema
   - Signal handler state tracking (no persistent state needed)
   - Content hash storage in ExtractedDocument model
   - Task retry metadata (attempt count, last_error)

2. **contracts/**: API/Interface contracts
   - `indexing_task.yaml`: Celery task signature and return schema
   - `signal_handler.yaml`: Signal handler interface contract
   - `duplicate_detection.yaml`: Hash-based duplicate detection logic

3. **quickstart.md**: Developer quickstart
   - How to test signal locally (create attachment via Indico API)
   - How to monitor indexing tasks (Celery Flower, logs)
   - How to manually trigger indexing (existing sync API)
   - Troubleshooting common issues (pgvector unavailable, worker down)

**Output**: Complete design artifacts ready for implementation

### Phase 2: Implementation Planning (Not part of /speckit.plan)

This phase generates `tasks.md` via the `/speckit.tasks` command after Phase 1 completes.

## Next Steps

1. **Execute Phase 0**: Run research on the 5 topics above
2. **Generate research.md**: Document findings and architectural decisions
3. **Execute Phase 1**: Create data-model.md, contracts/, quickstart.md
4. **Update agent context**: Run `.specify/scripts/bash/update-agent-context.sh copilot`
5. **Re-evaluate Constitution Check**: Verify design still passes all gates
6. **Run `/speckit.tasks`**: Generate implementation tasks (Phase 2)

## Dependencies & Integration Points

### Existing Components (No Changes)
- `services/document/extractor.py`: Text extraction from PDF/DOCX/TXT/MD
- `services/document/chunker.py`: Text chunking with overlap
- `services/embedding/service.py`: Embedding generation (384-dim vectors)
- `models/document.py`: ExtractedDocument model for storing chunks

### Components to Modify
- `plugin.py`: Add signal connection in `AssistantPlugin.init()`
- `services/vector_search/store.py`: Add `check_duplicate_by_hash()` method
- `tasks/__init__.py`: Export new `index_attachment_task`
- `default_settings.py`: Add `ASSISTANT_MAX_FILE_SIZE_MB` setting

### New Components
- `tasks/indexing.py`: New Celery task for real-time indexing
- `tests/unit/tasks/test_indexing.py`: Unit tests for indexing task
- `tests/integration/test_realtime_indexing.py`: End-to-end integration tests
- `tests/services/test_signal_handlers.py`: Signal handler performance tests

### External Dependencies
- `indico.modules.attachments.signals.attachment_created`: Indico core signal
- `indico.core.celery.celery`: Celery task decorator
- `indico.modules.attachments.models.attachments.Attachment`: Attachment model

## Risk Mitigation Strategies

| Risk | Mitigation in Design |
|------|---------------------|
| Signal handler blocks uploads | Keep handler <50 lines, <10ms; only queue task |
| High upload volume overwhelms queue | Use Celery rate limiting (`rate_limit='10/m'`); implement task priority |
| Large files cause OOM | Check file size in signal handler; reject >50MB before task creation |
| Race condition on duplicate hash check | Use database UNIQUE constraint + ON CONFLICT IGNORE; idempotent task design |
| Celery workers down | Tasks queue indefinitely; manual sync API provides fallback; monitoring alerts |
| Network failure during embedding | Celery auto-retry with exponential backoff; log full error context |
| Attachment deleted before indexing | Check attachment.exists() at task start; skip gracefully if missing |

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |

---

## Post-Design Constitution Re-Evaluation

*Phase 1 complete. Re-checking all principles against design artifacts.*

### I. Official Indico Plugin Architecture ✅ PASS
- ✅ Signal handler contract (`signal_handler.yaml`): Uses `attachment_created` signal
- ✅ Task contract (`indexing_task.yaml`): Celery task with `@celery.task` decorator
- ✅ Data model: UNIQUE constraints on `(event_id, attachment_id, chunk_index)`
- ✅ Research confirmed Blinker signal mechanism, documented signature
- ✅ Migration required for `content_hash` column addition
- **Status**: Fully compliant, architecture properly documented

### II. API-First Design with Optional UI ✅ PASS
- ✅ Signal-driven infrastructure approach (no HTTP API needed for this feature)
- ✅ No UI components in design
- ✅ Task accepts `force` parameter for programmatic control
- ✅ Task returns structured `IndexingTaskResult` for API consumption
- **Status**: Fully compliant, API-ready for future admin endpoints

### III. LLM Provider Abstraction ✅ PASS (N/A)
- ✅ Not applicable (confirmed in design)
- ✅ Uses existing `EmbeddingService` abstraction (sentence-transformers)
- **Status**: N/A (no violations)

### IV. Graceful Degradation ✅ PASS
- ✅ Signal handler: <100ms performance target, **never raises exceptions**
- ✅ Task contract: 4 error scenarios documented (attachment deleted, corrupted file, network timeout, DB error)
- ✅ Retry policy: 3 attempts with exact delays [60s, 300s, 900s]
- ✅ Idempotency via `IntegrityError` handling (duplicate prevention)
- ✅ Research confirmed streaming hash (8KB chunks) for memory safety
- ✅ Quickstart: Troubleshooting guide for all 6 failure modes
- **Status**: Fully compliant, graceful degradation guaranteed

### V. Configuration Hierarchy ✅ PASS
- ✅ File size tiers: <10MB (fast), 10-50MB (best-effort), >50MB (reject)
- ✅ Configurable via plugin settings (`ASSISTANT_MAX_FILE_SIZE_MB`)
- ✅ Task contract: Size validation before processing
- ✅ Quickstart: Configuration adjustment examples
- **Status**: Fully compliant, settings hierarchy supported

### VI. Test-First Development ✅ PASS (Design Ready)
- ✅ Quickstart includes 15+ manual test scenarios
- ✅ Performance benchmarking scripts (signal handler <100ms, task <30s)
- ✅ Monitoring via Flower dashboard, Celery CLI documented
- ✅ Contract tests: 6 validation checks (signal), 8 workflow steps (task)
- ✅ Next phase generates tasks.md with TDD implementation checklist
- **Status**: Design fully supports test-first approach, implementation pending

**POST-DESIGN GATE RESULT**: ✅ **ALL GATES PASS** - Ready for Phase 2 (task generation)

### Design Improvements Driven by Constitution

Constitution principles directly influenced these design decisions:

1. **Idempotency via IntegrityError** (Principle IV: Graceful Degradation)
   - Research established `try/except IntegrityError` pattern for race conditions
   - Data model adds UNIQUE constraint `(event_id, attachment_id, chunk_index)`
   - Signal handler never raises exceptions (logged errors only)

2. **Performance Targets** (Principle I: Plugin Architecture)
   - Signal handler <100ms to avoid blocking Indico request thread
   - Task SLA 30s for <10MB to maintain user experience
   - Research confirmed streaming hash (8KB chunks) for memory efficiency on large files

3. **Structured Task Result** (Principle II: API-First)
   - `IndexingTaskResult` schema with 10 fields for programmatic access
   - Task accepts `force` parameter for API/admin control
   - Enables future admin API endpoints for indexing status

4. **Comprehensive Testing Guide** (Principle VI: Test-First)
   - Quickstart includes 15+ test scenarios (upload, retry, errors, performance)
   - Performance benchmarking scripts for both signal handler and task
   - Troubleshooting guide covers 6 failure modes with diagnostic commands

**Constitution Impact**: High - Shaped architecture, error handling, performance, testability

---

## Phase 1 Completion Summary

✅ **Artifacts Created**:
- `research.md` - 6 research topics resolved (signal API, retry patterns, hashing, file size, idempotency, Indico behavior)
- `data-model.md` - 5 entities documented (input/result schemas, processing tier, document model changes)
- `contracts/signal_handler.yaml` - Signal handler interface contract
- `contracts/indexing_task.yaml` - Celery task contract with 8-step workflow
- `quickstart.md` - Developer guide with 15+ test scenarios, monitoring, troubleshooting

✅ **Agent Context Updated**: GitHub Copilot instructions refreshed with Python 3.11+, PostgreSQL schema

✅ **Constitution Re-Check**: All 6 principles pass post-design evaluation

⏭️ **Next Step**: Run `/speckit.tasks` to generate implementation task checklist (Phase 2)
