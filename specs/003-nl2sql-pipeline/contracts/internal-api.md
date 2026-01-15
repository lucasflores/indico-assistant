# NL2SQL Pipeline Internal API Contract

**Feature**: 003-nl2sql-pipeline | **Date**: 2026-01-14

## Overview

This document defines the internal Python API contract for the NL2SQL Pipeline. This is **not** a REST API - it's the programmatic interface used within the Indico Assistant plugin.

## Primary Interface

### NL2SQLPipeline.process()

**Purpose**: Main entry point for processing natural language questions.

```python
def process(
    self,
    question: str,
    user_id: int,
    event_ids: list[int] | None = None,
    force_refresh: bool = False,
) -> PipelineResult
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| question | str | Yes | Natural language question from user |
| user_id | int | Yes | Indico user ID for permission checks |
| event_ids | list[int] | No | Limit query to specific events (None = all accessible) |
| force_refresh | bool | No | Bypass cache if True (default: False) |

**Returns**: `PipelineResult`

**Guarantees**:
- Never raises exceptions (errors wrapped in PipelineResult)
- Always returns within `timeout_seconds + 5s` buffer
- Respects user permissions (filters results to accessible events)
- Logs to QueryAuditLog on every call

---

## Response Contract

### PipelineResult

```python
class PipelineResult(BaseModel):
    # Status
    success: bool                           # True if answer generated
    
    # Answer (present if success=True)
    answer: str | None                      # Natural language response
    confidence: float | None                # 0.0-1.0 confidence score
    
    # Query details (present if SQL was generated)
    generated_sql: str | None               # The executed SQL
    tables_accessed: list[str]              # Tables referenced
    row_count: int                          # Rows returned (0 if failed)
    
    # Performance metrics
    total_time_ms: int                      # End-to-end duration
    classification_time_ms: int             # Classification stage
    generation_time_ms: int                 # SQL generation stage
    execution_time_ms: int                  # Database execution
    
    # Error handling
    error: PipelineError | None             # Structured error (if success=False)
    correction_attempts: int                # Number of LLM retries
    corrected: bool                         # True if correction succeeded
    
    # Cache info
    from_cache: bool                        # True if result was cached
```

### Success Response Example

```python
PipelineResult(
    success=True,
    answer="There are 42 registrations for the Physics Workshop tomorrow.",
    confidence=0.92,
    generated_sql="SELECT COUNT(*) FROM events.registrations r JOIN events.events e ON r.event_id = e.id WHERE e.title ILIKE '%physics workshop%' AND e.start_dt::date = '2026-01-15'",
    tables_accessed=["events.registrations", "events.events"],
    row_count=1,
    total_time_ms=2450,
    classification_time_ms=800,
    generation_time_ms=1200,
    execution_time_ms=50,
    error=None,
    correction_attempts=0,
    corrected=False,
    from_cache=False,
)
```

### Error Response Example

```python
PipelineResult(
    success=False,
    answer=None,
    confidence=None,
    generated_sql="SELECT * FROM events.users",  # Invalid table
    tables_accessed=[],
    row_count=0,
    total_time_ms=1200,
    classification_time_ms=800,
    generation_time_ms=400,
    execution_time_ms=0,
    error=PipelineError(
        error_type=PipelineErrorType.VALIDATION_FAILED,
        message="Table 'events.users' not in allowed list",
        details={"table": "events.users", "allowed": ["events.events", ...]},
        user_message="I can only query event-related data. Please rephrase your question.",
    ),
    correction_attempts=0,
    corrected=False,
    from_cache=False,
)
```

---

## Error Contract

### PipelineError

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
    message: str                    # Technical message (for logging)
    details: dict[str, Any] | None  # Additional context
    user_message: str               # Safe message for end user
```

### Error Type Mapping

