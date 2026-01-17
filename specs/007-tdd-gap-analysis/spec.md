# Feature Specification: TDD Gap Analysis and Test Completion

**Feature Branch**: `007-tdd-gap-analysis`  
**Created**: 2026-01-16  
**Status**: Draft  
**Input**: User description: "Understand parameters and scope of test driven development, then systematically identify functions/components without unit/integration/contract tests and write and run those tests"

## Clarifications

### Session 2026-01-16

- Q: Do coverage thresholds apply to entire codebase or only new tests? → A: Coverage thresholds apply only to new tests written during this feature; existing gaps are documented but achieving full coverage is a stretch goal
- Q: How should test gaps be prioritized when writing missing tests? → A: Prioritize by risk/complexity: LLM integration services > data persistence services > pure business logic services
- Q: Where should the TDD Scope Document be stored? → A: In `specs/007-tdd-gap-analysis/` as a deliverable of this feature
- Q: What happens to low/medium priority gaps? → A: Documented in Gap Report but deferred to future work; only critical/high are addressed in this feature

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Define TDD Parameters and Scope Document (Priority: P1)

As a development team lead, I want a clear documented definition of TDD parameters and scope for this project so that all developers have a shared understanding of what tests are required for each type of component.

**Why this priority**: Without clear TDD guidelines, test coverage will remain inconsistent. This foundational document is required before any systematic gap identification can occur.

**Independent Test**: Can be fully tested by reviewing the TDD scope document against the constitution's testing requirements and verifying all component types have defined test requirements.

**Acceptance Scenarios**:

1. **Given** the constitution mandates ≥80% unit test coverage on services, **When** the TDD scope document is created, **Then** it explicitly lists which service modules require unit tests
2. **Given** the constitution mandates ≥60% integration test coverage on API endpoints, **When** the TDD scope document is created, **Then** it maps each API endpoint to required integration tests
3. **Given** the constitution mandates contract tests for LLM response models, **When** the TDD scope document is created, **Then** it identifies all Pydantic models requiring contract tests
4. **Given** the TDD scope document exists, **When** a developer creates a new service method, **Then** they can reference the document to know what tests are required

---

### User Story 2 - Inventory Existing Test Coverage (Priority: P1)

As a developer, I want a comprehensive inventory of existing tests mapped to source components so that I can identify which components have adequate test coverage and which have gaps.

**Why this priority**: Cannot identify gaps without first knowing what coverage exists. This is the baseline measurement required for gap analysis.

**Independent Test**: Can be fully tested by running the inventory process and verifying it produces a complete mapping of tests to source files/functions.

**Acceptance Scenarios**:

1. **Given** the test directory structure exists with unit/integration/contract folders, **When** inventory is run, **Then** a report lists all test files with the source files/classes they test
2. **Given** service modules exist under `services/`, **When** inventory is run, **Then** each service module is listed with its current test file coverage status
3. **Given** API controllers exist under `controllers/`, **When** inventory is run, **Then** each controller is listed with its integration test coverage status
4. **Given** Pydantic models exist for LLM responses, **When** inventory is run, **Then** each model is listed with its contract test coverage status

---

### User Story 3 - Identify Unit Test Gaps (Priority: P2)

As a developer, I want to identify service modules/methods that lack unit tests so that I can prioritize writing missing tests.

**Why this priority**: Unit tests are the foundation of test-driven development and have the highest coverage requirement (≥80%). Addressing unit test gaps has the biggest impact on code reliability.

**Independent Test**: Can be fully tested by comparing the inventory against the TDD scope requirements and generating a prioritized list of missing unit tests.

**Acceptance Scenarios**:

1. **Given** service modules exist without corresponding test files, **When** gap analysis runs, **Then** those modules are flagged as "missing all unit tests"
2. **Given** service modules exist with partial test coverage, **When** gap analysis runs, **Then** untested public methods are identified and listed
3. **Given** the constitution requires ≥80% coverage on services, **When** gap analysis runs, **Then** modules below threshold are prioritized by coverage gap size
4. **Given** new services were added (e.g., `document/`, `embedding/`, `vector_search/`, `observability/`), **When** gap analysis runs, **Then** these are identified as requiring new test files

---

### User Story 4 - Identify Integration Test Gaps (Priority: P2)

As a developer, I want to identify API endpoints that lack integration tests so that I can ensure all endpoints have proper end-to-end testing.

**Why this priority**: Integration tests verify the complete request/response cycle. With ≥60% coverage required, gaps here indicate untested API behavior.

**Independent Test**: Can be fully tested by comparing endpoint definitions against existing integration tests.

**Acceptance Scenarios**:

1. **Given** controllers define API endpoints, **When** gap analysis runs, **Then** endpoints without integration tests are identified
2. **Given** the chat API has multiple endpoints, **When** gap analysis runs, **Then** coverage for `/api/assistant/chat`, `/api/assistant/sessions`, `/api/assistant/feedback` is assessed
3. **Given** controllers exist for admin, search, health, **When** gap analysis runs, **Then** each controller's endpoints are mapped to integration tests

---

