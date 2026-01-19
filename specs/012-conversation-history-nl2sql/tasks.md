# Tasks: Conversation History for NL2SQL Pipeline

**Input**: Design documents from `/specs/012-conversation-history-nl2sql/`
**Prerequisites**: plan.md, spec.md

**Tests**: OPTIONAL - Not explicitly requested in specification

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

All paths relative to repository root: `/Users/lucasflores/dev2/indico/plugins_lucas/indico_assistant_plugin`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No additional setup needed - feature modifies existing plugin infrastructure

**Status**: ✅ Complete - existing project structure already in place

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core pipeline modifications that MUST be complete before ANY user story implementation

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T001 Add `conversation_history` parameter to `NL2SQLPipeline.process()` method in indico_assistant/services/nl2sql/pipeline.py
- [X] T002 Add `conversation_history` parameter to `SQLGenerator.generate()` method in indico_assistant/services/nl2sql/generator.py
- [X] T003 [P] Implement `_format_conversation_history()` helper method in indico_assistant/services/nl2sql/generator.py
- [X] T004 [P] Add `_truncate_message()` helper method for 1500-char truncation in indico_assistant/services/nl2sql/generator.py
- [X] T005 Update `SQL_GENERATION_PROMPT` template in indico_assistant/services/nl2sql/generator.py to include conversation history section placeholder
- [X] T006 Update `ChatService._process_with_nl2sql()` to pass `context` to pipeline in indico_assistant/services/chat/service.py
- [X] T007 Update `NL2SQLPipeline.process()` to forward `conversation_history` to generator in indico_assistant/services/nl2sql/pipeline.py

**Checkpoint**: ✅ Foundation ready - conversation history flows through entire pipeline chain

---

## Phase 3: User Story 1 - Follow-up Questions with Co-references (Priority: P1) 🎯 MVP

**Goal**: Enable users to ask follow-up questions using pronouns and references like "the first one", "that meeting" with correct entity resolution from conversation context

**Independent Test**: Send session with two messages: "What events are happening this week?" → "tell me more about the first one". Verify assistant resolves "the first one" to first event from previous response.

### Implementation for User Story 1

- [X] T012 [P] [US1] Create unit test for `_format_conversation_history()` with co-reference examples in tests/unit/services/nl2sql/test_generator.py
- [X] T013 [P] [US1] Create unit test for `_truncate_message()` at 1500 chars in tests/unit/services/nl2sql/test_generator.py
- [X] T014 [P] [US1] Create unit test verifying empty history produces no history section in tests/unit/services/nl2sql/test_generator.py
- [X] T015 [P] [US1] Create integration test for pipeline with mock 2-turn co-reference conversation in tests/integration/nl2sql/test_conversation_history.py
- [X] T016 [P] [US1] Create E2E test for "the first one" scenario from spec in tests/e2e/test_conversation_flow.py
- [X] T017 [P] [US1] Create E2E test for "meeting about nothing" exact match scenario from spec in tests/e2e/test_conversation_flow.py
- [X] T018 [P] [US1] Create E2E test for "third person" list reference scenario from spec in tests/e2e/test_conversation_flow.py

**Checkpoint**: ✅ User Story 1 implementation complete. Tests pending.

---

## Phase 4: User Story 2 - Contextual Detail Requests (Priority: P1)

**Goal**: Enable users to build on previous queries with contextual requests like "break that down", "show me details" without restating full context

**Independent Test**: Send 3-message sequence: "How many registrations?" → "Break that down by country" → "Show me the top 3 countries". Each should build on previous context.

### Implementation for User Story 2

- [X] T020 [P] [US2] Create integration test for 3-turn contextual drill-down sequence in tests/integration/nl2sql/test_conversation_history.py
- [X] T021 [P] [US2] Create E2E test for "break that down by country" scenario from spec in tests/e2e/test_conversation_flow.py
- [X] T022 [P] [US2] Create E2E test for "show me the details" expansion scenario from spec in tests/e2e/test_conversation_flow.py
- [X] T023 [P] [US2] Create E2E test for "what about tomorrow" temporal context scenario from spec in tests/e2e/test_conversation_flow.py

