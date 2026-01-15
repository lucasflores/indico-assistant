# Data Model: NL2SQL Pipeline

**Feature**: 003-nl2sql-pipeline | **Date**: 2026-01-14

## Entity Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NL2SQLPipeline                                    │
│  Orchestrates: classify → generate → validate → execute → correct → format │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  QueryClassifier │    │   SQLGenerator   │    │   SQLValidator   │
│  → intent        │    │  → SQL string    │    │  → safe/unsafe   │
│  → entities      │    │  → tables_used   │    │  → rejection     │
│  → time_range    │    │  → explanation   │    │    reason        │
│  → filters       │    │                  │    │                  │
└──────────────────┘    └──────────────────┘    └──────────────────┘
          │                         │                         │
          │                         ▼                         │
          │             ┌──────────────────┐                  │
          │             │  QueryExecutor   │◄─────────────────┘
          │             │  → raw results   │
          │             │  → row_count     │
          │             │  → exec_time     │
          │             └──────────────────┘
          │                         │
          │                         ▼
          │             ┌──────────────────┐    ┌──────────────────┐
          │             │ ErrorCorrector   │───►│   QueryCache     │
          │             │  → corrected_sql │    │  → cached result │
          │             │  → error_analysis│    │  → TTL tracking  │
          │             │  → changes_made  │    └──────────────────┘
          │             └──────────────────┘
          │                         │
          ▼                         ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  SchemaContext   │    │ ResultFormatter  │    │  QueryAuditLog   │
│  → intent→tables │    │  → answer text   │    │  (persistence)   │
│  → YAML loading  │    │  → confidence    │    │  → user, time    │
│  → prompt format │    │  → metadata      │    │  → sql, status   │
└──────────────────┘    └──────────────────┘    └──────────────────┘
```

---

## Service Components (Runtime)

### NL2SQLPipeline

**Purpose**: Main orchestrator coordinating the full question-to-answer flow.

```python
class NL2SQLPipeline:
    """Orchestrates natural language to SQL translation."""
    
    def __init__(
        self,
        llm_service: LLMService,
        schema_context: SchemaContext,
        cache: QueryCache | None = None,
        max_correction_attempts: int = 3,
        query_timeout_seconds: int = 30,
        max_result_rows: int = 1000,
    ) -> None: ...
    
    def process(
        self,
        question: str,
        user_id: int,
        event_ids: list[int] | None = None,
        force_refresh: bool = False,
    ) -> PipelineResult: ...
```

**Fields**:
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| llm_service | LLMService | required | LLM provider abstraction |
| schema_context | SchemaContext | required | Schema loading helper |
| cache | QueryCache | None | Optional result cache |
| max_correction_attempts | int | 3 | Max LLM retry attempts |
| query_timeout_seconds | int | 30 | DB query timeout |
| max_result_rows | int | 1000 | Result set limit |

---

### QueryClassifier

**Purpose**: Classifies user questions and extracts structured information.

```python
class QueryClassifier:
    """Classifies natural language questions for SQL generation."""
    
    def __init__(self, llm_service: LLMService) -> None: ...
    
    def classify(self, question: str) -> LLMResponse[QueryClassification]: ...
```

**Uses**: `QueryClassification` model from 002-llm-service-layer

---

### SQLGenerator

**Purpose**: Generates SQL from classification results with schema context.

```python
class SQLGenerator:
    """Generates SQL queries from classified questions."""
    
    def __init__(
        self,
        llm_service: LLMService,
        schema_context: SchemaContext,
    ) -> None: ...
    
    def generate(
        self,
        classification: QueryClassification,
        user_accessible_event_ids: list[int],
    ) -> LLMResponse[SQLGeneration]: ...
```

**Uses**: `SQLGeneration` model from 002-llm-service-layer

---

### SQLValidator

**Purpose**: Validates SQL safety before execution.

```python
class SQLValidator:
    """Validates SQL queries for safety and compliance."""
    
    def __init__(
        self,
        allowed_tables: set[str] | None = None,
    ) -> None: ...
    
    def validate(self, sql: str) -> ValidationResult: ...
```

**Output Model**:
```python
class ValidationResult(BaseModel):
    is_valid: bool
    rejection_reason: str | None = None
    tables_referenced: list[str] = []
