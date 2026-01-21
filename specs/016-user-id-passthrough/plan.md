# Implementation Plan: User ID Passthrough Fix

**Branch**: `016-user-id-passthrough` | **Date**: 2026-01-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/016-user-id-passthrough/spec.md`

## Summary

Fix the user_id passthrough issue where personalized queries ("what meetings do I have?") fail because user_id is null/0. The fix involves: (1) debugging and fixing the existing user_id extraction from JWT/session, (2) adding a personal query detection mechanism, (3) implementing on-demand identity prompting when user_id unavailable, and (4) supporting user lookup by name/email with session persistence.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: Flask, SQLAlchemy, Indico framework, Instructor (LLM)  
**Storage**: PostgreSQL (plugin_assistant schema)  
**Testing**: pytest with indico fixtures  
**Target Platform**: Linux server (Indico deployment)  
**Project Type**: Indico plugin (web)  
**Performance Goals**: Identity prompting response < 2 seconds  
**Constraints**: Read-only trust for user-provided identity; sensitive ops require auth  
**Scale/Scope**: Existing chat service enhancement

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Official Indico Plugin Architecture | ✅ PASS | Uses existing plugin structure, Indico's User model, plugin_assistant schema |
| II. API-First Design | ✅ PASS | Enhancement to existing /api/assistant/chat endpoint |
| III. LLM Provider Abstraction | ✅ PASS | Uses existing Instructor-based LLM service for personal query detection |
| IV. Graceful Degradation | ✅ PASS | Falls back to prompting user, never crashes on missing identity |
| V. Configuration Hierarchy | ✅ PASS | No new configuration required |
| VI. Test-First Development | ✅ PASS | Tests planned before implementation |

## Project Structure

### Documentation (this feature)

```text
specs/016-user-id-passthrough/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (affected files)

```text
indico_assistant/
├── controllers/
│   ├── base.py              # MODIFY: Fix JWT user extraction
│   └── chat.py              # MODIFY: Handle identity prompting flow
├── services/
│   ├── chat/
│   │   ├── service.py       # MODIFY: Add identity resolution logic
│   │   ├── identity.py      # NEW: Identity resolution service
│   │   └── session_manager.py # MODIFY: Store resolved identity
│   └── nl2sql/
│       ├── pipeline.py      # MODIFY: Remove user_id=0 fallback
│       └── classifier.py    # MODIFY: Add personal query detection
├── models/
│   └── session.py           # MODIFY: Add resolved_user_id column

tests/
├── unit/
│   └── services/
│       └── chat/
│           └── test_identity.py  # NEW: Identity service tests
└── integration/
    └── test_user_id_passthrough.py  # NEW: E2E identity flow tests
```

## Complexity Tracking

> No constitution violations - standard plugin enhancement following existing patterns.
