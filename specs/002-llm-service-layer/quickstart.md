# Quickstart: LLM Service Abstraction Layer

**Feature**: 002-llm-service-layer  
**Date**: 2026-01-14

## Prerequisites

- Python 3.11+
- Indico development environment set up
- Plugin foundation (001-plugin-foundation) installed
- One of: Ollama running locally, HuggingFace API key, or OpenAI-compatible API

## Installation

### 1. Add Dependencies

The following dependencies will be added to `pyproject.toml`:

```toml
dependencies = [
    # ... existing dependencies ...
    "instructor>=1.0.0",
    "openai>=1.0.0",
    "ollama>=0.3.0",
]
```

### 2. Install in Development Mode

```bash
cd /path/to/indico_assistant_plugin
pip install -e ".[dev]"
```

### 3. Configure LLM Provider

Via Indico Admin Panel:
1. Navigate to Admin → Plugins → Indico Assistant
2. Set the following settings:
   - **LLM Provider**: `ollama` (or `huggingface`, `openai`)
   - **LLM Model**: `llama3.2` (or your model)
   - **Base URL**: `http://localhost:11434` (for Ollama)
   - **API Key**: (leave empty for Ollama, set for others)

Or via environment for development:
```bash
# Ollama (default)
export INDICO_ASSISTANT_LLM_PROVIDER=ollama
export INDICO_ASSISTANT_LLM_MODEL=llama3.2
export INDICO_ASSISTANT_LLM_BASE_URL=http://localhost:11434

# HuggingFace
export INDICO_ASSISTANT_LLM_PROVIDER=huggingface
export INDICO_ASSISTANT_LLM_MODEL=meta-llama/Llama-3-8b
export INDICO_ASSISTANT_LLM_BASE_URL=https://api-inference.huggingface.co/v1/
export INDICO_ASSISTANT_LLM_API_KEY=hf_xxxxx
```

## Quick Usage

### Basic Structured Call

```python
from indico_assistant.services.llm import LLMService, QueryClassification
from indico_assistant.plugin import AssistantPlugin

# Get plugin instance (in real code, this comes from Indico)
plugin = AssistantPlugin.instance

# Create or get LLM service
llm_service = plugin.llm_service

# Make a structured call
response = llm_service.generate(
    prompt="What events are happening next week about AI?",
    response_model=QueryClassification,
)

# Handle response
if response.success:
    print(f"Intent: {response.result.intent}")
    print(f"Entities: {response.result.entities}")
    print(f"Time range: {response.result.time_range}")
else:
    print(f"Error: {response.error.error_type} - {response.error.message}")
```

### Check Provider Health

```python
status = llm_service.health_check()
print(f"Status: {status.status}")
print(f"Provider: {status.provider}/{status.model}")
if status.latency_ms:
    print(f"Latency: {status.latency_ms}ms")
```

### Use Pre-defined Models

```python
from indico_assistant.services.llm import (
    QueryClassification,
    SQLGeneration,
    SQLCorrection,
    ResponseSummary,
)

# SQL Generation
sql_response = llm_service.generate(
    prompt="Get all workshops starting next week",
    response_model=SQLGeneration,
    system_prompt="You are a SQL expert for the Indico database...",
)

if sql_response.success:
    print(f"SQL: {sql_response.result.query}")
    print(f"Explanation: {sql_response.result.explanation}")
    print(f"Tables: {sql_response.result.tables_used}")
```

### Custom Response Model

```python
from pydantic import BaseModel, Field

class EventHighlights(BaseModel):
    """Custom model for event highlights."""
    title: str
    key_speakers: list[str] = Field(default_factory=list)
    main_topics: list[str] = Field(default_factory=list)
    summary: str

response = llm_service.generate(
    prompt=f"Extract highlights from: {event_description}",
    response_model=EventHighlights,
)
```

## Testing

### Unit Test Example

```python
import pytest
from unittest.mock import Mock, patch
from indico_assistant.services.llm import LLMService, LLMResponse, QueryClassification

@pytest.fixture
def mock_plugin():
    plugin = Mock()
    plugin.settings = {
        "llm_provider": "ollama",
        "llm_model": "llama3.2",
        "llm_base_url": "http://localhost:11434",
        "llm_api_key": None,
        "timeout_seconds": 30,
        "max_retries": 2,
    }
    return plugin

def test_generate_success(mock_plugin):
    service = LLMService(mock_plugin)
    
    # Mock the instructor client
    with patch.object(service, "_client") as mock_client:
        mock_client.create.return_value = QueryClassification(
            intent="search_events",
            entities=[],
            time_range=None,
            filters={},
        )
        
        response = service.generate(
            "Find events",
            QueryClassification,
        )
        
        assert response.success
        assert response.result.intent == "search_events"

def test_generate_timeout(mock_plugin):
    service = LLMService(mock_plugin)
    
    with patch.object(service, "_client") as mock_client:
        from openai import APITimeoutError
        mock_client.create.side_effect = APITimeoutError(request=Mock())
        
        response = service.generate(
            "Find events",
            QueryClassification,
        )
        
        assert not response.success
        assert response.error.error_type == "timeout"
```

### Run Tests

```bash
# Run all LLM service tests
pytest tests/unit/services/llm/ -v

# Run with coverage
pytest tests/unit/services/llm/ --cov=indico_assistant.services.llm --cov-report=term-missing
```

## Verification Checklist

After implementation, verify:

- [ ] `llm_service.health_check()` returns "connected" when provider is accessible
- [ ] `llm_service.generate()` returns validated Pydantic models
- [ ] Timeouts return `LLMError` with `error_type="timeout"`
- [ ] Invalid API keys return `LLMError` with `error_type="authentication_error"`
- [ ] Changing plugin settings affects subsequent LLM calls
- [ ] No API keys appear in logs
- [ ] All pre-defined models (QueryClassification, etc.) are importable

## Common Issues

### Ollama Not Running

```
Error: connection_error - Connection refused
```

**Solution**: Start Ollama with `ollama serve`

### Model Not Found

```
Error: model_not_found - Model 'xyz' not found
```

**Solution**: Pull the model with `ollama pull xyz`

### HuggingFace Rate Limit

```
Error: rate_limit - Rate limit exceeded
```

**Solution**: Wait for `retry_after` seconds or upgrade HF plan

## Next Steps

After this feature is complete, you can:

1. Use `llm_service.generate()` to build query classification
2. Integrate with SQL generation for natural language queries
3. Add response summarization for query results
