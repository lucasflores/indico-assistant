# Contract: Vector Search Query Execution

**Feature**: 013-nl2sql-prompt-optimization  
**Component**: `indico_assistant/services/nl2sql/executor.py`  
**Method**: `QueryExecutor.execute()`

## Overview

This contract defines how the query executor handles SQL containing the `:query_vector` placeholder for pgvector similarity search.

---

## Detection Logic

```python
def _contains_vector_placeholder(self, sql: str) -> bool:
    """Check if SQL contains :query_vector parameter placeholder."""
    return ":query_vector" in sql
```

---

## Execution Flow

```
┌─────────────────────┐
│   execute(sql)      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ Contains :query_vector? │
└─────────┬───────────┘
          │
    ┌─────┴─────┐
    │           │
   Yes          No
    │           │
    ▼           ▼
┌───────────┐  ┌───────────┐
│ Generate  │  │ Execute   │
│ embedding │  │ normally  │
└─────┬─────┘  └───────────┘
      │
      ▼
┌─────────────────────┐
│ Format as PG vector │
│ '[0.1,0.2,...]'     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ Execute with params │
│ {"query_vector": v} │
└─────────────────────┘
```

---

## Interface Changes

### QueryExecutor.__init__

```python
def __init__(
    self,
    db_session_factory: Callable[[], Any],
    max_rows: int = 1000,
    timeout_seconds: int = 30,
    embedding_service: Optional["EmbeddingService"] = None,  # NEW
) -> None:
```

### QueryExecutor.execute

```python
def execute(
    self,
    sql: str,
    params: dict[str, Any] | None = None,
    question: str | None = None,  # NEW: For embedding generation
) -> ExecutionResult:
```

---

## Vector Parameter Handling

```python
def _prepare_vector_params(
    self, 
    sql: str, 
    question: str,
    params: dict[str, Any]
) -> dict[str, Any]:
    """Prepare parameters with query vector if needed.
    
    Args:
        sql: The SQL query (may contain :query_vector)
        question: User's original question (for embedding)
        params: Existing parameters
        
    Returns:
        Updated params dict with query_vector if needed
    """
    if not self._contains_vector_placeholder(sql):
        return params
    
    if self._embedding_service is None:
        raise ExecutionError(
            "Vector search requested but embedding service not available"
        )
    
    if not question:
        raise ExecutionError(
            "Vector search requested but no question provided for embedding"
        )
    
    # Generate embedding
    embedding = self._embedding_service.embed_text(question)
    
    # Format as PostgreSQL vector string
    vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
    
    # Add to params
    updated_params = dict(params) if params else {}
    updated_params["query_vector"] = vector_str
    
    return updated_params
```

---

## SQL Execution with Vector

```python
# The SQL from generator will look like:
sql = """
SELECT 
    ed.content_text,
    1 - (ed.embedding <=> :query_vector) AS similarity
FROM plugin_assistant.extracted_documents ed
WHERE ed.embedding IS NOT NULL
ORDER BY ed.embedding <=> :query_vector
LIMIT 10
"""

# After parameter preparation:
params = {
    "query_vector": "[0.023,-0.145,0.089,...]"  # 384 floats
}

# SQLAlchemy execution:
result = session.execute(
    text(sql), 
    params
)
```

---

## PostgreSQL Vector Casting

The pgvector extension automatically casts string to vector when used with `<=>` operator:

```sql
-- This works:
embedding <=> '[0.1,0.2,0.3]'

-- Explicit cast also works:
embedding <=> '[0.1,0.2,0.3]'::vector
```

No explicit cast needed in the parameter binding.

---

## Error Handling

| Scenario | Error Type | User Message |
|----------|------------|--------------|
| `:query_vector` but no embedding service | ExecutionError | "Document search is not available" |
| `:query_vector` but no question | ExecutionError | "Cannot search documents without a query" |
| Embedding generation fails | ExecutionError | "Unable to process your search query" |
| pgvector not installed | ExecutionError | "Vector search is not configured" |

---

## Contract Tests

### Test 1: Normal Query (No Vector)

**Input**:
```python
executor.execute(
    "SELECT * FROM events.events LIMIT 10",
    params=None,
    question="What events exist?"
)
```

**Expected**:
- Executes without calling embedding service
- Returns normal results

### Test 2: Vector Query with Embedding

**Input**:
```python
executor.execute(
    "SELECT content_text FROM plugin_assistant.extracted_documents ORDER BY embedding <=> :query_vector LIMIT 5",
    params=None,
    question="What does the presentation say about physics?"
)
```

**Expected**:
- Calls `embedding_service.embed_text("What does the presentation say about physics?")`
- Adds `query_vector` to params
- Executes with vector parameter

### Test 3: Vector Query Without Question

**Input**:
```python
executor.execute(
    "SELECT * FROM extracted_documents ORDER BY embedding <=> :query_vector",
    params=None,
    question=None
)
```

**Expected**:
- Raises ExecutionError
- Message indicates question is required

### Test 4: Vector Query Without Embedding Service

**Input**:
```python
# executor initialized without embedding_service
executor.execute(
    "SELECT * FROM extracted_documents ORDER BY embedding <=> :query_vector",
    params=None,
    question="some question"
)
```

**Expected**:
- Raises ExecutionError
- Message indicates vector search unavailable

---

## Integration with Pipeline

The `NL2SQLPipeline.process()` method must pass `question` to executor:

```python
# In pipeline.py
exec_result = self._executor.execute(
    generated_sql,
    params=None,
    question=question  # Pass original question for embedding
)
```

---

## Performance Considerations

1. **Embedding generation**: ~50-100ms for bge-small-en-v1.5
2. **Vector search**: Uses IVF index on `embedding` column for fast approximate search
3. **Combined latency**: Should remain under 500ms for typical queries

## Graceful Degradation

If pgvector is not available:
1. Validator should reject queries containing `extracted_documents` table
2. Classifier should not route to `document_content_query` intent
3. User receives helpful message: "Document search is not enabled for this installation"