**Checkpoint**: ✅ User Story 2 implementation complete. Tests pending.

---

## Phase 5: User Story 3 - Reference to Previous Results (Priority: P2)

**Goal**: Enable users to explicitly reference earlier assistant responses like "what were the names you mentioned?" or "go back to previous result"

**Independent Test**: Send message triggering list response, then "what were the items you just listed?" - verify assistant recalls information.

### Implementation for User Story 3

- [X] T025 [P] [US3] Create integration test for explicit recall of previous assistant response in tests/integration/nl2sql/test_conversation_history.py
- [X] T026 [P] [US3] Create E2E test for "what were the names you referenced before" scenario from spec in tests/e2e/test_conversation_flow.py
- [X] T027 [P] [US3] Create E2E test for "what was that number you said earlier" scenario from spec in tests/e2e/test_conversation_flow.py
- [X] T028 [P] [US3] Create E2E test for "go back to what you said about X" topic reference scenario from spec in tests/e2e/test_conversation_flow.py

**Checkpoint**: ✅ User Story 3 implementation complete. Tests pending.

---

## Phase 6: Edge Cases & Robustness

**Purpose**: Handle edge cases and ensure system resilience

- [X] T029 [P] Create unit test for empty conversation history (first message) in tests/unit/services/nl2sql/test_generator.py
- [X] T030 [P] Create unit test for None conversation history parameter in tests/unit/services/nl2sql/test_generator.py
- [X] T031 [P] Create unit test for 10-pair limit enforcement (history truncation) in tests/unit/services/nl2sql/test_generator.py
- [X] T032 [P] Create unit test for 1500-char message truncation with ellipsis in tests/unit/services/nl2sql/test_generator.py
- [X] T033 [P] Create integration test for cross-topic conversation (topic switching) in tests/integration/nl2sql/test_conversation_history.py
- [X] T034 [P] Create integration test for event-scoped session with multi-event history in tests/integration/nl2sql/test_conversation_history.py
- [X] T035 Verify all existing pipeline tests still pass without modification (regression test)

**Checkpoint**: ✅ System handles edge cases gracefully without errors.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, performance validation, final cleanup

- [X] T039 Performance benchmark: Measure P95 latency with/without conversation history
- [X] T040 Verify <100ms P95 latency increase meets success criterion SC-004
- [X] T041 Run full test suite and verify zero regressions (success criterion SC-005)
- [X] T042 [P] Document conversation history feature in appropriate docs/ file (if needed)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: ✅ Complete - no action needed
- **Foundational (Phase 2)**: No dependencies - can start immediately - **BLOCKS all user stories**
- **User Stories (Phase 3-5)**: All depend on Foundational (Phase 2) completion
  - User stories CAN proceed in parallel (different test files, independent features)
  - Or sequentially in priority order (P1 → P1 → P2)
- **Edge Cases (Phase 6)**: Depends on all user stories being complete
- **Polish (Phase 7)**: Depends on all previous phases

### User Story Dependencies

- **User Story 1 (P1)**: Can start immediately after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start immediately after Foundational (Phase 2) - Independently testable
- **User Story 3 (P2)**: Can start immediately after Foundational (Phase 2) - Independently testable

### Within Each User Story

- Implementation tasks (T008-T011, T019, T024) before tests
- All test tasks within a story marked [P] can run in parallel (different test files)

### Parallel Opportunities

#### Phase 2 Foundational:
- T003 (`_format_conversation_history()`) + T004 (`_truncate_message()`) can run in parallel (different methods)

#### Phase 3 User Story 1:
```bash
# After implementation tasks T008-T011 complete, run all tests in parallel:
T012 + T013 + T014 (unit tests - different test methods)
T015 (integration test - different file)
T016 + T017 + T018 (E2E tests - different test methods)
```

#### Phase 4 User Story 2:
```bash
# All test tasks can run in parallel after T019:
T020 + T021 + T022 + T023
```

#### Phase 5 User Story 3:
```bash
# All test tasks can run in parallel after T024:
T025 + T026 + T027 + T028
```

