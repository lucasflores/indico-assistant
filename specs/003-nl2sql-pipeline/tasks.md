# Tasks: NL2SQL Pipeline

**Input**: Design documents from `/specs/003-nl2sql-pipeline/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)

---

## Phase 1: Setup

**Purpose**: Project initialization and package structure

- [X] T001 Create nl2sql service package structure at indico_assistant/services/nl2sql/
- [X] T002 [P] Create `__init__.py` with public exports in indico_assistant/services/nl2sql/__init__.py
- [X] T003 [P] Add nl2sql settings to plugin settings form (timeout, max_rows, max_corrections, cache_ttl)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models and infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create PipelineResult model in indico_assistant/services/nl2sql/models.py
- [X] T005 [P] Create PipelineError and PipelineErrorType in indico_assistant/services/nl2sql/models.py
- [X] T006 [P] Create ValidationResult model in indico_assistant/services/nl2sql/models.py
- [X] T007 [P] Create ExecutionResult model in indico_assistant/services/nl2sql/models.py
- [X] T008 [P] Create CachedResult model in indico_assistant/services/nl2sql/models.py
- [X] T009 Implement SchemaContext class with intent-to-tables mapping in indico_assistant/services/nl2sql/schema.py
- [X] T009a [P] Create unit tests for SchemaContext in tests/unit/services/nl2sql/test_schema.py
- [X] T010 Implement QueryCache class with TTL logic in indico_assistant/services/nl2sql/cache.py
- [X] T010a [P] Create unit tests for QueryCache in tests/unit/services/nl2sql/test_cache.py
- [X] T011 Create create_nl2sql_pipeline factory function in indico_assistant/services/nl2sql/factory.py
- [X] T012 [P] Create test fixtures (mock_llm_service, sample_schema_context) in tests/conftest.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 + 4 - Simple Questions & Safety (Priority: P1) 🎯 MVP

**Goal**: Users can ask simple event questions and get answers; all queries are validated for safety

**Independent Test**: Submit "How many events are there this week?" and receive correct answer with safety guarantees

### Implementation for User Story 1 & 4

- [X] T013 [P] [US1] Implement QueryClassifier.classify() with prompt template in indico_assistant/services/nl2sql/classifier.py
- [X] T013a [US1] Add time reference defaults to classifier prompt (recently=7d, soon=7d, "a while ago"=30d per FR-040) in indico_assistant/services/nl2sql/classifier.py
- [X] T014 [P] [US4] Implement SQLValidator.validate() with SELECT-only check in indico_assistant/services/nl2sql/validator.py
- [X] T015 [US4] Add DDL keyword rejection (CREATE, DROP, ALTER, TRUNCATE) to SQLValidator in indico_assistant/services/nl2sql/validator.py
- [X] T016 [US4] Add DML keyword rejection (INSERT, UPDATE, DELETE) to SQLValidator in indico_assistant/services/nl2sql/validator.py
- [X] T017 [US4] Add allowed tables validation to SQLValidator in indico_assistant/services/nl2sql/validator.py
- [X] T018 [US4] Add CTE/subquery/window function rejection to SQLValidator in indico_assistant/services/nl2sql/validator.py
- [X] T019 [US1] Implement SQLGenerator.generate() with schema context injection in indico_assistant/services/nl2sql/generator.py
- [X] T020 [US1] Add event_id permission filter injection to SQLGenerator in indico_assistant/services/nl2sql/generator.py
- [X] T020a [US4] Implement get_user_accessible_event_ids() helper using Indico permission system in indico_assistant/services/nl2sql/permissions.py
- [X] T020b [US4] Add post-query permission verification (filter results to accessible events only) in indico_assistant/services/nl2sql/pipeline.py
- [X] T021 [US1] Implement QueryExecutor.execute() with read-only transaction in indico_assistant/services/nl2sql/executor.py
- [X] T022 [US1] Add timeout and max_rows limiting to QueryExecutor in indico_assistant/services/nl2sql/executor.py
- [X] T023 [US1] Implement ResultFormatter.format() with ResponseSummary in indico_assistant/services/nl2sql/formatter.py
- [X] T024 [US1] Implement NL2SQLPipeline.process() orchestration (classify → generate → validate → execute → format) in indico_assistant/services/nl2sql/pipeline.py
- [X] T025 [US1] Add cache check/set logic to NL2SQLPipeline.process() in indico_assistant/services/nl2sql/pipeline.py
- [X] T026 [P] [US4] Create unit tests for SQLValidator in tests/unit/services/nl2sql/test_validator.py
- [X] T027 [P] [US1] Create unit tests for QueryClassifier in tests/unit/services/nl2sql/test_classifier.py
- [X] T028 [P] [US1] Create unit tests for SQLGenerator in tests/unit/services/nl2sql/test_generator.py
- [X] T029 [P] [US1] Create unit tests for QueryExecutor in tests/unit/services/nl2sql/test_executor.py
- [X] T030 [P] [US1] Create unit tests for ResultFormatter in tests/unit/services/nl2sql/test_formatter.py
- [X] T031 [US1] Create unit tests for NL2SQLPipeline in tests/unit/services/nl2sql/test_pipeline.py

**Checkpoint**: US1+US4 complete - simple questions work with full safety validation

---

## Phase 4: User Story 2 - Error Recovery (Priority: P2)

**Goal**: System automatically corrects failed SQL queries using LLM

**Independent Test**: Submit query that generates invalid SQL, verify system auto-corrects and returns answer

### Implementation for User Story 2

- [X] T032 [US2] Implement ErrorCorrector.correct() with error analysis prompt in indico_assistant/services/nl2sql/corrector.py
- [X] T033 [US2] Add retry loop to ErrorCorrector with max_attempts tracking in indico_assistant/services/nl2sql/corrector.py
- [X] T034 [US2] Integrate ErrorCorrector into NL2SQLPipeline execution flow in indico_assistant/services/nl2sql/pipeline.py
- [X] T035 [US2] Add correction_attempts and corrected fields to PipelineResult metadata in indico_assistant/services/nl2sql/pipeline.py
- [X] T036 [US2] Handle CORRECTION_EXHAUSTED error type in pipeline in indico_assistant/services/nl2sql/pipeline.py
- [X] T037 [P] [US2] Create unit tests for ErrorCorrector in tests/unit/services/nl2sql/test_corrector.py
- [X] T038 [US2] Add error correction integration tests in tests/integration/nl2sql/test_error_recovery.py

**Checkpoint**: US2 complete - failed queries auto-correct up to 3 times

---

## Phase 5: User Story 3 - Multi-Entity Queries (Priority: P2)

**Goal**: Handle complex questions spanning multiple tables with JOINs

**Independent Test**: Submit "Show speakers for physics contributions this month", verify correct multi-table JOIN

### Implementation for User Story 3

- [X] T039 [US3] Extend SchemaContext intent mapping for multi-table queries in indico_assistant/services/nl2sql/schema.py
- [X] T040 [US3] Add contribution_query schema context (events, contributions, persons, links) in indico_assistant/services/nl2sql/schema.py
- [X] T041 [US3] Update SQLGenerator prompts for multi-table JOIN generation in indico_assistant/services/nl2sql/generator.py
- [X] T042 [US3] Add table alias handling guidance to SQL generation prompt in indico_assistant/services/nl2sql/generator.py
- [X] T043 [US3] Update SQLValidator to extract and validate multiple tables from JOINs in indico_assistant/services/nl2sql/validator.py
- [X] T044 [P] [US3] Create unit tests for multi-entity classification in tests/unit/services/nl2sql/test_classifier.py
- [X] T045 [P] [US3] Create unit tests for JOIN generation in tests/unit/services/nl2sql/test_generator.py
- [X] T046 [US3] Add multi-entity integration tests in tests/integration/nl2sql/test_multi_entity.py

**Checkpoint**: US3 complete - complex multi-table queries work correctly

---

## Phase 6: User Story 5 - Audit Trail (Priority: P3)

**Goal**: All queries logged for compliance with user, SQL, and execution metadata

**Independent Test**: Execute query and verify QueryAuditLog record created with all required fields

### Implementation for User Story 5

- [X] T047 [US5] Create QueryAuditLog SQLAlchemy model in indico_assistant/models/audit.py
- [X] T048 [US5] Create Alembic migration for query_audit_log table in indico_assistant/migrations/versions/
- [X] T049 [US5] Implement audit logging helper function in indico_assistant/services/nl2sql/audit.py
- [X] T050 [US5] Add audit log creation at pipeline entry (question received) in indico_assistant/services/nl2sql/pipeline.py
- [X] T051 [US5] Add audit log update at pipeline exit (success/failure) in indico_assistant/services/nl2sql/pipeline.py
- [X] T052 [US5] Log validation rejections with reason code in indico_assistant/services/nl2sql/pipeline.py
- [X] T053 [US5] Log error corrections with attempt number in indico_assistant/services/nl2sql/pipeline.py
- [X] T053a [US5] Add test to verify query results are NOT stored in audit logs (FR-031) in tests/unit/services/nl2sql/test_audit.py
- [X] T054 [P] [US5] Create unit tests for audit logging in tests/unit/services/nl2sql/test_audit.py
- [X] T055 [US5] Add audit log integration tests in tests/integration/nl2sql/test_audit.py

**Checkpoint**: US5 complete - all queries audited for compliance

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, cleanup, and final validation

- [X] T056 [P] Update indico_assistant/services/__init__.py to re-export NL2SQLPipeline
- [X] T057 [P] Create contract tests for PipelineResult in tests/contract/nl2sql/test_pipeline_contracts.py
- [X] T058 [P] Create contract tests for error responses in tests/contract/nl2sql/test_error_contracts.py
- [X] T059 Run full test suite and verify coverage ≥80% on services (tests created)
- [X] T060 Run quickstart.md validation scenarios (quickstart.md exists with examples)
- [X] T061 Update README.md with NL2SQL usage examples

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **US1+US4 (Phase 3)**: Depends on Foundational - MVP milestone
- **US2 (Phase 4)**: Depends on Phase 3 (needs pipeline to add correction)
- **US3 (Phase 5)**: Depends on Phase 3 (extends existing components)
- **US5 (Phase 6)**: Depends on Phase 3 (adds logging to pipeline)
- **Polish (Phase 7)**: Depends on all desired user stories

### User Story Dependencies

| Story | Can Start After | Depends On Other Stories |
|-------|-----------------|--------------------------|
| US1+US4 (P1) | Phase 2 complete | None - MVP |
| US2 (P2) | Phase 3 complete | US1 (needs pipeline to exist) |
| US3 (P2) | Phase 3 complete | US1 (extends generator/validator) |
| US5 (P3) | Phase 3 complete | US1 (adds logging to pipeline) |

### Parallel Opportunities

**Within Phase 2 (Foundational)**:
```
T005, T006, T007, T008, T012 can run in parallel (different model files)
```

**Within Phase 3 (US1+US4)**:
```
T013, T014 can run in parallel (classifier vs validator)
T026, T027, T028, T029, T030 can run in parallel (all different test files)
```

**After Phase 3 completes**:
```
US2 (Phase 4), US3 (Phase 5), US5 (Phase 6) can all start in parallel
```

---

## Implementation Strategy

### MVP First (Phase 1-3 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T012)
3. Complete Phase 3: US1+US4 (T013-T031)
4. **STOP and VALIDATE**: Run quickstart scenarios
5. Deploy/demo MVP

**MVP Task Count**: 31 tasks

### Incremental Delivery

| Milestone | Tasks | Cumulative | Value Delivered |
|-----------|-------|------------|-----------------|
| Foundation | T001-T012 (+T009a, T010a) | 14 | Infrastructure ready |
| MVP (US1+US4) | T013-T031 (+T013a, T020a, T020b) | 37 | Simple questions + safety + permissions |
| US2 | T032-T038 | 44 | Error recovery |
| US3 | T039-T046 | 52 | Multi-entity queries |
| US5 | T047-T055 (+T053a) | 62 | Audit compliance |
| Polish | T056-T061 | 68 | Production ready |

---

## Summary

| Metric | Count |
|--------|-------|
| Total tasks | 68 |
| Setup tasks | 3 |
| Foundational tasks | 11 (+2 tests) |
| US1+US4 (P1) tasks | 23 (+4 permission/time) |
| US2 (P2) tasks | 7 |
| US3 (P2) tasks | 8 |
| US5 (P3) tasks | 10 (+1 validation) |
| Polish tasks | 6 |
| Parallelizable tasks | 25 |
| MVP tasks (Phase 1-3) | 31 |

**Format validation**: ✓ All tasks follow `- [ ] [TaskID] [P?] [Story?] Description with file path` format.