```

**Validation Rules**:
- Must start with SELECT (case-insensitive)
- No DDL: CREATE, DROP, ALTER, TRUNCATE
- No DML: INSERT, UPDATE, DELETE
- No advanced SQL: WITH (CTE), subqueries, OVER (window)
- All tables in allowed list

---

### QueryExecutor

**Purpose**: Executes validated SQL against database.

```python
class QueryExecutor:
    """Executes validated SQL queries against Indico database."""
    
    def __init__(
        self,
        timeout_seconds: int = 30,
        max_rows: int = 1000,
    ) -> None: ...
    
    def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> ExecutionResult: ...
```

**Output Model**:
```python
class ExecutionResult(BaseModel):
    success: bool
    rows: list[dict[str, Any]] = []
    row_count: int = 0
    execution_time_ms: int = 0
    error: str | None = None
    truncated: bool = False  # True if hit max_rows limit
```

---

### ErrorCorrector

**Purpose**: Attempts to fix failed queries via LLM.

```python
class ErrorCorrector:
    """Corrects failed SQL queries using LLM analysis."""
    
    def __init__(
        self,
        llm_service: LLMService,
        schema_context: SchemaContext,
        max_attempts: int = 3,
    ) -> None: ...
    
    def correct(
        self,
        original_sql: str,
        error_message: str,
        classification: QueryClassification,
    ) -> LLMResponse[SQLCorrection]: ...
```

**Uses**: `SQLCorrection` model from 002-llm-service-layer

---

### ResultFormatter

**Purpose**: Formats results and generates natural language summary.

```python
class ResultFormatter:
    """Formats query results with natural language summaries."""
    
    def __init__(self, llm_service: LLMService) -> None: ...
    
    def format(
        self,
        question: str,
        results: list[dict[str, Any]],
        tables_used: list[str],
    ) -> LLMResponse[ResponseSummary]: ...
```

**Uses**: `ResponseSummary` model from 002-llm-service-layer

---

### SchemaContext

**Purpose**: Loads relevant schema context for SQL generation prompts.

```python
class SchemaContext:
    """Manages database schema context for LLM prompts."""
    
    def __init__(self, schema_file_path: str) -> None: ...
    
    def get_tables_for_intent(self, intent: str) -> list[str]: ...
    
    def get_schema_prompt(self, tables: list[str]) -> str: ...
```

**Intent-to-Tables Mapping**:
| Intent | Tables |
|--------|--------|
| event_query | events.events, categories.categories |
| registration_query | events.events, events.registrations |
| contribution_query | events.events, events.contributions, events.persons, events.contribution_person_links |
| attachment_query | attachments.files, events.events |
| general_info | events.events |

---

### QueryCache

**Purpose**: Caches query results for performance.

```python
class QueryCache:
    """TTL-based cache for query results."""
    
    def __init__(
        self,
        ttl_seconds: int = 600,
        max_entries: int = 1000,
    ) -> None: ...
    
    def get(self, cache_key: str) -> CachedResult | None: ...
    
    def set(self, cache_key: str, result: PipelineResult) -> None: ...
    
    @staticmethod
    def make_key(user_id: int, sql: str, params: dict | None) -> str: ...
```

**Cache Entry**:
```python
class CachedResult(BaseModel):
    result: PipelineResult
    cached_at: datetime
    expires_at: datetime
```

---

## Response Models (Pipeline Output)

### PipelineResult

**Purpose**: Complete pipeline response returned to caller.

```python
class PipelineResult(BaseModel):
    """Complete result from NL2SQL pipeline."""
    
    success: bool
    answer: str | None = None
    confidence: float | None = None
    
    # Query details
    generated_sql: str | None = None
    tables_accessed: list[str] = []
    row_count: int = 0
    
    # Performance
    total_time_ms: int = 0
    classification_time_ms: int = 0
    generation_time_ms: int = 0
    execution_time_ms: int = 0
    
    # Error handling
    error: PipelineError | None = None
    correction_attempts: int = 0
    corrected: bool = False
    
    # Cache info
    from_cache: bool = False
```

### PipelineError

**Purpose**: Structured error information.

```python
class PipelineErrorType(str, Enum):
    CLASSIFICATION_FAILED = "classification_failed"
    OUT_OF_SCOPE = "out_of_scope"
    GENERATION_FAILED = "generation_failed"
    VALIDATION_FAILED = "validation_failed"
    EXECUTION_FAILED = "execution_failed"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    CORRECTION_EXHAUSTED = "correction_exhausted"

