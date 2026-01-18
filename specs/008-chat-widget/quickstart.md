# Quickstart: Chat Widget for Indico Assistant

**Feature**: 008-chat-widget  
**Prerequisites**: Indico instance running, Chainlit server running

## Overview

This guide explains how to enable the chat widget in your Indico installation.

## Prerequisites

1. **Indico Assistant Plugin** installed and configured
2. **Chainlit Server** running (the `indico_assistant` app)
3. **Shared JWT Secret** configured in both systems

## Configuration Steps

### Step 0: Local env (recommended for dev)

```bash
# In indico_assistant (Chainlit app)
cp .env.quickstart.example .env.quickstart
# Edit .env.quickstart to set CHAINLIT_AUTH_SECRET and INDICO_SERVICE_TOKEN
source .env.quickstart
```

The Chainlit config at `.chainlit/config.toml` is pre-set to allow `http://localhost:8080` for quickstart. Adjust `allow_origins` if your Indico dev host differs.

### Step 1: Configure Chainlit Server

Add CORS settings to your Chainlit configuration:

```toml
# .chainlit/config.toml
[project]
allow_origins = ["https://your-indico-domain.com"]
```

Or via environment variable:
```bash
export CHAINLIT_ALLOW_ORIGINS=https://your-indico-domain.com
```

### Step 2: Set Shared Authentication Secret

Generate a secure secret:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Set in Chainlit:
```bash
export CHAINLIT_AUTH_SECRET=your-generated-secret
```

### Step 3: Configure Indico Plugin

In Indico admin panel → Plugins → Indico Assistant → Settings:

| Setting | Value |
|---------|-------|
| Chat Widget Enabled | ✓ Yes |
| Chainlit Server URL | `http://localhost:8001` |
| Chainlit Auth Secret | (same secret from Step 2) |

Or via `indico.conf`:
```python
PLUGINS = {
    'assistant': {
        'chat_widget_enabled': True,
        'chainlit_server_url': 'http://chainlit-server:8000',
        'chainlit_auth_secret': 'your-generated-secret'
    }
}
```

### Step 4: Restart Services

```bash
# Restart Indico (dev server)
source /Users/lucasflores/dev2/indico/env/bin/activate
INDICO_CONFIG=/Users/lucasflores/dev2/indico/src/indico/indico.conf indico run -h 127.0.0.1 -p 8000

# Ensure Chainlit is running (separate shell)
cd /path/to/indico_assistant
source .env.quickstart
chainlit run src/app_chnlit.py --port 8001
```

## Verification

1. Log into Indico as any user
2. Look for chat button in bottom-right corner
3. Click to expand chat panel
4. Send a test message: "What events do I have access to?"

## Troubleshooting

### Widget not appearing

1. Check browser console for errors
2. Verify `chat_widget_enabled` is True
3. Ensure Chainlit server is accessible from browser

### Authentication errors

1. Verify JWT secrets match
2. Check Chainlit logs for token validation errors
3. Ensure CORS is configured correctly

### CORS errors

1. Add your Indico domain to `allow_origins`
2. If using HTTPS, ensure Chainlit has valid SSL certificate
3. Check for `CHAINLIT_COOKIE_SAMESITE=none` if domains differ

## API Reference

### JavaScript Functions

```javascript
// Toggle widget programmatically
window.toggleChainlitCopilot();

// Get current thread ID
const threadId = window.getChainlitCopilotThreadId();

// Clear thread (start new conversation)
window.clearChainlitCopilotThreadId();

// Send system message to assistant
window.sendChainlitMessage({
    type: "system_message",
    output: "User selected event ID 123"
});
```

### Widget Configuration Options

```javascript
window.mountChainlitWidget({
    chainlitServer: "http://localhost:8000",
    accessToken: "jwt-token",
    theme: "light",  // or "dark"
    button: {
        containerId: "custom-container",  // optional
        imageUrl: "/custom-icon.svg",     // optional
        className: "my-custom-class"      // optional
    },
    expanded: false,  // start collapsed
    language: "en-US"
});
```

## Architecture

```
User Browser
    │
    ├── Indico Page (plugin injects widget script)
    │   └── Chainlit Copilot Widget (iframe)
    │       ├── localStorage: thread ID persistence
    │       └── sessionStorage: auth token
    │
    └── WebSocket/REST → Chainlit Server
                              │
                              ├── LLM Service (via Instructor)
                              ├── Langfuse (observability)
                              └── Indico API (feedback, data)
```

## Next Steps

- [Configure feedback storage](../005-langfuse-observability/quickstart.md)
- [Set up vector search](../006-vector-search-rag/quickstart.md)
- [Customize prompts](../../docs/PROMPTS.md)
