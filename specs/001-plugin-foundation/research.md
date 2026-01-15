# Research: Plugin Foundation

**Feature**: 001-plugin-foundation  
**Date**: 2025-01-14  
**Status**: ✅ Complete

---

## 1. Indico Plugin Architecture

### Decision: Subclass `IndicoPlugin` with `IndicoPluginBlueprint`

### Rationale

Indico plugins must subclass `IndicoPlugin` from `indico.core.plugins`. This provides:
- Automatic settings management via `settings_form` property
- Event settings via `event_settings` property  
- Signal connection for extending Indico behavior
- Blueprint registration for HTTP endpoints
- CLI command registration

### Implementation Pattern

```python
from indico.core.plugins import IndicoPlugin, IndicoPluginBlueprint

class AssistantPlugin(IndicoPlugin):
    """Indico Assistant Plugin - AI-powered assistant for events."""
    
    configurable = True  # Show in admin settings
    
    default_settings = {
        'llm_provider': 'ollama',
        'llm_model': 'llama3.2',
        'llm_base_url': 'http://localhost:11434',
        'enabled': True,
    }
    
    settings_form = SettingsForm  # WTForms form class
    
    def init(self):
        super().init()
        self.connect(signals.plugin.cli, self._extend_cli)
```

### Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Flask Blueprint only | Would not integrate with Indico's plugin system, no settings UI |
| Direct Flask app | Indico controls the WSGI app, cannot run standalone |
| Celery-only worker | Need HTTP endpoints for health checks and API |

---

## 2. Secure Settings Storage

### Decision: Use Indico's built-in settings mechanism (no custom encryption)

### Rationale

From clarification response: "A: Use Indico's built-in secure settings storage mechanism"

Indico stores plugin settings in the database via its own mechanism. For API keys and sensitive values:
- Use `PasswordField` in WTForms (masks input, stores as-is)
- Indico does not encrypt settings by default, but they're server-side only
- Production deployments typically use environment variables for secrets

The `settings` property on IndicoPlugin provides dict-like access to persisted values.

### Implementation Pattern

```python
from wtforms.fields import StringField, PasswordField, BooleanField
from indico.web.forms.base import IndicoForm

class SettingsForm(IndicoForm):
    enabled = BooleanField('Enable Assistant')
    llm_provider = StringField('LLM Provider')
    llm_api_key = PasswordField('API Key')  # Masked in UI
    llm_base_url = StringField('LLM Base URL')
```

Access in code:
```python
api_key = self.settings.get('llm_api_key')
```

### Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Custom Fernet encryption | Added complexity, Indico doesn't do this for other plugins |
| Environment variables only | Less flexible, can't change via admin UI |
| Separate secrets store | Over-engineering for plugin scope |

---

## 3. Per-Event Settings

### Decision: Use Indico's `event_settings` plugin property

### Rationale

From clarification response: "B1: Yes - use Indico's standard event_settings plugin property"

Indico plugins can override global settings per-event using the `event_settings` property:

```python
class AssistantPlugin(IndicoPlugin):
    event_settings_schema = {
        'enabled': None,  # None = inherit from global
        'custom_prompt': None,
    }
    
    # event_settings automatically provided by IndicoPlugin
```

Access per-event settings:
```python
# In a request handler with event context
enabled = self.plugin.event_settings.get(event, 'enabled')
if enabled is None:
    enabled = self.plugin.settings.get('enabled')  # Fall back to global
```

### Implementation Pattern

```python
class EventSettingsForm(IndicoForm):
    enabled = BooleanField('Enable for this event', 
                           description='Leave unchecked to inherit global setting')
    custom_prompt = TextAreaField('Custom system prompt')
```

Registration in plugin:
```python
def init(self):
    super().init()
    self.connect(signals.event_management.sidemenu, self._extend_event_menu)
```

---

## 4. Indico Version Checking

### Decision: Check version at import time, fail fast with clear error

### Rationale

From clarification response: "C: Yes - target Indico 3.3+ only. Plugin should fail fast with clear error message on older versions."

Use `packaging.version` to compare versions at module import:

```python
from packaging.version import Version
import indico

MINIMUM_INDICO_VERSION = '3.3'

def check_indico_version():
    current = Version(indico.__version__)
    minimum = Version(MINIMUM_INDICO_VERSION)
    
    if current < minimum:
        raise RuntimeError(
            f"Indico Assistant requires Indico {MINIMUM_INDICO_VERSION}+, "
            f"but found {indico.__version__}"
        )
```

Call in `plugin.py` before plugin class definition.

### Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Warn and continue | Could cause subtle bugs with missing APIs |
| Feature detection | More complex, version check is cleaner |
| Only check in pyproject.toml | pip doesn't always enforce, runtime check safer |

---

## 5. Graceful Degradation

### Decision: Plugin loads without LLM; health endpoint reports degraded status

### Rationale

FR-002: "Plugin MUST load successfully even when LLM services are unavailable"

The plugin should:
1. Not attempt LLM connection at load time
2. Defer LLM client initialization to first use
3. Report status via health endpoint

### Implementation Pattern

```python
class AssistantPlugin(IndicoPlugin):
    def init(self):
        super().init()
        self._llm_client = None  # Lazy initialization
    
    @property
    def llm_client(self):
        if self._llm_client is None:
            self._llm_client = self._create_llm_client()
        return self._llm_client
    
    def _create_llm_client(self):
        try:
            return LLMClient(self.settings)
        except Exception:
            return None  # Degraded mode
```

Health endpoint returns:
```json
{
  "status": "degraded",
  "plugin_version": "0.1.0",
  "indico_version": "3.3.0",
  "llm_status": "unavailable",
  "timestamp": "2025-01-14T12:00:00Z"
}
```

---

## 6. Blueprint and Controller Pattern

### Decision: Use RH (Request Handler) classes per Indico convention

### Rationale

Indico uses a custom request handler pattern (`RH` classes) rather than plain Flask view functions:

```python
from indico.web.rh import RH

class RHHealth(RH):
    """Health check endpoint - no authentication required."""
    
    def _process(self):
        from flask import jsonify
        return jsonify({
            'status': 'healthy',
            'plugin_version': '0.1.0',
        })
```

Blueprint setup:
```python
from indico.core.plugins import IndicoPluginBlueprint

blueprint = IndicoPluginBlueprint(
    'assistant', 
    __name__,
    url_prefix='/api/assistant'
)

blueprint.add_url_rule('/health', 'health', RHHealth, methods=['GET'])
```

---

## Summary of Decisions

| Topic | Decision |
|-------|----------|
| Plugin base class | `IndicoPlugin` with `IndicoPluginBlueprint` |
| Settings storage | Indico's built-in mechanism, no custom encryption |
| Event settings | `event_settings` property with inheritance |
| Version check | Fail fast at import for Indico < 3.3 |
| Graceful degradation | Lazy LLM init, degraded status in health |
| Request handlers | RH classes per Indico convention |