class PipelineError(BaseModel):
    error_type: PipelineErrorType
    message: str
    details: dict[str, Any] | None = None
    user_message: str  # Safe to show to user
```

---

## Database Model (Persistence)

### QueryAuditLog

**Purpose**: Audit trail for compliance (FR-032-035).

**Schema**: `plugin_assistant` (isolated from Indico core)

```python
from indico.core.db import db
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum as SQLEnum, ARRAY
from sqlalchemy.dialects.postgresql import JSONB

class QueryAuditLog(db.Model):
    """Audit log for NL2SQL queries."""
    
    __tablename__ = 'query_audit_log'
    __table_args__ = {'schema': 'plugin_assistant'}
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Query content
    question_text = Column(Text, nullable=False)
    classification_intent = Column(String(50), nullable=True)
    generated_sql = Column(Text, nullable=True)
    
    # Execution details
    tables_accessed = Column(ARRAY(String), default=[])
    event_ids = Column(ARRAY(Integer), default=[])
    row_count = Column(Integer, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    
    # Status
    status = Column(
        SQLEnum('success', 'validation_error', 'execution_error', 
                'timeout', 'permission_denied', 'out_of_scope',
                name='query_status'),
        nullable=False
    )
    error_message = Column(Text, nullable=True)
    correction_attempts = Column(Integer, default=0)
    
    # Metadata
    metadata = Column(JSONB, default={})
```

**Indexes**:
- `ix_query_audit_log_user_id` - Filter by user
- `ix_query_audit_log_timestamp` - Time-range queries
- `ix_query_audit_log_status` - Error analysis

---

## State Transitions

### Pipeline Flow States

```
┌─────────────┐
│  RECEIVED   │ Question received
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────────────┐
│ CLASSIFYING │────►│ CLASSIFICATION_FAILED│
└──────┬──────┘     └─────────────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────────────┐
│ GENERATING  │────►│ GENERATION_FAILED   │
└──────┬──────┘     └─────────────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────────────┐
│ VALIDATING  │────►│ VALIDATION_FAILED   │
└──────┬──────┘     └─────────────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────────────┐
│  EXECUTING  │────►│ EXECUTION_FAILED    │──┐
└──────┬──────┘     └─────────────────────┘  │
       │                                      │
       │            ┌─────────────────────┐  │
       │            │    CORRECTING       │◄─┘
       │            └──────────┬──────────┘
       │                       │ (max 3)
       │            ┌──────────▼──────────┐
       │            │ CORRECTION_EXHAUSTED│
       │            └─────────────────────┘
       │
       ▼
┌─────────────┐
│ FORMATTING  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  COMPLETE   │
└─────────────┘
```

---

## Validation Rules

### SQL Content Validation

| Rule | Check | Rejection Message |
|------|-------|-------------------|
| SELECT_ONLY | `sql.strip().upper().startswith('SELECT')` | "Only SELECT queries allowed" |
| NO_DDL | No CREATE, DROP, ALTER, TRUNCATE | "DDL statements not allowed" |
| NO_DML | No INSERT, UPDATE, DELETE | "DML statements not allowed" |
| NO_CTE | No WITH clause | "CTEs not supported" |
| NO_SUBQUERY | No nested SELECT | "Subqueries not supported" |
| NO_WINDOW | No OVER clause | "Window functions not supported" |
| ALLOWED_TABLES | All tables in allowlist | "Table {table} not allowed" |

### Permission Validation

| Rule | Check | Action |
|------|-------|--------|
| USER_EVENTS | Query filters to user's events | Inject `event_id IN (...)` |
| NO_REVEAL | Don't reveal denied events exist | Return generic "no results" |

---

## Relationships

```
NL2SQLPipeline
├── has-a LLMService (from 002)
├── has-a SchemaContext
├── has-a QueryCache (optional)
├── creates QueryClassifier
├── creates SQLGenerator  
├── creates SQLValidator
├── creates QueryExecutor
├── creates ErrorCorrector
├── creates ResultFormatter
└── logs-to QueryAuditLog

QueryClassifier
└── uses QueryClassification (from 002)

SQLGenerator
├── uses SQLGeneration (from 002)
└── uses SchemaContext

SQLValidator
└── produces ValidationResult

QueryExecutor
└── produces ExecutionResult

ErrorCorrector
├── uses SQLCorrection (from 002)
└── uses SchemaContext

ResultFormatter
└── uses ResponseSummary (from 002)
```
