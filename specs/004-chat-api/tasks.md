# Tasks: Chat REST API

**Input**: Design documents from `/specs/004-chat-api/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Based on plan.md, this is an **Indico plugin** with structure:
- Models: `indico_assistant/models/`
- Services: `indico_assistant/services/`
- Controllers: `indico_assistant/controllers/`
- Tests: `tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, database migration, and base schemas

- [X] T001 Create database migration `002_create_chat_tables.py` in indico_assistant/migrations/versions/
- [X] T002 [P] Create Pydantic request/response schemas in indico_assistant/schemas/chat.py
- [X] T003 [P] Create Pydantic session schemas in indico_assistant/schemas/session.py
- [X] T004 [P] Create Pydantic feedback schemas in indico_assistant/schemas/feedback.py
- [X] T005 [P] Create common error response schema in indico_assistant/schemas/errors.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T006 Create ChatSession model in indico_assistant/models/session.py
- [X] T007 Create ChatMessage model in indico_assistant/models/message.py
- [X] T008 Create FeedbackEntry model in indico_assistant/models/feedback.py
- [X] T009 Update indico_assistant/models/__init__.py to export new models
- [X] T010 [P] Create rate limiter service in indico_assistant/services/chat/rate_limiter.py
- [X] T011 [P] Create RHChatBase authenticated base class in indico_assistant/controllers/base.py
- [ ] T012 Run migration and verify database tables created

**Checkpoint**: Foundation ready - all three models exist, rate limiter functional, auth base class ready

---

## Phase 3: User Story 1 - Send Chat Message and Get Response (Priority: P1) 🎯 MVP

**Goal**: User sends a natural language question and receives an AI-generated response

**Independent Test**: POST `/api/assistant/chat` with `{"message": "How many events?"}` returns response with session_id, message_id, and answer text

### Implementation for User Story 1

- [X] T013 [US1] Create context builder service in indico_assistant/services/chat/context_builder.py
- [X] T014 [US1] Create session manager service in indico_assistant/services/chat/session_manager.py
- [X] T015 [US1] Create chat service orchestrator in indico_assistant/services/chat/service.py
- [X] T016 [US1] Create indico_assistant/services/chat/__init__.py exporting ChatService
- [X] T017 [US1] Implement RHChat controller in indico_assistant/controllers/chat.py
- [X] T018 [US1] Register POST /chat route in indico_assistant/blueprint.py
- [X] T019 [US1] Add unit tests for context builder in tests/unit/services/chat/test_context_builder.py
- [X] T020 [US1] Add unit tests for session manager in tests/unit/services/chat/test_session_manager.py
- [X] T021 [US1] Add unit tests for chat service in tests/unit/services/chat/test_service.py
- [X] T022 [US1] Add integration test for chat endpoint in tests/integration/chat/test_chat_endpoint.py

**Checkpoint**: User can send chat messages and receive AI responses. Sessions are created and messages persisted.

---

## Phase 4: User Story 2 - View Chat Session History (Priority: P2)

**Goal**: User can list their sessions and view message history within a session

**Independent Test**: GET `/api/assistant/sessions` returns paginated list; GET `/api/assistant/sessions/{id}` returns messages

### Implementation for User Story 2

- [X] T023 [US2] Implement RHSessionList controller in indico_assistant/controllers/sessions.py
- [X] T024 [US2] Implement RHSessionDetail controller in indico_assistant/controllers/sessions.py
- [X] T025 [US2] Implement RHSessionDelete controller in indico_assistant/controllers/sessions.py
- [X] T026 [US2] Register GET /sessions route in indico_assistant/blueprint.py
- [X] T027 [US2] Register GET /sessions/<id> route in indico_assistant/blueprint.py
- [X] T028 [US2] Register DELETE /sessions/<id> route in indico_assistant/blueprint.py
- [X] T029 [US2] Add unit tests for session controllers in tests/unit/controllers/test_sessions.py
- [X] T030 [US2] Add integration test for sessions endpoints in tests/integration/chat/test_sessions_endpoint.py

**Checkpoint**: User can list all their sessions with pagination, view full message history, and delete sessions.

---

## Phase 5: User Story 3 - Provide Feedback on Responses (Priority: P3)

**Goal**: User can submit thumbs up/down, ratings, and comments on assistant responses

**Independent Test**: POST `/api/assistant/feedback` with message_id and feedback_type stores feedback successfully

### Implementation for User Story 3

