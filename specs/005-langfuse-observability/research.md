# Research: Langfuse Observability

**Feature**: 005-langfuse-observability  
**Date**: 2026-01-15

## Research Tasks Completed

### 1. Langfuse Python SDK Integration Patterns

**Decision**: Use `langfuse` Python SDK with context manager API (`start_as_current_observation`)

**Rationale**:
- Context managers automatically handle span lifecycle (start/end)
- Automatic parent-child nesting via OpenTelemetry context propagation
- Native Instructor integration available but we'll use manual instrumentation for more control
- Async by default - traces buffered and sent in background
- `flush()` method available for explicit send in short-lived processes

**Alternatives Considered**:
- OpenTelemetry direct: More complex, would need custom exporter for Langfuse
- Decorator-only approach: Less flexible for pipeline stages where we need explicit span control

**Key API Patterns**:
```python
from langfuse import get_client, propagate_attributes

langfuse = get_client()

# Root trace with user context
with langfuse.start_as_current_observation(as_type="span", name="chat-request") as root:
    with propagate_attributes(user_id=str(user_id), session_id=session_id):
        # Nested generation span for LLM call
        with langfuse.start_as_current_observation(
            as_type="generation", 
            name="llm-call",
            model=model_name
        ) as gen:
            gen.update(
                input={"prompt": prompt},
                output=response,
                usage_details={"input_tokens": in_tokens, "output_tokens": out_tokens}
            )
```

### 2. Graceful Degradation Strategy

**Decision**: Wrap Langfuse client in LangfuseClient class that catches all errors and logs warnings

**Rationale**:
- Constitution principle IV requires user requests never fail due to observability
- Langfuse SDK already handles errors gracefully but we add explicit fallback
- Use `auth_check()` at startup to validate credentials and log clearly

**Implementation Pattern**:
```python
class LangfuseClient:
    def __init__(self, settings):
        self._client = None
        self._enabled = settings.get("langfuse_enabled", False)
        if self._enabled:
            try:
                self._client = get_client()
                if not self._client.auth_check():
                    logger.error("Langfuse credentials invalid")
                    self._enabled = False
            except Exception as e:
                logger.warning(f"Langfuse initialization failed: {e}")
                self._enabled = False
    
    @contextmanager
    def trace(self, name, **kwargs):
        if not self._enabled or not self._client:
            yield NoOpSpan()  # No-op context manager
            return
        try:
            with self._client.start_as_current_observation(name=name, **kwargs) as span:
                yield span
        except Exception as e:
            logger.warning(f"Tracing error: {e}")
            yield NoOpSpan()
```

### 3. Privacy Level Implementation

**Decision**: Implement three privacy levels at the tracer layer before sending to Langfuse

**Rationale**:
- "metadata" level: Don't set input/output on spans at all
- "masked" level: Apply PII redaction before setting input/output
- "full" level: Pass through unchanged
- Cleaner than post-processing; data never leaves the plugin in undesired form

**PII Patterns to Redact (per clarification)**:
- Email addresses: `r'\b[\w.-]+@[\w.-]+\.\w+\b'` → `[EMAIL]`
- @username mentions: `r'@\w+'` → `[USERNAME]`
- Common name patterns: Configurable list or pattern matching (keep simple initially)

### 4. Local Metrics Storage Strategy

**Decision**: Store aggregated stats in PostgreSQL, sync from Langfuse hourly via Celery

**Rationale** (per clarification):
- Ensures admin stats available even when Langfuse unreachable
- PostgreSQL already available via Indico
- Celery already used in plugin for cleanup tasks (Feature 004)
- Hourly sync balances freshness vs API load

**Tables**:
- `observability_usage_stats`: period, total_queries, avg_latency_ms, error_count, etc.
- `observability_error_records`: timestamp, correlation_id, error_type, message, stack_trace
- `observability_sync_log`: sync_id, started_at, completed_at, records_synced, status

**Sync Approach**:
- Use Langfuse API to fetch traces/observations
- Aggregate into stats records
- Store recent errors (last 7 days rolling)
- Log sync status for debugging

### 5. NL2SQL Pipeline Instrumentation Points

**Decision**: Add span tracking at existing audit log points in pipeline.py

**Rationale**:
- Pipeline already has AuditLogger with timing for each stage
- Instrument at the same points: classification, generation, execution, correction, formatting
- Spans nest naturally with pipeline's sequential execution

**Integration Points** (from pipeline.py analysis):
1. `log_classification` → `query_classification` span
2. `log_generation` → `sql_generation` span
3. `log_execution` → `sql_execution` span
4. `log_correction_attempt` → `sql_correction` span
5. ResultFormatter call → `response_summarization` span

### 6. Admin API Design

**Decision**: Two endpoints under `/api/assistant/admin/` prefix with admin permission check

**Rationale**:
- Matches existing API structure
- Uses Indico's admin permission check via RH base class
- Period filtering for flexible time range queries

**Endpoints**:
- `GET /api/assistant/admin/stats?period=day|week|month` - Usage statistics
- `GET /api/assistant/admin/errors?limit=50&error_type=<type>` - Recent errors

### 7. Async Tracing Implementation

**Decision**: Use Langfuse's built-in async batching, no custom queue needed

**Rationale**:
- Langfuse SDK already buffers spans and sends async in background threads
- SDK provides `flush()` for explicit send, `shutdown()` for cleanup
- Bounded queue built into SDK with configurable batch size
- Constitution FR-017/FR-018 satisfied by SDK defaults

**Configuration**:
- `LANGFUSE_BATCH_SIZE`: Controls batch size (default: 15)
- `LANGFUSE_FLUSH_INTERVAL`: Controls flush interval (default: 60s)
- Call `langfuse.flush()` in request teardown for critical paths

## Technology Decisions Summary

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Tracing SDK | `langfuse` Python package | Official SDK, async, OpenTelemetry-based |
| Context Management | Context managers (`start_as_current_observation`) | Automatic nesting, lifecycle management |
| Local Storage | PostgreSQL (plugin_assistant schema) | Consistent with existing models |
| Background Sync | Celery task | Consistent with Feature 004 cleanup tasks |
| Privacy Redaction | Regex-based PII masking | Simple, deterministic, testable |
| Admin Auth | Indico RH admin permission check | Consistent with plugin architecture |
