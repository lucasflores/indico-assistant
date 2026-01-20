# Tasks: NL2SQL and Vector Search Prompt Optimization

**Input**: Design documents from `/specs/013-nl2sql-prompt-optimization/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, contracts/ ✅

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, configuration, and test infrastructure

- [X] T001 Add `extracted_documents` table to allowlist in `indico_assistant/config_modules/available_tables.yaml`
- [X] T002 [P] Create contract test file structure in `tests/contract/test_prompt_contracts.py`
- [X] T003 [P] Create integration test file structure in `tests/integration/test_vector_sql_queries.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Expose `embed_text()` method publicly in `indico_assistant/services/embedding/service.py` (verify accessibility for QueryExecutor)
- [X] T005 Add `question` parameter to `QueryExecutor.execute()` signature in `indico_assistant/services/nl2sql/executor.py`
- [X] T006 Add optional `embedding_service` dependency injection to `QueryExecutor.__init__()` in `indico_assistant/services/nl2sql/executor.py`
- [X] T007 Implement `_contains_vector_placeholder()` helper method in `indico_assistant/services/nl2sql/executor.py`
- [X] T008 Implement `_prepare_vector_params()` method for embedding substitution in `indico_assistant/services/nl2sql/executor.py`
- [X] T009 Update `NL2SQLPipeline.process()` in `indico_assistant/services/nl2sql/pipeline.py` to pass `question` to executor

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Query Events with Rich Context (Priority: P1) 🎯 MVP

**Goal**: Users asking about events receive comprehensive results with event IDs, formatted dates, timezones, and contextual information.

**Independent Test**: Ask "What events are happening this week?" and verify response includes event_id, properly formatted dates with timezone, and contextual fields.

### Contract Tests for User Story 1

- [X] T010 [P] [US1] Contract test: event query returns required columns (event_id, event_title, event_start_dt, event_timezone) in `tests/contract/test_prompt_contracts.py`
- [X] T011 [P] [US1] Contract test: event query uses `to_char()` with `AT TIME ZONE` for date formatting in `tests/contract/test_prompt_contracts.py`
- [X] T012 [P] [US1] Contract test: time-relative queries use PostgreSQL functions (CURRENT_DATE, NOW()) in `tests/contract/test_prompt_contracts.py`
- [X] T013 [P] [US1] Contract test: generated SQL contains no forbidden patterns (CTE, subquery, window functions) in `tests/contract/test_prompt_contracts.py`

### Implementation for User Story 1

- [X] T014 [US1] Enhance `SQL_GENERATION_PROMPT` in `indico_assistant/services/nl2sql/generator.py` with STRICT RULES section
- [X] T015 [US1] Add REQUIRED OUTPUT COLUMNS section to prompt in `indico_assistant/services/nl2sql/generator.py`
- [X] T016 [US1] Add FOREIGN KEY RELATIONSHIPS section to prompt in `indico_assistant/services/nl2sql/generator.py`
- [X] T017 [US1] Add Template 1 (Event Queries) SQL example to prompt in `indico_assistant/services/nl2sql/generator.py`
- [X] T018 [US1] Update `SchemaContext.get_schema_prompt()` to include "commonly useful columns" section in `indico_assistant/services/nl2sql/schema.py`

**Checkpoint**: User Story 1 complete - event queries return rich, formatted results with event IDs

---

## Phase 4: User Story 2 - Query Contributor and Speaker Information (Priority: P1)

**Goal**: Users asking about speakers receive properly joined, aggregated results with contributor names, affiliations, and contribution details.

**Independent Test**: Ask "Who spoke at event X?" and verify response includes aggregated speaker names, affiliations, contribution titles without duplicate rows.

### Contract Tests for User Story 2

- [X] T019 [P] [US2] Contract test: speaker query uses STRING_AGG for aggregation in `tests/contract/test_prompt_contracts.py`
- [X] T020 [P] [US2] Contract test: speaker query joins contribution_person_links and persons tables in `tests/contract/test_prompt_contracts.py`
- [X] T021 [P] [US2] Contract test: speaker query includes GROUP BY clause in `tests/contract/test_prompt_contracts.py`

### Implementation for User Story 2

- [X] T022 [US2] Add Template 2 (Contributor/Speaker Queries) SQL example with STRING_AGG pattern to prompt in `indico_assistant/services/nl2sql/generator.py`
- [X] T023 [US2] Add explicit JOIN hints for contribution_person_links → persons relationship in prompt in `indico_assistant/services/nl2sql/generator.py`
- [X] T024 [US2] Update `ResultFormatter` to handle aggregated contributor data cleanly in `indico_assistant/services/nl2sql/formatter.py`

