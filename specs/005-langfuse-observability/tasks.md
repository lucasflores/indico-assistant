# Tasks: Langfuse Observability

**Feature**: 005-langfuse-observability  
**Input**: Design documents from `/specs/005-langfuse-observability/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Not explicitly requested in specification. Test tasks NOT included (can be added later if needed).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1-US4) - Setup/Foundational phases have no story label

---

## Phase 1: Setup

**Purpose**: Project initialization, settings, and database schema

- [X] T001 Add langfuse dependency to pyproject.toml and requirements.txt
- [X] T002 [P] Add Langfuse settings (host, public_key, secret_key, enabled, privacy_level) to indico_assistant/default_settings.py
- [X] T003 [P] Add observability error types enum to indico_assistant/models/observability.py
- [X] T004 Create UsageStats model in indico_assistant/models/observability.py
- [X] T005 [P] Create ErrorRecord model in indico_assistant/models/observability.py
- [X] T006 [P] Create MetricsSyncLog model in indico_assistant/models/observability.py
- [X] T007 Export new models from indico_assistant/models/__init__.py
- [X] T008 Create migration 003_create_observability_tables.py in indico_assistant/migrations/versions/

**Checkpoint**: Database schema ready, settings available ✅

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core observability infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T009 Create observability package structure indico_assistant/services/observability/__init__.py
- [X] T010 Implement NoOpSpan class for graceful degradation in indico_assistant/services/observability/client.py
- [X] T011 Implement LangfuseClient wrapper with auth_check and graceful degradation in indico_assistant/services/observability/client.py
- [X] T012 Add client factory function get_langfuse_client() in indico_assistant/services/observability/client.py
- [X] T013 Implement PII redaction patterns (email, @username) in indico_assistant/services/observability/privacy.py
- [X] T014 Create admin Pydantic schemas (UsageStatsResponse, ErrorListResponse, HealthResponse) in indico_assistant/schemas/admin.py
- [X] T015 Configure structured logging format and levels (DEBUG/INFO/WARNING/ERROR) for observability module in indico_assistant/services/observability/__init__.py

**Checkpoint**: Foundation ready - user story implementation can begin ✅

---

## Phase 3: User Story 1 - LLM Call Tracing (Priority: P1) 🎯 MVP

**Goal**: Enable real-time tracing of all LLM interactions with timing and token usage metrics

**Independent Test**: Make a chat query and verify trace appears in Langfuse dashboard with model, tokens, latency

### Implementation for User Story 1

- [X] T016 [US1] Implement trace context manager in indico_assistant/services/observability/tracer.py
- [X] T017 [US1] Implement generation span context manager for LLM calls in indico_assistant/services/observability/tracer.py
- [X] T018 [US1] Add privacy level handling (metadata/masked/full) to tracer context managers in indico_assistant/services/observability/tracer.py
- [X] T019 [US1] Add tracing instrumentation to LLMService.generate() in indico_assistant/services/llm/service.py
- [X] T020 [US1] Add session_id and user_id_hash propagation to traces in indico_assistant/services/observability/tracer.py
- [X] T021 [US1] Add correlation_id generation and propagation in indico_assistant/services/observability/tracer.py
- [X] T022 [US1] Ensure async tracing with bounded queue (verify SDK defaults) in indico_assistant/services/observability/client.py
- [X] T023 [US1] Add flush() call in request teardown for critical paths in indico_assistant/blueprint.py

**Checkpoint**: LLM calls traced to Langfuse with timing, tokens, model info. User requests succeed even if Langfuse unavailable. ✅

---

## Phase 4: User Story 2 - Pipeline Span Tracking (Priority: P2)

**Goal**: Enable detailed performance analysis of each NL2SQL pipeline stage

**Independent Test**: Execute a query and verify nested spans (classification → generation → execution → formatting) appear in Langfuse

### Implementation for User Story 2

- [X] T024 [US2] Implement span context manager for pipeline stages in indico_assistant/services/observability/tracer.py
- [X] T025 [US2] Add span instrumentation to query_classification stage in indico_assistant/services/nl2sql/pipeline.py
- [X] T026 [P] [US2] Add span instrumentation to sql_generation stage in indico_assistant/services/nl2sql/pipeline.py
- [X] T027 [P] [US2] Add span instrumentation to sql_execution stage in indico_assistant/services/nl2sql/pipeline.py
- [X] T028 [P] [US2] Add span instrumentation to sql_correction stage in indico_assistant/services/nl2sql/pipeline.py
- [X] T029 [P] [US2] Add span instrumentation to response_summarization stage in indico_assistant/services/nl2sql/pipeline.py
- [X] T030 [US2] Ensure parent-child span nesting via SDK context propagation in indico_assistant/services/nl2sql/pipeline.py
- [X] T031 [US2] Add error status capture to spans when stage fails in indico_assistant/services/observability/tracer.py

**Checkpoint**: Full pipeline stages visible as nested spans in Langfuse. Can identify slowest stage for any request. ✅

---

## Phase 5: User Story 3 - Admin Statistics Dashboard (Priority: P3)

**Goal**: Enable administrators to view usage statistics and debug errors via REST API

**Independent Test**: Call GET /admin/stats and GET /admin/errors endpoints, verify JSON response with statistics

### Implementation for User Story 3

- [X] T032 [US3] Implement MetricsService for querying local stats in indico_assistant/services/observability/metrics.py
- [X] T033 [US3] Implement ErrorRecordService for querying/storing errors in indico_assistant/services/observability/metrics.py
- [X] T034 [US3] Implement Celery sync task skeleton in indico_assistant/services/observability/sync.py
- [X] T035 [US3] Implement Langfuse API fetching in sync task in indico_assistant/services/observability/sync.py
- [X] T036 [US3] Implement stats aggregation logic in sync task in indico_assistant/services/observability/sync.py
- [X] T037 [US3] Implement error extraction logic in sync task in indico_assistant/services/observability/sync.py
- [X] T038 [US3] Register Celery task with hourly schedule in indico_assistant/services/observability/sync.py
- [X] T039 [US3] Create RHAdminStats handler for GET /admin/stats in indico_assistant/controllers/admin.py
- [X] T040 [P] [US3] Create RHAdminErrors handler for GET /admin/errors in indico_assistant/controllers/admin.py
- [X] T041 [P] [US3] Create RHAdminHealth handler for GET /admin/health in indico_assistant/controllers/admin.py
- [X] T042 [US3] Add admin permission check to all admin handlers in indico_assistant/controllers/admin.py
- [X] T043 [US3] Register admin routes in blueprint.py in indico_assistant/blueprint.py
- [X] T044 [US3] Implement period filtering (day/week/month) for stats endpoint in indico_assistant/controllers/admin.py
- [X] T045 [US3] Implement error type filtering and pagination for errors endpoint in indico_assistant/controllers/admin.py
- [X] T046 [US3] Add 7-day rolling cleanup for ErrorRecord table in indico_assistant/services/observability/sync.py

**Checkpoint**: Admin API endpoints return statistics from local cache. Data survives Langfuse outages. ✅

---

## Phase 6: User Story 4 - Privacy-Aware Tracing (Priority: P4)

**Goal**: Ensure tracing complies with privacy policies via configurable content masking

**Independent Test**: Set privacy_level="masked", send query with email in prompt, verify [EMAIL] redaction in Langfuse

### Implementation for User Story 4

- [X] T047 [US4] Implement email redaction regex pattern in indico_assistant/services/observability/privacy.py
- [X] T048 [P] [US4] Implement @username redaction pattern in indico_assistant/services/observability/privacy.py
- [X] T049 [US4] Implement mask_pii() function combining all patterns in indico_assistant/services/observability/privacy.py
- [X] T050 [US4] Integrate privacy filtering into tracer before content capture in indico_assistant/services/observability/tracer.py
- [X] T051 [US4] Ensure metadata level captures NO prompt/response content in indico_assistant/services/observability/tracer.py
- [X] T052 [US4] Ensure stack_trace only captured at full privacy level in indico_assistant/services/observability/metrics.py
- [X] T053 [US4] Add runtime privacy level configuration support in indico_assistant/services/observability/client.py

**Checkpoint**: Privacy controls fully operational. Can audit that metadata level captures zero content. ✅

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final integration, documentation, and validation

- [X] T054 [P] Document Langfuse setup in README or LANGFUSE_SETUP.md → docs/LANGFUSE_SETUP.md
- [X] T055 [P] Add environment variable documentation for Langfuse credentials → included in LANGFUSE_SETUP.md
- [X] T056 Update services/__init__.py to export observability module
- [ ] T057 Verify graceful degradation by testing with Langfuse disabled
- [ ] T058 Performance validation: measure tracing overhead (<5ms target)
- [ ] T059 Run quickstart.md validation scenarios

**Checkpoint**: All implementation complete. Manual testing/validation remaining. ✅

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) ──► Phase 2 (Foundational) ──┬──► Phase 3 (US1: LLM Tracing) ──► US1 Complete
                                             │
                                             ├──► Phase 4 (US2: Pipeline Spans) ──► US2 Complete
                                             │
                                             ├──► Phase 5 (US3: Admin Dashboard) ──► US3 Complete
                                             │
                                             └──► Phase 6 (US4: Privacy) ──► US4 Complete
                                             
All User Stories ──► Phase 7 (Polish)
```

