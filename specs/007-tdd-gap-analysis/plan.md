# Implementation Plan: TDD Gap Analysis and Test Completion

**Branch**: `007-tdd-gap-analysis` | **Date**: 2026-01-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/007-tdd-gap-analysis/spec.md`

## Summary

Systematic identification and remediation of test coverage gaps across the indico-assistant plugin. The feature produces documentation (TDD Scope Document, Coverage Inventory, Gap Report) and writes missing tests for critical/high priority gaps, prioritizing LLM integration services > data persistence > pure business logic.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: pytest, pytest-cov, indico fixtures  
**Storage**: N/A (documentation + test files)  
**Testing**: pytest with `pytest_plugins = ('indico.testing.fixtures',)`  
**Target Platform**: Development environment (macOS/Linux)
**Project Type**: Single Indico plugin  
**Performance Goals**: Test suite under 5 min (unit), 10 min (full)  
**Constraints**: Tests must be deterministic, no external services required  
**Scale/Scope**: ~49 service modules, 7 controllers, 7 schema files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Official Indico Plugin Architecture | ✅ PASS | Feature produces documentation + tests, no plugin architecture changes |
| II. API-First Design | ✅ PASS | No new API endpoints; tests verify existing API behavior |
| III. LLM Provider Abstraction | ✅ PASS | Tests will use mocks; no changes to LLM abstraction |
| IV. Graceful Degradation | ✅ PASS | Tests verify degradation behavior, no changes to it |
| V. Configuration Hierarchy | ✅ PASS | No configuration changes |
| VI. Test-First Development | ✅ PASS | This feature IS about improving test coverage |

**Gate Status**: ✅ ALL GATES PASS - Proceed to Phase 0

## Project Structure

### Documentation (this feature)

```text
specs/007-tdd-gap-analysis/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: Coverage analysis findings
├── tdd-scope.md         # Phase 1: TDD requirements by component type
├── gap-report.md        # Phase 1: Prioritized gap list
├── test-templates.md    # Phase 1: Reusable test patterns
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
indico_assistant/
├── controllers/         # 7 files: admin, base, chat, feedback, health, search, sessions
├── models/              # 6 files: audit, document, feedback, message, observability, session
├── schemas/             # 7 files: admin, chat, errors, feedback, search, session
└── services/
    ├── chat/            # 4 files: context_builder, rate_limiter, service, session_manager
    ├── document/        # 3 files: chunker, extractor, processor
    ├── embedding/       # 2 files: cache, service
    ├── feedback/        # 1 file: service
    ├── llm/
    │   ├── models/      # 4 files: base, classification, sql, summary
    │   ├── errors.py
    │   ├── factory.py
    │   └── service.py
    ├── nl2sql/          # 13 files: audit, cache, classifier, corrector, executor, factory, formatter, generator, models, permissions, pipeline, schema, validator
    ├── observability/   # 5 files: client, metrics, privacy, sync, tracer
    └── vector_search/   # 4 files: rag, search, store, validation

tests/
├── conftest.py          # Shared fixtures
├── contract/
│   ├── chat/            # 1 file: test_api_contracts
│   ├── llm/             # 3 files: test_error_models, test_models, test_response_models
│   ├── nl2sql/          # 2 files: test_error_contracts, test_pipeline_contracts
│   └── test_api_health.py
├── integration/
│   ├── chat/            # 3 files: test_chat_endpoint, test_feedback_endpoint, test_sessions_endpoint
│   ├── nl2sql/          # 3 files: test_audit, test_error_recovery, test_multi_entity
│   ├── test_health.py
│   └── test_settings.py
└── unit/
    ├── controllers/     # 1 file: test_sessions
    ├── services/
    │   ├── chat/        # 4 files: test_context_builder, test_rate_limiter, test_service, test_session_manager
    │   ├── feedback/    # 1 file: test_service
    │   ├── llm/         # 3 files: test_errors, test_factory, test_service
    │   └── nl2sql/      # 10 files: test_audit, test_cache, test_classifier, test_corrector, test_executor, test_formatter, test_generator, test_pipeline, test_schema, test_validator
    ├── test_cli.py
    ├── test_forms.py
    ├── test_plugin.py
    └── test_version.py
```

**Structure Decision**: Existing test structure follows `tests/{contract,integration,unit}/` pattern. New tests will follow the same organization.

## Complexity Tracking

> No constitution violations - this feature is fully aligned with Principle VI (Test-First Development)

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
