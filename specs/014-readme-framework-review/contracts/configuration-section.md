# Contract: Configuration Section

## Section Requirements

**Location**: After Installation section  
**Purpose**: Document all configurable settings with accurate defaults  
**Format**: Three subsections with tables

## Content Structure

### Main Header
```markdown
## Configuration
```

### Intro Paragraph
Brief explanation that settings are configured via Indico admin interface with three levels: global, chat widget, and per-event.

---

### Subsection 1: Global Settings

```markdown
### Global Settings

1. Log in to Indico as an administrator
2. Navigate to **Admin → Plugins → Assistant → Settings**
3. Configure the following:

| Setting | Description | Default |
|---------|-------------|---------|
| Enable Assistant | Master switch for the plugin | Enabled |
| LLM Provider | Select your LLM provider (Ollama, HuggingFace, OpenAI-compatible) | Ollama |
| LLM Model | Model name/identifier | llama3.2 |
| LLM Base URL | API endpoint URL | http://localhost:11434 |
| API Key | Authentication key (for cloud providers) | - |
| Timeout | Request timeout in seconds | 30 |
| Max Tokens | Maximum response tokens | 2048 |
```

**Verification**: All values MUST match `indico_assistant/default_settings.py` → `DEFAULT_SETTINGS` dictionary

---

### Subsection 2: Chat Widget Settings

```markdown
### Chat Widget Settings

Configured in **Admin → Plugins → Assistant → Settings** (must match Chainlit server):

| Setting | Description | Default |
|---------|-------------|---------|
| Chat Widget Enabled | Master switch for widget injection | False |
| Chainlit Server URL | Base URL of the Chainlit app | http://localhost:8000 |
| Chainlit Auth Secret | Shared HS256 secret for JWT auth | (blank) |

**Widget behavior**:
- JWT issued per user via `get_vars_js()` and validated by Chainlit header_auth_callback
- Theme auto-detected from Indico CSS vars / media queries; overrides via `IndicoAssistant.theme`
- Session continuity via Chainlit threadId; feedback bridged to Indico API
- Graceful degradation: loading/error bubble, hidden when not ready

See [Deployment Guide](docs/DEPLOYMENT.md) for complete setup instructions.
```

**Verification**: 
- Settings match `default_settings.py`
- Behavior description matches actual implementation in widget JavaScript
- Link to DEPLOYMENT.md is valid

---

### Subsection 3: Per-Event Settings

```markdown
### Per-Event Settings

Event managers can override global settings for specific events:

1. Navigate to **Event → Management → Assistant Settings**
2. Configure:
   - **Enable/Disable** for this event
   - **Custom System Prompt** for event-specific context
   - **Allowed Tables** to restrict data access

These settings override global defaults when configured.
```

**Verification**: 
- Navigation path is correct
- Setting names match `default_settings.py` → `EVENT_SETTINGS_DEFAULTS`
- Override behavior accurately described

---

## Additional Subsections (if observability/vector search settings exist)

### Observability Settings (if applicable)
```markdown
### Observability Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Langfuse Enabled | Enable Langfuse tracing | False |
| Langfuse Public Key | Langfuse project public key | (blank) |
| Langfuse Secret Key | Langfuse project secret key | (blank) |
| Langfuse Host | Langfuse API endpoint | https://cloud.langfuse.com |

See [Langfuse Setup](docs/LANGFUSE_SETUP.md) for configuration details.
```

### Vector Search Settings (if applicable)
```markdown
### Vector Search Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Vector Search Enabled | Enable semantic document search | False |
| Embedding Model | Sentence-transformers model name | all-MiniLM-L6-v2 |
| Chunk Size | Document chunk size (characters) | 1000 |
| Chunk Overlap | Overlap between chunks (characters) | 200 |

See [Vector Search Setup](docs/VECTOR_SEARCH_SETUP.md) for pgvector installation and index creation.
```

---

## Content Requirements

1. **Navigation paths MUST be accurate**: Test in actual Indico admin interface
2. **Default values MUST match code**: Cross-reference with `default_settings.py`
3. **Setting descriptions MUST be user-friendly**: Avoid technical jargon where possible
4. **Table format**: Markdown tables with three columns (Setting | Description | Default)
5. **Links to detailed docs**: Where complexity warrants separate guide

## Verification Checklist

- [ ] All settings from `default_settings.py` included
- [ ] Default values are accurate (not placeholders)
- [ ] Navigation paths tested in Indico admin UI
- [ ] Table formatting correct (renders properly in preview)
- [ ] Links to external docs are valid
- [ ] Sensitive data (secrets) marked as "(blank)" not exposed
- [ ] Widget behavior notes accurate (JWT, theme, session)

## Success Criteria

- Administrator can configure plugin without external help
- All defaults match actual code
- Navigation instructions lead to correct UI screens
- Cross-references to detailed guides provide next steps
