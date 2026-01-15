# Implementation Plan: Chat REST API

**Branch**: `004-chat-api` | **Date**: 2026-01-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/004-chat-api/spec.md`

## Phase Status

| Phase | Status | Output |
|-------|--------|--------|
| Phase 0: Research | ✅ Complete | [research.md](research.md) |
| Phase 1: Design | ✅ Complete | [data-model.md](data-model.md), [contracts/openapi.yaml](contracts/openapi.yaml), [quickstart.md](quickstart.md) |
| Phase 2: Tasks | ✅ Complete | [tasks.md](tasks.md) |

## Summary

Implement REST API endpoints for conversational chat with session persistence and feedback collection. The chat endpoint processes natural language questions through the existing NL2SQL pipeline (Feature 003), maintains conversation context within sessions, and allows users to provide feedback on responses. All endpoints require Indico authentication with per-user rate limiting.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: Flask (via Indico), SQLAlchemy, Pydantic, Feature 003 NL2SQL Pipeline  
**Storage**: PostgreSQL with `plugin_assistant` schema (ChatSession, ChatMessage, FeedbackEntry tables)  
**Testing**: pytest with indico fixtures  
**Target Platform**: Indico web server  
**Project Type**: Indico plugin (single project)  
**Performance Goals**: 5s p95 chat response, 500ms session listing, 200ms feedback  
**Constraints**: 60 req/min chat rate limit, 200 req/min read operations  
**Scale/Scope**: 100+ concurrent chat sessions

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Compliance Notes |
|-----------|--------|------------------|
| I. Official Indico Plugin Architecture | ✅ Pass | Routes via `IndicoPluginBlueprint`, models use Indico's `db`, tables in `plugin_assistant` schema |
| II. API-First Design | ✅ Pass | All functionality exposed via REST API at `/api/assistant/*`, requires Indico auth |
| III. LLM Provider Abstraction | ✅ Pass | Uses existing NL2SQL pipeline which uses Instructor-based LLM service |
| IV. Graceful Degradation | ✅ Pass | Error responses with user-friendly messages, configurable timeouts |
| V. Configuration Hierarchy | ✅ Pass | Rate limits configurable via plugin settings |
| VI. Test-First Development | ✅ Pass | Unit tests for services (≥80%), integration tests for endpoints (≥60%) |

**Constitution Check Result**: ✅ All gates passed

## Project Structure

### Documentation (this feature)

```text
specs/004-chat-api/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI spec)
└── tasks.md             # Phase 2 output (from /speckit.tasks)
```

### Source Code (repository root)

```text
indico_assistant/
├── models/
│   ├── __init__.py           # Export all models
│   ├── audit.py              # Existing QueryAuditLog
│   ├── session.py            # NEW: ChatSession model
│   ├── message.py            # NEW: ChatMessage model
│   └── feedback.py           # NEW: FeedbackEntry model
├── services/
│   ├── chat/                 # NEW: Chat service layer
│   │   ├── __init__.py
│   │   ├── service.py        # ChatService class
│   │   ├── session_manager.py # Session CRUD operations
│   │   ├── context_builder.py # Build conversation context for LLM
│   │   └── rate_limiter.py   # Per-user rate limiting
│   ├── feedback/             # NEW: Feedback service layer
│   │   ├── __init__.py
│   │   └── service.py        # FeedbackService class
│   ├── nl2sql/               # Existing NL2SQL pipeline
│   └── llm/                  # Existing LLM service
├── controllers/              # NEW: Reorganize controllers
│   ├── __init__.py
│   ├── health.py             # Move from controllers.py
│   ├── chat.py               # NEW: RHChat endpoint
│   ├── sessions.py           # NEW: RHSessionList, RHSessionDetail, RHSessionDelete
│   └── feedback.py           # NEW: RHFeedback endpoint
├── migrations/versions/
│   └── 002_create_chat_tables.py  # NEW: ChatSession, ChatMessage, FeedbackEntry
└── blueprint.py              # Update with new routes

tests/
├── unit/
│   └── services/
│       ├── chat/             # NEW: Chat service tests
│       │   ├── test_service.py
│       │   ├── test_session_manager.py
│       │   ├── test_context_builder.py
│       │   └── test_rate_limiter.py
│       └── feedback/         # NEW: Feedback service tests
│           └── test_service.py
├── integration/
│   └── chat/                 # NEW: Endpoint integration tests
│       ├── test_chat_endpoint.py
│       ├── test_sessions_endpoint.py
│       └── test_feedback_endpoint.py
└── contract/
    └── chat/                 # NEW: API contract tests
        └── test_api_contracts.py
```

**Structure Decision**: Follows existing Indico plugin pattern with models in `models/`, services in `services/`, and request handlers in `controllers/`. Controllers reorganized from single file to package for maintainability.

## Complexity Tracking

No constitution violations - no entries needed.