| Error Type | Cause | User Message |
|------------|-------|--------------|
| CLASSIFICATION_FAILED | LLM failed to classify question | "I couldn't understand your question. Please try rephrasing." |
| OUT_OF_SCOPE | Question not about Indico data | "I can only answer questions about Indico event data." |
| GENERATION_FAILED | LLM failed to generate SQL | "I couldn't generate a query for that question." |
| VALIDATION_FAILED | SQL failed safety checks | "I can only query event-related data. Please rephrase." |
| EXECUTION_FAILED | Database error after corrections | "There was an error running the query. Please try a simpler question." |
| TIMEOUT | Query exceeded time limit | "The query took too long. Try asking about fewer events." |
| PERMISSION_DENIED | User lacks access to queried events | "No matching data found." (don't reveal existence) |
| CORRECTION_EXHAUSTED | Max retries reached | "I couldn't find a valid query after multiple attempts." |

---

## Factory Contract

### create_nl2sql_pipeline()

**Purpose**: Factory function to create configured pipeline instance.

```python
def create_nl2sql_pipeline(
    plugin: "AssistantPlugin",
    enable_cache: bool = True,
) -> NL2SQLPipeline
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| plugin | AssistantPlugin | Yes | Plugin instance for settings and services |
| enable_cache | bool | No | Enable result caching (default: True) |

**Configuration Sources** (from plugin.settings):

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| nl2sql_timeout_seconds | int | 30 | Query timeout |
| nl2sql_max_rows | int | 1000 | Result row limit |
| nl2sql_max_corrections | int | 3 | Max LLM retry attempts |
| nl2sql_cache_ttl_seconds | int | 600 | Cache TTL |
| nl2sql_allowed_tables | list[str] | [...] | Table allowlist |

---

## Component Contracts

### QueryClassifier.classify()

```python
def classify(self, question: str) -> LLMResponse[QueryClassification]
```

**Input**: Natural language question string
**Output**: `LLMResponse[QueryClassification]` from 002-llm-service-layer

---

### SQLGenerator.generate()

```python
def generate(
    self,
    classification: QueryClassification,
    user_accessible_event_ids: list[int],
) -> LLMResponse[SQLGeneration]
```

**Input**: Classification result + user's accessible events
**Output**: `LLMResponse[SQLGeneration]` from 002-llm-service-layer

---

### SQLValidator.validate()

```python
def validate(self, sql: str) -> ValidationResult

class ValidationResult(BaseModel):
    is_valid: bool
    rejection_reason: str | None = None
    tables_referenced: list[str] = []
```

**Input**: SQL string to validate
**Output**: Validation result with reason if invalid

---

### QueryExecutor.execute()

```python
def execute(
    self,
    sql: str,
    params: dict[str, Any] | None = None,
) -> ExecutionResult

class ExecutionResult(BaseModel):
    success: bool
    rows: list[dict[str, Any]] = []
    row_count: int = 0
    execution_time_ms: int = 0
    error: str | None = None
    truncated: bool = False
```

**Input**: Validated SQL string + optional parameters
**Output**: Execution result with rows or error

---

### ErrorCorrector.correct()

```python
def correct(
    self,
    original_sql: str,
    error_message: str,
    classification: QueryClassification,
) -> LLMResponse[SQLCorrection]
```

**Input**: Failed SQL + error + original classification
**Output**: `LLMResponse[SQLCorrection]` from 002-llm-service-layer

---

### ResultFormatter.format()

```python
def format(
    self,
    question: str,
    results: list[dict[str, Any]],
    tables_used: list[str],
) -> LLMResponse[ResponseSummary]
```

**Input**: Original question + query results + tables
**Output**: `LLMResponse[ResponseSummary]` from 002-llm-service-layer

---

## Audit Logging Contract

Every call to `NL2SQLPipeline.process()` creates a `QueryAuditLog` entry:

```python
QueryAuditLog(
    user_id=user_id,
    timestamp=datetime.utcnow(),
    question_text=question,
    classification_intent=classification.intent if classification else None,
    generated_sql=generated_sql,
    tables_accessed=tables,
    event_ids=event_ids,
    row_count=result.row_count,
    execution_time_ms=result.execution_time_ms,
    status=status,  # success, validation_error, etc.
    error_message=error.message if error else None,
    correction_attempts=correction_attempts,
)
```

**Privacy Guarantee**: Result data is NOT logged, only metadata.

---

## Usage Example

```python
from indico_assistant.services.nl2sql import create_nl2sql_pipeline

# Create pipeline from plugin
pipeline = create_nl2sql_pipeline(plugin)

# Process a question
result = pipeline.process(
    question="How many people registered for the physics conference?",
    user_id=current_user.id,
)

if result.success:
    print(f"Answer: {result.answer}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Found {result.row_count} rows in {result.total_time_ms}ms")
else:
    print(f"Error: {result.error.user_message}")
```
