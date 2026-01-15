# Tasks: LLM Service Abstraction Layer

**Input**: Design documents from `/specs/002-llm-service-layer/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

**Tests**: Unit and contract tests included per Constitution Principle VI (Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

Based on plan.md structure:
- **Source**: `indico_assistant/services/llm/`
- **Tests**: `tests/unit/services/llm/`, `tests/contract/llm/`

---

## Phase 1: Setup

**Purpose**: Create directory structure and add dependencies

- [X] T001 Create LLM service directory structure: `indico_assistant/services/llm/` with `__init__.py`, `models/` subdirectory
- [X] T002 Create test directory structure: `tests/unit/services/llm/`, `tests/contract/llm/` with `__init__.py` files
- [X] T003 Add dependencies to `pyproject.toml`: instructor>=1.0.0, openai>=1.0.0, ollama>=0.3.0

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core error types and base models that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 [P] Create ErrorType enum and LLMError model in `indico_assistant/services/llm/errors.py`
- [X] T005 [P] Create LLMResponse[T] generic wrapper in `indico_assistant/services/llm/models/base.py`
- [X] T006 [P] Create HealthStatus model in `indico_assistant/services/llm/models/base.py`
- [X] T007 Create `indico_assistant/services/llm/models/__init__.py` with exports for LLMResponse, HealthStatus (note: LLMError is in errors.py, re-exported at package level)
- [X] T008 [P] Create contract tests for LLMError validation in `tests/contract/llm/test_error_models.py`
- [X] T009 [P] Create contract tests for LLMResponse consistency rules in `tests/contract/llm/test_response_models.py`

**Checkpoint**: Foundation ready - LLMError and LLMResponse can be imported and used

---

## Phase 3: User Story 1 - Make Structured LLM Calls (Priority: P1) 🎯 MVP

**Goal**: Developers can call `llm_service.generate(prompt, ResponseModel)` and receive validated Pydantic responses

**Independent Test**: Call generate() with a test model, verify validated response or structured error returned

### Tests for User Story 1

- [X] T010 [P] [US1] Unit test for LLMService.generate() success path in `tests/unit/services/llm/test_service.py`
- [X] T011 [P] [US1] Unit test for LLMService.generate() retry on validation failure in `tests/unit/services/llm/test_service.py`
- [X] T012 [P] [US1] Unit test for LLMService.generate() returns LLMError after max retries in `tests/unit/services/llm/test_service.py`

### Implementation for User Story 1

- [X] T013 [US1] Create LLMService class skeleton with `__init__`, `generate`, `_create_client` methods in `indico_assistant/services/llm/service.py`
- [X] T014 [US1] Implement `_get_settings()` helper to extract LLM config from plugin settings in `indico_assistant/services/llm/service.py`
- [X] T015 [US1] Implement `_create_client()` using `instructor.from_provider()` in `indico_assistant/services/llm/service.py`
- [X] T016 [US1] Implement `generate()` method with Instructor client.create() call in `indico_assistant/services/llm/service.py`
- [X] T017 [US1] Add latency tracking, retry counting, and log each retry attempt with validation error details (FR-008) in `indico_assistant/services/llm/service.py`
- [X] T018 [US1] Add structured logging (metadata only, no content) to generate() in `indico_assistant/services/llm/service.py`
- [X] T019 [US1] Create `indico_assistant/services/llm/__init__.py` with exports for LLMService, create_llm_service factory

**Checkpoint**: LLMService.generate() works with any Pydantic model; returns LLMResponse with success or error

---

## Phase 4: User Story 2 - Switch LLM Providers via Configuration (Priority: P1)

**Goal**: Provider switching works by changing plugin settings only, no code changes required

**Independent Test**: Change provider setting, verify subsequent calls use new provider

### Tests for User Story 2

- [X] T020 [P] [US2] Unit test for client factory with Ollama provider in `tests/unit/services/llm/test_factory.py`
- [X] T021 [P] [US2] Unit test for client factory with HuggingFace provider in `tests/unit/services/llm/test_factory.py`
- [X] T022 [P] [US2] Unit test for client factory with OpenAI-compatible provider in `tests/unit/services/llm/test_factory.py`
- [X] T023 [P] [US2] Unit test for unsupported provider returns not_configured error in `tests/unit/services/llm/test_factory.py`

### Implementation for User Story 2

- [X] T024 [US2] Extract client creation logic to `create_instructor_client()` factory in `indico_assistant/services/llm/factory.py`
- [X] T025 [US2] Implement Ollama provider support in factory (format: `ollama/{model}`) in `indico_assistant/services/llm/factory.py`
- [X] T026 [US2] Implement HuggingFace provider support via OpenAI client with custom base_url in `indico_assistant/services/llm/factory.py`
- [X] T027 [US2] Implement generic OpenAI-compatible provider support in `indico_assistant/services/llm/factory.py`
- [X] T028 [US2] Add provider validation with not_configured error for unknown providers in `indico_assistant/services/llm/factory.py`
- [X] T029 [US2] Update LLMService._create_client() to use factory function in `indico_assistant/services/llm/service.py`
- [X] T030 [US2] Export create_instructor_client from `indico_assistant/services/llm/__init__.py`

**Checkpoint**: Provider can be switched via plugin settings; factory creates correct client for each provider

---

## Phase 5: User Story 3 - Check Provider Health (Priority: P2)

**Goal**: Administrators can verify LLM provider connectivity and latency

**Independent Test**: Call health_check(), verify status and latency returned

### Tests for User Story 3

- [X] T031 [P] [US3] Unit test for health_check() returns connected status on success in `tests/unit/services/llm/test_service.py`
- [X] T032 [P] [US3] Unit test for health_check() returns unavailable on connection error in `tests/unit/services/llm/test_service.py`
- [X] T033 [P] [US3] Unit test for health_check() returns timeout status on timeout in `tests/unit/services/llm/test_service.py`

### Implementation for User Story 3

- [X] T034 [US3] Create HealthCheckResponse internal model for minimal LLM test in `indico_assistant/services/llm/service.py`
- [X] T035 [US3] Implement `health_check()` method with minimal LLM call in `indico_assistant/services/llm/service.py`
- [X] T036 [US3] Add latency measurement to health_check() in `indico_assistant/services/llm/service.py`
- [X] T037 [US3] Update plugin.py to expose llm_service.health_check() for existing health endpoint in `indico_assistant/plugin.py`
- [X] T038 [US3] Integration test for health endpoint with LLM status in `tests/integration/test_llm_health.py`

**Checkpoint**: health_check() returns HealthStatus with provider connectivity info

---

## Phase 6: User Story 4 - Handle LLM Errors Gracefully (Priority: P2)

**Goal**: All LLM errors are wrapped in structured LLMError objects, never raised as exceptions

**Independent Test**: Simulate error conditions, verify structured LLMError returned

### Tests for User Story 4

- [X] T039 [P] [US4] Unit test for timeout error mapping in `tests/unit/services/llm/test_errors.py`
- [X] T040 [P] [US4] Unit test for connection error mapping in `tests/unit/services/llm/test_errors.py`
- [X] T041 [P] [US4] Unit test for rate limit error mapping in `tests/unit/services/llm/test_errors.py`
- [X] T042 [P] [US4] Unit test for authentication error mapping in `tests/unit/services/llm/test_errors.py`

### Implementation for User Story 4

- [X] T043 [US4] Create `_map_exception_to_error()` helper for exception → LLMError mapping in `indico_assistant/services/llm/errors.py`
- [X] T044 [US4] Add try/except wrapper to generate() catching all provider exceptions in `indico_assistant/services/llm/service.py`
- [X] T045 [US4] Ensure API keys are never logged (only present/absent) in error handling in `indico_assistant/services/llm/service.py`
- [X] T046 [US4] Add error mapping to health_check() for unavailable/timeout status in `indico_assistant/services/llm/service.py`

**Checkpoint**: All exceptions caught and converted to LLMError; no exceptions leak to callers

---

## Phase 7: User Story 5 - Use Pre-defined Response Models (Priority: P3)

**Goal**: Developers can import and use pre-defined Pydantic models for common tasks

**Independent Test**: Import models, use in generate() call, verify structured output

### Tests for User Story 5

- [X] T047 [P] [US5] Contract test for QueryClassification model validation in `tests/contract/llm/test_models.py`
- [X] T048 [P] [US5] Contract test for SQLGeneration model with SQL safety validation in `tests/contract/llm/test_models.py`
- [X] T049 [P] [US5] Contract test for SQLCorrection model in `tests/contract/llm/test_models.py`
- [X] T050 [P] [US5] Contract test for ResponseSummary model confidence bounds in `tests/contract/llm/test_models.py`

### Implementation for User Story 5

- [X] T051 [P] [US5] Create Entity and TimeRange nested models in `indico_assistant/services/llm/models/classification.py`
- [X] T052 [P] [US5] Create QueryClassification model in `indico_assistant/services/llm/models/classification.py`
- [X] T053 [P] [US5] Create SQLGeneration model with SQL safety validator in `indico_assistant/services/llm/models/sql.py`
- [X] T054 [P] [US5] Create SQLCorrection model in `indico_assistant/services/llm/models/sql.py`
- [X] T055 [P] [US5] Create ResponseSummary model with confidence bounds in `indico_assistant/services/llm/models/summary.py`
- [X] T056 [US5] Update `indico_assistant/services/llm/models/__init__.py` to export all pre-defined models
- [X] T057 [US5] Update `indico_assistant/services/llm/__init__.py` to export models at package level

**Checkpoint**: All pre-defined models importable from `indico_assistant.services.llm`

---

## Phase 8: Polish & Integration

**Purpose**: Final integration, documentation, and validation

- [X] T058 [P] Update `indico_assistant/services/__init__.py` to export LLM service
- [X] T059 Add `llm_service` property to AssistantPlugin with lazy initialization in `indico_assistant/plugin.py` (service instantiation only)
- [X] T060 [P] Run all tests and verify ≥80% coverage on services/llm
- [X] T061 [P] Run quickstart.md validation scenarios
- [X] T062 Update health endpoint controller to call llm_service.health_check() and include result in response in `indico_assistant/controllers.py`

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) ← BLOCKS all user stories
    ↓
┌───────────────────────────────────────────────────────┐
│  Phase 3 (US1) ─────→ Phase 4 (US2)                  │
│       ↓                    ↓                          │
│  Phase 5 (US3) ←── depends on service                │
│       ↓                                               │
│  Phase 6 (US4) ←── builds on error handling          │
│       ↓                                               │
│  Phase 7 (US5) ←── independent models                │
└───────────────────────────────────────────────────────┘
    ↓
Phase 8 (Polish)
```

