# Quickstart: NL2SQL and Vector Search Prompt Optimization

**Feature**: 013-nl2sql-prompt-optimization  
**Date**: 2026-01-19

## Overview

This feature enhances the NL2SQL pipeline prompts to improve SQL generation quality and unifies vector search into the LLM-generated SQL queries.

## Key Changes

### 1. Enhanced SQL Generation Prompt

**File**: `indico_assistant/services/nl2sql/generator.py`

The `SQL_GENERATION_PROMPT` is expanded to include:
- Required output columns (event_id, event_title, event_start_dt, event_timezone)
- Date formatting instructions using `to_char()` and `AT TIME ZONE`
- Four SQL templates (events, contributors, attachments, vector search)
- Explicit foreign key relationship hints
- Clear instructions against CTEs, subqueries, and window functions

### 2. New Classification Intent

**File**: `indico_assistant/services/nl2sql/classifier.py`

Added `document_content_query` intent to distinguish:
- `attachment_query`: "What files are attached?" → File metadata
- `document_content_query`: "What does the presentation say?" → Vector search

### 3. Parameterized Vector Search

**File**: `indico_assistant/services/nl2sql/executor.py`

The executor now:
- Detects `:query_vector` placeholder in generated SQL
- Generates embedding from user question using `EmbeddingService`
- Substitutes the vector parameter before execution

## Development Setup

```bash
# Ensure you're on the feature branch
git checkout 013-nl2sql-prompt-optimization

# Install dependencies (if not already)
pip install -e ".[dev]"

# Run tests for affected modules
pytest tests/unit/services/nl2sql/ -v
pytest tests/contract/ -v
```

## Testing the Changes

### Test Event Queries

```python
from indico_assistant.services.nl2sql import create_nl2sql_pipeline_from_plugin

pipeline = create_nl2sql_pipeline_from_plugin(plugin)
result = pipeline.process(
    question="What events are happening this week?",
    user_id=1
)

# Verify SQL contains required columns
assert "AS event_id" in result.generated_sql
assert "AS event_title" in result.generated_sql
assert "to_char(" in result.generated_sql
```

### Test Document Content Queries

```python
result = pipeline.process(
    question="What does the presentation say about machine learning?",
    user_id=1
)

# Verify vector search pattern
assert ":query_vector" in result.generated_sql or "document_content" in str(result)
assert "ORDER BY" in result.generated_sql
assert "<=> :query_vector" in result.generated_sql
```

### Test Classification

```python
from indico_assistant.services.nl2sql.classifier import QueryClassifier

classifier = QueryClassifier(llm_service)

# File metadata query
result = classifier.classify("What files are attached to event 123?")
assert result.data.intent == "attachment_query"

# Document content query
result = classifier.classify("What does the presentation say about physics?")
assert result.data.intent == "document_content_query"
```

## Contract Tests

Run the contract tests to verify prompt outputs:

```bash
pytest tests/contract/test_prompt_contracts.py -v
```

Contract tests verify:
1. Event queries include required columns
2. Speaker queries use STRING_AGG
3. Document queries use vector pattern
4. No forbidden patterns (CTEs, subqueries)

## Configuration

No new configuration required. Existing settings are used:
- `vector_search_enabled`: Controls whether document search is available
- `embedding_model`: Model for query embeddings (default: bge-small-en-v1.5)

## Troubleshooting

### "Vector search is not available"

Ensure pgvector extension is installed:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

And `vector_search_enabled` is True in plugin settings.

### "Document search not configured"

Ensure embedding service is initialized:
```python
plugin.settings.get("vector_search_enabled", True)  # Must be True
```

### Queries returning duplicate rows for speakers

Verify the generated SQL includes `GROUP BY` and `STRING_AGG`. If not, the classification may have been incorrect. Check classifier logs.

## Files Modified

| File | Change |
|------|--------|
| `services/nl2sql/generator.py` | Enhanced `SQL_GENERATION_PROMPT` |
| `services/nl2sql/classifier.py` | Added `document_content_query` intent |
| `services/nl2sql/executor.py` | Added vector parameter handling |
| `services/nl2sql/schema.py` | Enhanced schema context with common columns |
| `services/chat/service.py` | Removed separate RAG retrieval |
| `config_modules/available_tables.yaml` | Added extracted_documents schema |

## Migration Notes

- No database migrations required
- No API changes
- Backward compatible with existing queries
- RAGService remains available but is no longer called from ChatService