**Checkpoint**: User Story 2 complete - speaker/contributor queries return aggregated, deduplicated results

---

## Phase 5: User Story 3 - Query Document Content with Vector Search (Priority: P2)

**Goal**: Users asking about document content receive relevant excerpts via unified SQL-based vector search (not separate RAG retrieval).

**Independent Test**: Ask "What does the presentation say about X?" and verify generated SQL includes `ORDER BY embedding <=> :query_vector` pattern.

### Contract Tests for User Story 3

- [X] T025 [P] [US3] Contract test: document content query classified as `document_content_query` intent in `tests/contract/test_prompt_contracts.py`
- [X] T026 [P] [US3] Contract test: document query SQL uses `<=>` operator in ORDER BY (not WHERE) in `tests/contract/test_prompt_contracts.py`
- [X] T027 [P] [US3] Contract test: document query SQL includes `:query_vector` placeholder in `tests/contract/test_prompt_contracts.py`
- [X] T028 [P] [US3] Contract test: executor substitutes `:query_vector` with actual embedding in `tests/contract/test_prompt_contracts.py`

### Implementation for User Story 3

- [X] T029 [US3] Add `document_content_query` intent to `CLASSIFICATION_PROMPT` in `indico_assistant/services/nl2sql/classifier.py`
- [X] T030 [US3] Add classification hints distinguishing `attachment_query` vs `document_content_query` in `indico_assistant/services/nl2sql/classifier.py`
- [X] T030a [US3] Add hybrid query routing rule (metadata + content) and document behavior in `CLASSIFICATION_PROMPT` in `indico_assistant/services/nl2sql/classifier.py`
- [X] T031 [US3] Add Template 4 (Document Content Vector Search) SQL example to prompt in `indico_assistant/services/nl2sql/generator.py`
- [X] T032 [US3] Add vector search warnings (operator usage, no WHERE comparison) to prompt in `indico_assistant/services/nl2sql/generator.py`
- [X] T033 [US3] Wire embedding service into QueryExecutor in `indico_assistant/services/nl2sql/executor.py`
- [X] T034 [US3] Update `ChatService._process_with_nl2sql()` to remove separate RAGService call in `indico_assistant/services/chat/service.py`

**Checkpoint**: User Story 3 complete - document content queries generate unified SQL with vector search

---

## Phase 6: User Story 4 - Query Attachments and Materials (Priority: P2)

**Goal**: Users asking about files and attachments receive metadata and file references through proper JOIN patterns.

**Independent Test**: Ask "What files are attached to event X?" and verify response includes storage_file_id, filename, and content_type.

### Contract Tests for User Story 4

- [X] T035 [P] [US4] Contract test: attachment query joins folders → attachments → files tables in `tests/contract/test_prompt_contracts.py`
- [X] T036 [P] [US4] Contract test: attachment query classified as `attachment_query` (not document_content_query) in `tests/contract/test_prompt_contracts.py`

### Implementation for User Story 4

- [X] T037 [US4] Add Template 3 (Attachment/Material Queries) SQL example to prompt in `indico_assistant/services/nl2sql/generator.py`
- [X] T038 [US4] Add attachment table JOIN hints (folders.id → attachments.folder_id → files.id) to prompt in `indico_assistant/services/nl2sql/generator.py`

**Checkpoint**: User Story 4 complete - attachment queries return file metadata with proper relationships

---

## Phase 7: User Story 5 - Relaxed Query Flexibility (Priority: P3)

**Goal**: Queries that would benefit from restricted syntax (CTEs, subqueries) are handled gracefully with alternative patterns or helpful explanations.

**Independent Test**: Ask "What are the top 5 events by registration count?" and verify system generates valid SQL or explains the limitation clearly.

### Contract Tests for User Story 5

- [X] T039 [P] [US5] Contract test: guardrail violation returns user-friendly error with alternative suggestion in `tests/contract/test_prompt_contracts.py`
- [X] T040 [P] [US5] Contract test: ranking queries use ORDER BY + LIMIT pattern instead of window functions in `tests/contract/test_prompt_contracts.py`

### Implementation for User Story 5

