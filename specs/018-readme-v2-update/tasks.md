# Tasks: 018-readme-v2-update

> Generated from spec.md and plan.md
> Feature: README v2.0.0 Update with Demo Video
> All tasks ✅ COMPLETE (implementation finished)

---

## Phase 1: Setup

**Purpose**: Initialize documentation update environment

- [x] T001 Create feature branch 018-readme-v2-update
- [x] T002 Review current README.md content and structure
- [x] T003 [P] Identify recent features from git log (features 015, 016, 017)
- [x] T004 [P] Research GitHub video format requirements and limits

**Checkpoint**: Branch created, context gathered

---

## Phase 2: Foundational

**Purpose**: Research and prepare assets before README updates

- [x] T005 Fetch GitHub video documentation for format/size limits
- [x] T006 [P] Fetch Stack Overflow for GIF auto-loop behavior research
- [x] T007 Document findings: GIF auto-loops, MP4/WebM don't, 10MB limit
- [x] T008 Prepare demo.gif file in docs/ directory
- [x] T009 Optimize demo GIF with ffmpeg (14MB → 3.1MB) in docs/demo_optimized.gif

**Checkpoint**: Demo asset ready, format decision documented

---

## Phase 3: User Story 1 - Demo Video Section (Priority: P1)

**Goal**: Enable potential users to see the plugin in action before installation

**Independent Test**: Demo GIF displays and loops automatically on GitHub README

### Implementation for User Story 1

- [x] T010 [US1] Add Demo link to Table of Contents in README.md
- [x] T011 [US1] Create 🎬 Demo section with GIF embed in README.md
- [x] T012 [US1] Reference docs/demo_optimized.gif with alt text
- [x] T013 [US1] Add descriptive caption below demo in README.md

**Checkpoint**: README displays auto-looping demo when viewed on GitHub

---

## Phase 4: User Story 2 - Feature Documentation (Priority: P1)

**Goal**: Understand new capabilities added since last README version

**Independent Test**: All 3 new features are documented with descriptions

### Implementation for User Story 2

- [x] T014 [US2] Update version from 0.1.0 → 2.0.0 in README.md header
- [x] T015 [US2] Update date to February 3, 2026 in README.md header
- [x] T016 [P] [US2] Add Source Citations feature to Core Capabilities in README.md
- [x] T017 [P] [US2] Add Personalized Queries feature to Core Capabilities in README.md
- [x] T018 [P] [US2] Add Streaming Responses feature to Core Capabilities in README.md
- [x] T019 [US2] Add Loading Animation to User Interface section in README.md
- [x] T020 [US2] Add Token Streaming to User Interface section in README.md
- [x] T021 [US2] Expand Supported Questions table with new capabilities in README.md

**Checkpoint**: All new features documented with clear descriptions

---

## Phase 5: User Story 3 - API Response Documentation (Priority: P2)

**Goal**: Understand how the API returns citations metadata

**Independent Test**: API response example shows citations field with source metadata

### Implementation for User Story 3

- [x] T022 [US3] Update API response example with citations array in README.md
- [x] T023 [US3] Document citation object structure (source, type, url) in README.md
- [x] T024 [US3] Ensure response example includes realistic citation data

**Checkpoint**: API documentation matches actual response format

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final quality checks and spec documentation

- [x] T025 [P] Create spec.md with user stories and requirements
- [x] T026 [P] Create plan.md with technical context
- [x] T027 [P] Create research.md documenting GIF format decisions
- [x] T028 [P] Create quickstart.md with implementation steps
- [x] T029 Create checklists/requirements.md with quality checks
- [x] T030 Run quickstart.md validation steps
- [x] T031 Generate tasks.md (this file)

**Checkpoint**: All spec documentation complete, README validated

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - start immediately
- **Foundational (Phase 2)**: Depends on Setup - asset preparation
- **User Story 1 (Phase 3)**: Depends on Foundational (needs optimized GIF)
- **User Story 2 (Phase 4)**: Depends on Setup only (can parallel with US1)
- **User Story 3 (Phase 5)**: Depends on Setup only (can parallel with US1, US2)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Requires optimized demo GIF from Phase 2
- **User Story 2 (P1)**: Independent - only edits README feature sections
- **User Story 3 (P2)**: Independent - only edits README API section

### Parallel Opportunities

- T003 and T004 can run in parallel (different research topics)
- T005 and T006 can run in parallel (different web fetches)
- T016, T017, T018 can run in parallel (different feature sections)
- T025, T026, T027, T028 can run in parallel (different spec files)

---

## Parallel Example: User Story 2

```bash
# Launch all feature documentation tasks together:
Task: "Add Source Citations feature to Core Capabilities in README.md"
Task: "Add Personalized Queries feature to Core Capabilities in README.md"
Task: "Add Streaming Responses feature to Core Capabilities in README.md"
```

---

## Implementation Strategy

### Completed Sequence

1. ✅ Phase 1: Setup - Branch created, context gathered
2. ✅ Phase 2: Foundational - Demo GIF optimized (14MB → 3.1MB)
3. ✅ Phase 3: User Story 1 - Demo section added
4. ✅ Phase 4: User Story 2 - All features documented
5. ✅ Phase 5: User Story 3 - API response updated
6. ✅ Phase 6: Polish - Spec documentation complete

### Key Decisions Made

- **GIF format**: Chosen for auto-loop (MP4/WebM don't loop)
- **Optimization**: ffmpeg palettegen for 78% size reduction
- **Version bump**: 0.1.0 → 2.0.0 (major feature additions)

---

## Summary

| Metric | Value |
|--------|-------|
| Total Tasks | 31 |
| Tasks per Story | US1: 4, US2: 8, US3: 3 |
| Parallel Opportunities | 8 |
| Status | ✅ ALL COMPLETE |

---

## Notes

- All tasks completed during implementation session
- No test tasks needed (documentation-only feature)
- Constitution check: PASS (documentation exempt from Indico patterns)
- Demo GIF successfully renders and loops on GitHub
