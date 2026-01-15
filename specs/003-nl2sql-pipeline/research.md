# Research: NL2SQL Pipeline

**Feature**: 003-nl2sql-pipeline | **Date**: 2026-01-14

## Research Questions Resolved

### 1. LLM Service Integration Pattern

**Decision**: Use `LLMService.generate()` method with existing Pydantic models

**Rationale**: 
- 002-llm-service-layer provides `LLMService` with `generate(prompt, response_model, ...)` method
- Pre-built models: `QueryClassification`, `SQLGeneration`, `SQLCorrection`, `ResponseSummary`
- Returns `LLMResponse[T]` wrapper with `success`, `result`, `error`, `latency_ms`, `retries`
- Error handling via `LLMError` with typed `ErrorType` enum

**Alternatives Considered**:
- Direct Instructor client: Rejected because service abstraction handles retries, logging, provider config
- Custom LLM wrapper: Rejected because existing service already implements constitution requirements

**Import Pattern**:
```python
from indico_assistant.services.llm import (
    LLMService, create_llm_service,
    QueryClassification, SQLGeneration, SQLCorrection, ResponseSummary,
    LLMResponse, LLMError, ErrorType,
)
```

---

### 2. Database Access Pattern

**Decision**: Use `db.session` from Indico with read-only transaction context

**Rationale**:
- Indico plugins must use `indico.core.db.db` for session management
- Read-only transactions enforce SELECT-only at database level
- Existing pattern in `indico_assistant/src/database/` uses `transaction_context(read_only=True)`

**Alternatives Considered**:
- Raw psycopg2: Rejected because bypasses Indico's connection management
- New SQLAlchemy engine: Rejected because violates plugin architecture (Constitution I)

**Implementation Pattern**:
```python
from indico.core.db import db

def execute_validated_query(sql: str, params: dict = None) -> list[dict]:
    with db.session.connection() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        result = conn.execute(text(sql), params or {})
        return [dict(row._mapping) for row in result]
```

---

### 3. Schema Context Strategy

**Decision**: Load relevant tables only based on query classification intent

**Rationale**:
- Clarification answer: "Include schema for relevant tables only (detected from classification)"
- Reduces prompt size, improves generation accuracy
- `all_tables.yaml` (280 lines) provides full schema documentation

**Implementation Approach**:
1. Map intent → relevant tables:
   - `event_query` → `events.events`, `categories.categories`
   - `registration_query` → `events.events`, `events.registrations`
   - `contribution_query` → `events.events`, `events.contributions`, `events.persons`, `events.contribution_person_links`
   - `attachment_query` → `attachments.files`, `events.events`
2. Load only those table definitions from YAML for prompt context

**Alternatives Considered**:
- Full schema in every prompt: Rejected because exceeds context limits, reduces accuracy
- Pre-summarized schema: Rejected because loses column detail needed for accurate SQL

---

### 4. SQL Complexity Boundaries

**Decision**: Single-level queries with JOINs and basic aggregations only

**Rationale**:
- Clarification answer: "Single-level queries with JOINs and basic aggregations (no CTEs, subqueries, or window functions)"
- Simpler SQL is more reliable for LLM generation
- Covers 90%+ of real-world Indico questions

**Validation Rules**:
- ✅ Allowed: SELECT, FROM, JOIN, WHERE, GROUP BY, HAVING, ORDER BY, LIMIT
- ✅ Allowed aggregations: COUNT, SUM, AVG, MIN, MAX
- ❌ Rejected: WITH (CTE), subqueries in SELECT/WHERE, OVER (window functions)

**Alternatives Considered**:
- Full SQL support: Rejected because error rate increases significantly with complexity
- Decompose to multiple queries: Future enhancement, not in scope for 003

---

### 5. Cross-Event Query Security

**Decision**: Allow cross-event queries, filter by user permissions

**Rationale**:
- Clarification answer: "Allow queries across all events user has access to (cross-event by default)"
- User's accessible events determined by Indico's permission system
- Pipeline must filter results post-query OR inject permission filter into SQL

**Implementation Approach**:
1. Get user's accessible event IDs from Indico permission system
2. Inject `WHERE event_id IN (...)` filter into generated SQL
3. Validator ensures no query bypasses this filter

**Alternatives Considered**:
- Require explicit event context: Rejected by clarification
- Trust LLM to add filter: Rejected because security-critical; must be enforced in validator

---

### 6. Time Reference Defaults

**Decision**: Use sensible defaults for ambiguous time terms

