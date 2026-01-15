# Implementation Plan: LLM Service Abstraction Layer

**Branch**: `002-llm-service-layer` | **Date**: 2026-01-14 | **Spec**: [specs/002-llm-service-layer/spec.md](spec.md)
**Input**: Feature specification from `/specs/002-llm-service-layer/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build an LLM service abstraction layer using the Instructor library that supports structured outputs with Pydantic validation. The service provides a unified interface for multiple LLM providers (Ollama, HuggingFace, OpenAI-compatible) with configuration-driven provider switching, automatic retry on validation failures, and comprehensive error handling. All LLM calls return validated Pydantic models or structured errors.

## Technical Context

**Language/Version**: Python 3.11+ (match Indico)
**Primary Dependencies**: instructor, pydantic (via Indico), ollama, openai
**Storage**: N/A (stateless service)
**Testing**: pytest with indico fixtures, ≥80% service coverage
**Target Platform**: Linux server (Indico deployment)
**Project Type**: Single project (Indico plugin)
**Performance Goals**: LLM call latency <30s (configurable timeout), health check <5s
**Constraints**: Synchronous calls only, no streaming, no caching
**Scale/Scope**: Single instance per plugin, lazy-initialized

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Official Indico Plugin Architecture | ✅ PASS | Service integrates with plugin via `plugin.py`, uses plugin settings, no new blueprints required |
| II. API-First Design with Optional UI | ✅ PASS | LLMService is internal API; health check already exposed via existing `/api/assistant/health` endpoint |
| III. LLM Provider Abstraction (NON-NEGOTIABLE) | ✅ PASS | Core purpose of this feature - Instructor with swappable providers |
| IV. Graceful Degradation (NON-NEGOTIABLE) | ✅ PASS | FR-017: All errors returned as LLMError objects, never raised; FR-032: No fallback, caller handles |
| V. Configuration Hierarchy | ✅ PASS | Uses plugin.settings for global config; event-level override deferred (future feature) |
| VI. Test-First Development | ✅ PASS | Contract tests for Pydantic models, unit tests for service methods, mocking via DI |

**Gate Result**: PASS - All constitution principles satisfied. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/002-llm-service-layer/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
indico_assistant/
├── services/
│   ├── __init__.py          # Export LLMService and models
│   └── llm/
│       ├── __init__.py      # Module exports
│       ├── service.py       # LLMService class
│       ├── factory.py       # Client factory (create_instructor_client)
│       ├── errors.py        # LLMError, error types enum
│       └── models/
│           ├── __init__.py  # Export all response models
│           ├── base.py      # LLMResponse generic wrapper
│           ├── classification.py  # QueryClassification model
│           ├── sql.py       # SQLGeneration, SQLCorrection models
│           └── summary.py   # ResponseSummary model
├── plugin.py                # Update: integrate LLMService
└── default_settings.py      # Already has LLM settings (no changes needed)

tests/
├── unit/
│   └── services/
│       └── llm/
│           ├── test_service.py   # LLMService unit tests
│           ├── test_factory.py   # Client factory tests
│           └── test_errors.py    # Error handling tests
├── contract/
│   └── llm/
│       └── test_models.py        # Pydantic model contract tests
└── integration/
    └── test_llm_health.py        # Health endpoint integration
```

**Structure Decision**: Single project structure following existing plugin layout. LLM service code goes under `indico_assistant/services/llm/` to keep service layer organized for future services (query, search, etc.).

## Complexity Tracking

> No constitution violations requiring justification. Design follows all principles.

---

## Post-Design Constitution Re-Check

*Completed after Phase 1 design artifacts.*

| Principle | Status | Post-Design Evidence |
|-----------|--------|---------------------|
| I. Official Indico Plugin Architecture | ✅ PASS | LLMService lives in `services/llm/`, integrates via plugin.py property |
| II. API-First Design with Optional UI | ✅ PASS | Internal Python API only; no new REST endpoints needed |
| III. LLM Provider Abstraction (NON-NEGOTIABLE) | ✅ PASS | Instructor from_provider() with Ollama/HF/OpenAI support |
| IV. Graceful Degradation (NON-NEGOTIABLE) | ✅ PASS | LLMResponse wrapper ensures no exceptions leak; all errors structured |
| V. Configuration Hierarchy | ✅ PASS | Settings from plugin.settings; generate() accepts overrides |
| VI. Test-First Development | ✅ PASS | Contract tests for models; DI enables mocking; test patterns documented |

**Final Gate Result**: PASS - Ready for Phase 2 task generation.
