# Tasks: Chat Widget Styling

**Input**: Design documents from `/specs/009-chat-widget-styling/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅

**Tests**: Not requested - this is a visual/configuration feature verified through manual testing.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)
- Exact file paths included in descriptions

## Path Conventions

- **Chainlit app**: `chainlit_app/` at repository root
- **Public assets**: `chainlit_app/public/`
- **Config**: `chainlit_app/.chainlit/`

---

## Phase 1: Setup

**Purpose**: Verify current state and prepare asset sources

- [X] T001 Document current widget appearance (screenshot for comparison) in chainlit_app/
- [X] T002 [P] Verify Chainlit server runs correctly with `chainlit run app_chnlit.py`
- [X] T003 [P] Create avatars directory at chainlit_app/public/avatars/

---

## Phase 2: Foundational (Asset Preparation)

**Purpose**: Prepare all Indico logo assets before configuration changes

**⚠️ CRITICAL**: Logo assets must exist before they can be referenced in configuration

- [X] T004 [P] Copy logo_light.png from Indico codebase to chainlit_app/public/logo_light.png
- [X] T005 [P] Create logo_dark.png from logo_dark.svg using `rsvg-convert` or ImageMagick, save to chainlit_app/public/logo_dark.png
- [X] T006 [P] Copy or create favicon.png (48x48) to chainlit_app/public/favicon.png
- [X] T007 [P] Create assistant.png avatar (64x64) from existing Indico logo or favicon, save to chainlit_app/public/avatars/assistant.png

**Checkpoint**: All logo assets exist and are valid image files

---

## Phase 3: User Story 1 - Readable Chat Widget Background (Priority: P1) 🎯 MVP

**Goal**: Fix widget transparency so all text is readable against solid backgrounds

**Independent Test**: Open widget on any page background and verify no page content bleeds through

### Implementation for User Story 1

- [X] T008 [US1] Update theme.json with full CSS variables for opaque backgrounds in chainlit_app/public/theme.json
- [X] T009 [US1] Fix widget.css opacity values from 0.9 to 1.0 in chainlit_app/public/widget.css
- [X] T010 [US1] Remove or fix broken CSS selectors in chainlit_app/public/widget.css
- [X] T011 [US1] Verify config.toml has correct custom_css path in chainlit_app/.chainlit/config.toml
- [X] T012 [US1] Test: Restart Chainlit and verify widget background is fully opaque
- [X] T013 [US1] Test: Verify text contrast meets WCAG AA (4.5:1 ratio) using browser dev tools

**Checkpoint**: User Story 1 complete - widget is readable with solid backgrounds

---

## Phase 4: User Story 2 - Indico Branded Logo Display (Priority: P2)

**Goal**: Replace default logos with Indico branding in header, avatar, and launcher

**Independent Test**: Open widget and visually confirm all 3 logo placements show Indico branding

### Implementation for User Story 2

- [X] T014 [US2] Verify logo_light.png and logo_dark.png display in widget header (Chainlit auto-detects)
- [X] T015 [US2] Verify favicon.png appears in browser tab and widget launcher button (replaces indico-icon.svg)
- [X] T016 [US2] Verify assistant.png displays as avatar next to assistant messages
- [X] T017 [US2] Update config.toml name from "Assistant" to "Indico Assistant" in chainlit_app/.chainlit/config.toml
- [X] T018 [US2] Remove obsolete indico-icon.svg CSS references from chainlit_app/public/widget.css
- [X] T019 [US2] Test: Clear browser cache and verify all logos load correctly
- [X] T020 [US2] Test: Verify fallback behavior when logo files are temporarily renamed

**Checkpoint**: User Story 2 complete - all logo placements show Indico branding

---

## Phase 5: Polish & Validation

**Purpose**: Final verification and cleanup

- [X] T021 [P] Remove obsolete indico-icon.svg from chainlit_app/public/ (replaced by favicon.png for widget launcher)
- [X] T022 Take final screenshot for before/after comparison
- [X] T023 Run quickstart.md validation checklist
- [X] T024 Update README.md if needed with logo customization notes in chainlit_app/README.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - assets must exist before config
- **User Story 1 (Phase 3)**: Depends on Foundational - theme.json needs valid paths
- **User Story 2 (Phase 4)**: Depends on Foundational - logos must exist to verify display
- **Polish (Phase 5)**: Depends on both user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start immediately after Foundational - independent of US2
- **User Story 2 (P2)**: Can start immediately after Foundational - independent of US1 (but logically follows)

### Parallel Opportunities

Within Phase 2 (Foundational):
```bash
# All asset tasks can run in parallel:
T004: Copy logo_light.png
T005: Create logo_dark.png
T006: Copy favicon.png
T007: Create assistant.png avatar
```

---

## Parallel Example: Asset Preparation

```bash
# Launch all asset tasks together (Phase 2):
Task T004: "Copy logo_light.png from Indico codebase to chainlit_app/public/logo_light.png"
Task T005: "Create logo_dark.png from logo_dark.svg and save to chainlit_app/public/logo_dark.png"
Task T006: "Copy or create favicon.png (48x48) to chainlit_app/public/favicon.png"
Task T007: "Create assistant.png avatar (32x32 or 64x64) in chainlit_app/public/avatars/assistant.png"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (verify current state)
2. Complete Phase 2: Foundational (prepare assets)
3. Complete Phase 3: User Story 1 (fix opacity)
4. **STOP and VALIDATE**: Widget is now readable
5. Can deploy/demo with just opacity fix if logos are delayed

### Incremental Delivery

1. Complete Setup + Foundational → Assets ready
2. Add User Story 1 → Test independently → **MVP: Readable widget!**
3. Add User Story 2 → Test independently → Full branding complete
4. Polish → Documentation and cleanup

---

## Notes

- [P] tasks = different files, no dependencies
- [US1]/[US2] labels map tasks to specific user stories
- Each user story is independently completable and testable
- Browser cache must be cleared to see logo changes
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
