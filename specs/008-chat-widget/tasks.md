# Tasks: Chat Widget for Indico Assistant

**Input**: Design documents from `/specs/008-chat-widget/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, contracts/ ✅

**Tests**: Tests are included as requested by specification (quickstart.md defines validation scenarios).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Plugin source**: `indico_assistant/` (plugin package root)
- **Static assets**: `indico_assistant/static/js/`
- **Tests**: `tests/unit/`, `tests/integration/`, `tests/e2e/`
- **Chainlit app**: `../indico_assistant/src/` (separate workspace)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Plugin settings infrastructure and dependencies

- [X] T001 Add `PyJWT` dependency to `indico_assistant/pyproject.toml` for token generation
- [X] T002 [P] Add widget settings to `indico_assistant/default_settings.py` (enabled, chainlit_url, auth_secret)
- [X] T003 [P] Add settings form fields to `indico_assistant/forms.py` for admin UI configuration

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create `indico_assistant/services/jwt_service.py` with `create_chainlit_token(user, secret)` function per JWT claims schema in research.md R1 (identifier, metadata.name, metadata.email, exp)
- [X] T005 [P] Update `indico_assistant/plugin.py` to add `get_vars_js()` method exposing WidgetConfig schema
- [X] T006 [P] Create `indico_assistant/static/js/chat_widget.js` stub with initialization skeleton
- [X] T007 Update `indico_assistant/plugin.py` to call `inject_bundle('chat_widget.js')` in `init()`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Basic Chat Access (Priority: P1) 🎯 MVP

**Goal**: As an Indico user, I want to access a chat widget from any page in Indico so that I can ask questions without leaving my current context.

**Independent Test**: Load any Indico page → Floating chat button visible → Click opens chat panel → Can send message and receive response

### Tests for User Story 1

- [X] T008 [P] [US1] Create unit test for JWT token generation in `tests/unit/test_jwt_service.py`
- [X] T009 [P] [US1] Create unit test for widget config in `tests/unit/test_widget_config.py`
- [X] T010 [P] [US1] Create E2E test for widget visibility in `tests/e2e/test_chat_widget.py`

### Implementation for User Story 1

- [X] T011 [US1] Load Chainlit Copilot script (`/copilot/index.js`) dynamically in `indico_assistant/static/js/chat_widget.js`
- [X] T012 [US1] Call `window.mountChainlitWidget()` after script loads with config from `IndicoAssistant` global (manual mount required)
- [X] T013 [US1] Add authentication token retrieval from `IndicoAssistant.authToken` in widget JS
- [X] T014 [US1] Configure CORS in `../indico_assistant/.chainlit/config.toml` with `allow_origins`
- [X] T015 [US1] Add `@cl.header_auth_callback` decorator in `../indico_assistant/src/app_chnlit.py` for JWT validation

**Checkpoint**: At this point, User Story 1 should be fully functional - authenticated users can chat

---

## Phase 4: User Story 2 - Conversation Continuity (Priority: P1)

**Goal**: As a returning user, I want my previous conversations preserved so that I can continue where I left off.

**Independent Test**: Send message → Reload page → Chat history persists → Thread ID maintained

### Tests for User Story 2

- [X] T016 [P] [US2] Create integration test for session persistence in `tests/integration/test_session_persistence.py`

### Implementation for User Story 2

- [X] T017 [US2] Enable Chainlit thread persistence via `CHAINLIT_DATABASE_URL` in `../indico_assistant/langfuse/docker-compose.langfuse-v3.yml`
- [X] T018 [US2] Configure localStorage thread ID storage in `indico_assistant/static/js/chat_widget.js`
- [X] T019 [US2] Add thread resumption logic via `accessToken` claim with thread ID

**Checkpoint**: At this point, User Stories 1 AND 2 should both work - chat persists across sessions

---

## Phase 5: User Story 3 - Feedback Collection (Priority: P2)

**Goal**: As an administrator, I want to collect user feedback on chat responses so that I can improve the assistant quality.

**Independent Test**: Click thumbs up/down on response → Feedback stored in database → Visible in admin panel

### Tests for User Story 3

- [X] T020 [P] [US3] Create integration test for feedback bridge in `tests/integration/test_feedback_bridge.py`

### Implementation for User Story 3

- [X] T021 [US3] Implement `@cl.on_feedback` handler in `../indico_assistant/src/app_chnlit.py` to forward to plugin API
- [X] T022 [US3] Add httpx POST to `/api/assistant/feedback` endpoint in feedback handler
- [X] T023 [US3] Add service-to-service auth token for Chainlit→Indico feedback calls

**Checkpoint**: At this point, User Stories 1-3 work - chat with persistence and feedback

---

## Phase 6: User Story 4 - Visual Integration (Priority: P2)

**Goal**: As a user, I want the chat widget to visually match Indico's interface so that it feels like a native feature.

**Independent Test**: Toggle Indico dark mode → Widget theme updates → Colors match Indico palette

### Tests for User Story 4

- [X] T024 [P] [US4] Create E2E test for theme synchronization in `tests/e2e/test_widget_theme.py`

### Implementation for User Story 4

- [X] T025 [US4] Add theme detection logic in `indico_assistant/static/js/chat_widget.js` reading Indico CSS vars
- [X] T026 [US4] Implement `theme` parameter sync with `mountChainlitWidget({ theme: detectedTheme })`
- [X] T027 [US4] Add CSS overrides in `indico_assistant/static/css/chat_widget.css` for Indico palette matching

**Checkpoint**: At this point, User Stories 1-4 work - chat is visually integrated

---

## Phase 7: User Story 5 - Keyboard Accessibility (Priority: P3)

**Goal**: As a keyboard user, I want to access all chat features without a mouse so that I can use the assistant efficiently.

**Independent Test**: Tab to chat button → Enter opens panel → Tab through messages → Escape closes panel

### Tests for User Story 5

- [X] T028 [P] [US5] Create accessibility test for keyboard navigation in `tests/e2e/test_accessibility.py`

### Implementation for User Story 5

- [X] T029 [US5] Add keyboard event listeners (Escape, Enter) in `indico_assistant/static/js/chat_widget.js`
- [X] T030 [US5] Implement focus trap within chat panel when open
- [X] T031 [US5] Add `aria-label` and `role` attributes to widget container element

**Checkpoint**: At this point, User Stories 1-5 work - chat is keyboard accessible

---

## Phase 8: User Story 6 - Screen Reader Support (Priority: P3)

**Goal**: As a screen reader user, I want chat messages announced properly so that I can follow the conversation.

**Independent Test**: VoiceOver/NVDA → New message announced → Chat panel labeled correctly

### Tests for User Story 6

- [X] T031b [P] [US6] Create screen reader test (aria-live announcements) in `tests/e2e/test_accessibility.py`

### Implementation for User Story 6

- [X] T032 [US6] Add `aria-live="polite"` region for new messages in widget initialization
- [X] T033 [US6] Ensure Chainlit widget's built-in ARIA attributes are preserved (no-op verification)
- [X] T034 [US6] Document screen reader testing procedure in `docs/ACCESSIBILITY.md`

**Checkpoint**: All user stories (1-6) should now be independently functional

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T035 [P] Update `indico_assistant/README.md` with chat widget configuration section
- [X] T036 [P] Add widget configuration to `docs/DEPLOYMENT.md`
- [ ] T037 Run `quickstart.md` validation scenarios end-to-end
- [X] T038 Add error handling for Chainlit server unavailability in widget JS
- [X] T039 [P] Add loading state indicator while Chainlit script loads
- [X] T040 Security review: Validate JWT secret rotation documentation
- [X] T041 [P] Verify Chainlit built-in features: auto-scroll (FR-020), multi-line input (FR-021), Enter-to-send (FR-018)
- [X] T042 [P] Add `<noscript>` fallback or CSS `.no-js` class to hide widget container (FR-032/FR-033)
- [X] T043 [P] Document CSP header additions required for Chainlit iframe/script in `docs/DEPLOYMENT.md`

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) ─────────────────────────────────────────────┐
                                                             │
Phase 2 (Foundational) ──────────────────────────────────────┤
                                                             │
                    ┌────────────────────────────────────────┘
                    │
                    ▼
            ┌───────────────┐
            │ US1 (P1) MVP  │ ◄─── Start here for MVP
            └───────┬───────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
    ┌───────┐   ┌───────┐   ┌───────┐
    │US2 P1 │   │US3 P2 │   │US4 P2 │  (can parallelize)
    └───────┘   └───────┘   └───────┘
        │           │           │
        └───────────┼───────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
    ┌───────┐               ┌───────┐
    │US5 P3 │               │US6 P3 │  (can parallelize)
    └───────┘               └───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Phase 9 Polish│
            └───────────────┘
```

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after US1 (needs working chat first)
- **User Story 3 (P2)**: Can start after Foundational - Independent of other stories
- **User Story 4 (P2)**: Can start after Foundational - Independent of other stories
- **User Story 5 (P3)**: Can start after US1 (needs widget to exist)
- **User Story 6 (P3)**: Can start after US1 (needs widget to exist)

