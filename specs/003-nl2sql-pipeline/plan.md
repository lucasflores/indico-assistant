# Implementation Plan: NL2SQL Pipeline

**Branch**: `003-nl2sql-pipeline` | **Date**: 2026-01-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-nl2sql-pipeline/spec.md`

## Summary

Implement a natural language to SQL translation pipeline that safely converts user questions into database queries. The pipeline orchestrates: question classification → SQL generation → validation → execution → error correction → result formatting. Uses the LLM service layer (002) for all LLM interactions with structured Pydantic outputs.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Instructor (LLM), SQLAlchemy (ORM), PostgreSQL (database)
**Storage**: PostgreSQL (Indico's `db.session`), pgvector for future RAG
**Testing**: pytest with `indico.testing.fixtures`, MockPlugin pattern
**Target Platform**: Linux server (Indico deployment)
**Project Type**: single (Indico plugin)
**Performance Goals**: Simple queries <10s, complex queries <30s, 80% first-attempt success
**Constraints**: SELECT-only queries, 1000 row limit, 30s timeout, relevant-tables-only schema context
**Scale/Scope**: Single-tenant per Indico instance, cross-event queries within user permissions

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Official Indico Plugin Architecture | ✅ PASS | Uses `db.session` from Indico, integrates with plugin settings, no new entry points |
| II. API-First Design | ✅ PASS | FR-038: Internal Python API first; REST endpoint explicitly out of scope |
| III. LLM Provider Abstraction | ✅ PASS | Uses LLMService from 002-llm-service-layer with Instructor |
| IV. Graceful Degradation | ✅ PASS | LLMResponse wrapper handles all errors; returns structured errors, never raises |
| V. Configuration Hierarchy | ✅ PASS | Uses plugin.settings; FR-030 supports per-event table allowlists |
| VI. Test-First Development | ✅ PASS | Test patterns established in 002; contract + unit + integration structure |

**Security Requirements Check**:
- SQL injection: FR-012-018 mandate parameterized queries and validation
- Generated SQL validation: FR-012-15 ensure SELECT-only, allowed tables
- Input sanitization: Classification extracts entities before SQL generation
- Rate limiting: Inherited from plugin infrastructure
- Audit logging: FR-032-35 mandate comprehensive logging

### Post-Design Re-evaluation (Phase 1 Complete)

| Principle | Status | Design Evidence |
|-----------|--------|-----------------|
| I. Official Indico Plugin Architecture | ✅ PASS | QueryAuditLog in `plugin_assistant` schema; uses `indico.core.db.db` |
| II. API-First Design | ✅ PASS | `NL2SQLPipeline.process()` as primary interface; documented in contracts/internal-api.md |
| III. LLM Provider Abstraction | ✅ PASS | All components use LLMService.generate(); reuses models from 002 |
| IV. Graceful Degradation | ✅ PASS | PipelineResult always returns; PipelineError for all failure modes |
| V. Configuration Hierarchy | ✅ PASS | Settings documented in quickstart.md; per-event table allowlist via FR-030 |
| VI. Test-First Development | ✅ PASS | Test structure defined in Project Structure; fixtures documented in research.md |

**All constitution gates pass. Ready for Phase 2 task breakdown.**

## Project Structure

### Documentation (this feature)

```text
specs/003-nl2sql-pipeline/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (internal API contracts)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
indico_assistant/
├── models/
│   └── audit.py                    # QueryAuditLog SQLAlchemy model
├── services/
│   ├── __init__.py                 # Re-exports NL2SQLPipeline
│   ├── llm/                        # Existing from 002
│   └── nl2sql/
│       ├── __init__.py             # Re-exports pipeline + components
│       ├── pipeline.py             # NL2SQLPipeline orchestrator
│       ├── classifier.py           # QueryClassifier component
│       ├── generator.py            # SQLGenerator component
│       ├── validator.py            # SQLValidator component
│       ├── executor.py             # QueryExecutor component
│       ├── corrector.py            # ErrorCorrector component
│       ├── formatter.py            # ResultFormatter component
│       ├── cache.py                # QueryCache (TTL-based)
│       └── schema.py               # SchemaContext (relevant tables)
└── migrations/
    └── versions/
        └── xxx_add_query_audit_log.py

tests/
├── contract/
│   └── nl2sql/
│       └── test_pipeline_contracts.py  # Input/output contracts
├── integration/
│   └── nl2sql/
│       └── test_pipeline_integration.py
└── unit/
    └── services/
        └── nl2sql/
            ├── test_pipeline.py
            ├── test_classifier.py
            ├── test_generator.py
            ├── test_validator.py
            ├── test_executor.py
            ├── test_corrector.py
            └── test_formatter.py
```

**Structure Decision**: Single project layout following existing 002-llm-service-layer pattern. New `nl2sql/` service package parallel to `llm/`.

## Complexity Tracking

> No constitution violations. Design follows established patterns from 002-llm-service-layer.
