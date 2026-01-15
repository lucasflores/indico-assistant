# Quickstart: Plugin Foundation

**Feature**: 001-plugin-foundation  
**Date**: 2025-01-14  
**Purpose**: Validation scenarios for implementation testing

---

## Prerequisites

1. Indico 3.3+ installed and running
2. PostgreSQL database configured
3. Plugin installed via `pip install -e .` in plugin directory

---

## Scenario 1: Plugin Registration

**Goal**: Verify plugin loads and registers with Indico

### Steps

1. Install the plugin:
   ```bash
   cd indico_assistant_plugin
   pip install -e .
   ```

2. Verify plugin is listed:
   ```bash
   indico plugin list
   ```

3. Expected output includes:
   ```
   assistant    Indico Assistant    0.1.0    enabled
   ```

### Validation

- [ ] Plugin appears in `indico plugin list`
- [ ] No errors during Indico startup
- [ ] Plugin version matches pyproject.toml

---

## Scenario 2: Version Check (Fail Fast)

**Goal**: Verify plugin rejects Indico < 3.3

### Steps

1. Temporarily mock an old Indico version (test only):
   ```python
   # In test
   with patch('indico.__version__', '3.2.0'):
       with pytest.raises(RuntimeError, match='requires Indico 3.3'):
           import indico_assistant.plugin
   ```

### Validation

- [ ] RuntimeError raised with clear message
- [ ] Message includes both required and actual version

---

## Scenario 3: Health Endpoint

**Goal**: Verify health check returns correct status

### Steps

1. Start Indico with plugin enabled

2. Call health endpoint:
   ```bash
   curl http://localhost:8000/api/assistant/health
   ```

3. Expected response (healthy):
   ```json
   {
     "status": "healthy",
     "plugin_version": "0.1.0",
     "indico_version": "3.3.0",
     "llm_status": "connected",
     "settings_valid": true,
     "timestamp": "2025-01-14T12:00:00Z"
   }
   ```

4. Stop LLM service (e.g., Ollama), call again:
   ```bash
   curl http://localhost:8000/api/assistant/health
   ```

5. Expected response (degraded):
   ```json
   {
     "status": "degraded",
     "plugin_version": "0.1.0",
     "indico_version": "3.3.0",
     "llm_status": "unavailable",
     "settings_valid": true,
     "timestamp": "2025-01-14T12:00:00Z"
   }
   ```

### Validation

- [ ] Endpoint responds at `/api/assistant/health`
- [ ] Returns `healthy` when LLM available
- [ ] Returns `degraded` when LLM unavailable (not error!)
- [ ] Response matches OpenAPI schema
- [ ] No authentication required

---

## Scenario 4: Global Settings Form

**Goal**: Verify admin can configure plugin settings

### Steps

1. Log in to Indico as admin

2. Navigate to: Admin → Plugins → Assistant → Settings

3. Verify form fields present:
   - [x] Enable Assistant (checkbox)
   - [x] LLM Provider (dropdown: ollama, huggingface, openai)
   - [x] LLM Model (text input)
   - [x] LLM Base URL (text input)
   - [x] API Key (password field, masked)
   - [x] Timeout (number input)
   - [x] Max Tokens (number input)

4. Change settings and save

5. Verify settings persisted (reload page)

### Validation

- [ ] Settings form renders without errors
- [ ] All fields display current values
- [ ] Password field is masked
- [ ] Save persists changes
- [ ] Invalid values show validation errors

---

## Scenario 5: Per-Event Settings

**Goal**: Verify event managers can override settings

### Steps

1. Create or navigate to an existing event

2. As event manager, go to: Event → Management → Assistant Settings

3. Verify form fields present:
   - [x] Enable for this event (checkbox, tri-state: inherit/yes/no)
   - [x] Custom system prompt (textarea)

4. Save with "Enable" unchecked (inherit global)

5. Verify in code that `event_settings.get(event, 'enabled')` returns `None`

6. Check "Enable" and save

7. Verify `event_settings.get(event, 'enabled')` returns `True`

### Validation

- [ ] Event settings form accessible to event managers
- [ ] Inherit option works (null stored, global used)
- [ ] Override option works (explicit value stored)
- [ ] Settings isolated per event

---

## Scenario 6: Graceful Degradation

**Goal**: Verify plugin loads without LLM

### Steps

1. Stop LLM service (e.g., `systemctl stop ollama`)

2. Restart Indico:
   ```bash
   indico run
   ```

3. Verify Indico starts successfully

4. Verify plugin is loaded:
   ```bash
   indico plugin list
   ```

5. Verify health reports degraded (not error):
   ```bash
   curl http://localhost:8000/api/assistant/health
   # Should return {"status": "degraded", ...}
   ```

### Validation

- [ ] Indico starts even with LLM unavailable
- [ ] No exception during plugin initialization
- [ ] Health endpoint returns degraded status
- [ ] Settings UI still accessible

---

## Scenario 7: CLI Commands

**Goal**: Verify CLI commands work

### Steps

1. Check plugin health via CLI:
   ```bash
   indico assistant health
   ```
   Expected output:
   ```
   Plugin Status: healthy
   Version: 0.1.0
   LLM: connected (ollama @ http://localhost:11434)
   ```

2. Show current config:
   ```bash
   indico assistant config
   ```
   Expected output:
   ```
   LLM Provider: ollama
   LLM Model: llama3.2
   Base URL: http://localhost:11434
   Enabled: true
   ```

### Validation

- [ ] `indico assistant health` returns status
- [ ] `indico assistant config` shows current settings
- [ ] Commands work without web server running

---

## Scenario 8: Settings Validation

**Goal**: Verify invalid settings are rejected

### Steps

1. Via admin UI, try to save:
   - Empty LLM Model → Should error
   - Timeout = 0 → Should error
   - Timeout = 999 → Should error (max 300)
   - Max Tokens = 50 → Should error (min 100)
   - Invalid URL format → Should error

### Validation

- [ ] Validation errors shown in UI
- [ ] Invalid values not persisted
- [ ] Error messages are user-friendly

---

## Test Coverage Targets

| Component | Target | Type |
|-----------|--------|------|
| `plugin.py` | 80% | Unit |
| `forms.py` | 80% | Unit |
| `controllers.py` | 80% | Unit |
| Health endpoint | 100% | Integration |
| Settings flow | 80% | Integration |
| API contract | 100% | Contract |

---

## Quick Test Commands

```bash
# Run all tests
pytest tests/

# Run unit tests only
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run with coverage
pytest --cov=indico_assistant --cov-report=html tests/

# Run contract tests
pytest tests/contract/
```