- [X] T031 [US3] Create feedback service in indico_assistant/services/feedback/service.py
- [X] T032 [US3] Create indico_assistant/services/feedback/__init__.py exporting FeedbackService
- [X] T033 [US3] Implement RHFeedback controller in indico_assistant/controllers/feedback.py
- [X] T034 [US3] Register POST /feedback route in indico_assistant/blueprint.py
- [X] T035 [US3] Add unit tests for feedback service in tests/unit/services/feedback/test_service.py
- [X] T036 [US3] Add integration test for feedback endpoint in tests/integration/chat/test_feedback_endpoint.py

**Checkpoint**: User can submit all feedback types on assistant responses. Duplicate feedback updates existing entry.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Rate limiting enforcement, cleanup task, documentation, security

- [X] T037 [P] Add rate limit enforcement decorator to chat endpoint in indico_assistant/controllers/chat.py
- [X] T038 [P] Add rate limit enforcement to session endpoints in indico_assistant/controllers/sessions.py
- [X] T039 [P] Create Celery cleanup task for 90-day session expiry in indico_assistant/tasks/cleanup.py
- [X] T040 [P] Register cleanup task with Celery beat schedule
- [X] T041 [P] Add unit tests for rate limiter in tests/unit/services/chat/test_rate_limiter.py
- [X] T042 [P] Add API contract tests against OpenAPI spec in tests/contract/chat/test_api_contracts.py
- [ ] T043 Run quickstart.md validation - verify all endpoints work end-to-end
- [ ] T044 Update README.md with Chat API documentation

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup ──────────────────┐
                                 │
                                 ▼
Phase 2: Foundational ───────────┤
         (BLOCKS all stories)    │
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
Phase 3: US1 (P1)       Phase 4: US2 (P2)       Phase 5: US3 (P3)
Chat Endpoint           Sessions Endpoints       Feedback Endpoint
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
Phase 6: Polish & Cross-Cutting
```

### User Story Dependencies

| Story | Depends On | Can Parallelize With |
|-------|------------|---------------------|
| US1 (Chat) | Phase 2 Foundational | US2, US3 (after Phase 2) |
| US2 (Sessions) | Phase 2 Foundational | US1, US3 (after Phase 2) |
| US3 (Feedback) | Phase 2 Foundational | US1, US2 (after Phase 2) |

### Within Each User Story

1. Services before controllers
2. Controllers before routes
3. Routes before tests
4. Tests validate functionality

### Parallel Opportunities per Phase

**Phase 1 (Setup)**:
```bash
# All schema files can be created in parallel:
T002: indico_assistant/schemas/chat.py
T003: indico_assistant/schemas/session.py
T004: indico_assistant/schemas/feedback.py
T005: indico_assistant/schemas/errors.py
```

**Phase 2 (Foundational)**:
```bash
# Rate limiter and base class in parallel:
T010: indico_assistant/services/chat/rate_limiter.py
T011: indico_assistant/controllers/base.py
```

**Phase 3-5 (User Stories)**:
```bash
# After Phase 2, all three user stories can proceed in parallel
# by different developers if team capacity allows
```

**Phase 6 (Polish)**:
```bash
# All polish tasks marked [P] can run in parallel:
T037, T038, T039, T040, T041, T042
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. ✅ Complete Phase 1: Setup (migration + schemas)
2. ✅ Complete Phase 2: Foundational (models + rate limiter + base class)
3. ✅ Complete Phase 3: User Story 1 (chat endpoint)
4. **STOP and VALIDATE**: Test chat endpoint works independently
5. Deploy/demo with chat capability

### Incremental Delivery

| Increment | What's Deliverable | Value |
|-----------|-------------------|-------|
| MVP | Chat endpoint | Users can ask questions and get answers |
| +US2 | Session history | Users can review and continue conversations |
| +US3 | Feedback | System can collect improvement signals |
| +Polish | Rate limiting, cleanup | Production-ready with operational features |

### Task Count Summary

| Phase | Tasks | Parallelizable |
|-------|-------|----------------|
| Phase 1: Setup | 5 | 4 |
| Phase 2: Foundational | 7 | 2 |
| Phase 3: US1 Chat | 10 | 0 (sequential) |
| Phase 4: US2 Sessions | 8 | 0 (sequential) |
| Phase 5: US3 Feedback | 6 | 0 (sequential) |
| Phase 6: Polish | 8 | 6 |
| **Total** | **44** | **12** |

---

## Notes

- All endpoints require Indico authentication (via RHChatBase)
- Rate limits: 60/min for chat, 200/min for reads (configurable)
- Session cleanup runs daily via Celery, deletes sessions >90 days inactive
- UUID primary keys prevent enumeration attacks
- Cascade deletes handle session→messages→feedback cleanup
- Error format: `{"error": "CODE", "message": "text", "details": {...}}`
