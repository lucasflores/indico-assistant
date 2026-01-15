# Tasks: Plugin Foundation

**Input**: Design documents from `/specs/001-plugin-foundation/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Tests included per constitution principle VI (Test-First Development).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1-US5) - only in user story phases

---

## Phase 1: Setup

**Purpose**: Project initialization and basic structure

- [X] T001 Create pyproject.toml with indico.plugins entry point at pyproject.toml
- [X] T002 Create package __init__.py with version export at indico_assistant/__init__.py
- [X] T003 [P] Create default_settings.py with DEFAULT_SETTINGS dict at indico_assistant/default_settings.py
- [X] T004 [P] Create version.py with Indico version check utility at indico_assistant/version.py
- [X] T005 [P] Create tests/conftest.py with pytest_plugins and base fixtures at tests/conftest.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T006 Create plugin.py with AssistantPlugin class skeleton (subclass IndicoPlugin, configurable=True, empty init()) at indico_assistant/plugin.py
- [X] T007 Create blueprint.py with IndicoPluginBlueprint named 'assistant' with url_prefix='/api/assistant' at indico_assistant/blueprint.py
- [X] T008 [P] Create controllers.py with imports (RH from indico.web.rh, jsonify from flask) at indico_assistant/controllers.py
- [X] T009 [P] Create forms.py with imports (IndicoForm from indico.web.forms.base, field types from wtforms) at indico_assistant/forms.py
- [X] T010 [P] Create cli.py with click group 'assistant' and signal connection stub at indico_assistant/cli.py

**Checkpoint**: Foundation ready - user story implementation can begin

---

## Phase 3: User Story 1 - Install and Enable Plugin (Priority: P1) 🎯 MVP

**Goal**: Plugin installs via pip, Indico starts without errors, plugin appears in admin list

**Independent Test**: Install plugin, start Indico, verify plugin listed and no startup errors

### Tests for User Story 1

- [X] T011 [P] [US1] Create test_plugin.py with plugin initialization tests at tests/unit/test_plugin.py
- [X] T012 [P] [US1] Create test_version.py with version check tests at tests/unit/test_version.py

### Implementation for User Story 1

- [X] T013 [US1] Implement version check in version.py with MINIMUM_INDICO_VERSION at indico_assistant/version.py
- [X] T014 [US1] Implement AssistantPlugin.init() with lazy LLM init at indico_assistant/plugin.py
- [X] T015 [US1] Add default_settings to AssistantPlugin class at indico_assistant/plugin.py
- [X] T016 [US1] Register blueprint in plugin.py at indico_assistant/plugin.py
- [X] T017 [US1] Update __init__.py to call version check on import at indico_assistant/__init__.py

**Checkpoint**: Plugin installs, Indico starts, plugin visible in admin list

---

## Phase 4: User Story 2 - Configure Global Settings (Priority: P1)

**Goal**: Admin can configure LLM provider settings via UI form

**Independent Test**: Access plugin settings, change values, verify persistence

### Tests for User Story 2

- [X] T018 [P] [US2] Create test_forms.py with SettingsForm validation tests at tests/unit/test_forms.py
- [X] T019 [P] [US2] Create test_settings.py with settings persistence tests at tests/integration/test_settings.py

### Implementation for User Story 2

- [X] T020 [US2] Implement SettingsForm with all fields in forms.py at indico_assistant/forms.py
- [X] T021 [US2] Add URL validation to SettingsForm.llm_base_url at indico_assistant/forms.py
- [X] T022 [US2] Add PasswordField for llm_api_key with masking at indico_assistant/forms.py
- [X] T023 [US2] Wire SettingsForm to AssistantPlugin.settings_form at indico_assistant/plugin.py
- [X] T024 [US2] Add field-level validation (timeout range, max_tokens range) at indico_assistant/forms.py

**Checkpoint**: Admin can configure all global settings, values persist

---

## Phase 5: User Story 3 - Check Service Health (Priority: P2)

**Goal**: Health endpoint returns accurate status of plugin and LLM service

**Independent Test**: Call GET /api/assistant/health, verify JSON matches OpenAPI schema

### Tests for User Story 3

- [X] T025 [P] [US3] Create test_api_health.py contract test at tests/contract/test_api_health.py
- [X] T026 [P] [US3] Create test_health.py integration test at tests/integration/test_health.py

### Implementation for User Story 3

- [X] T027 [US3] Implement RHHealth controller in controllers.py at indico_assistant/controllers.py
- [X] T028 [US3] Add health status computation logic (healthy/degraded/unhealthy) at indico_assistant/controllers.py
- [X] T029 [US3] Register /health route in blueprint.py at indico_assistant/blueprint.py
- [X] T030 [US3] Add LLM connectivity check to health computation at indico_assistant/controllers.py
- [X] T031 [US3] Add timestamp and version info to health response at indico_assistant/controllers.py

**Checkpoint**: Health endpoint works, returns correct status

---

## Phase 6: User Story 4 - Configure Per-Event Settings (Priority: P2)

**Goal**: Event managers can customize assistant settings per event

**Independent Test**: Access event settings, configure override, verify it applies to that event only

### Tests for User Story 4

- [X] T032 [P] [US4] Add event settings tests to test_settings.py at tests/integration/test_settings.py

### Implementation for User Story 4

- [X] T033 [US4] Implement EventSettingsForm in forms.py at indico_assistant/forms.py
- [X] T034 [US4] Add event_settings_schema to AssistantPlugin at indico_assistant/plugin.py
- [X] T035 [US4] Connect event menu signal for settings page at indico_assistant/plugin.py
- [X] T036 [US4] Implement get_effective_setting() helper for inheritance at indico_assistant/plugin.py

**Checkpoint**: Event managers can configure per-event overrides

---

## Phase 7: User Story 5 - Run Admin CLI Commands (Priority: P3)

**Goal**: Admin can run assistant commands from terminal

**Independent Test**: Run `indico assistant health` and `indico assistant config show`

### Tests for User Story 5

- [X] T037 [P] [US5] Create test_cli.py with CLI command tests at tests/unit/test_cli.py

### Implementation for User Story 5

- [X] T038 [US5] Implement health CLI command in cli.py at indico_assistant/cli.py
- [X] T039 [US5] Implement config show CLI command in cli.py at indico_assistant/cli.py
- [X] T040 [US5] Connect CLI commands via signals.plugin.cli at indico_assistant/plugin.py
- [X] T041 [US5] Add masked output for sensitive settings in config command at indico_assistant/cli.py

**Checkpoint**: CLI commands work, output matches API

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Quality improvements across all user stories

- [X] T042 [P] Add docstrings to all public functions and classes
- [X] T043 [P] Create README.md with installation and configuration instructions at README.md
- [X] T044 Run quickstart.md validation scenarios (all 8 scenarios)
- [X] T045 Verify test coverage meets targets (80% services, 60% endpoints)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - start immediately
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational completion
  - US1 (P1) → US2 (P1) → US3 (P2) → US4 (P2) → US5 (P3)
  - Or work in parallel if staffed
- **Polish (Phase 8)**: After all stories complete

### User Story Dependencies

- **US1**: No dependencies after Foundational
- **US2**: Builds on US1 (plugin must load to show settings)
- **US3**: Builds on US1 (needs blueprint registered)
- **US4**: Builds on US2 (extends settings pattern)
- **US5**: Builds on US3 (CLI health mirrors API health)

### Parallel Opportunities Per Phase

```text
Phase 1: T003, T004, T005 can run in parallel
Phase 2: T008, T009, T010 can run in parallel
Phase 3: T011, T012 can run in parallel
Phase 4: T018, T019 can run in parallel
Phase 5: T025, T026 can run in parallel
Phase 6: T032 standalone
Phase 7: T037 standalone
Phase 8: T042, T043 can run in parallel
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T010)
3. Complete Phase 3: User Story 1 (T011-T017)
4. Complete Phase 4: User Story 2 (T018-T024)
5. **STOP and VALIDATE**: Plugin installs, settings work
6. Deploy/demo MVP

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Plugin loads → Testable
3. Add US2 → Settings work → First admin value
4. Add US3 → Health endpoint → Ops-ready
5. Add US4 → Per-event config → Event manager value
6. Add US5 → CLI → Automation-ready
7. Polish → Production-ready

---

## Notes

- All tasks include exact file paths
- [P] = parallelizable (different files)
- [US#] = maps to user story for traceability
- Tests written first per constitution
- Commit after each task or logical group
- Verify tests fail before implementing
