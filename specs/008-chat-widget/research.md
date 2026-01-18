# Research: Chat Widget for Indico Assistant

**Feature**: 008-chat-widget  
**Date**: 2026-01-17

## Research Questions

### R1: Chainlit Copilot Widget Integration

**Question**: How can we embed Chainlit's Copilot widget into Indico pages?

**Decision**: Use Chainlit's official Copilot widget via script injection

**Rationale**: Chainlit provides a production-ready embeddable widget with:
- Floating button that expands to chat panel
- Built-in message history and thread persistence
- Markdown rendering
- Mobile responsive design
- Accessibility features
- Feedback collection

**Alternatives Considered**:
| Alternative | Why Rejected |
|-------------|--------------|
| Custom vanilla JS widget | 3-4 weeks implementation, maintenance burden |
| React-based custom widget | Adds heavy dependencies, conflicts with Indico |
| iframe with custom page | Poor UX, no native feel |

**Integration Code**:
```html
<script src="http://chainlit-server:8000/copilot/index.js"></script>
<script>
  window.mountChainlitWidget({
    chainlitServer: "http://chainlit-server:8000",
    accessToken: "jwt-token-here",
    theme: "light"
  });
</script>
```

---

### R2: Authentication Token Handoff

**Question**: How to authenticate Indico users with the Chainlit server?

**Decision**: Generate JWT tokens in Indico plugin, pass to Chainlit widget

**Rationale**: Chainlit supports JWT-based authentication. The Indico plugin can generate tokens containing user identity, which Chainlit validates using a shared secret.

**Implementation**:
```python
# In Indico plugin
import jwt
from datetime import datetime, timedelta

def create_chainlit_token(user, secret):
    return jwt.encode({
        "identifier": str(user.id),
        "metadata": {
            "name": user.full_name,
            "email": user.email
        },
        "exp": datetime.utcnow() + timedelta(hours=24)
    }, secret, algorithm="HS256")
```

The secret is shared via plugin settings and Chainlit's `CHAINLIT_AUTH_SECRET` env var.

---

### R3: CORS Configuration

**Question**: What CORS settings are needed for cross-origin embedding?

**Decision**: Configure Chainlit's `allow_origins` to include Indico domain

**Rationale**: The Chainlit widget makes requests from the Indico page to the Chainlit server, requiring CORS headers.

**Configuration** (`.chainlit/config.toml`):
```toml
[project]
allow_origins = ["https://indico.example.com"]
```

**Environment Variable Alternative**:
```bash
CHAINLIT_ALLOW_ORIGINS=https://indico.example.com
```

**Cookie Considerations**: If Indico and Chainlit are on different domains:
```bash
CHAINLIT_COOKIE_SAMESITE=none
```

---

### R4: Indico Plugin Asset Injection

**Question**: How to inject the widget script into Indico pages?

**Decision**: Use `IndicoPlugin.inject_bundle()` method

**Rationale**: This is the official Indico plugin pattern for injecting JavaScript into pages. The Chainlit widget self-mounts to `document.body`, so no template hook is needed for the UI.

**Implementation**:
```python
class AssistantPlugin(IndicoPlugin):
    def init(self):
        super().init()
        # Inject widget script on all pages
        self.inject_bundle('chat_widget.js')
    
    def get_vars_js(self):
        """Expose config to JavaScript as IndicoAssistant.*"""
        from flask_login import current_user
        return {
            'enabled': self.settings.get('chat_widget_enabled'),
            'chainlitUrl': self.settings.get('chainlit_server_url'),
            'authToken': self._get_auth_token(current_user) if current_user.is_authenticated else None
        }
```

---

### R5: Feedback Integration

**Question**: How to bridge Chainlit's feedback to existing feedback API?

**Decision**: Use Chainlit's `@cl.on_feedback` decorator to forward to plugin API

**Rationale**: Chainlit has built-in feedback buttons. We can capture feedback events and forward them to the existing `/api/assistant/feedback` endpoint for unified storage.

**Implementation** (in `app_chnlit.py`):
```python
import chainlit as cl
import httpx

@cl.on_feedback
async def on_feedback(feedback: cl.Feedback):
    """Forward Chainlit feedback to Indico plugin API."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{INDICO_URL}/api/assistant/feedback",
            json={
                "message_id": feedback.forId,
                "rating": "positive" if feedback.value == 1 else "negative",
                "comment": feedback.comment
            },
            headers={"Authorization": f"Bearer {get_service_token()}"}
        )
```

---

### R6: Thread Persistence

**Question**: How is chat history persisted across page navigations?

**Decision**: Use Chainlit's built-in localStorage thread persistence

**Rationale**: Chainlit Copilot automatically stores `threadId` in localStorage, enabling:
- Chat restoration after page reload
- Session continuity across Indico page navigations
- `getChainlitCopilotThreadId()` and `clearChainlitCopilotThreadId()` for programmatic control

**No additional implementation needed** - this is handled by the Chainlit widget automatically.

---

## Summary

| Question | Decision | Complexity |
|----------|----------|------------|
| Widget UI | Chainlit Copilot | Low |
| Authentication | JWT token handoff | Medium |
| CORS | Configure allow_origins | Low |
| Asset injection | inject_bundle() | Low |
| Feedback | Forward via @cl.on_feedback | Medium |
| Thread persistence | Chainlit built-in | None |

**Total estimated complexity**: Low-Medium (leveraging existing Chainlit infrastructure)

---

## Implementation Findings

- Shadow DOM styling remains unresolved: custom overrides in `public/widget.css`, `.chainlit/config.toml` `custom_css`, and icon/background tweaks do not pierce the Copilot shadow root. A follow-up is needed (either upstream hook or inline injection) to apply Indico palette/opacity.
- Auth flow is scaffolded (JWT header callback in Chainlit, token issuance in plugin service) but not fully exercised end-to-end with the widget embedded in Indico.
- Theme assets (icon, theme.json) are present; effective visual integration still blocked by the shadow DOM limitation above.
