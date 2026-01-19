# Implementation Plan: Chat Pipeline Integration

**Branch**: `010-chat-pipeline-integration` | **Date**: 2026-01-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/010-chat-pipeline-integration/spec.md`

## Summary

Fix the chat pipeline to deliver actual LLM responses through the complete backend. The current implementation has two blocking issues:
1. The chat service imports non-existent `NL2SQLService` (should use `NL2SQLPipeline` via factory)
2. The Chainlit app echoes messages instead of calling the Indico REST API

**Technical approach**: Wire Chainlit to call `/api/assistant/chat` over HTTP with JWT forwarding, fix the chat service to use the correct NL2SQL factory function, and ensure end-to-end message flow through the pipeline.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: Flask (Indico), Chainlit 2.9.5, Instructor, httpx (for async HTTP client)  
**Storage**: PostgreSQL (Indico's db via SQLAlchemy)  
**Testing**: pytest with indico fixtures  
**Target Platform**: Linux server (Indico deployment)  
**Project Type**: Indico plugin with external Chainlit companion service  
**Performance Goals**: <10s end-to-end latency for typical queries  
**Constraints**: Must not break existing Indico functionality; graceful degradation required  
**Scale/Scope**: Single user sessions, existing database schema

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Official Indico Plugin Architecture | ✅ PASS | Uses IndicoPluginBlueprint, existing routes, no new models |
| II. API-First Design | ✅ PASS | All functionality via `/api/assistant/chat` REST endpoint |
| III. LLM Provider Abstraction | ✅ PASS | Uses existing LLMService with Instructor; no changes to provider layer |
| IV. Graceful Degradation | ✅ PASS | Error handling returns user-friendly messages, does not crash Indico |
| V. Configuration Hierarchy | ✅ PASS | Uses existing plugin settings, adds `INDICO_API_URL` env var for Chainlit |
| VI. Test-First Development | ✅ PASS | Integration tests for API calls, unit tests for service fixes |

**Gate Status**: ✅ PASSED - No violations

## Project Structure

### Documentation (this feature)

```text
specs/010-chat-pipeline-integration/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (minimal - mostly integration)
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API contract verification)
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
indico_assistant/
├── services/
│   ├── chat/
│   │   └── service.py       # FIX: Use NL2SQLPipeline instead of NL2SQLService
│   └── nl2sql/
│       └── __init__.py      # Already exports NL2SQLPipeline correctly
└── ...

chainlit_app/
├── app_chnlit.py            # FIX: Call Indico API instead of echo
├── requirements.txt         # ADD: httpx for async HTTP client
└── .env.example             # ADD: Document required environment variables

tests/
├── integration/
│   └── test_chat_pipeline.py   # NEW: End-to-end pipeline tests
└── unit/
    └── test_chat_service.py    # NEW: Unit tests for fixed service
```

**Structure Decision**: Existing plugin structure with fixes to two key files. No new modules required - this is primarily an integration/wiring fix.

## Complexity Tracking

> No constitution violations - table not required.

---

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1 design completion.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Official Indico Plugin Architecture | ✅ PASS | No new routes/models; fixes existing integration |
| II. API-First Design | ✅ PASS | Chainlit calls existing REST API; no UI-only features |
| III. LLM Provider Abstraction | ✅ PASS | Uses existing factory pattern; no provider changes |
| IV. Graceful Degradation | ✅ PASS | Error handling provides user-friendly messages |
| V. Configuration Hierarchy | ✅ PASS | Env vars for Chainlit; plugin settings unchanged |
| VI. Test-First Development | ✅ PASS | Tests defined for service fixes and integration |

**Post-Design Gate Status**: ✅ PASSED

---

## Phase 1 Artifacts Generated

- [x] `research.md` - Root cause analysis and decisions
- [x] `data-model.md` - Minimal (no new models, integration fix)
- [x] `contracts/chat-api.md` - API contract documentation
- [x] `quickstart.md` - Developer setup guide
- [x] Agent context updated via `update-agent-context.sh copilot`

## Next Steps

Run `/speckit.tasks` to generate the implementation task breakdown.
