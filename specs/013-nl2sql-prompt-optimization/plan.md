# Implementation Plan: NL2SQL and Vector Search Prompt Optimization

**Branch**: `013-nl2sql-prompt-optimization` | **Date**: 2026-01-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-nl2sql-prompt-optimization/spec.md`

## Summary

Enhance NL2SQL and vector search prompting based on reference implementation patterns to improve query quality. Key changes: (1) Enhanced SQL generation prompt with templates, required columns, and formatting instructions; (2) Unified vector search into LLM-generated SQL using `:query_vector` parameter; (3) Classification improvements for document vs metadata query routing; (4) Schema context enrichment with JOIN hints and column recommendations.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: Instructor (LLM), SQLAlchemy, pgvector, sentence-transformers  
**Storage**: PostgreSQL 14+ with pgvector extension, `plugin_assistant` schema  
**Testing**: pytest with indico fixtures, minimum 80% coverage on services  
**Target Platform**: Indico plugin (Flask-based web application)  
**Project Type**: Single Indico plugin  
**Performance Goals**: SQL generation <2s, query execution <30s  
**Constraints**: SELECT-only queries, no CTEs/subqueries/window functions, allowlisted tables  
**Scale/Scope**: Prompts affect all NL2SQL queries; vector search integration affects document queries

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Official Indico Plugin Architecture | ✅ PASS | Changes are internal to existing plugin structure |
| II. API-First Design | ✅ PASS | No new APIs; enhances existing `/api/assistant/chat` |
| III. LLM Provider Abstraction | ✅ PASS | Uses existing `LLMService` via Instructor |
| IV. Graceful Degradation | ✅ PASS | Vector search remains optional; fallback behavior preserved |
| V. Configuration Hierarchy | ✅ PASS | Prompt templates can be configured per-event if needed |
| VI. Test-First Development | ✅ PASS | Contract tests for prompt outputs; unit tests for executor |

**Security Requirements Check**:
- ✅ SQL injection: Parameterized `:query_vector` uses SQLAlchemy text() binding
- ✅ Generated SQL validation: Existing validator unchanged (no DDL, SELECT-only)
- ✅ Audit logging: Existing logging covers enhanced queries

## Project Structure

### Documentation (this feature)

```text
specs/013-nl2sql-prompt-optimization/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (N/A - no new entities)
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── sql-generation-prompt.md
│   ├── classifier-prompt.md
│   └── vector-search-execution.md
└── tasks.md             # Phase 2 output
```

### Source Code (files to modify)

```text
indico_assistant/
├── services/
│   ├── nl2sql/
│   │   ├── generator.py         # Enhanced SQL_GENERATION_PROMPT
│   │   ├── classifier.py        # Add document_query intent
│   │   ├── executor.py          # Support :query_vector parameter
│   │   ├── schema.py            # Enhanced JOIN hints, column recommendations
│   │   └── formatter.py         # Enhanced result formatting
│   ├── vector_search/
│   │   └── rag.py               # Deprecate in favor of unified SQL
│   └── embedding/
│       └── service.py           # Expose embed_text for query vectors
├── config_modules/
│   └── available_tables.yaml    # Add extracted_documents schema
└── services/chat/
    └── service.py               # Remove RAGService call, pass embedding to executor

tests/
├── contract/
│   └── test_prompt_contracts.py # Validate LLM outputs match expected patterns
├── unit/
│   └── services/
│       └── nl2sql/
│           ├── test_generator.py
│           ├── test_classifier.py
│           └── test_executor.py
└── integration/
    └── test_vector_sql_queries.py
```

**Structure Decision**: Single plugin structure maintained; changes isolated to services layer

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1 design completion.*

| Principle | Status | Design Impact |
|-----------|--------|---------------|
| I. Official Indico Plugin Architecture | ✅ PASS | No changes to plugin structure; prompts are internal |
| II. API-First Design | ✅ PASS | API contract unchanged; internal improvements only |
| III. LLM Provider Abstraction | ✅ PASS | Prompts work with any Instructor-compatible provider |
| IV. Graceful Degradation | ✅ PASS | If embedding service unavailable, executor returns error gracefully |
| V. Configuration Hierarchy | ✅ PASS | No new settings required; uses existing config |
| VI. Test-First Development | ✅ PASS | Contract tests defined in `/contracts/` before implementation |

**Security Re-Check**:
- ✅ SQL injection: `:query_vector` uses SQLAlchemy parameterized binding
- ✅ Validation: `extracted_documents` table added to allowlist in schema.py
- ✅ Permissions: Vector search respects existing event_id filtering

## Phase Summary

| Phase | Artifacts | Status |
|-------|-----------|--------|
| Phase 0: Research | [research.md](./research.md) | ✅ Complete |
| Phase 1: Design | [contracts/](./contracts/), [quickstart.md](./quickstart.md) | ✅ Complete |
| Phase 2: Tasks | tasks.md | ⏳ Run `/speckit.tasks` |

## Next Steps

1. Run `/speckit.tasks` to generate implementation tasks
2. Implement contract tests first (test-first per constitution)
3. Update prompts following contracts
4. Update executor for vector parameter handling
5. Integration testing with real queries
