# Indico Assistant Plugin

**Version**: 0.1.0 | **Last Updated**: January 20, 2026

AI-powered assistant plugin for [Indico](https://getindico.io/) - the open-source event management system.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Global Settings](#global-settings)
  - [Chat Widget Settings](#chat-widget-settings)
  - [Per-Event Settings](#per-event-settings)
- [NL2SQL Pipeline](#nl2sql-pipeline)
- [API Endpoints](#api-endpoints)
- [CLI Commands](#cli-commands)
- [Development](#development)
- [Architecture](#architecture)
- [Security](#security)
- [Documentation](#documentation)
- [License](#license)

## Features

### Core Capabilities

- **Natural Language Queries**: Ask questions about event data using natural language
- **Conversation History**: Multi-turn conversations with context awareness - ask follow-up questions using pronouns ("the first one", "that meeting") and contextual references
- **NL2SQL Pipeline**: Translates natural language to SQL with validation, permission filtering, and security constraints

### LLM Integration

- **Multiple LLM Providers**: Support for Ollama (local), HuggingFace Router, and OpenAI-compatible APIs
- **Structured Outputs**: All LLM responses validated via Pydantic models with automatic retry logic
- **Provider Abstraction**: Swap LLM providers via configuration without code changes

### Document Intelligence

- **Vector Search RAG**: Semantic search across documents using pgvector and sentence-transformers embeddings. See [Vector Search Setup](docs/VECTOR_SEARCH_SETUP.md)
- **Real-time Document Indexing**: Automatically indexes PDF, DOCX, DOC, TXT, and Markdown files when uploaded as attachments, making them immediately searchable
  - Immediate Search: Documents become searchable within seconds of upload
  - Duplicate Detection: Skips re-indexing identical documents based on content hash
  - Graceful Degradation: Continues working even when vector search is unavailable
  - File Size Tiers: Fast indexing (<10MB), best-effort (10-50MB), automatic rejection (>50MB)
  - Supported Formats: PDF, DOCX, DOC, TXT, MD (silently ignores images, videos, archives)

### User Interface

- **Embedded Chat Widget**: Chainlit Copilot widget injected on every page with JWT auth, theme sync, persistence, and feedback. See [Deployment Guide](docs/DEPLOYMENT.md)
  - JWT Authentication: Secure token-based auth per user
  - Theme Synchronization: Auto-detects Indico theme and applies matching styles
  - Session Persistence: Conversations persist across page reloads
  - Feedback Mechanism: Thumbs up/down with optional comments
  - Graceful Degradation: Loading/error states, hidden when not ready

### Configuration & Management

- **Per-Event Configuration**: Customize assistant behavior for specific events
- **Health Monitoring**: Built-in health check endpoint for monitoring
- **CLI Tools**: Command-line interface for administration and diagnostics

### Observability & Quality

- **Langfuse Observability**: Integrated tracing and monitoring for all LLM interactions with privacy filters. See [Langfuse Setup](docs/LANGFUSE_SETUP.md)
- **Test Coverage**: Comprehensive unit, integration, and contract tests (80%+ coverage on services)

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
| Enable Assistant | Master switch for the plugin | True |
| LLM Provider | Select your LLM provider (Ollama, HuggingFace, OpenAI-compatible) | ollama |
| LLM Model | Model name/identifier | llama3.2 |
| LLM Base URL | API endpoint URL | http://localhost:11434 |
| API Key | Authentication key (for cloud providers) | None |
| Timeout | Request timeout in seconds | 30 |
| Max Tokens | Maximum response tokens | 2048 |

### Chat Widget Settings

Configured in **Admin → Plugins → Assistant → Settings** (must match Chainlit server):

| Setting | Description | Default |
|---------|-------------|---------|
| Chat Widget Enabled | Master switch for widget injection | True |
| Chainlit Server URL | Base URL of the Chainlit app | http://localhost:8000 |
| Chainlit Auth Secret | Shared HS256 secret for JWT auth | (blank) |

Widget behavior:
- JWT issued per user via `get_vars_js()` and validated by Chainlit header_auth_callback
- Theme auto-detected from Indico CSS vars / media queries; overrides via `IndicoAssistant.theme`
- Session continuity via Chainlit threadId; feedback bridged to Indico API
- Graceful degradation: loading/error bubble, hidden when not ready

See [Deployment Guide](docs/DEPLOYMENT.md) for complete setup instructions.

### Per-Event Settings

Event managers can override global settings for specific events:

1. Navigate to **Event → Management → Assistant Settings**
2. Configure:
   - **Enable/Disable** for this event
   - **Custom System Prompt** for event-specific context
   - **Allowed Tables** to restrict data access

These settings override global defaults when configured.

### Observability Settings

Configure Langfuse observability for tracing LLM interactions:

| Setting | Description | Default |
|---------|-------------|---------|
| Langfuse Enabled | Enable Langfuse tracing | False |
| Langfuse Host | Langfuse API endpoint | https://cloud.langfuse.com |
| Langfuse Public Key | Public API key | None |
| Langfuse Secret Key | Secret API key | None |
| Privacy Level | Data privacy level (metadata, masked, full) | metadata |

See [Langfuse Setup](docs/LANGFUSE_SETUP.md) for detailed configuration instructions.

### Vector Search Settings

Configure vector search for document intelligence:

| Setting | Description | Default |
|---------|-------------|---------|
| Vector Search Enabled | Enable semantic document search | True |
| Embedding Model | Sentence transformer model | BAAI/bge-small-en-v1.5 |
| Chunk Size | Document chunk size (characters) | 1000 |
| Chunk Overlap | Overlap between chunks | 200 |
| Similarity Threshold | Minimum similarity score (0-1) | 0.7 |
| Max Search Results | Maximum results per query | 5 |

See [Vector Search Setup](docs/VECTOR_SEARCH_SETUP.md) for detailed configuration and PostgreSQL extension setup.

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

### Chat API

#### POST /api/assistant/chat

Send a message to the assistant:

```json
{
  "message": "How many events are there this week?",
  "session_id": "optional-session-id",
  "event_id": 123
}
```

Response:

```json
{
  "answer": "There are 12 events this week...",
  "session_id": "generated-or-provided-id",
  "metadata": {
    "sql_generated": "SELECT COUNT(*) ...",
    "confidence": 0.95,
    "data_sources": ["events", "registrations"]
  }
}
```

### Session Management

#### GET /api/assistant/sessions

List user's chat sessions:

```json
{
  "sessions": [
    {
      "id": "session-123",
      "created_at": "2026-01-20T10:00:00Z",
      "last_message_at": "2026-01-20T10:15:00Z",
      "message_count": 5
    }
  ]
}
```

#### GET /api/assistant/sessions/{session_id}

Get conversation history for a specific session.

#### DELETE /api/assistant/sessions/{session_id}

Delete a chat session and its history.

### Feedback

#### POST /api/assistant/feedback

Submit feedback on assistant responses:

```json
{
  "session_id": "session-123",
  "message_id": "msg-456",
  "rating": 1,
  "comment": "Very helpful!"
}
```

### Vector Search

#### POST /api/assistant/search

Perform semantic search across indexed documents:

```json
{
  "query": "budget allocation process",
  "event_id": 123,
  "max_results": 5
}
```

Response:

```json
{
  "results": [
    {
      "content": "The budget allocation follows...",
      "document_name": "Financial Guidelines.pdf",
      "similarity_score": 0.89,
      "page": 5
    }
  ]
}
```

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

The plugin provides command-line tools for administration and diagnostics:

```bash
# Check plugin and LLM health status
indico assistant health

# Show current configuration (secrets masked)
indico assistant config

# Show configuration with secrets visible
indico assistant config --show-secrets
```

**Health Check Output:**
- Plugin status (loaded/not loaded)
- Plugin enabled status
- LLM provider and base URL
- LLM connection status
- Response latency (if connected)

**Config Output:**
- Enabled status
- LLM provider and model
- Base URL
- Timeout and max tokens
- API key (masked by default, visible with `--show-secrets`)

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

The plugin follows Indico's official plugin architecture with modular services:

```
indico_assistant/
├── __init__.py              # Package init with version check
├── plugin.py                # AssistantPlugin (IndicoPlugin subclass)
├── blueprint.py             # URL routing and API endpoints
├── cli.py                   # CLI commands (health, config)
├── default_settings.py      # Default configuration values
├── version.py               # Version compatibility checks
├── controllers/             # HTTP request handlers
│   ├── health.py           # Health check endpoint
│   ├── chat.py             # Chat API endpoint
│   ├── sessions.py         # Session management
│   ├── feedback.py         # Feedback submission
│   ├── search.py           # Vector search endpoints
│   └── admin.py            # Admin statistics and monitoring
├── services/                # Business logic layer
│   ├── llm/                # LLM provider abstraction
│   ├── nl2sql/             # Natural language to SQL pipeline
│   ├── chat/               # Chat orchestration service
│   ├── embedding/          # Document embedding service
│   ├── vector_search/      # Semantic search with pgvector
│   ├── feedback/           # Feedback collection service
│   └── observability/      # Langfuse tracing integration
├── models/                  # SQLAlchemy database models
│   ├── session.py          # Chat session model
│   ├── message.py          # Message model
│   ├── feedback.py         # Feedback model
│   ├── document.py         # Indexed document model
│   └── audit.py            # Query audit log model
├── schemas/                 # Pydantic validation schemas
└── tasks/                   # Background Celery tasks
    ├── indexing.py         # Document indexing worker
    ├── sync.py             # Langfuse sync worker
    └── cleanup.py          # Session cleanup worker
```

**Key Modules:**
- **plugin.py**: Main plugin class, settings registration, signal connections
- **blueprint.py**: URL routing, request/response handling
- **services/**: Business logic isolated from HTTP layer
- **controllers/**: Thin request handlers that delegate to services
- **models/**: Database schema for sessions, messages, feedback, documents
- **tasks/**: Asynchronous background processing

## Security

The plugin implements multiple layers of security:

### SQL Injection Prevention
- **Parameterized queries**: All SQL uses bound parameters, never string concatenation
- **SELECT-only**: NL2SQL pipeline enforces read-only queries, no INSERT/UPDATE/DELETE
- **Query validation**: Generated SQL parsed and validated before execution

### Permission-Based Filtering
- **Event access control**: Users can only query events they have permission to access
- **Table allowlist**: Configurable per-event restrictions on queryable tables
- **Row-level security**: Results automatically filtered by user permissions

### JWT Authentication
- **Chat widget auth**: HS256-signed JWTs issued per user with expiration
- **Secret rotation**: Chainlit auth secret configurable per environment
- **Token validation**: Chainlit server validates signatures before accepting requests

### Secure Secret Handling
- **Masked display**: CLI `config` command masks API keys by default
- **Environment variables**: Secrets loaded from environment, never committed to code
- **Database encryption**: Sensitive settings stored in Indico's encrypted settings table

### Additional Protections
- **Rate limiting**: Prevents abuse of chat and search endpoints
- **Query timeout**: Prevents long-running queries from consuming resources
- **Audit logging**: All queries logged with user, timestamp, and result metadata

## Documentation

Additional documentation for advanced topics:

- **[Deployment Guide](docs/DEPLOYMENT.md)**: Chat widget deployment, bundle injection, JavaScript configuration, noscript fallbacks
- **[Accessibility](docs/ACCESSIBILITY.md)**: Screen reader support, keyboard navigation, ARIA labels, WCAG 2.1 compliance
- **[Langfuse Setup](docs/LANGFUSE_SETUP.md)**: Observability configuration, trace collection, privacy levels, dashboard setup
- **[Vector Search Setup](docs/VECTOR_SEARCH_SETUP.md)**: PostgreSQL pgvector extension installation, embedding configuration, index optimization

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.
