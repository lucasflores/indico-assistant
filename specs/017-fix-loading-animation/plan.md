# Implementation Plan: Loading Animation Indicator

**Branch**: `017-fix-loading-animation` | **Date**: January 28, 2026 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/017-fix-loading-animation/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

The Chainlit chat widget currently lacks visual loading feedback when processing user messages, causing confusion about whether the system is responding. This plan addresses implementing a visible loading/thinking animation that appears immediately upon message submission and persists until the response is delivered. The technical approach involves leveraging Chainlit's built-in `cl.Message` API with the `content=""` pattern to create a temporary loading state that gets replaced with the actual response.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: Chainlit 2.9.5, httpx >=0.27, pyjwt >=2.8  
**Storage**: N/A (UI-only feature, no data persistence)  
**Testing**: pytest (unit tests for loading state logic), manual QA (visual validation)  
**Target Platform**: Web browser (Chrome, Firefox, Safari) via Chainlit widget interface  
**Project Type**: Web application (frontend behavior in Chainlit app)  
**Performance Goals**: Loading animation must appear within 100ms of message send, maintain 60fps during animation  
**Constraints**: Must work in both light/dark themes, must respect prefers-reduced-motion accessibility setting, must not block UI interactions  
**Scale/Scope**: Single Chainlit app file modification (app_chnlit.py), potential CSS additions to widget.css

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Official Indico Plugin Architecture
- ✅ **COMPLIANT**: This is a UI enhancement to the Chainlit widget. No changes to plugin architecture, blueprints, or Indico integration required.

### Principle II: API-First Design with Optional UI
- ✅ **COMPLIANT**: Loading animation is a pure UI enhancement that doesn't add new functionality. The underlying `/api/assistant/chat` API remains unchanged.

### Principle III: LLM Provider Abstraction
- ✅ **COMPLIANT**: No LLM interaction changes. Animation occurs before/during API call, independent of LLM provider.

### Principle IV: Graceful Degradation
- ✅ **COMPLIANT**: If animation fails to display (CSS not loaded, JS error), the chat still functions normally. Animation is enhancement, not requirement for core functionality.

### Principle V: Configuration Hierarchy
- ✅ **COMPLIANT**: No configuration needed. Animation behavior is purely client-side visual feedback.

### Principle VI: Test-First Development
- ✅ **COMPLIANT**: Unit tests will be written for loading state management logic. Visual behavior will be validated through manual QA checklist.

**GATE STATUS**: ✅ **PASSED** - No constitutional violations. Feature is a pure UI enhancement with no impact on architecture, APIs, or configuration.

---

### Post-Phase 1 Re-evaluation

After completing research, data model, and contracts:

**Principle I (Plugin Architecture)**: ✅ Still compliant - only `app_chnlit.py` modified, no plugin changes  
**Principle II (API-First)**: ✅ Still compliant - no API contract changes identified  
**Principle III (LLM Abstraction)**: ✅ Still compliant - uses existing Chainlit message APIs  
**Principle IV (Graceful Degradation)**: ✅ Still compliant - error handling ensures no orphaned loading states  
**Principle V (Configuration)**: ✅ Still compliant - zero configuration required  
**Principle VI (Test-First)**: ✅ Still compliant - test strategy defined (unit + manual QA)

**FINAL GATE STATUS**: ✅ **PASSED** - Constitution compliance maintained through design phase

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
chainlit_app/
├── app_chnlit.py           # Main Chainlit application - contains @cl.on_message handler
│                           # MODIFICATION: Add loading state management
├── public/
│   └── widget.css          # Widget styling
│                           # POTENTIAL MODIFICATION: Add loading animation CSS if needed
└── requirements.txt        # Dependencies (Chainlit 2.9.5)

tests/
├── unit/
│   └── test_loading_animation.py  # NEW: Unit tests for loading state logic
└── e2e/
    └── test_widget_loading.py     # NEW: End-to-end visual validation tests

docs/
└── LOADING_ANIMATION.md    # NEW: Documentation for loading animation implementation
```

**Structure Decision**: This feature modifies the existing Chainlit app structure. Primary changes occur in `app_chnlit.py` within the `@cl.on_message` handler. CSS modifications to `widget.css` may be needed if Chainlit's default loading styles require customization for the Indico theme (light/dark mode support).

## Complexity Tracking

> **No violations - this section intentionally left empty**

No constitutional violations exist for this feature. All principles are satisfied.