### User Story Dependencies

| Story | Can Start After | Dependencies on Other Stories |
|-------|-----------------|-------------------------------|
| US1 (LLM Tracing) | Phase 2 complete | None - MVP standalone |
| US2 (Pipeline Spans) | Phase 2 complete | Uses tracer from US1 (T016-T017) |
| US3 (Admin Dashboard) | Phase 2 complete | None - uses local DB only |
| US4 (Privacy) | Phase 2 complete | Integrates with tracer from US1 |

**Recommended Order**: US1 → US4 → US2 → US3 (Privacy early to avoid rework)

### Within Each User Story

1. Models/schemas before services
2. Services before controllers
3. Core implementation before integration points
4. Verify independently before moving to next story

### Parallel Opportunities

**Phase 1**:
- T002, T003 can run in parallel
- T005, T006 can run in parallel (after T004 creates the file)

**Phase 2**:
- All foundational tasks must be sequential (build on each other)

**Phase 4 (US2)**:
- T025, T026, T027, T028 can run in parallel (different pipeline stages)

**Phase 5 (US3)**:
- T039, T040 can run in parallel (different endpoint handlers)

**Phase 6 (US4)**:
- T047, T048 can run in parallel (different PII patterns)

**Phase 7**:
- T054, T055, T056 can run in parallel

