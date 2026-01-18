# Implementation Plan: Chat Widget for Indico Assistant

**Branch**: `008-chat-widget` | **Date**: 2026-01-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-chat-widget/spec.md`

## Summary

Embed a chat widget into Indico's global header using the Chainlit Copilot widget. This approach leverages Chainlit's production-ready chat UI instead of building a custom widget from scratch, dramatically reducing implementation complexity while meeting all functional requirements.

**Key Decision**: Use Chainlit Copilot widget embedded via iframe/script injection rather than building a custom chat interface. The existing `indico_assistant` Chainlit app already provides the chat backend.

## Technical Context

**Language/Version**: Python 3.11+ (plugin), JavaScript ES6 (widget injection)  
**Primary Dependencies**: Chainlit Copilot widget, Flask (via Indico), Indico plugin system  
**Storage**: sessionStorage (client-side thread persistence via Chainlit), PostgreSQL (existing)  
**Testing**: pytest with Indico fixtures, Playwright for E2E widget tests  
**Target Platform**: Indico web application (all modern browsers)  
**Project Type**: Indico plugin extension (frontend injection)  
**Performance Goals**: Widget interactive within 2 seconds of page load  
**Constraints**: <50KB additional JS (Chainlit widget external), CORS configuration for Chainlit server  
**Scale/Scope**: All authenticated Indico users on any page with global header

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Official Indico Plugin Architecture | ✅ PASS | Uses `IndicoPlugin.template_hook()` and `inject_bundle()` methods |
| II. API-First Design | ✅ PASS | Chainlit exposes REST/WebSocket API; widget is optional UI enhancement |
| III. LLM Provider Abstraction | ✅ PASS | Chainlit app already uses existing LLM abstraction |
| IV. Graceful Degradation | ✅ PASS | Widget hidden if JS disabled; noscript fallback; Chainlit server unavailable shows error |
| V. Configuration Hierarchy | ✅ PASS | Chainlit URL/enabled flag configurable in plugin settings |
| VI. Test-First Development | ✅ PASS | Contract tests for config API, E2E tests for widget |

**Pre-design Gate**: ✅ PASSED

## Project Structure

### Documentation (this feature)

```text
specs/008-chat-widget/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (minimal - client-side state only)
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── widget-config.yaml
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
indico_assistant/
├── plugin.py                    # Add template_hook + inject_bundle registration
├── default_settings.py          # Add chat widget settings
├── forms.py                     # Add widget settings form fields
├── static/
│   └── js/
│       └── chat_widget.js       # Chainlit widget initialization script
├── templates/
│   └── assistant/
│       └── chat_widget.html     # Template hook HTML (widget container)
└── controllers/
    └── widget.py                # Optional: widget config endpoint

tests/
├── unit/
│   └── test_widget_config.py    # Widget settings validation
├── integration/
│   └── test_widget_injection.py # Template hook registration
└── e2e/
    └── test_chat_widget.py      # Playwright browser tests
```

**Structure Decision**: Minimal additions to existing plugin structure. No new services needed - leverages existing Chainlit server running as separate process.

## Architecture Decision: Chainlit Copilot vs Custom Widget

### Option A: Chainlit Copilot Widget (SELECTED)

**Approach**: Embed Chainlit's Copilot widget which provides:
- Pre-built chat UI with message history
- Thread persistence via localStorage
- Markdown rendering built-in
- Mobile responsive by default
- Accessibility features included
- Feedback collection via Chainlit's `cl.feedback_buttons`

**Integration**:
```javascript
// chat_widget.js
window.mountChainlitWidget({
    chainlitServer: IndicoAssistant.chainlitUrl,
    accessToken: IndicoAssistant.authToken,  // JWT from Indico session
    theme: document.body.classList.contains('dark') ? 'dark' : 'light',
    button: {
        containerId: 'assistant-widget-container'
    }
});
```

**Pros**:
- 90% of UI requirements met out-of-box
- Existing `app_chnlit.py` already works
- Feedback integration via Chainlit
- Thread persistence handled automatically
- <1 week implementation vs 3-4 weeks custom

**Cons**:
- Requires Chainlit server running separately
- CORS configuration needed
- Authentication token handoff complexity

### Option B: Custom Widget (REJECTED)

**Approach**: Build custom chat UI from scratch using vanilla JS.

**Pros**:
- Full control over UI
- No external dependency
- Direct integration with `/api/assistant/chat`

**Cons**:
- 3-4 weeks implementation
- Must build: message rendering, scroll management, markdown, feedback UI, session storage, accessibility
- Maintenance burden
- Risk of bugs in edge cases

### Decision Rationale

Chainlit Copilot reduces implementation from ~20 tasks to ~8 tasks. The existing `indico_assistant` app already runs Chainlit, so the backend is ready. The primary work is:
1. Configure CORS on Chainlit server
2. Implement JWT token handoff for authentication
3. Inject widget script via Indico template hooks
4. Configure widget settings in plugin

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Indico Web Application                       │
│                                                                  │
│                    inject_bundle('chat_widget.js')               │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Chainlit Copilot Widget                         ││
│  │  - Self-mounts to document.body                              ││
│  │  - Floating button (bottom-right, fixed position)            ││
│  │  - Expandable chat panel                                     ││
│  │  - localStorage thread persistence                           ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ WebSocket + REST
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Chainlit Server (existing)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ app_chnlit.py│  │ LLM Service  │  │ Langfuse     │          │
│  │ @cl.on_message│ │ (Instructor) │  │ Observability│          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## Phase 0: Research

### Research Tasks

1. **Chainlit Copilot authentication**: How to pass Indico session to Chainlit as JWT
2. **CORS configuration**: Required settings for cross-origin Chainlit embedding  
3. **Indico template hooks**: Validate `global-announcement` hook availability and behavior
4. **Chainlit feedback API**: How to map Chainlit feedback to existing `/api/assistant/feedback`

### Findings

#### R1: Chainlit Authentication with JWT

Chainlit supports JWT-based authentication via `accessToken` in widget config:

```python
# Generate JWT in Indico plugin
import jwt
from datetime import datetime, timedelta

