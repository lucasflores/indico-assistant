# Quickstart: Langfuse Observability

**Feature**: 005-langfuse-observability  
**Date**: 2026-01-15

## Prerequisites

1. Indico instance running with assistant plugin installed
2. Langfuse account (cloud or self-hosted)
3. Admin access to Indico
4. PostgreSQL accessible (via Indico)

## Setup Steps

### 1. Get Langfuse Credentials

1. Sign up at https://cloud.langfuse.com (or use self-hosted instance)
2. Create a new project
3. Go to Settings → API Keys
4. Copy the Public Key and Secret Key

### 2. Configure Plugin Settings

In Indico admin panel → Plugins → Indico Assistant:

```yaml
# Langfuse Settings
langfuse_enabled: true
langfuse_public_key: "pk-lf-..."
langfuse_secret_key: "sk-lf-..."
langfuse_host: "https://cloud.langfuse.com"  # or your self-hosted URL

# Privacy Settings
observability_privacy_level: "metadata"  # options: metadata, masked, full
observability_max_content_length: 10000  # truncate large prompts/responses

# Sync Settings (for admin dashboard)
metrics_sync_interval_hours: 1
metrics_retention_days: 30
error_retention_days: 7
```

### 3. Run Database Migration

```bash
cd /path/to/indico
indico db --plugin assistant migrate
```

This creates the observability tables:
- `plugin_assistant.observability_usage_stats`
- `plugin_assistant.observability_error_records`
- `plugin_assistant.observability_sync_log`

### 4. Verify Setup

#### Check Langfuse Connection

```bash
# Via CLI
indico assistant check-langfuse

# Expected output:
# ✓ Langfuse client initialized
# ✓ Authentication successful
# ✓ Project: your-project-name
```

#### Check Admin Health Endpoint

```bash
curl -X GET "http://localhost:8000/api/assistant/admin/health" \
  -H "Cookie: session=<your-session-cookie>"
```

Expected response:
```json
{
  "status": "healthy",
  "components": {
    "langfuse": {
      "status": "connected",
      "last_check": "2026-01-15T14:30:00Z"
    },
    "local_storage": {
      "status": "connected",
      "last_sync": null,
      "sync_status": null
    }
  }
}
```

## Validation Tests

### Test 1: LLM Tracing (US1)

**Goal**: Verify LLM calls create traces in Langfuse

1. Send a chat message:
```bash
curl -X POST "http://localhost:8000/api/assistant/chat" \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your-session-cookie>" \
  -d '{"message": "How many events are there?", "event_id": 123}'
```

2. Open Langfuse dashboard
3. Verify trace appears with:
   - Trace name containing "chat-request"
   - Generation span for LLM call
   - Model name, latency, token counts visible
   - Input/output visible only if privacy_level != "metadata"

**Expected**: Trace visible in Langfuse within 60 seconds

### Test 2: Pipeline Span Tracking (US2)

**Goal**: Verify NL2SQL pipeline stages create nested spans

1. Send a complex query:
```bash
curl -X POST "http://localhost:8000/api/assistant/chat" \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your-session-cookie>" \
  -d '{"message": "Show me all events in January with more than 100 participants", "event_id": 123}'
```

2. Open Langfuse dashboard and view the trace
3. Verify nested spans:
   - `query_classification` (with intent captured)
   - `sql_generation`
   - `sql_execution`
   - `response_summarization`

**Expected**: Hierarchical span view showing pipeline stages with individual durations

### Test 3: Graceful Degradation (US1/SC-003)

**Goal**: Verify requests complete when Langfuse is unreachable

1. Temporarily break Langfuse connection:
```yaml
# In plugin settings
langfuse_host: "https://invalid-host.example.com"
```

2. Send a chat message:
```bash
curl -X POST "http://localhost:8000/api/assistant/chat" \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your-session-cookie>" \
  -d '{"message": "How many events?", "event_id": 123}'
```

3. Verify:
   - Request completes successfully
   - Check logs for warning: "Langfuse tracing error"

