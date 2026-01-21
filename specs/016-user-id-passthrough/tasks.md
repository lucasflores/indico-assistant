# Tasks: User ID Passthrough Fix

**Input**: Design documents from `/specs/016-user-id-passthrough/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Database migration and shared infrastructure

- [X] T001 Create migration file `indico_assistant/migrations/005_add_identity_columns.py` to add `resolved_user_id` and `identity_source` columns to `chat_sessions` table
- [X] T002 [P] Update `indico_assistant/models/session.py` to add `resolved_user_id` (INTEGER, nullable) and `identity_source` (VARCHAR(20), nullable) columns to ChatSession model
- [X] T003 [P] Create `indico_assistant/services/chat/identity.py` with `IdentityResolution` dataclass and empty `IdentityService` class skeleton

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core utilities that all user stories depend on

**⚠️ CRITICAL**: User story work depends on this phase

- [X] T004 Implement `is_personal_query(question: str) -> bool` helper function in `indico_assistant/services/nl2sql/classifier.py` using regex patterns for "I", "me", "my" pronouns
- [X] T005 [P] Add `IdentityStatus` schema to `indico_assistant/schemas/chat.py` with `source` (str) and `disclaimer` (Optional[str]) fields
- [X] T006 [P] Update `ChatResponse` schema in `indico_assistant/schemas/chat.py` to include `identity_status` in metadata

**Checkpoint**: Foundation ready - user story implementation can begin

---

## Phase 3: User Story 1 - Authenticated User Personal Query (Priority: P1) 🎯 MVP

**Goal**: Fix user_id passthrough so authenticated users get correct personal query results

**Independent Test**: Log in, ask "What meetings do I have?", verify correct results returned

### Implementation for User Story 1

- [X] T007 [US1] Add debug logging in `indico_assistant/controllers/base.py` `_get_user_from_bearer_token()` to trace JWT payload fields and user extraction
- [X] T008 [US1] Fix `indico_assistant/controllers/base.py` `_check_access()` to ensure `self._user` is always set when user is available (from session or JWT)
- [X] T009 [US1] Remove `user_id or 0` fallback in `indico_assistant/services/chat/service.py` `_process_with_nl2sql()` method - pass `user_id` as-is (can be None)
- [X] T010 [US1] Update `indico_assistant/services/nl2sql/pipeline.py` `process()` to accept `user_id: int | None` instead of `user_id: int`
- [X] T011 [US1] Update `indico_assistant/services/nl2sql/generator.py` to handle `user_id=None` case - set context to "unknown" if None
- [X] T012 [US1] Add identity_status metadata to response in `indico_assistant/services/chat/service.py` with `source='authenticated'` when user_id is available

**Checkpoint**: Authenticated users should now get correct personal query results

---

## Phase 4: User Story 2 - Graceful Identity Prompting (Priority: P2)

**Goal**: When user_id unavailable and query is personal, prompt user for identity info

**Independent Test**: Simulate null user_id, ask personal query, verify prompting message returned

### Implementation for User Story 2

- [X] T013 [US2] Implement `lookup_by_email(email: str) -> User | None` in `indico_assistant/services/chat/identity.py` using Indico's User model
- [X] T014 [US2] Implement `lookup_by_name(first_name: str, last_name: str) -> list[User]` in `indico_assistant/services/chat/identity.py` with case-insensitive matching
- [X] T015 [US2] Implement `lookup_by_id(user_id: int) -> User | None` in `indico_assistant/services/chat/identity.py`
- [X] T016 [US2] Implement `extract_identity_from_message(message: str) -> tuple[str, str | None]` in `indico_assistant/services/chat/identity.py` to detect email/name/ID patterns in user messages
- [X] T017 [US2] Implement `resolve_identity(user_id: int | None, message: str, session: ChatSession) -> IdentityResolution` in `indico_assistant/services/chat/identity.py` that orchestrates the full resolution flow
- [X] T018 [US2] Define identity prompting message constant in `indico_assistant/services/chat/identity.py` per spec
- [X] T019 [US2] Update `indico_assistant/services/chat/service.py` `process_message()` to call `is_personal_query()` and `resolve_identity()` before NL2SQL processing
- [X] T020 [US2] Return prompting message when identity needed but unknown in `indico_assistant/services/chat/service.py`
- [X] T021 [US2] Update `indico_assistant/services/chat/session_manager.py` to save `resolved_user_id` and `identity_source` to session when identity resolved
- [X] T022 [US2] Implement multiple-match handling in `indico_assistant/services/chat/identity.py` - return count and ask for email/ID (FR-009)
- [X] T023 [US2] Add disclaimer constant for user-provided identity in `indico_assistant/services/chat/identity.py`

**Checkpoint**: Users without auth context are prompted for identity and can provide name/email

---

## Phase 5: User Story 3 - Transparent Identity Status (Priority: P3)

**Goal**: Response metadata shows identity status so users understand how they were identified

**Independent Test**: Check response metadata includes identity_status with correct source value

### Implementation for User Story 3

- [X] T024 [US3] Update `indico_assistant/controllers/chat.py` `_process()` to include identity_status in response metadata
- [X] T025 [US3] Add disclaimer to response text when `identity_source='user_provided'` in `indico_assistant/services/chat/service.py`
- [X] T026 [US3] Ensure identity_status is populated for all three sources: 'authenticated', 'user_provided', 'unknown'

**Checkpoint**: All user stories functional - identity status visible in API responses

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Tests, documentation, edge cases

- [X] T027 [P] Create unit tests for `is_personal_query()` in `tests/unit/services/nl2sql/test_classifier.py`
- [X] T028 [P] Create unit tests for `IdentityService` methods in `tests/unit/services/chat/test_identity.py`
- [X] T029 [P] Create integration test for authenticated user flow in `tests/integration/test_user_id_passthrough.py`
- [X] T030 [P] Create integration test for identity prompting flow in `tests/integration/test_user_id_passthrough.py`
- [X] T031 Handle edge case: JWT token valid but no identifier field - return identity_source='unknown' in `indico_assistant/controllers/base.py`
- [X] T032 Handle edge case: User lookup database error - catch exception, log, return unknown in `indico_assistant/services/chat/identity.py`
- [ ] T033 Run migration on test database: `indico db --plugin assistant upgrade`

---

## Dependencies

```
T001 ─┬─► T002 ─────────────────────────────────────────────────────────┐
      │                                                                  │
      └─► T003 ─► T013 ─► T014 ─► T015 ─► T016 ─► T017 ─► T019 ─► T020  │
                                                                  │      │
