# Data Model: Plugin Foundation

**Feature**: 001-plugin-foundation  
**Date**: 2025-01-14  
**Status**: ✅ Complete

---

## Overview

The Plugin Foundation feature uses Indico's built-in settings storage mechanism rather than custom database tables. This document defines the logical data model for plugin settings.

---

## 1. Global Plugin Settings

**Storage**: Indico's plugin settings table (managed by framework)  
**Access**: `plugin.settings.get(key)` / `plugin.settings.set(key, value)`

### Schema

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `enabled` | boolean | `true` | Yes | Master enable/disable for plugin |
| `llm_provider` | string | `"ollama"` | Yes | LLM provider identifier |
| `llm_model` | string | `"llama3.2"` | Yes | Model name/identifier |
| `llm_base_url` | string | `"http://localhost:11434"` | No | Base URL for LLM API |
| `llm_api_key` | string | `null` | No | API key for cloud providers |
| `timeout_seconds` | integer | `30` | Yes | Request timeout for LLM calls |
| `max_tokens` | integer | `2048` | Yes | Maximum response tokens |

### Validation Rules

```yaml
enabled:
  type: boolean
  
llm_provider:
  type: string
  enum: ["ollama", "huggingface", "openai"]
  
llm_model:
  type: string
  min_length: 1
  max_length: 100
  
llm_base_url:
  type: string
  format: uri
  nullable: true
  
llm_api_key:
  type: string
  nullable: true
  sensitive: true  # Masked in UI
  
timeout_seconds:
  type: integer
  minimum: 5
  maximum: 300
  
max_tokens:
  type: integer
  minimum: 100
  maximum: 32000
```

---

## 2. Per-Event Settings

**Storage**: Indico's event settings table (managed by framework)  
**Access**: `plugin.event_settings.get(event, key)` / `plugin.event_settings.set(event, key, value)`

### Schema

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `enabled` | boolean | `null` | No | Override global enable (null = inherit) |
| `custom_system_prompt` | string | `null` | No | Custom prompt for this event |
| `allowed_tables` | array[string] | `null` | No | Restrict queryable tables |

### Inheritance Behavior

```python
def get_effective_setting(plugin, event, key):
    """Get setting with event → global fallback."""
    event_value = plugin.event_settings.get(event, key)
    if event_value is not None:
        return event_value
    return plugin.settings.get(key)
```

### Validation Rules

```yaml
enabled:
  type: boolean
  nullable: true  # null means inherit from global
  
custom_system_prompt:
  type: string
  nullable: true
  max_length: 10000
  
allowed_tables:
  type: array
  items:
    type: string
  nullable: true  # null means all tables allowed
```

---

## 3. Health Status (Runtime, Not Persisted)

**Storage**: None (computed at request time)  
**Access**: GET `/api/assistant/health`

### Schema

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | One of: `healthy`, `degraded`, `unhealthy` |
| `plugin_version` | string | Plugin version (e.g., `0.1.0`) |
| `indico_version` | string | Indico version (e.g., `3.3.0`) |
| `llm_status` | string | One of: `connected`, `unavailable`, `not_configured` |
| `settings_valid` | boolean | Whether current settings pass validation |
| `timestamp` | string | ISO 8601 timestamp |
| `details` | object | Additional diagnostic info (optional) |

### Status Determination

```python
def determine_health_status(plugin) -> str:
    if not plugin.settings.get('enabled'):
        return 'unhealthy'  # Disabled by admin
    
    llm_status = check_llm_connectivity(plugin)
    if llm_status != 'connected':
        return 'degraded'  # LLM unavailable but plugin works
    
    return 'healthy'
```

---

## Entity Relationship Diagram

```text
┌─────────────────────────────────────────────────────────────┐
│                    Indico Core                              │
│  ┌─────────────────┐      ┌─────────────────────────────┐   │
│  │ Plugin Settings │      │ Event Settings              │   │
│  │ (plugin_id, key,│      │ (plugin_id, event_id, key,  │   │
│  │  value)         │      │  value)                     │   │
│  └────────┬────────┘      └──────────────┬──────────────┘   │
│           │                              │                   │
└───────────│──────────────────────────────│───────────────────┘
            │                              │
            ▼                              ▼
┌───────────────────────────────────────────────────────────────┐
│                    AssistantPlugin                            │
│  ┌─────────────────────────┐   ┌────────────────────────────┐ │
│  │ plugin.settings         │   │ plugin.event_settings      │ │
│  │ (dict-like interface)   │   │ (event-scoped interface)   │ │
│  │                         │   │                            │ │
│  │ • enabled               │   │ • enabled (nullable)       │ │
│  │ • llm_provider          │   │ • custom_system_prompt     │ │
│  │ • llm_model             │   │ • allowed_tables           │ │
│  │ • llm_base_url          │   │                            │ │
│  │ • llm_api_key           │   │ Inherits from global if    │ │
│  │ • timeout_seconds       │   │ value is null              │ │
│  │ • max_tokens            │   │                            │ │
│  └─────────────────────────┘   └────────────────────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Health Status (computed)                                │  │
│  │ • status: healthy | degraded | unhealthy               │  │
│  │ • plugin_version, indico_version                        │  │
│  │ • llm_status, settings_valid, timestamp                 │  │
│  └─────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

---

## Default Values Configuration

To be defined in `indico_assistant/default_settings.py`:

```python
DEFAULT_SETTINGS = {
    'enabled': True,
    'llm_provider': 'ollama',
    'llm_model': 'llama3.2',
    'llm_base_url': 'http://localhost:11434',
    'llm_api_key': None,
    'timeout_seconds': 30,
    'max_tokens': 2048,
}

EVENT_SETTINGS_DEFAULTS = {
    'enabled': None,  # Inherit from global
    'custom_system_prompt': None,
    'allowed_tables': None,  # All tables allowed
}
```

---

## Migration Notes

This feature creates **no custom database tables**. All settings are stored via Indico's built-in plugin settings mechanism, which handles schema migrations automatically.

Future features (002-database-schema) will introduce custom tables in the `plugin_assistant` schema.