**Expected**: 200 OK response, warning logged, no trace in Langfuse

4. Restore valid Langfuse host

### Test 4: Admin Stats Endpoint (US3)

**Goal**: Verify admin stats API returns aggregated metrics

1. Trigger metrics sync (or wait for scheduled sync):
```bash
indico assistant sync-metrics --force
```

2. Request stats:
```bash
curl -X GET "http://localhost:8000/api/assistant/admin/stats?period=day" \
  -H "Cookie: session=<admin-session-cookie>"
```

**Expected**:
```json
{
  "period": {
    "type": "day",
    "start": "2026-01-15T00:00:00Z",
    "end": "2026-01-15T23:59:59Z"
  },
  "stats": {
    "total_queries": 25,
    "successful_queries": 24,
    "error_count": 1,
    "error_rate": 0.04,
    "avg_latency_ms": 2100.5
  },
  "last_synced_at": "2026-01-15T14:00:00Z"
}
```

### Test 5: Admin Errors Endpoint (US3)

**Goal**: Verify admin errors API returns recent errors

1. Request errors:
```bash
curl -X GET "http://localhost:8000/api/assistant/admin/errors?limit=10" \
  -H "Cookie: session=<admin-session-cookie>"
```

**Expected**:
```json
{
  "errors": [
    {
      "id": "...",
      "correlation_id": "abc123...",
      "timestamp": "2026-01-15T10:30:00Z",
      "error_type": "SQL_EXECUTION_ERROR",
      "error_message": "Query execution timed out",
      "langfuse_trace_url": "https://cloud.langfuse.com/trace/..."
    }
  ],
  "total": 5,
  "limit": 10,
  "offset": 0
}
```

### Test 6: Privacy Levels (US4)

**Goal**: Verify each privacy level controls content capture correctly

#### Test 6a: Metadata Level
```yaml
observability_privacy_level: "metadata"
```

1. Send chat message
2. View trace in Langfuse
3. Verify: No input/output content, only timing and model info

#### Test 6b: Masked Level
```yaml
observability_privacy_level: "masked"
```

1. Send message containing email: "Find registrations for user@example.com"
2. View trace in Langfuse
3. Verify: Email replaced with `[EMAIL]` in trace content

#### Test 6c: Full Level
```yaml
observability_privacy_level: "full"
```

1. Send chat message
2. View trace in Langfuse
3. Verify: Complete prompt and response content visible

### Test 7: Permission Check (US3)

**Goal**: Verify non-admin users cannot access admin endpoints

1. Login as non-admin user
2. Request admin stats:
```bash
curl -X GET "http://localhost:8000/api/assistant/admin/stats" \
  -H "Cookie: session=<non-admin-session-cookie>"
```

**Expected**: 403 Forbidden
```json
{
  "error": "FORBIDDEN",
  "message": "Admin permission required"
}
```

## Troubleshooting

### Traces Not Appearing in Langfuse

1. Check credentials:
```bash
indico assistant check-langfuse
```

2. Check logs for errors:
```bash
grep -i langfuse /path/to/indico/logs/indico.log
```

3. Verify flush is called (check for "Langfuse flush" in logs)

### Metrics Sync Not Running

1. Check Celery worker is running:
```bash
celery -A indico.celery inspect active
```

2. Check sync log:
```sql
SELECT * FROM plugin_assistant.observability_sync_log 
ORDER BY started_at DESC LIMIT 5;
```

3. Manual sync:
```bash
indico assistant sync-metrics --force
```

### High Latency Impact

If tracing adds noticeable latency:

1. Verify async mode (should be default)
2. Reduce flush frequency in settings
3. Check network latency to Langfuse host
4. Consider self-hosted Langfuse for lower latency

## Performance Expectations

| Metric | Target | Measurement |
|--------|--------|-------------|
| Tracing overhead | < 5ms | Time difference with/without tracing |
| Admin stats response | < 500ms | Response time for 30-day query |
| Memory overhead | < 50MB | Additional memory for trace buffer |
| Sync duration | < 5min | Time for hourly sync job |
