# indico_assistant_plugin Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-01-14

## Active Technologies
- Python 3.11+ (match Indico) + instructor, pydantic (via Indico), ollama, openai (002-llm-service-layer)
- N/A (stateless service) (002-llm-service-layer)
- Python 3.11+ + Instructor (LLM), SQLAlchemy (ORM), PostgreSQL (database) (003-nl2sql-pipeline)
- PostgreSQL (Indico's `db.session`), pgvector for future RAG (003-nl2sql-pipeline)
- Python 3.11+ + Flask (via Indico), SQLAlchemy, Pydantic, Feature 003 NL2SQL Pipeline (004-chat-api)
- PostgreSQL with `plugin_assistant` schema (ChatSession, ChatMessage, FeedbackEntry tables) (004-chat-api)
- Python 3.11+ + langfuse (Python SDK), SQLAlchemy (via Indico), Celery (background sync) (005-langfuse-observability)
- PostgreSQL (plugin_assistant schema) for local metrics cache (005-langfuse-observability)

- Python 3.11+ + Indico 3.3+, Flask (via Indico), WTForms (via Indico), SQLAlchemy (via Indico) (001-plugin-foundation)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.11+: Follow standard conventions

## Recent Changes
- 005-langfuse-observability: Added Python 3.11+ + langfuse (Python SDK), SQLAlchemy (via Indico), Celery (background sync)
- 004-chat-api: Added Python 3.11+ + Flask (via Indico), SQLAlchemy, Pydantic, Feature 003 NL2SQL Pipeline
- 003-nl2sql-pipeline: Added Python 3.11+ + Instructor (LLM), SQLAlchemy (ORM), PostgreSQL (database)


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