---

## Parallel Example: User Story 2

```bash
# After T023-T024 complete, launch pipeline stage instrumentation together:
Task T025: "Add span instrumentation to sql_generation stage"
Task T026: "Add span instrumentation to sql_execution stage"  
Task T027: "Add span instrumentation to sql_correction stage"
Task T028: "Add span instrumentation to response_summarization stage"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T008)
2. Complete Phase 2: Foundational (T009-T014)
3. Complete Phase 3: User Story 1 - LLM Tracing (T015-T022)
4. **STOP and VALIDATE**: Verify traces appear in Langfuse, graceful degradation works
5. Deploy MVP - all LLM calls now traced!

### Incremental Delivery

| Increment | Stories Included | Value Delivered |
|-----------|------------------|-----------------|
| MVP | US1 only | LLM call tracing with timing/tokens |
| v1.1 | US1 + US4 | + Privacy controls for production |
| v1.2 | US1 + US4 + US2 | + Pipeline stage visibility |
| Full | All | + Admin dashboard with offline stats |

### Story Independence

Each user story is designed to be independently testable:

- **US1**: Make a query → see trace in Langfuse
- **US2**: Make a query → see nested pipeline spans
- **US3**: Call /admin/stats → see usage statistics JSON
- **US4**: Send email in prompt → see [EMAIL] in Langfuse (masked mode)

---

## Notes

- **[P]** tasks can run in parallel (different files, no dependencies)
- **[USx]** labels map tasks to specific user stories for traceability
- Commit after each task or logical group
- Constitution principle IV (graceful degradation) is critical - test with Langfuse disabled
- Default privacy_level="metadata" captures timing only (safest default)
- Langfuse SDK handles async batching - no custom queue implementation needed
