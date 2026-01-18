# Indico Assistant Plugin

AI-powered assistant plugin for [Indico](https://getindico.io/) - the open-source event management system.

## Features

- **Natural Language Queries**: Ask questions about event data using natural language
- **Multiple LLM Providers**: Support for Ollama (local), HuggingFace Router, and OpenAI-compatible APIs
- **Per-Event Configuration**: Customize assistant behavior for specific events
- **Health Monitoring**: Built-in health check endpoint for monitoring
- **CLI Tools**: Command-line interface for administration and diagnostics
- **Embedded Chat Widget**: Chainlit Copilot widget injected on every page with JWT auth, theme sync, persistence, and feedback

## Requirements

- **Indico 3.3+**
- **Python 3.11+**
- **PostgreSQL** (Indico's default database)

## Installation

```bash
pip install indico-plugin-assistant
```

Or for development:

```bash
git clone https://github.com/your-org/indico-plugin-assistant.git
cd indico-plugin-assistant
pip install -e ".[dev]"
```

## Configuration

### Global Settings

1. Log in to Indico as an administrator
2. Navigate to **Admin → Plugins → Assistant → Settings**
3. Configure the following:

| Setting | Description | Default |
|---------|-------------|---------|
| Enable Assistant | Master switch for the plugin | Enabled |
| LLM Provider | Select your LLM provider | Ollama |
| LLM Model | Model name/identifier | llama3.2 |
| LLM Base URL | API endpoint URL | http://localhost:11434 |
| API Key | Authentication key (for cloud providers) | - |
| Timeout | Request timeout in seconds | 30 |
| Max Tokens | Maximum response tokens | 2048 |

### Chat Widget Settings

Configured in **Admin → Plugins → Assistant → Settings** (must match Chainlit server):

| Setting | Description | Default |
|---------|-------------|---------|
| Chat Widget Enabled | Master switch for widget injection | False |
| Chainlit Server URL | Base URL of the Chainlit app | http://localhost:8000 |
| Chainlit Auth Secret | Shared HS256 secret for JWT auth | (blank) |

Widget behavior:
- JWT issued per user via `get_vars_js()` and validated by Chainlit header_auth_callback
- Theme auto-detected from Indico CSS vars / media queries; overrides via `IndicoAssistant.theme`
- Session continuity via Chainlit threadId; feedback bridged to Indico API
- Graceful degradation: loading/error bubble, hidden when not ready, `noscript` fallback available (see docs/DEPLOYMENT.md)

### Per-Event Settings

Event managers can override global settings for specific events:

1. Navigate to **Event → Management → Assistant Settings**
2. Configure:
   - **Enable/Disable** for this event
   - **Custom System Prompt** for event-specific context
   - **Allowed Tables** to restrict data access

## API Endpoints

### Health Check

```bash
GET /api/assistant/health
```

Returns the health status of the plugin:

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

Status values:
- `healthy`: All services operational
- `degraded`: Plugin functional but LLM unavailable
- `unhealthy`: Plugin disabled or critical error

## NL2SQL Pipeline

The NL2SQL pipeline allows users to ask natural language questions about event data:

### Basic Usage

```python
from indico_assistant.services import NL2SQLPipeline, create_nl2sql_pipeline

# In a request handler
pipeline = create_nl2sql_pipeline(plugin)
result = pipeline.process(
    question="How many events are there this week?",
    user_id=current_user.id,
)

if result.success:
    print(result.answer)  # "There are 12 events this week..."
else:
    print(result.error.user_message)  # "I couldn't understand..."
```

### Supported Questions

| Question Type | Example |
|--------------|---------|
| Event counts | "How many events are there this month?" |
| Event lists | "Show me all workshops next week" |
| Registrations | "Who registered for the physics conference?" |
| Contributions | "List talks in the parallel sessions" |
| Speakers | "Who are the speakers at tomorrow's event?" |

### Security Features

- **SELECT-only queries**: No data modification allowed
- **Table allowlist**: Only approved tables can be queried
- **Permission filtering**: Results filtered by user access
- **Query timeout**: 30-second default timeout
- **Row limit**: Maximum 1000 rows per query

### Pipeline Result

```python
result = pipeline.process(question="...", user_id=user_id)

# Success response
result.success        # True
result.answer         # Natural language answer
result.generated_sql  # SQL query (for debugging)
result.row_count      # Number of results
result.total_time_ms  # Processing time

# Error response
result.success                  # False
result.error.user_message       # User-friendly error
result.error.error_type         # Error classification
result.error.message            # Internal error (for logging)
```

## CLI Commands

```bash
# Check plugin health
indico assistant health

# Show current configuration (secrets masked)
indico assistant config

# Show configuration with secrets visible
indico assistant config --show-secrets
```

## Development

### Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with development dependencies
pip install -e ".[dev]"
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=indico_assistant --cov-report=html

# Run specific test types
pytest tests/unit/
pytest tests/integration/
pytest tests/contract/
```

### Code Quality

```bash
# Linting
ruff check .

# Formatting
black .

# Type checking
mypy indico_assistant
```

## Architecture

```
indico_assistant/
├── __init__.py         # Package init, version check
├── plugin.py           # AssistantPlugin (IndicoPlugin subclass)
├── blueprint.py        # URL routing
├── controllers.py      # Request handlers
├── forms.py            # Settings forms
├── cli.py              # CLI commands
├── default_settings.py # Default configuration
└── version.py          # Version utilities
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.
