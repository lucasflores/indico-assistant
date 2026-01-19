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
- Python 3.11+ (matches Indico minimum) + sentence-transformers (BAAI/bge-small-en-v1.5), pgvector, PyPDF2, python-docx (006-rag-vector-search)
- PostgreSQL with pgvector extension, `plugin_assistant` schema (006-rag-vector-search)
- Python 3.11+ + pytest, pytest-cov, indico fixtures (007-tdd-gap-analysis)
- N/A (documentation + test files) (007-tdd-gap-analysis)
- Python 3.11+ (plugin), JavaScript ES6 (widget injection) + Chainlit Copilot widget, Flask (via Indico), Indico plugin system (008-chat-widget)
- sessionStorage (client-side thread persistence via Chainlit), PostgreSQL (existing) (008-chat-widget)
- Python 3.11+ (Chainlit app), CSS, JSON + Chainlit 2.9.x (copilot widget mode) (009-chat-widget-styling)
- N/A (static configuration files only) (009-chat-widget-styling)
- Python 3.11+ + Flask (Indico), Chainlit 2.9.5, Instructor, httpx (for async HTTP client) (010-chat-pipeline-integration)
- PostgreSQL (Indico's db via SQLAlchemy) (010-chat-pipeline-integration)
- Python 3.11+ (matching Indico requirements) (011-realtime-attachment-indexing)
- PostgreSQL (`extracted_documents` table with event_id, attachment_id, content_hash, embeddings) (011-realtime-attachment-indexing)

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
- 011-realtime-attachment-indexing: Added Python 3.11+ (matching Indico requirements)
- 010-chat-pipeline-integration: Added Python 3.11+ + Flask (Indico), Chainlit 2.9.5, Instructor, httpx (for async HTTP client)
- 009-chat-widget-styling: Added Python 3.11+ (Chainlit app), CSS, JSON + Chainlit 2.9.x (copilot widget mode)


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