### Within Each User Story

- Tests written first, MUST fail before implementation
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- T002 & T003 can run in parallel (different files)
- T005, T006 can run in parallel (different files)
- T008, T009, T010 can run in parallel (all tests for US1)
- US3 (Feedback) and US4 (Theme) can be developed in parallel after US1
- US5 (Keyboard) and US6 (Screen Reader) can be developed in parallel after US1

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all tests for User Story 1 together:
Task T008: "Unit test for JWT token generation in tests/unit/test_jwt_service.py"
Task T009: "Unit test for widget config in tests/unit/test_widget_config.py"
Task T010: "E2E test for widget visibility in tests/e2e/test_chat_widget.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (3 tasks)
2. Complete Phase 2: Foundational (4 tasks)
3. Complete Phase 3: User Story 1 (8 tasks)
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready - **Users can chat!**

### Incremental Delivery

1. Setup + Foundational → Foundation ready (7 tasks)
2. Add User Story 1 → Test independently → Deploy (MVP: basic chat)
3. Add User Story 2 → Test independently → Deploy (chat with persistence)
4. Add User Story 3 → Test independently → Deploy (chat with feedback)
5. Add User Story 4 → Test independently → Deploy (themed chat)
6. Add User Story 5+6 → Test independently → Deploy (accessible chat)

### Parallel Team Strategy

With multiple developers after Phase 2:
- Developer A: User Story 1 (MVP)
- After US1 complete:
  - Developer A: User Story 2 (persistence)
  - Developer B: User Story 3 (feedback)
  - Developer C: User Story 4 (theming)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Chainlit Copilot handles most UI complexity - focus on integration
- JWT secret must match between plugin settings and `CHAINLIT_AUTH_SECRET`
- Test with both authenticated and anonymous users (anonymous should see disabled widget or prompt to log in)
