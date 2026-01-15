# Quickstart: NL2SQL Pipeline

**Feature**: 003-nl2sql-pipeline | **Date**: 2026-01-14

## Prerequisites

- [ ] Feature 002-llm-service-layer is implemented and tested
- [ ] Feature 001-plugin-foundation is implemented
- [ ] Indico development environment is configured
- [ ] PostgreSQL database with Indico schema is accessible
- [ ] LLM provider (Ollama or HuggingFace) is configured in plugin settings

## Quick Usage

### Basic Question Processing

```python
from indico_assistant.services.nl2sql import create_nl2sql_pipeline

# In an Indico request handler context
def handle_question(plugin, user, question_text):
    pipeline = create_nl2sql_pipeline(plugin)
    
    result = pipeline.process(
        question=question_text,
        user_id=user.id,
    )
    
    if result.success:
        return {
            "answer": result.answer,
            "confidence": result.confidence,
            "sql": result.generated_sql,  # Optional: for transparency
        }
    else:
        return {
            "error": result.error.user_message,
        }
```

### Scoped to Specific Events

```python
# Limit query to specific event(s)
result = pipeline.process(
    question="How many contributions are there?",
    user_id=user.id,
    event_ids=[123, 456],  # Only these events
)
```

### Force Fresh Query (Bypass Cache)

```python
result = pipeline.process(
    question="How many registrations today?",
    user_id=user.id,
    force_refresh=True,  # Skip cache
)
```

## Sample Questions

The pipeline handles these types of questions:

| Question Type | Example |
|---------------|---------|
| Count queries | "How many events are there this month?" |
| List queries | "Show me all workshops next week" |
| Filter queries | "List events with more than 100 registrations" |
| Time-based | "What events happened recently?" |
| Entity lookup | "Find the physics conference" |
| Multi-entity | "Who are the speakers at tomorrow's workshop?" |

## Configuration

Plugin settings for NL2SQL (set via admin panel):

```python
# In plugin settings form
'nl2sql_timeout_seconds': 30,        # Query timeout
'nl2sql_max_rows': 1000,             # Result limit
'nl2sql_max_corrections': 3,         # LLM retry attempts
'nl2sql_cache_ttl_seconds': 600,     # Cache duration (10 min)
```

## Testing

### Run Unit Tests

```bash
cd /path/to/indico_assistant_plugin
pytest tests/unit/services/nl2sql/ -v
```

### Run Contract Tests

```bash
pytest tests/contract/nl2sql/ -v
```

### Run Integration Tests

```bash
# Requires LLM provider and database
pytest tests/integration/nl2sql/ -v
```

### Manual Test

```python
# In Indico shell
from indico_assistant.services.nl2sql import create_nl2sql_pipeline
from indico_assistant.plugin import AssistantPlugin

plugin = AssistantPlugin.instance
pipeline = create_nl2sql_pipeline(plugin)

result = pipeline.process(
    question="How many events are there?",
    user_id=1,  # Admin user
)

print(f"Success: {result.success}")
print(f"Answer: {result.answer}")
print(f"SQL: {result.generated_sql}")
```

## Architecture Overview

```
User Question
     │
     ▼
┌─────────────────┐
│ QueryClassifier │ → Extracts intent, entities, time ranges
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  SQLGenerator   │ → Creates PostgreSQL SELECT query
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  SQLValidator   │ → Ensures safety (SELECT-only, allowed tables)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ QueryExecutor   │ → Runs against Indico database
└────────┬────────┘
         │
    Error? ──────► ErrorCorrector (up to 3 retries)
         │
         ▼
┌─────────────────┐
│ ResultFormatter │ → Natural language summary
└────────┬────────┘
         │
         ▼
   PipelineResult
```

## Key Files

| File | Purpose |
|------|---------|
| `indico_assistant/services/nl2sql/pipeline.py` | Main orchestrator |
| `indico_assistant/services/nl2sql/classifier.py` | Question classification |
| `indico_assistant/services/nl2sql/generator.py` | SQL generation |
| `indico_assistant/services/nl2sql/validator.py` | SQL safety validation |
| `indico_assistant/services/nl2sql/executor.py` | Database execution |
| `indico_assistant/services/nl2sql/corrector.py` | Error correction loop |
| `indico_assistant/services/nl2sql/formatter.py` | Result formatting |
| `indico_assistant/services/nl2sql/schema.py` | Schema context loading |
| `indico_assistant/services/nl2sql/cache.py` | Query result caching |
| `indico_assistant/models/audit.py` | QueryAuditLog model |

## Common Issues

### "LLM not configured"

Ensure LLM settings are configured in plugin admin:
- `llm_provider`: "ollama" or "huggingface"
- `llm_model`: Model name (e.g., "llama3.2")
- `llm_base_url`: Provider URL

### "Table not allowed"

The query references a table not in the allowlist. Check `nl2sql_allowed_tables` setting.

### "Timeout"

Query took too long. Increase `nl2sql_timeout_seconds` or simplify the question.

### "Correction exhausted"

LLM couldn't fix the SQL after 3 attempts. Try rephrasing the question.

## Next Steps

After implementing NL2SQL pipeline:

1. **REST API exposure** (future feature): Expose pipeline via `/api/assistant/query`
2. **Chat interface**: Integrate with Chainlit for conversational UI
3. **Query suggestions**: Add autocomplete based on common questions