**Rationale**:
- Clarification answer: "Use sensible defaults (recently = last 7 days, soon = next 7 days, etc.)"
- Better UX than rejecting ambiguous queries

**Default Mappings**:
| Term | Interpretation |
|------|----------------|
| "recently" | last 7 days |
| "soon" | next 7 days |
| "a while ago" | last 30 days |
| "upcoming" | next 30 days |
| "this week" | current ISO week |
| "this month" | current calendar month |
| "last week" | previous ISO week |
| "last month" | previous calendar month |

**Implementation**: Handle in `QueryClassification` prompt with explicit mapping instructions.

---

### 7. Result Caching Strategy

**Decision**: Cache identical SQL queries with configurable TTL (default: 10 minutes)

**Rationale**:
- Clarification answer: "Cache identical queries with short TTL (5-15 minutes)"
- Reduces database load for repeated questions
- Short TTL ensures data freshness

**Implementation Approach**:
1. Cache key: SHA256 hash of (user_id, normalized_sql, params)
2. Storage: In-memory LRU cache (plugin restart clears cache)
3. Configurable: `cache_ttl_seconds` in plugin settings (default: 600)
4. Cache bypass: Add `force_refresh=True` parameter

**Alternatives Considered**:
- No caching: Rejected because repeat questions common
- Semantic caching: Rejected because cache invalidation complexity too high

---

### 8. Error Correction Prompting

**Decision**: Send error message + original SQL + schema context to LLM

**Rationale**:
- `SQLCorrection` model from 002 already defines: `corrected_query`, `error_analysis`, `changes_made`
- LLM needs original context to understand what was attempted

**Prompt Template**:
```
The following SQL query failed:
{original_sql}

Error message: {error_message}

Schema context:
{schema_for_tables}

Please fix the query. Common issues:
- Wrong column names
- Missing table aliases
- Type mismatches

Return only the corrected query.
```

**Retry Strategy**:
- Max 3 attempts (configurable)
- Each retry includes previous error
- Track attempts in response metadata

---

### 9. Audit Log Schema

**Decision**: New `QueryAuditLog` SQLAlchemy model in `plugin_assistant` schema

**Rationale**:
- FR-032-035 require comprehensive audit logging
- Must not pollute Indico core schema (Constitution I)
- PostgreSQL native JSON for flexible metadata storage

**Fields**:
| Column | Type | Purpose |
|--------|------|---------|
| id | Integer PK | Auto-increment |
| user_id | Integer FK | Reference to users.users |
| timestamp | DateTime | Query submission time (UTC) |
| question_text | Text | Original natural language question |
| generated_sql | Text | Generated SQL (may be null if classification failed) |
| tables_accessed | ARRAY(String) | List of tables in query |
| row_count | Integer | Number of rows returned (null if failed) |
| execution_time_ms | Integer | Query execution duration |
| status | Enum | success, validation_error, execution_error, timeout |
| error_message | Text | Error details (if failed) |
| correction_attempts | Integer | Number of LLM correction retries |
| event_ids | ARRAY(Integer) | Events involved in query |

---

### 10. Testing Strategy

**Decision**: Follow 002-llm-service-layer patterns with pipeline-specific fixtures

**Test Categories**:

1. **Contract Tests** (`tests/contract/nl2sql/`):
   - Input validation for NL2SQLPipeline
   - Output structure guarantees
   - Error response formats

2. **Unit Tests** (`tests/unit/services/nl2sql/`):
   - Each component tested in isolation
   - Mock LLMService, mock database
   - Cover all error paths

3. **Integration Tests** (`tests/integration/nl2sql/`):
   - End-to-end pipeline with real LLM (if available)
   - Database execution with test data
   - Permission filtering verification

**Key Fixtures**:
```python
@pytest.fixture
def mock_llm_service():
    """Pre-configured LLMService that returns predictable responses."""
    
@pytest.fixture
def sample_schema_context():
    """Schema context for events + registrations tables."""
    
@pytest.fixture
def sample_audit_log(db_session):
    """Creates a QueryAuditLog entry for testing."""
```

---

## Dependencies Verified

| Dependency | Status | Notes |
|------------|--------|-------|
| 002-llm-service-layer | ✅ Complete | LLMService, all models available |
| 001-plugin-foundation | ✅ Complete | Plugin settings, database access |
| all_tables.yaml | ✅ Exists | 280 lines of schema documentation |
| Indico core | ✅ Available | `db.session`, permission system |

## Open Questions (None)

All clarifications resolved. Ready for Phase 1 design.