T004 ─────────────────────────────────────────────────────────────┤      │
                                                                  │      │
T005 ─► T006 ────────────────────────────────────────────────────►├──────┤
                                                                  │      │
T007 ─► T008 ─► T009 ─► T010 ─► T011 ─► T012 ─────────────────────┤      │
                                                                  │      │
                                  T018 ─► T019                     │      │
                                                                  │      │
                                  T021 ──────────────────────────►│      │
                                                                  │      │
                                  T022 ─► T023 ─────────────────►│      │
                                                                  │      │
T024 ◄────────────────────────────────────────────────────────────┘      │
  │                                                                      │
  └─► T025 ─► T026                                                       │
                                                                         │
T027, T028, T029, T030 ◄─────────────────────────────────────────────────┘
```

## Parallel Execution Examples

### Wave 1 (Can run simultaneously)
- T001, T002, T003 (different files, no deps)

### Wave 2 (After Wave 1)
- T004, T005, T006, T007 (foundation tasks)

### Wave 3 (US1 Implementation)
- T008 → T009 → T010 → T011 → T012 (sequential within US1)

### Wave 4 (US2 Implementation - can overlap with late US1)
- T013, T014, T015 (parallel lookups)
- T016 → T017 → T019 → T020 (sequential flow)

### Wave 5 (US3 + Polish)
- T024 → T025 → T026 (sequential)
- T027, T028, T029, T030 (parallel tests)

---

## Implementation Strategy

1. **MVP Scope**: User Story 1 (T007-T012) delivers core fix for authenticated users
2. **Incremental**: Each user story adds value independently
3. **Test Coverage**: Unit tests for new services, integration tests for flows
4. **Migration**: Run T033 after T001/T002 to update database schema
