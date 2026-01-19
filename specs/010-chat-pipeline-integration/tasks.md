# Tasks: Chat Pipeline Integration

**Feature**: 010-chat-pipeline-integration  
**Input**: Design documents from `/specs/010-chat-pipeline-integration/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[US#]**: Which user story this task belongs to (US1, US2, US3, US4, US5)
- Exact file paths included in descriptions

---

## Phase 1: Setup

**Purpose**: Add dependencies and configuration for Chainlit-Indico integration

- [x] T001 Add httpx dependency to chainlit_app/requirements.txt
- [x] T002 [P] Create chainlit_app/.env.example with INDICO_API_URL and CHAINLIT_AUTH_SECRET

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Fix the core import error that causes mock response fallback

**⚠️ CRITICAL**: This fix unblocks all user stories - must be done first

- [x] T003 Fix NL2SQL import in indico_assistant/services/chat/service.py (replace NL2SQLService with create_nl2sql_pipeline_from_plugin)
- [x] T004 Store original JWT token in Chainlit user metadata in chainlit_app/app_chnlit.py (header_auth_callback)

**Checkpoint**: Foundation ready - chat service can now use real NL2SQL pipeline

---

## Phase 3: User Story 1 - Send Query and Receive LLM Response (Priority: P1) 🎯 MVP

**Goal**: Users receive intelligent LLM responses instead of echoes

**Independent Test**: Send "What can you help me with?" and receive contextual response (not echo)

### Implementation for User Story 1

- [x] T005 [US1] Implement HTTP client helper in chainlit_app/app_chnlit.py (create async httpx client for Indico API calls)
- [x] T006 [US1] Replace echo handler with Indico API call in chainlit_app/app_chnlit.py (on_message function)
- [x] T007 [US1] Add environment variable loading for INDICO_API_URL in chainlit_app/app_chnlit.py

**Checkpoint**: Messages flow through real LLM pipeline; no more echoes

---

## Phase 4: User Story 2 - NL2SQL Query Execution (Priority: P1)

**Goal**: Data queries return actual database results with generated SQL

**Independent Test**: Ask "How many events are there?" and receive count with sql_generated in metadata

### Implementation for User Story 2

- [x] T008 [US2] Update _process_with_nl2sql to use pipeline.process() correctly in indico_assistant/services/chat/service.py
- [x] T009 [US2] Ensure metadata (sql_generated, confidence, data_sources) is populated in response in indico_assistant/services/chat/service.py
- [x] T010 [P] [US2] Add debug logging for pipeline execution stages in indico_assistant/services/chat/service.py

**Checkpoint**: Data queries execute SQL and return real results

---

## Phase 5: User Story 3 - Chainlit Backend Integration (Priority: P1)

**Goal**: Complete Chainlit-to-Indico integration with JWT forwarding

**Independent Test**: Verify via logs that messages hit /api/assistant/chat endpoint

### Implementation for User Story 3

- [x] T011 [US3] Forward JWT token in Authorization header when calling Indico API in chainlit_app/app_chnlit.py
- [x] T012 [US3] Parse and display response from Indico API in chainlit_app/app_chnlit.py
- [x] T013 [P] [US3] Add request/response logging in Chainlit for debugging in chainlit_app/app_chnlit.py

**Checkpoint**: Full end-to-end message flow with authentication

---

## Phase 6: User Story 4 - Error Handling and Graceful Degradation (Priority: P2)

**Goal**: Users see helpful error messages, not raw exceptions

**Independent Test**: Disable LLM API key, send message, verify user-friendly error appears

### Implementation for User Story 4

- [x] T014 [US4] Add try/catch error handling in on_message handler in chainlit_app/app_chnlit.py
- [x] T015 [US4] Map HTTP status codes to user-friendly messages in chainlit_app/app_chnlit.py (401→re-auth, 422→validation, 500→generic error)
- [x] T016 [P] [US4] Improve error messages in chat service exceptions in indico_assistant/services/chat/service.py

**Checkpoint**: All errors display gracefully to users

---

## Phase 7: User Story 5 - Session Persistence Across Messages (Priority: P2)

**Goal**: Conversation context maintained across multiple messages

**Independent Test**: Ask "What events next week?", then "Show me the first one" - second query resolves reference

### Implementation for User Story 5

- [x] T017 [US5] Store Indico session_id in cl.user_session after first response in chainlit_app/app_chnlit.py
- [x] T018 [US5] Pass session_id in subsequent API requests in chainlit_app/app_chnlit.py
- [x] T019 [P] [US5] Add session initialization on chat start in chainlit_app/app_chnlit.py

**Checkpoint**: Multi-turn conversations work with context

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, cleanup, testing, and verification

- [x] T020 [P] Update chainlit_app/README.md with setup instructions for INDICO_API_URL
- [x] T021 [P] Add integration smoke test verifying end-to-end flow in tests/integration/test_chat_pipeline.py
- [x] T022 [P] Add unit tests for chat service NL2SQL integration in tests/unit/test_chat_service.py (mock pipeline, verify factory call)
- [x] T023 Verify all acceptance scenarios pass (manual verification against spec.md)

---

## Dependencies

```
T001, T002 (setup) → can run in parallel
     ↓
T003, T004 (foundational) → sequential, unblocks everything
     ↓
T005 → T006, T007 (US1) → US1 complete
     ↓
T008 → T009, T010 (US2) → US2 complete  
     ↓
T011 → T012, T013 (US3) → US3 complete (MVP done here)
     ↓
T014 → T015, T016 (US4) → US4 complete
     ↓
T017 → T018, T019 (US5) → US5 complete
     ↓
T020, T021, T022 (polish) → can run in parallel → T023 (final verification)
```

## Parallel Execution Examples

**Maximum parallelism per phase**:
- Phase 1: T001 ‖ T002
- Phase 3: T006, T007 after T005
- Phase 4: T009, T010 after T008
- Phase 5: T012, T013 after T011
- Phase 6: T015, T016 after T014
- Phase 7: T018, T019 after T017
- Phase 8: T020 ‖ T021 ‖ T022, then T023

## Implementation Strategy

**MVP Scope**: Complete through Phase 5 (User Stories 1-3)
- After T013, the widget will have working LLM responses
- This is the minimum viable deliverable

**Full Scope**: All phases including US4, US5, and polish
- Adds error handling and session persistence
- Recommended for production readiness

## Task Count Summary

| Phase | Tasks | Parallel Opportunities |
|-------|-------|----------------------|
| Setup | 2 | 2 |
| Foundational | 2 | 0 |
| US1 (P1) | 3 | 2 after T005 |
| US2 (P1) | 3 | 2 after T008 |
| US3 (P1) | 3 | 2 after T011 |
| US4 (P2) | 3 | 2 after T014 |
| US5 (P2) | 3 | 2 after T017 |
| Polish | 4 | 3 |
| **Total** | **23** | — |
