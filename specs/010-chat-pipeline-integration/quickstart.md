# Quickstart: Chat Pipeline Integration

**Feature**: 010-chat-pipeline-integration  
**Time to first test**: ~15 minutes

## Prerequisites

- Indico instance running with assistant plugin installed
- LLM provider configured (Azure OpenAI, OpenAI, or Ollama)
- Python 3.11+ environment for Chainlit

## Quick Setup

### 1. Configure Chainlit Environment

Create/update `chainlit_app/.env`:

```bash
# Required: Indico API base URL
INDICO_API_URL=http://localhost:8000

# Required: JWT secret (must match plugin setting)
CHAINLIT_AUTH_SECRET=your-secret-key-here

# Optional: Logging
CHAINLIT_LOG_LEVEL=INFO
```

### 2. Install Dependencies

```bash
cd chainlit_app
pip install httpx  # Add to existing environment
```

### 3. Start Services

Terminal 1 - Indico:
```bash
indico run -h 0.0.0.0 -p 8000
```

Terminal 2 - Chainlit:
```bash
cd chainlit_app
chainlit run app_chnlit.py -w
```

### 4. Verify Integration

Open the widget and send a test message:
```
What events are happening this week?
```

**Expected**: A contextual response from the LLM, NOT "Echo: What events are happening this week?"

## Verification Checklist

- [ ] Message is NOT echoed back
- [ ] Response is contextual and helpful
- [ ] No "NL2SQL pipeline is not configured" message
- [ ] `sql_generated` appears in response metadata (for data queries)
- [ ] Session persists across multiple messages

## Common Issues

### "Echo: ..." responses
- Chainlit is not calling the Indico API
- Check `INDICO_API_URL` environment variable
- Verify Indico is accessible from Chainlit container/process

### "NL2SQL pipeline is not configured"
- The chat service import fix hasn't been applied
- Check that `NL2SQLPipeline` is being used (not `NL2SQLService`)

### 401 Unauthorized from Indico
- JWT secret mismatch between Chainlit and Indico plugin
- Verify `CHAINLIT_AUTH_SECRET` matches plugin `jwt_secret` setting

### Connection refused
- Indico not running or not accessible
- Check network connectivity and firewall rules
- Verify `INDICO_API_URL` is correct

## Development Workflow

1. Make changes to `app_chnlit.py` or chat service
2. Chainlit auto-reloads with `-w` flag
3. For Indico changes, restart Indico or use debug mode
4. Test via widget or direct API calls:

```bash
# Direct API test
curl -X POST http://localhost:8000/api/assistant/chat \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "How many events are there?"}'
```
