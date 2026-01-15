# Research: LLM Service Abstraction Layer

**Feature**: 002-llm-service-layer  
**Date**: 2026-01-14

## Research Tasks

### 1. Instructor Library Integration Patterns

**Question**: How does Instructor's `from_provider()` work with different providers?

**Findings**:
- Instructor provides `instructor.from_provider("provider/model")` for unified client creation
- Format: `"ollama/llama3.2"`, `"openai/gpt-4"`, etc.
- Returns either `Instructor` (sync) or `AsyncInstructor` (async) based on `async_client` parameter
- Automatic mode selection based on model capabilities (TOOLS vs JSON)
- Built-in retry with validation error feedback to LLM

**Decision**: Use `instructor.from_provider()` as primary factory mechanism.

**Rationale**: 
- Single API for all providers reduces code complexity
- Automatic mode selection handles provider-specific differences
- Well-maintained library with active development

**Alternatives Considered**:
- Manual client wrapping with `instructor.from_openai()` / `instructor.from_ollama()` → Rejected: More code, same functionality
- Direct LLM API calls without Instructor → Rejected: Loses structured output validation

---

### 2. Ollama Provider Configuration

**Question**: What configuration is needed for Ollama integration?

**Findings**:
- Ollama uses OpenAI-compatible API internally
- Default endpoint: `http://localhost:11434`
- No API key required for local Ollama
- Model name format: `llama3.2`, `mistral`, `qwen2.5`, etc.
- Timeout handling is critical - Ollama can be slow with large models

**Decision**: Use existing plugin settings (llm_base_url, llm_model) with Instructor's auto-detection.

**Rationale**: Settings already defined in 001-plugin-foundation match Instructor's expectations.

**Code Pattern**:
```python
import instructor

client = instructor.from_provider(
    f"ollama/{model_name}",
    mode=instructor.Mode.JSON,  # or TOOLS for supported models
)
```

---

### 3. HuggingFace Router Integration

**Question**: How to integrate HuggingFace models via Instructor?

**Findings**:
- HuggingFace offers "HF Router" - OpenAI-compatible endpoint
- Endpoint: `https://api-inference.huggingface.co/v1/`
- Requires HF API token as bearer auth
- Use OpenAI client with custom base_url

**Decision**: Treat HuggingFace as OpenAI-compatible provider with custom base_url.

**Rationale**: Avoids needing separate HuggingFace-specific code paths.

**Code Pattern**:
```python
import instructor
from openai import OpenAI

client = instructor.from_openai(
    OpenAI(
        base_url="https://api-inference.huggingface.co/v1/",
        api_key=hf_api_key,
    ),
    mode=instructor.Mode.JSON,
)
```

---

### 4. Error Handling Patterns

**Question**: What errors can Instructor/providers throw and how to catch them?

**Findings**:
- `openai.APIConnectionError` - Connection failures
- `openai.APITimeoutError` - Request timeout
- `openai.RateLimitError` - Rate limiting (429)
- `openai.AuthenticationError` - Invalid API key (401)
- `instructor.exceptions.InstructorRetryException` - Retries exhausted
- `pydantic.ValidationError` - Schema validation failure

**Decision**: Wrap all provider calls in try/except, map to LLMError types.

**Error Type Mapping**:
| Provider Exception | LLMError.error_type |
|-------------------|---------------------|
| APITimeoutError | "timeout" |
| APIConnectionError | "connection_error" |
| RateLimitError | "rate_limit" |
| AuthenticationError | "authentication_error" |
| InstructorRetryException | "validation_error" |
| Any other | "unknown_error" |

---

### 5. Retry Configuration

**Question**: How does Instructor handle retries for validation failures?

**Findings**:
- Instructor has built-in retry via `max_retries` parameter
- On validation failure, sends error back to LLM for correction
- Default: 1 retry (2 total attempts)
- Can be configured per-call or at client level
- Respects timeout across all retry attempts

**Decision**: Use Instructor's built-in retry, configure via plugin settings `max_retries`.

**Rationale**: Built-in retry includes intelligent feedback to LLM, improving success rate.

**Code Pattern**:
```python
response = client.create(
    messages=[{"role": "user", "content": prompt}],
    response_model=ResponseModel,
    max_retries=settings.max_retries,
    timeout=settings.timeout_seconds,
)
```

---

### 6. Health Check Implementation

**Question**: How to test LLM provider connectivity?

**Findings**:
- No standard health check endpoint across providers
- Best approach: Send minimal completion request
- Measure latency from request to response
- Catch connection/timeout errors for status

**Decision**: Implement health check as minimal LLM call with simple response model.

**Rationale**: Actually exercises the full path (connection, auth, model loading).

**Code Pattern**:
```python
class HealthCheckResponse(BaseModel):
    status: str = "ok"

def health_check() -> HealthStatus:
    start = time.time()
    try:
        response = client.create(
            messages=[{"role": "user", "content": "Reply with exactly: ok"}],
            response_model=HealthCheckResponse,
            timeout=5.0,
        )
        latency_ms = int((time.time() - start) * 1000)
        return HealthStatus(status="connected", latency_ms=latency_ms)
    except Exception as e:
        return HealthStatus(status="unavailable", error=str(e))
```

---

### 7. Thread Safety

**Question**: Is the Instructor client thread-safe for concurrent requests?

**Findings**:
- OpenAI client is thread-safe for concurrent calls
- Instructor wraps OpenAI client, inherits thread safety
- Each call is independent (no shared mutable state)
- Singleton pattern is safe for multi-threaded Flask

**Decision**: Lazy-initialized singleton per plugin is safe.

**Rationale**: Reduces connection overhead while maintaining thread safety.

---

## Summary of Decisions

| Topic | Decision |
|-------|----------|
| Client Factory | `instructor.from_provider()` for unified interface |
| Ollama | Direct support via `ollama/model` format |
| HuggingFace | OpenAI-compatible with custom base_url |
| OpenAI-compatible | Generic support via base_url + api_key |
| Error Handling | Map provider exceptions to LLMError types |
| Retry Logic | Use Instructor's built-in max_retries |
| Health Check | Minimal LLM call with simple response model |
| Thread Safety | Singleton pattern is safe |

## Dependencies to Add

```toml
# pyproject.toml additions
dependencies = [
    "instructor>=1.0.0",
    "openai>=1.0.0",
    "ollama>=0.3.0",
]
```
