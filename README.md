# Indico Assistant Plugin

**Version**: 2.0.0 | **Last Updated**: February 3, 2026

AI-powered assistant plugin for [Indico](https://getindico.io/) - the open-source event management system.

## 🎬 Demo

![Indico Assistant Demo](docs/demo_optimized.gif)

*Ask questions about events, search documents, and get instant answers with source citations.*

## Table of Contents

- [Demo](#-demo)
- [Features](#features)
- [Chat actions](#chat-actions)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Global Settings](#global-settings)
  - [Chat Widget Settings](#chat-widget-settings)
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
- **Personalized Queries**: Ask about your own data with "What meetings do I have?" or "Show my contributions" - the assistant identifies you automatically via session or JWT auth
- **Source Citations**: Every answer includes inline source links - click to jump directly to the event page or attached document
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

- **Chat panel**: an Assistant tab on the right edge of every page for logged-in users (one cached script). It opens Chainlit's full app in a panel docked to the right, in Indico's look.
  - **It follows the user around Indico:** the panel comes back open, on the same conversation, on every page they go to.
  - **"This event" is the page's event:** each question refers to the page it's asked from.
  - **Past Chats:** a sidebar to search, reopen, rename and delete conversations.
  - **Thumbs up and down:** saved as Indico feedback.
  - **Stored in Indico:** conversations live in Indico's database.

  See the [Deployment Guide](docs/DEPLOYMENT.md).
  - JWT Authentication: Secure token-based auth per user
  - Light like Indico: Chainlit's own switch turns the panel dark, and the choice is kept across pages
  - Graceful Degradation: Loading/error states, hidden when not ready

### Configuration & Management

- **Health Monitoring**: Built-in health check endpoint for monitoring
- **CLI Tools**: Command-line interface for administration and diagnostics

### Observability & Quality

- **Langfuse Observability**: Integrated tracing and monitoring for all LLM interactions with privacy filters. See [Langfuse Setup](docs/LANGFUSE_SETUP.md)
- **Test Coverage**: Comprehensive unit, integration, and contract tests (80%+ coverage on services)

## Chat actions

Besides answering questions, the assistant can create and change meetings from the chat ("Set up a Teams meeting
with Makoto tomorrow at 2pm, 20 minutes each"). It never writes on its own: every request becomes a **plan**, a
list of the exact changes, which the user reads and confirms. Nothing touches Indico or Microsoft until then.

**Enabling.** Off by default. In **Administration → Plugins → Assistant**, tick **Enable chat actions**, then untick
any action under **Allowed actions** you do not want offered. Run `indico db --all-plugins upgrade` first (it
adds `plugin_assistant.action_plans`), and run the Celery worker on the `assistant` queue, which carries out the
confirmed plans.

| Action | What it does |
| --- | --- |
| Create event | A new meeting in a category you can create events in |
| Propose event | In a moderated category: an unlisted meeting plus a publication request |
| Update event | Move, retime, rename or re-describe one of your meetings (its timetable moves with it) |
| Add contribution / Update contribution | Talks with speakers (Indico users, or guests with an email) |
| Add Teams room | A Microsoft Teams meeting, with co-organizers; needs the `vc_teams` plugin |
| Add reminder | A reminder to the invitees and speakers (default: **Reminder before a meeting**, 15 minutes) |
| Attach link / Attach file | Links, or files sent in the chat, on a meeting or one of its talks |
| Delete created | Undo: reverses one of your plans from the last 24 hours; if someone changed the objects since, the plan says what differs before you confirm |

**What the user can do, and nothing more.** Each step is checked with Indico's own permissions as the user, when
the plan is made and again when it runs. The assistant can only do what the user could do on the page, and
Indico's event log attributes every change to them. If anything fails, the whole plan is rolled back, including
Teams meetings and emails. Plans are single-use: a plan expires after 30 minutes or when it is revised, and
**Confirm** works once. A plan has at most 25 steps.

**Help while planning.** Unclear requests get a question instead of a guess, such as which category or which
"Makoto". Missing times are offered from free slots in Indico: yours and the named people's. Outlook free/busy is
not used yet: it waits for a check that Microsoft Graph allows it with the Teams app's scoped setup. Until then
the **Use Outlook free/busy** switch only makes the suggestions say that Outlook was not consulted.
Suggestions come from the user's similar past meetings: material, attendees and length. Each names its source
and is added only when the user accepts it. The language model sees Indico content only as fenced data, and
anything in a plan that the user did not ask for is dropped.

**Uploads.** Up to 5 files per message, 25 MB each (or Indico's `MAX_UPLOAD_FILE_SIZE`, if lower). Only PDF,
Word, PowerPoint and Excel (`.docx/.pptx/.xlsx`), PNG, JPEG, text and Markdown files are accepted, checked by
extension and by content. A file stays unattached until a confirmed plan attaches it; Indico removes unclaimed
files after a day.

**Teams.** `add_teams_room` needs the `vc_teams` plugin, configured with a Microsoft 365 tenant. Co-organizers
must have a tenant account; the plan says so when they do not. If Microsoft is unreachable, the plan is offered
without the room.

**Keeping plans.** Plans are kept for **Keep chat action plans** days (default 90) for audit.

The design is in `specs/019-chat-actions/`, and the local walkthrough is in its `quickstart.md`.

## Requirements

- **Indico 3.3+**
- **Python 3.11+**
- **PostgreSQL** (Indico's default database)

## Installation

### From Source (Recommended)

```bash
# Clone the repository
git clone https://github.com/lucasflores/indico-assistant.git
cd indico-assistant

# Install in production mode
pip install .

# Or install in development mode (editable)
pip install -e ".[dev]"
```

### From Git Repository

```bash
# Install directly from git (requires git to be installed)
pip install git+https://github.com/lucasflores/indico-assistant.git
```

**Note**: This plugin is not yet published to PyPI. Use one of the methods above to install from source.

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
- JWT issued per user by `GET /api/assistant/widget/config` (only when the widget is opened, `no-store`) and validated by Chainlit header_auth_callback
- Theme auto-detected from Indico CSS vars / media queries; overrides via `IndicoAssistant.theme`
- Session continuity via Chainlit threadId; feedback bridged to Indico API
- Graceful degradation: loading/error bubble, hidden when not ready

See [Deployment Guide](docs/DEPLOYMENT.md) for complete setup instructions.

![Indico Assistant Demo](docs/setup.png)

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

It is public, for load balancers and monitoring. Only admins trigger a live LLM check (which
costs a request); everyone else gets `configured` from the settings alone. Anonymous requests to
every other assistant endpoint get 401.

Status values:
- `healthy`: All services operational
- `degraded`: Plugin functional but LLM unavailable
- `unhealthy`: Plugin disabled or critical error

### Chat API

#### POST /api/assistant/chat

Send a message to the assistant. The answer is produced by a Celery worker (queue `assistant`), so
LLM calls never hold an Indico web worker; the request only saves the message and returns `202`:

```json
{"message": "How many events are there this week?", "session_id": "optional-session-id", "event_id": 123}
```

`session_id` may be a new id chosen by the client: the chat panel starts a conversation under Chainlit's thread id. `event_id` is the event of the page the message is sent from, and it's kept on the message. `answer_id` (optional) is the id to store the answer under. The panel sends its Chainlit run's id, because Chainlit's thumbs vote on the run.

```json
{"job_id": "374c73cc…", "session_id": "f982fd9d-…", "created_session": true, "status": "pending"}
```

#### GET /api/assistant/chat/jobs/{job_id}

Poll until the answer is ready (`202` while pending; jobs expire after an hour). When done:

```json
{
  "status": "done",
  "response": "There are 12 events this week ([source](http://localhost:8000/event/5/))...",
  "session_id": "f982fd9d-…",
  "message_id": "4be4e637-…",
  "metadata": {"sql_generated": "SELECT COUNT(*) ...", "confidence": 0.95, "data_sources": [...],
               "suggested_followups": [...]}
}
```

A failed or timed-out answer (2 minutes per answer) returns `500` with `error` and `message`.

**Deployment**: run Celery workers that consume the plugin's queues: `assistant` (chat answers; its
concurrency is the cluster-wide cap on simultaneous answers) and `assistant_bulk` (attachment
indexing, syncs, nightly cleanup; low concurrency is fine). For example
`indico celery worker -Q celery,assistant,assistant_bulk`, or dedicated pools per queue.

**Document index lifecycle**: an uploaded or edited attachment is indexed after its transaction
commits; deleting an attachment or folder removes its chunks in the same transaction. Chunks record
the Indico file version they came from, so a sync (`POST /api/assistant/search/sync/all`) finds what
changed in SQL without reading files, and queues only that. Text already indexed for another
attachment (cloned events) is copied instead of re-embedded. A nightly task removes chunks of
attachments deleted while the plugin was off and closes sync runs whose worker died.

**Retention**: a nightly task (03:11, queue `assistant_bulk`, needs Celery beat) deletes chat sessions
idle 90 days (with their messages and feedback), audit-log rows after 90 days, error records after 30
days and sync logs after 90 days. Each period is an admin setting (Admin → Plugins → Assistant);
0 keeps that data forever.

### Session Management

#### GET /api/assistant/sessions

The caller's conversations, most recently active first, one page at a time. The parameters are `limit`, `cursor` (the previous page's `next_cursor`) and `search` (words in the title or the messages):

```json
{
  "sessions": [
    {"session_id": "f982fd9d-…", "title": "Move the weekly sync", "event_id": 351,
     "created_at": "2026-09-27T10:00:00+00:00", "updated_at": "2026-09-28T09:00:00+00:00", "message_count": 4}
  ],
  "next_cursor": "…"
}
```

#### GET /api/assistant/sessions/{session_id}

A conversation's messages, with each answer's feedback from the caller. It also returns `pending_job_id` while a question is still being answered, and `waiting_plan_id` when a plan waits for confirmation. With `?messages=0`, it only confirms the conversation exists and is the caller's.

#### PATCH /api/assistant/sessions/{session_id}

Rename a conversation: `{"title": "…"}`, 1 to 200 characters. Owner only.

#### PUT /api/assistant/sessions/{session_id}

Start a conversation under this id before its first question is stored: `{"first_message": "…"}`. It returns `201` if created, `200` if it's already the caller's own, and `403` if it belongs to someone else. The panel uses it so Past Chats lists a new conversation at once.

#### DELETE /api/assistant/sessions/{session_id}

Delete a conversation and its messages. Its action plans are kept for the audit trail.

### Feedback

#### POST /api/assistant/feedback

Feedback on one of the caller's answers. A thumb is one vote, so switching between up and down replaces it. A vote counts against the read limit, not as a question:

```json
{"message_id": "4be4e637-…", "feedback_type": "thumbs_down", "value": true}
```

`feedback_type` is `thumbs_up`, `thumbs_down`, `rating` (with `value` from 1 to 5) or `comment` (with `value` a text). A thumb may carry a `comment`, stored with it: both are kept, or neither.

#### DELETE /api/assistant/feedback/{feedback_id}

Take back a thumbs vote, together with its comment: `204`. A vote that isn't the caller's returns `404`.

### Vector Search

#### POST /api/assistant/search

Perform semantic search across indexed documents. Requires a logged-in user and the
[NL2SQL database role](#nl2sql-database-role): the search runs as that role, so it only returns
chunks from events and attachments the user may see. `event_id` is checked with Indico's
`can_access` (no access: empty results); `event_ids` only narrows the search.

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
    user=session.user,     # decides what the query can see; no user = no query
    event_ids=[event.id],  # optional: one id limits the query to that event
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
| Contributions | "List talks in the parallel sessions" |
| Speakers | "Who are the speakers at tomorrow's event?" |
| **Personal queries** | "What meetings do I have this week?" |
| **Document search** | "What does the budget report say about travel?" |

**Note**: All responses include inline source citations linking directly to events or documents.

### Security Features

- **Read-only database role**: generated SQL runs as `indico_assistant_ro`, never as Indico's role
  (see [NL2SQL database role](#nl2sql-database-role))
- **Row security**: the database, not the prompt, decides which events the user can see
- **Validator**: one SELECT statement, no comments, no system schemas or `pg_*`/`dblink`/`lo_*`
  functions, no `SET`/`COPY`/locking, only allowlisted tables
- **Table allowlist**: `config_modules/available_tables.yaml`; no users, registrations, emails,
  phone numbers, access keys or assistant chat tables
- **Query timeout**: 10 seconds per query (also the read-only role's own default)
- **Row limit**: at most 1000 rows, applied around the generated query

### NL2SQL database role

Generated SQL runs through its own connection, as a Postgres role that can read only the allowlisted
columns, and only rows the asking user may see. Each query carries a signed
`user_id:event_id:is_admin` context; the policies reject queries without a valid one.

Setup (a DBA, or anyone who owns the Indico tables):

```bash
# 1. Generate the script from available_tables.yaml and apply it as the Indico owner role
indico assistant nl2sql-db-sql --password 'choose-one' > nl2sql_setup.sql
psql -d indico -v ON_ERROR_STOP=1 -f nl2sql_setup.sql

# 2. Point the Indico web server (and Celery workers) at the new role
export ASSISTANT_NL2SQL_DATABASE_URI='postgresql://indico_assistant_ro:choose-one@dbhost/indico'
```

Omit `--password` for local peer/trust authentication. Re-run step 1 after editing
`available_tables.yaml`; `--teardown` prints the script that removes the role and policies.
Without `ASSISTANT_NL2SQL_DATABASE_URI`, event-data questions fail with an error naming it.

The script creates `pgcrypto` (for the signature check) and `plugin_assistant.nl2sql_secret` (the
signing key; the role cannot read it), and sets on the role: read-only transactions, a 10 s statement
timeout, 1 s lock timeout, `work_mem` 16MB, no parallel workers, 20 connections, and
`hnsw.iterative_scan` (pgvector 0.8+) so filtered vector searches are not cut short.

What a user can see: events that are public, plus events granted to them directly, through a local
group, through read access to the event's category, or because they manage the category. Admins see
everything. A question asked on an event page sees only that event, after Indico's own `can_access`
check. Grants through **external (multipass) groups, IP networks, registrations or access keys are not
recognised** by the policies, so those events stay hidden from the assistant (it fails closed).

Check the setup against a real database:

```bash
ASSISTANT_NL2SQL_DATABASE_URI=postgresql://indico_assistant_ro@/indico \
  pytest tests/integration/nl2sql/test_readonly_role.py
```

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