### User Story 5 - Identify Contract Test Gaps (Priority: P2)

As a developer, I want to identify Pydantic models (especially LLM response models) that lack contract tests so that I can ensure type safety boundaries are verified.

**Why this priority**: Contract tests are critical for LLM integrations where response shapes can vary. Constitution mandates contract tests for LLM response models.

**Independent Test**: Can be fully tested by scanning `services/llm/models/` and other Pydantic model definitions against existing contract tests.

**Acceptance Scenarios**:

1. **Given** Pydantic models exist in `services/llm/models/`, **When** gap analysis runs, **Then** each model is checked for corresponding contract tests
2. **Given** the schemas directory contains API response schemas, **When** gap analysis runs, **Then** request/response contracts are verified
3. **Given** NL2SQL has structured output models, **When** gap analysis runs, **Then** each model (query classification, generated SQL, etc.) is mapped to contract tests

---

### User Story 6 - Write and Run Missing Tests (Priority: P3)

As a developer, I want to systematically write tests for identified gaps and run them to verify they pass and improve coverage.

**Why this priority**: This is the execution phase that depends on all previous analysis. Lower priority because it requires the gap identification to be complete first.

**Independent Test**: Can be fully tested by selecting a gap, writing the test, running pytest, and verifying coverage improvement.

**Acceptance Scenarios**:

1. **Given** a unit test gap is identified for a service method, **When** the test is written, **Then** it follows pytest conventions and uses appropriate fixtures
2. **Given** an integration test gap is identified for an endpoint, **When** the test is written, **Then** it tests the full request/response cycle with mocked dependencies
3. **Given** a contract test gap is identified for a Pydantic model, **When** the test is written, **Then** it verifies model validation, serialization, and edge cases
4. **Given** tests are written, **When** pytest runs, **Then** all new tests pass and coverage increases toward thresholds

---

### Edge Cases

- What happens when a source file has no public methods to test? → Document as "no test required" with justification
- What happens when a test file exists but tests private methods only? → Flag as needing refactoring to test public interface
- What happens when coverage is calculated differently by different tools? → Use pytest-cov as the authoritative source
- What happens when integration tests require external services? → Use mocks/fixtures, document in test prerequisites
- What happens when contract tests conflict with actual LLM behavior? → Contract tests define expected behavior; document deviations

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST produce a TDD Scope Document defining test requirements for each component type (services, controllers, models, schemas)
- **FR-002**: System MUST generate an inventory report mapping existing test files to their corresponding source files
- **FR-003**: System MUST identify service modules lacking the required ≥80% unit test coverage
- **FR-004**: System MUST identify API endpoints lacking integration tests
- **FR-005**: System MUST identify Pydantic models (especially LLM response models) lacking contract tests
- **FR-006**: System MUST prioritize gaps by risk/complexity: LLM integration services (highest) > data persistence services > pure business logic services (lowest)
- **FR-007**: System MUST provide test templates/patterns for each test type (unit, integration, contract)
- **FR-008**: Tests written MUST follow the existing project conventions (pytest, indico fixtures, mocking patterns)
- **FR-009**: System MUST verify new tests pass before considering a gap resolved
- **FR-010**: System MUST track coverage improvements after each test addition

### Key Entities

- **TDD Scope Document**: Defines test requirements by component type, coverage thresholds, and test patterns; stored in `specs/007-tdd-gap-analysis/tdd-scope.md`
- **Coverage Inventory**: Maps source files → test files → coverage percentage
- **Gap Report**: Prioritized list of components missing required tests with severity (critical/high/medium/low); low/medium gaps are deferred to future work
- **Test Template**: Reusable patterns for unit/integration/contract tests specific to this project

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: TDD Scope Document is created and reviewed, covering all component types in the project
- **SC-002**: Coverage inventory accurately reflects current state with less than 5% variance from actual pytest-cov measurements
- **SC-003**: All service modules in `services/` have corresponding unit test files identified or gaps documented
- **SC-004**: All controllers in `controllers/` have integration test mapping completed
- **SC-005**: All Pydantic models in `services/llm/models/` and `schemas/` have contract test mapping completed
- **SC-006**: New unit tests written during this feature achieve ≥80% coverage on the specific modules they target (full codebase coverage is a stretch goal)
- **SC-007**: New integration tests written during this feature achieve ≥60% coverage on the specific endpoints they target (full codebase coverage is a stretch goal)
- **SC-008**: All identified critical and high priority gaps have tests written and passing
- **SC-009**: New tests follow project conventions and use existing fixtures appropriately
- **SC-010**: Test suite execution time remains reasonable (under 5 minutes for unit tests, under 10 minutes for full suite)

## Assumptions

- The constitution's coverage thresholds (≥80% unit, ≥60% integration) are the authoritative requirements
- pytest-cov is the authoritative tool for measuring coverage
- Existing test fixtures in `conftest.py` should be reused where applicable
- Tests should be deterministic and not require external services (LLM, database) running
- The current test directory structure (unit/, integration/, contract/) is the correct organization
- Priority should be given to testing public interfaces over internal implementation details