- [X] T041 [US5] Add "ALTERNATIVE PATTERNS" section to prompt documenting JOIN alternatives to CTEs in `indico_assistant/services/nl2sql/generator.py`
- [X] T042 [US5] Update validator error messages to include actionable suggestions in `indico_assistant/services/nl2sql/validator.py`
- [X] T043 [US5] Add guardrail rationale documentation as comments in prompt in `indico_assistant/services/nl2sql/generator.py`

**Checkpoint**: User Story 5 complete - restricted queries handled gracefully with alternatives or explanations

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Integration testing, documentation, and final validation

- [X] T044 [P] Integration test: end-to-end event query with formatted dates in `tests/integration/test_vector_sql_queries.py`
- [X] T045 [P] Integration test: end-to-end speaker query with aggregation in `tests/integration/test_vector_sql_queries.py`
- [X] T046 [P] Integration test: end-to-end vector search query with embedding substitution in `tests/integration/test_vector_sql_queries.py`
- [X] T047 Update unit tests for modified executor signature in `tests/unit/services/nl2sql/test_executor.py`
- [X] T048 Update unit tests for new classifier intent in `tests/unit/services/nl2sql/test_classifier.py`
- [ ] T049 [P] Run quickstart.md validation scenarios manually
- [X] T050 Update VECTOR_SEARCH_SETUP.md with unified architecture documentation in `docs/VECTOR_SEARCH_SETUP.md`

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
    │
    ▼
Phase 2 (Foundational) ─── BLOCKS ALL ───▶ [User Stories]
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│ User Stories can proceed in parallel (P1 first, then P2/P3) │
│                                                             │
│   Phase 3 (US1: Events) ──┐                                │
│   Phase 4 (US2: Speakers) ─┼──▶ Priority P1 (MVP)          │
│                            │                                │
│   Phase 5 (US3: Vector) ───┼──▶ Priority P2                │
│   Phase 6 (US4: Attachments)┘                              │
│                                                             │
│   Phase 7 (US5: Flexibility) ──▶ Priority P3               │
└───────────────────────────────────────────────────────────┘
    │
    ▼
Phase 8 (Polish)
```

### User Story Dependencies

| Story | Depends On | Can Start After |
|-------|------------|-----------------|
| US1 (Events) | Phase 2 | Foundational complete |
| US2 (Speakers) | Phase 2 | Foundational complete |
| US3 (Vector) | Phase 2, T004-T009 | Foundational complete (needs executor changes) |
| US4 (Attachments) | Phase 2 | Foundational complete |
| US5 (Flexibility) | Phase 2 | Foundational complete |

### Critical Path (Minimum for MVP)

1. Phase 1 (Setup): T001-T003
2. Phase 2 (Foundational): T004-T009
3. Phase 3 (US1 - Events): T010-T018
4. Phase 4 (US2 - Speakers): T019-T024

**MVP Scope**: User Stories 1 + 2 (P1 priority) = Event and Speaker queries with rich context

### Parallel Opportunities

**Within Phase 1**:
- T002, T003 can run in parallel (different files)

**Within Phase 3 (US1)**:
- T010, T011, T012, T013 (contract tests) can run in parallel
- T014-T018 (implementation) are sequential (same file)

**Within Phase 5 (US3)**:
- T025, T026, T027, T028 (contract tests) can run in parallel
- T029-T034 implementation is sequential (depends on classifier → generator → executor flow)

**Cross-Story**:
- Once Phase 2 complete, US1 and US2 can proceed in parallel (different prompt sections)
- US3 and US4 can proceed in parallel after Phase 2

---

## Summary

| Phase | Tasks | Story | Status |
|-------|-------|-------|--------|
| Phase 1: Setup | T001-T003 | - | ⏳ |
| Phase 2: Foundational | T004-T009 | - | ⏳ |
| Phase 3: User Story 1 | T010-T018 | Events (P1) | ⏳ |
| Phase 4: User Story 2 | T019-T024 | Speakers (P1) | ⏳ |
| Phase 5: User Story 3 | T025-T034 | Vector Search (P2) | ⏳ |
| Phase 6: User Story 4 | T035-T038 | Attachments (P2) | ⏳ |
| Phase 7: User Story 5 | T039-T043 | Flexibility (P3) | ⏳ |
| Phase 8: Polish | T044-T050 | - | ⏳ |

**Total Tasks**: 50  
**Per Story**: US1=9, US2=6, US3=10, US4=4, US5=5  
**Parallelizable**: 24 tasks marked [P]  
**MVP (US1+US2)**: 24 tasks (Phases 1-4)
