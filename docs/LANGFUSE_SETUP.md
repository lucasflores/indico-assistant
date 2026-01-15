# Langfuse Observability Setup Guide

## Overview

Feature 005 integrates Langfuse observability into the Indico Assistant plugin, enabling:
- Real-time tracing of LLM calls
- Pipeline stage performance monitoring  
- Usage statistics and error tracking
- Privacy-aware content capture

## Quick Start

### 1. Get Langfuse Credentials

**Option A: Langfuse Cloud (Recommended)**
1. Sign up at https://cloud.langfuse.com
2. Create a new project
3. Go to Settings → API Keys
4. Copy your Public Key and Secret Key

**Option B: Self-Hosted Langfuse**
1. Follow the [Langfuse deployment guide](https://langfuse.com/docs/deployment/self-host)
2. Access your Langfuse instance
3. Create a project and generate API keys

### 2. Configure Plugin Settings

In the Indico admin panel (Administration → Plugins → Indico Assistant):

| Setting | Description | Default |
|---------|-------------|---------|
| `langfuse_enabled` | Enable/disable tracing | `false` |
| `langfuse_host` | Langfuse API endpoint | `https://cloud.langfuse.com` |
| `langfuse_public_key` | Your public API key | (required) |
| `langfuse_secret_key` | Your secret API key | (required) |
| `langfuse_privacy_level` | Content capture level | `metadata` |

### 3. Privacy Levels

Choose the appropriate privacy level for your deployment:

| Level | Captures | Use Case |
|-------|----------|----------|
| `metadata` | Timing, tokens, model info only. NO prompt/response content. | Production with strict privacy |
| `masked` | Content with PII (emails, @usernames) redacted | Balanced debugging capability |
| `full` | Complete content including prompts and responses | Development/debugging only |

## Environment Variables (Alternative Configuration)

For containerized deployments, set via environment variables:

```bash
# Required when enabled
export LANGFUSE_HOST="https://cloud.langfuse.com"
export LANGFUSE_PUBLIC_KEY="pk-..."
export LANGFUSE_SECRET_KEY="sk-..."

# Set in Indico plugin settings
# langfuse_enabled: true
# langfuse_privacy_level: metadata
```

## Verification

### Check Connection Status

```bash
curl -X GET "https://your-indico-instance/api/assistant/admin/health" \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

Expected response:
```json
{
  "status": "healthy",
  "components": {
    "langfuse": {
      "status": "connected",
      "privacy_level": "metadata"
    }
  }
}
```

### View Traces in Langfuse

1. Open your Langfuse dashboard
2. Navigate to Traces
3. Make a chat query in Indico Assistant
4. Verify the trace appears with:
   - Root trace: `chat-request`
   - Nested spans: `query_classification`, `sql_generation`, `sql_execution`, `response_summarization`
   - Generation span for LLM calls

## Admin Dashboard

Access usage statistics and errors via the admin API:

### Usage Statistics
```bash
GET /api/assistant/admin/stats?period=day
GET /api/assistant/admin/stats?period=week
GET /api/assistant/admin/stats?period=month
```

### Error Records
```bash
GET /api/assistant/admin/errors?limit=50&offset=0
GET /api/assistant/admin/errors?error_type=llm_error
```

## Graceful Degradation

The plugin is designed to never fail user requests due to tracing issues:

- **Langfuse unavailable**: Traces are silently dropped, chat continues working
- **Invalid credentials**: Warning logged at startup, tracing disabled
- **Network errors**: Logged but don't affect user requests

## Troubleshooting

### "Langfuse credentials not configured"
- Verify `langfuse_public_key` and `langfuse_secret_key` are set
- Check for typos in the keys

### "Langfuse credentials invalid"
- Regenerate API keys in Langfuse dashboard
- Ensure keys match the correct project

### "No traces appearing"
- Check `langfuse_enabled` is `true`
- Verify network connectivity to `langfuse_host`
- Check Indico logs for tracing errors

### Performance Concerns
- Tracing adds <5ms overhead per request
- Uses async batching (SDK default)
- Traces are flushed at request teardown

## Architecture

```
User Request
    │
    ▼
┌─────────────────┐
│   Chat API      │──── Tracer.trace() ────┐
│   Controller    │                        │
└────────┬────────┘                        │
         │                                 │
         ▼                                 ▼
┌─────────────────┐                ┌──────────────┐
│  NL2SQL Pipeline│                │   Langfuse   │
│                 │                │    Cloud     │
│ ┌─────────────┐ │                │              │
│ │Classification│◄── span() ─────►│   Traces     │
│ └─────────────┘ │                │   Spans      │
│ ┌─────────────┐ │                │   Metrics    │
│ │ SQL Gen     │◄── generation() ─►│              │
│ └─────────────┘ │                └──────────────┘
│ ┌─────────────┐ │                        │
│ │ Execution   │◄── span() ───────────────┘
│ └─────────────┘ │
│ ┌─────────────┐ │
│ │ Formatting  │◄── span()
│ └─────────────┘ │
└─────────────────┘
```

## Metrics Sync

An hourly Celery task syncs metrics from Langfuse to local PostgreSQL:
- Aggregates usage stats (requests, tokens, errors)
- Stores error records for debugging
- Enables admin dashboard to work even during Langfuse outages
- Automatically cleans up error records older than 7 days
