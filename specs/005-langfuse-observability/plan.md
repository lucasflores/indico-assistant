# Implementation Plan: Langfuse Observability

**Branch**: `005-langfuse-observability` | **Date**: 2026-01-15 | **Spec**: [spec.md](spec.md)

## Summary

Implement LLM observability using the Langfuse Python SDK to trace all LLM interactions, instrument the NL2SQL pipeline stages with nested spans, store aggregated metrics locally in PostgreSQL for offline availability, and provide admin API endpoints for usage statistics and error debugging. The implementation uses Langfuse's context manager API for automatic span nesting, with configurable privacy levels controlling content capture.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: langfuse (Python SDK), SQLAlchemy (via Indico), Celery (background sync)  
**Storage**: PostgreSQL (plugin_assistant schema) for local metrics cache  
**Testing**: pytest with indico fixtures, mocked Langfuse client  
**Target Platform**: Indico plugin (Flask-based)  
**Project Type**: Single plugin with observability services  
**Performance Goals**: <5ms added latency for tracing, <500ms admin stats response  
**Constraints**: Must not fail user requests if Langfuse unavailable; async tracing  
**Scale/Scope**: All LLM calls traced, hourly metrics sync, 30-day stats retention

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Official Indico Plugin Architecture | ✅ PASS | Uses IndicoPluginBlueprint, RH handlers, plugin settings |
| II. API-First Design | ✅ PASS | Admin endpoints via REST API before any UI |
| III. LLM Provider Abstraction | ✅ PASS | Tracing wraps existing LLMService, doesn't change providers |
| IV. Graceful Degradation | ✅ PASS | Core requirement: FR-003, FR-019 ensure user requests never fail |
| V. Configuration Hierarchy | ✅ PASS | Plugin settings for Langfuse config, runtime privacy level changes |
| VI. Test-First Development | ✅ PASS | Unit tests for services, integration tests for endpoints |

## Project Structure

### Documentation (this feature)

```text
specs/005-langfuse-observability/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI for admin endpoints)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
indico_assistant/
├── services/
│   ├── observability/           # NEW: Observability services
│   │   ├── __init__.py
│   │   ├── client.py            # Langfuse client wrapper with graceful degradation
│   │   ├── tracer.py            # Trace/span context managers and decorators
│   │   ├── privacy.py           # PII redaction for masked privacy level
│   │   ├── metrics.py           # Local metrics aggregation service
│   │   └── sync.py              # Celery task for Langfuse → PostgreSQL sync
│   ├── llm/
│   │   └── service.py           # MODIFY: Add tracing to generate() method
│   └── nl2sql/
│       └── pipeline.py          # MODIFY: Add span tracking for pipeline stages
├── models/
│   ├── observability.py         # NEW: UsageStats, ErrorRecord, MetricsSyncLog models
│   └── __init__.py              # MODIFY: Export new models
├── controllers/
│   └── admin.py                 # NEW: Admin stats/errors endpoints
├── schemas/
│   └── admin.py                 # NEW: Pydantic schemas for admin responses
├── migrations/versions/
│   └── 003_create_observability_tables.py  # NEW: Local metrics tables
├── default_settings.py          # MODIFY: Add Langfuse settings
└── blueprint.py                 # MODIFY: Register admin routes

tests/
├── unit/services/observability/
│   ├── test_client.py
│   ├── test_tracer.py
│   ├── test_privacy.py
│   └── test_metrics.py
├── integration/observability/
│   └── test_admin_endpoints.py
└── contract/observability/
    └── test_admin_api_contracts.py
```

**Structure Decision**: Follows existing plugin structure with new `services/observability/` package. Admin endpoints go in `controllers/admin.py` following the pattern from Feature 004.

**Path Note**: All paths above are relative within the `indico_assistant/` package root. Task descriptions in `tasks.md` use full paths (e.g., `indico_assistant/services/observability/client.py`) for explicit instructions.