### User Story Dependencies

| User Story | Depends On | Can Parallel With |
|------------|------------|-------------------|
| US1 (Make Calls) | Phase 2 only | - |
| US2 (Switch Providers) | US1 (needs service) | - |
| US3 (Health Check) | US1 + US2 (needs service + factory) | - |
| US4 (Error Handling) | US1 (needs service) | US3 |
| US5 (Response Models) | Phase 2 only | US1, US2, US3, US4 |

### Parallel Opportunities by Phase

**Phase 2** (all [P] tasks):
```
T004 (ErrorType/LLMError) || T005 (LLMResponse) || T006 (HealthStatus)
T008 (error tests) || T009 (response tests)
```

**Phase 3** (tests):
```
T010 || T011 || T012
```

**Phase 4** (tests):
```
T020 || T021 || T022 || T023
```

**Phase 5** (tests):
```
T031 || T032 || T033
```

**Phase 6** (tests):
```
T039 || T040 || T041 || T042
```

**Phase 7** (tests + models):
```
T047 || T048 || T049 || T050  (tests)
T051 || T052 || T053 || T054 || T055  (models)
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1: Setup (3 tasks)
2. Complete Phase 2: Foundational (6 tasks)
3. Complete Phase 3: US1 - Make Structured Calls (10 tasks)
4. Complete Phase 4: US2 - Provider Switching (11 tasks)
5. **VALIDATE MVP**: Test generate() with Ollama, switch to HuggingFace, verify
6. Deploy/demo MVP functionality

### Incremental Additions

- Add US3 (Health Check) → Operational monitoring
- Add US4 (Error Handling) → Production reliability
- Add US5 (Response Models) → Developer convenience

### Task Count Summary

| Phase | Tasks | Cumulative |
|-------|-------|------------|
| Setup | 3 | 3 |
| Foundational | 6 | 9 |
| US1 (P1) | 10 | 19 |
| US2 (P1) | 11 | 30 |
| US3 (P2) | 8 | 38 |
| US4 (P2) | 8 | 46 |
| US5 (P3) | 11 | 57 |
| Polish | 5 | 62 |

**Total**: 62 tasks

---

## Notes

- Tests use mocked Instructor client to avoid actual LLM calls
- API keys must never appear in logs (FR-025)
- All methods return structured responses, never raise exceptions (FR-017)
- Settings already exist from 001-plugin-foundation (no changes to default_settings.py)