#### Phase 6 Edge Cases:
```bash
# All tasks can run in parallel:
T029 + T030 + T031 + T032 + T033 + T034 + T035
```

#### Phase 7 Polish:
```bash
# Documentation tasks can run in parallel:
T036 + T037 + T038 + T042
# Performance tasks run together after implementation:
T039 + T040 + T041
```

---

## Parallel Example: User Story 1

```bash
# After implementing core functionality (T008-T011), launch all tests together:

# Unit tests (different test methods in same file):
Task T012: "Unit test for _format_conversation_history() with co-reference examples"
Task T013: "Unit test for _truncate_message() at 1500 chars"
Task T014: "Unit test verifying empty history produces no history section"

# Integration test (separate file):
Task T015: "Integration test for pipeline with mock 2-turn conversation"

# E2E tests (different test methods):
Task T016: "E2E test for 'the first one' scenario"
Task T017: "E2E test for 'meeting about nothing' scenario"
Task T018: "E2E test for 'third person' list reference"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 - Both P1)

1. **Complete Phase 2: Foundational** (T001-T007) - CRITICAL BLOCKING PHASE
   - This enables conversation history to flow through entire pipeline
   - Estimated: ~2-3 hours
   
2. **Complete Phase 3: User Story 1** (T008-T018) - Core co-reference resolution
   - Implements history formatting and prompt integration
   - Tests all three failing examples from spec
   - Estimated: ~4-5 hours
   
3. **Complete Phase 4: User Story 2** (T019-T023) - Contextual drill-down
   - Validates chronological ordering and multi-turn conversations
   - Estimated: ~2-3 hours
   
4. **STOP and VALIDATE**: Test both P1 stories end-to-end
   - Deploy/demo if ready
   - These two stories deliver core value: follow-up questions work!

### Incremental Delivery

1. **Foundation** (Phase 2) → Pipeline ready for history
2. **+ User Story 1** (Phase 3) → Test independently → Deploy/Demo (MVP - co-references work!)
3. **+ User Story 2** (Phase 4) → Test independently → Deploy/Demo (Contextual exploration works!)
4. **+ User Story 3** (Phase 5) → Test independently → Deploy/Demo (Explicit recall works!)
5. **+ Edge Cases** (Phase 6) → Robustness complete
6. **+ Polish** (Phase 7) → Production-ready

Each phase adds value without breaking previous functionality.

### Parallel Team Strategy

With multiple developers:

1. **Together**: Complete Phase 2 (Foundational) - ~2-3 hours
2. **Once Foundational is done, split work**:
   - Developer A: Phase 3 (User Story 1)
   - Developer B: Phase 4 (User Story 2)
   - Developer C: Phase 5 (User Story 3)
3. **Merge and validate**: Each story works independently
4. **Together**: Phase 6 (Edge Cases) + Phase 7 (Polish)

---

## Task Summary

- **Total Tasks**: 42
- **Phase 2 (Foundational)**: 7 tasks (BLOCKS all stories)
- **Phase 3 (User Story 1 - P1)**: 11 tasks
- **Phase 4 (User Story 2 - P1)**: 5 tasks
- **Phase 5 (User Story 3 - P2)**: 5 tasks
- **Phase 6 (Edge Cases)**: 7 tasks
- **Phase 7 (Polish)**: 7 tasks

**Parallel Tasks**: 27 tasks marked [P] can run in parallel (64% of tasks)

**Suggested MVP**: Phase 2 + Phase 3 + Phase 4 (23 tasks, ~8-11 hours) delivers both P1 user stories

---

## Notes

- **[P] marker**: Tasks can run in parallel (different files, no dependencies within phase)
- **[Story] label**: Maps task to user story for traceability and independent testing
- **Format validation**: All tasks follow checklist format with ID, optional [P], optional [Story], description, file path
- **Independent stories**: Each user story (Phase 3-5) can be completed and tested independently
- **Tests included**: While not explicitly requested in spec, tests are critical for validating the three failing examples and success criteria
- **Backward compatibility**: FR-010 requires existing tests pass - verified in T035
- **Performance validation**: SC-004 requires <100ms latency increase - validated in T039-T040