def create_chainlit_token(user):
    return jwt.encode({
        "identifier": str(user.id),
        "metadata": {
            "name": user.full_name,
            "email": user.email
        },
        "exp": datetime.utcnow() + timedelta(hours=24)
    }, CHAINLIT_AUTH_SECRET, algorithm="HS256")
```

The token is passed via `get_vars_js()` and used by the widget.

#### R2: CORS Configuration

In Chainlit's `.chainlit/config.toml`:
```toml
[project]
allow_origins = ["https://indico.example.com", "http://localhost:8000"]
```

Or via environment variable: `CHAINLIT_ALLOW_ORIGINS=https://indico.example.com`

#### R3: Template Hook Availability

Indico's `global-announcement` hook is rendered on all pages via `render_announcements()` macro. The hook accepts:
- `priority`: Integer (lower = first)
- `markup`: Boolean (True for HTML output)

Alternative: Use `inject_bundle()` with a self-contained widget that mounts to `document.body`.

**Decision**: Use `inject_bundle()` only (no template hook). The Chainlit widget self-mounts to body, so we just need to load the script and call `mountChainlitWidget()`.

#### R4: Feedback Integration

Chainlit has built-in feedback via `@cl.on_feedback`:

```python
@cl.on_feedback
def on_feedback(feedback):
    # Forward to existing feedback API
    requests.post(
        "http://localhost:8000/api/assistant/feedback",
        json={
            "message_id": feedback.forId,
            "rating": "positive" if feedback.value == 1 else "negative",
            "comment": feedback.comment
        }
    )
```

This bridges Chainlit feedback to the plugin's feedback storage.

## Phase 1: Design & Contracts

### Data Model (Client-Side State)

No new database models required. Client-side state:

| Entity | Storage | Fields |
|--------|---------|--------|
| Thread ID | localStorage (Chainlit) | `chainlit-copilot-thread-id` |
| Auth Token | sessionStorage | `indico-assistant-token` |
| Widget State | memory | `expanded: boolean` |

### API Contracts

#### Widget Configuration Endpoint (Optional)

```yaml
# contracts/widget-config.yaml
openapi: 3.0.0
paths:
  /api/assistant/widget/config:
    get:
      summary: Get widget configuration
      description: Returns Chainlit server URL and auth token for current user
      responses:
        200:
          content:
            application/json:
              schema:
                type: object
                properties:
                  enabled:
                    type: boolean
                  chainlitUrl:
                    type: string
                  accessToken:
                    type: string
                  theme:
                    type: string
                    enum: [light, dark, auto]
```

**Alternative**: Embed config directly in `get_vars_js()` to avoid extra API call.

### Settings Schema

```python
# default_settings.py additions
WIDGET_SETTINGS = {
    'chat_widget_enabled': True,
    'chainlit_server_url': 'http://localhost:8000',
    'chainlit_auth_secret': '',  # For JWT signing
}
```

## Quickstart

See [quickstart.md](./quickstart.md) after Phase 1 completion.

## Post-Design Constitution Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Official Indico Plugin Architecture | ✅ PASS | Uses `inject_bundle()` method |
| II. API-First Design | ✅ PASS | Widget config exposed via `get_vars_js()` |
| III. LLM Provider Abstraction | ✅ PASS | No changes to LLM layer |
| IV. Graceful Degradation | ✅ PASS | Widget script has try/catch; fails silently |
| V. Configuration Hierarchy | ✅ PASS | Settings in `default_settings.py` with admin form |
| VI. Test-First Development | ✅ PASS | E2E tests with Playwright |

**Post-design Gate**: ✅ PASSED

## Implementation Phases

### Phase 1: Plugin Configuration (P1 Foundation)
- Add widget settings to `default_settings.py`
- Add settings form fields to `forms.py`
- Implement `get_vars_js()` for client-side config
- Unit tests for settings validation

### Phase 2: Widget Injection (P1 Core)
- Create `chat_widget.js` with Chainlit initialization
- Register via `inject_bundle()` in `plugin.py`
- Handle authentication token generation
- Integration tests for bundle injection

### Phase 3: Chainlit Configuration (P1 Core)
- Configure CORS on Chainlit server
- Implement JWT authentication handler
- Connect feedback to existing API
- End-to-end tests with Playwright

### Phase 4: Polish & Accessibility (P3)
- Theme detection (dark/light mode)
- Keyboard shortcut support
- Screen reader announcements
- Mobile responsiveness validation

## Complexity Tracking

No constitution violations. Standard complexity within existing patterns.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Chainlit server not running | Widget shows error | Health check before mounting; graceful error UI |
| CORS misconfiguration | Widget fails to load | Detailed setup docs; health endpoint validation |
| JWT token expiry | Auth failure mid-session | Auto-refresh token; clear error message |
| Indico CSP blocks iframe | Widget blocked | Document CSP additions needed in setup guide |

## Dependencies

- Existing `indico_assistant` Chainlit app must be running
- Chainlit server must be accessible from user's browser
- CORS must be configured to allow Indico domain
- JWT secret must be shared between Indico plugin and Chainlit

## Next Steps

Run `/speckit.tasks` to generate implementation tasks from this plan.
