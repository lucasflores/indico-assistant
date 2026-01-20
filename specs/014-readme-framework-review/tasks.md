---
description: "Task list for README framework review and update"
---

# Tasks: Comprehensive Framework Review and README Update

**Input**: Design documents from `/specs/014-readme-framework-review/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: No test tasks included - this is a documentation-only feature

**Organization**: Tasks are grouped by user story to enable independent implementation and validation of each documentation goal.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different sections, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

All tasks modify: `README.md` at repository root

Verification against:
- `indico_assistant/default_settings.py`
- `indico_assistant/cli.py`
- `indico_assistant/controllers/*.py`
- `pyproject.toml`
- `indico_assistant/version.py`
- `specs/001-*/spec.md` through `specs/013-*/spec.md`

---

## Phase 1: Setup (Document Structure Foundation)

**Purpose**: Establish README structure and navigation framework

- [X] T001 Update version badge to v0.1.0 and last updated date in README.md header
- [X] T002 Create table of contents with markdown anchor links in README.md (per contracts/toc-structure.md)
- [X] T003 Verify all TOC anchor links resolve to actual section headers in README.md

**Checkpoint**: README has navigable structure - content updates can now proceed in parallel

---

## Phase 2: Foundational (Core Information Sections)

**Purpose**: Essential information that ALL users need (requirements, installation)

**⚠️ CRITICAL**: These sections provide baseline context for all other content

- [X] T004 Write Requirements section documenting Indico 3.3+, Python 3.11+, PostgreSQL in README.md
- [X] T005 Write Installation section with PyPI and development installation methods in README.md (per contracts/installation-section.md)
- [X] T006 Verify installation commands match pyproject.toml package name

**Checkpoint**: Users can install the plugin - feature-specific documentation can now be added independently

---

## Phase 3: User Story 1 - Developer Onboarding (Priority: P1) 🎯 MVP

**Goal**: Enable new developers to understand, install, and configure the plugin within 15 minutes

**Independent Test**: A developer unfamiliar with the project can read the README and successfully install, configure, and use basic features

### Implementation for User Story 1

- [X] T007 [P] [US1] Write Configuration > Global Settings subsection with table of 7 settings in README.md (verify against default_settings.py)
- [X] T008 [P] [US1] Write Configuration > Chat Widget Settings subsection with table of 3 settings in README.md (verify against default_settings.py)
- [X] T009 [P] [US1] Write Configuration > Per-Event Settings subsection in README.md (per contracts/configuration-section.md)
- [X] T010 [P] [US1] Write NL2SQL Pipeline section with Python usage example in README.md
- [X] T011 [P] [US1] Create supported question types table in NL2SQL section (event counts, lists, registrations, contributions, speakers)
- [X] T012 [P] [US1] Document NL2SQL security features list (SELECT-only, table allowlist, permissions, timeout, row limit) in README.md
- [X] T013 [US1] Write CLI Commands section documenting 5 commands with examples in README.md (verify against cli.py)
- [X] T014 [US1] Run quickstart.md validation Step 1 (Version Accuracy)
- [X] T015 [US1] Run quickstart.md validation Step 3 (Configuration Settings Accuracy)
- [X] T016 [US1] Run quickstart.md validation Step 5 (CLI Commands Accuracy)

**Checkpoint**: Developer onboarding complete - developers can install, configure, and use basic NL2SQL features

---

## Phase 4: User Story 4 - Comprehensive Feature Documentation (Priority: P1) 🎯 MVP

**Goal**: Accurately document all 13 implemented features so stakeholders understand complete capabilities

**Independent Test**: Users can identify all 13 completed features and understand their purpose, with links to detailed documentation where available

### Implementation for User Story 4

- [X] T017 [P] [US4] Write Features section Group 1: Core Capabilities (NL, Conversation History, NL2SQL) in README.md
- [X] T018 [P] [US4] Write Features section Group 2: LLM Integration (Multiple Providers, Structured Outputs, Provider Abstraction) in README.md
- [X] T019 [P] [US4] Write Features section Group 3: Document Intelligence (Vector Search RAG, Real-time Indexing with sub-bullets) in README.md
- [X] T020 [P] [US4] Write Features section Group 4: User Interface (Embedded Chat Widget with sub-bullets) in README.md
- [X] T021 [P] [US4] Write Features section Group 5: Configuration & Management (Per-Event Config, Health Monitoring, CLI Tools) in README.md
- [X] T022 [P] [US4] Write Features section Group 6: Observability & Quality (Langfuse, Test Coverage) in README.md
- [X] T023 [US4] Add links to detailed docs: Vector Search→VECTOR_SEARCH_SETUP.md, Chat Widget→DEPLOYMENT.md, Observability→LANGFUSE_SETUP.md in README.md
- [ ] T024 [US4] Run quickstart.md validation Step 6 (Feature Descriptions Accuracy - compare against specs/001-013)
- [ ] T025 [US4] Run quickstart.md validation Step 7 (External Documentation Links)

**Checkpoint**: All 13 features documented - users have complete understanding of capabilities

---

## Phase 5: User Story 2 - Feature Discovery (Priority: P2)

**Goal**: Enable administrators to understand LLM providers, question types, event configuration, and monitoring options

**Independent Test**: An administrator can read the README and determine which LLM providers are supported, what questions can be answered, how to configure per event, and what monitoring exists

### Implementation for User Story 2

- [X] T026 [P] [US2] Write API Endpoints > Health Check subsection with GET /api/assistant/health in README.md
- [X] T027 [P] [US2] Document health check response format with status values (healthy, degraded, unhealthy) in README.md
- [X] T027.5 [US2] Verify existence of observability settings (langfuse_enabled, langfuse_public_key, etc.) and vector search settings (vector_search_enabled, embedding_model, etc.) in indico_assistant/default_settings.py to determine if T028-T029 apply
- [X] T028 [P] [US2] Add Configuration > Observability Settings subsection (if Langfuse settings exist per T027.5) in README.md
- [X] T029 [P] [US2] Add Configuration > Vector Search Settings subsection (if vector search settings exist per T027.5) in README.md
- [X] T030 [US2] Run quickstart.md validation Step 4 (API Endpoints Accuracy - health endpoint)

**Checkpoint**: Administrators can discover and configure all plugin capabilities

---

## Phase 6: User Story 3 - Technical Reference (Priority: P3)

**Goal**: Enable developers to understand architecture, use APIs, set up dev environment, and contribute code

**Independent Test**: A developer can use the README to understand the codebase, find/use API endpoints, set up dev environment, and run tests in under 10 minutes

### Implementation for User Story 3

- [X] T031 [P] [US3] Write API Endpoints > Chat Endpoints subsection (4 endpoints: create session, list sessions, send message, get history) in README.md
- [X] T032 [P] [US3] Write API Endpoints > Search Endpoint subsection with POST /api/assistant/search in README.md
- [X] T033 [P] [US3] Write API Endpoints > Feedback Endpoint subsection with POST /api/assistant/feedback in README.md
- [X] T034 [P] [US3] Add request/response JSON examples for all 7 API endpoints in README.md (per contracts/api-endpoints-section.md)
- [X] T035 [P] [US3] Write Development > Setup subsection with virtual environment and installation commands in README.md
- [X] T036 [P] [US3] Write Development > Testing subsection with pytest commands and test organization in README.md
- [X] T037 [P] [US3] Write Development > Code Quality subsection with ruff, black, mypy commands in README.md
- [X] T038 [P] [US3] Write Architecture section with directory tree and module descriptions in README.md
- [X] T039 [P] [US3] Write Security section documenting 6 security features (SQL injection prevention, permission filtering, JWT auth, secret handling, rate limiting, audit logging) in README.md
- [X] T040 [US3] Run quickstart.md validation Step 4 (API Endpoints Accuracy - all 7 endpoints vs controllers/*.py)
- [X] T041 [US3] Run quickstart.md validation Step 8 (Architecture Section Accuracy vs actual file structure)
- [X] T042 [US3] Run quickstart.md validation Step 10 (Code Examples Validity)

**Checkpoint**: Technical reference complete - developers can contribute and integrate

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final touches, cross-references, and comprehensive validation

- [X] T043 [P] Write Documentation section with links to all 4 external docs (DEPLOYMENT.md, ACCESSIBILITY.md, LANGFUSE_SETUP.md, VECTOR_SEARCH_SETUP.md) in README.md
- [X] T044 [P] Write License section with MIT license and link to LICENSE file in README.md
- [X] T045 [P] Write Contributing section (if contribution guidelines exist) in README.md
- [X] T046 Run quickstart.md validation Step 2 (Dependencies Accuracy vs pyproject.toml)
- [X] T047 Run quickstart.md validation Step 9 (Table of Contents Navigation - test all links)
- [X] T048 Review README for consistency: terminology, formatting, tone
- [X] T049 Check README length is 300-500 lines and readable in 10-15 minutes
- [X] T050 Final proofread: spelling, grammar, markdown syntax

**Final Checkpoint**: README complete, accurate, and validated against codebase

---

## Task Dependencies

### Parallel Execution Opportunities

**Phase 1**: All tasks sequential (structure foundation)

**Phase 2**: All tasks sequential (baseline information)

**Phase 3 (US1)**: 
- T007-T013 can run in parallel (different sections)
- T014-T016 sequential (validation after content)

**Phase 4 (US4)**:
- T017-T022 can run in parallel (different feature groups)
- T023-T025 sequential (links and validation after content)

**Phase 5 (US2)**:
- T026-T029 can run in parallel (different subsections)
- T030 after T026-T027 (validation)

**Phase 6 (US3)**:
- T031-T039 can run in parallel (different sections)
- T040-T042 sequential (validation after content)

**Phase 7 (Polish)**:
- T043-T045 can run in parallel (different sections)
- T046-T050 sequential (final validation)

### User Story Completion Order

1. **Phase 1 & 2**: Complete first (foundation)
2. **MVP (US1 + US4)**: Can proceed together after Phase 2
   - US1: Developer onboarding path
   - US4: Feature discovery path
3. **US2**: After US1 (builds on configuration knowledge)
4. **US3**: After US2 (most technical, references other sections)
5. **Phase 7**: After all user stories (final polish)

---

## Suggested MVP Scope

**Minimum Viable Documentation** (delivers immediate value):

Include: Phase 1, Phase 2, Phase 3 (US1), Phase 4 (US4)

**Delivers**:
- ✅ Navigable structure (TOC)
- ✅ Installation instructions
- ✅ Configuration guide
- ✅ All 13 features documented
- ✅ Basic usage examples (NL2SQL, CLI)

**Deferred to post-MVP**:
- API endpoint details (US3)
- Development setup (US3)
- Architecture documentation (US3)
- Advanced configuration (US2)

**Estimated Effort**: 
- MVP: 3-4 hours
- Full completion: 4-6 hours

---

## Implementation Strategy

### Incremental Delivery

1. **Sprint 1: Foundation + MVP** (3-4 hours)
   - Phase 1: Setup (30 min)
   - Phase 2: Foundational (30 min)
   - Phase 3: US1 Developer Onboarding (1-1.5 hours)
   - Phase 4: US4 Feature Documentation (1-1.5 hours)
   - **Deliverable**: Basic README with installation, config, features

2. **Sprint 2: Enhanced Documentation** (1-2 hours)
   - Phase 5: US2 Feature Discovery (30-45 min)
   - Phase 6: US3 Technical Reference (45-60 min)
   - **Deliverable**: Complete README with API, dev, architecture docs

3. **Sprint 3: Polish** (30-45 min)
   - Phase 7: Final validation and polish
   - **Deliverable**: Production-ready README

### Parallel Work Distribution

If multiple contributors:
- **Contributor 1**: US1 tasks (Configuration, NL2SQL, CLI)
- **Contributor 2**: US4 tasks (Features section all groups)
- **Contributor 3**: US2 tasks (API health, monitoring)
- **Contributor 4**: US3 tasks (API details, Development, Architecture)
- **Final reviewer**: Phase 7 polish tasks

---

## Quality Gates

### Per-Phase Validation

- **Phase 1**: TOC links work in GitHub preview
- **Phase 2**: Installation commands tested
- **Phase 3**: Quickstart validations 1, 3, 5 pass
- **Phase 4**: Quickstart validations 6, 7 pass
- **Phase 5**: Quickstart validation 4 (health) passes
- **Phase 6**: Quickstart validations 4 (all APIs), 8, 10 pass
- **Phase 7**: All quickstart validations pass (100%)

### Success Criteria (from spec.md)

- [ ] SC-001: New developers can install and configure within 15 minutes
- [ ] SC-002: 100% of features from specs 001-013 documented
- [ ] SC-003: All settings match code (verified via quickstart)
- [ ] SC-004: Usage example for each major capability
- [ ] SC-005: All 4 external docs linked with descriptions
- [ ] SC-006: Technical reviewer validates in <30 minutes
- [ ] SC-007: Logical organization with TOC, findable in <2 min
- [ ] SC-008: All endpoints, settings, CLI commands 100% accurate

---

## Total Task Count

- **Phase 1 (Setup)**: 3 tasks
- **Phase 2 (Foundational)**: 3 tasks
- **Phase 3 (US1 - P1)**: 10 tasks
- **Phase 4 (US4 - P1)**: 9 tasks
- **Phase 5 (US2 - P2)**: 5 tasks
- **Phase 6 (US3 - P3)**: 12 tasks
- **Phase 7 (Polish)**: 8 tasks

**Total**: 50 tasks

**Parallel opportunities**: 29 tasks marked [P] (58% parallelizable)

**Independent test criteria**: Each user story phase includes validation tasks that verify the story delivers its promised value independently
