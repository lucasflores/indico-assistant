# Research: Comprehensive Framework Review and README Update

**Phase**: 0 (Research & Discovery)  
**Date**: January 20, 2026  
**Status**: Complete

## Overview

This document captures research findings from a comprehensive review of the Indico Assistant Plugin framework to ensure README accuracy.

## Research Tasks Completed

### 1. Framework Feature Audit (Specs 001-013)

**Decision**: All 13 features are implemented and operational  
**Rationale**: Verified by presence of service modules, controller endpoints, and integration points  
**Alternatives considered**: 
- Partial documentation (rejected - incomplete picture for users)
- External feature matrix (rejected - creates maintenance burden)

**Findings**:
- ✅ **001 - Plugin Foundation**: Core plugin structure with IndicoPlugin subclass, blueprint, settings
- ✅ **002 - LLM Service Layer**: Instructor-based LLM abstraction with Ollama, HuggingFace, OpenAI support
- ✅ **003 - NL2SQL Pipeline**: Complete pipeline with schema analysis, SQL generation, validation, execution
- ✅ **004 - Chat API**: REST endpoints for chat sessions, messages, feedback
- ✅ **005 - Langfuse Observability**: Integrated tracing with langfuse client and privacy filters
- ✅ **006 - Vector Search RAG**: pgvector integration with sentence-transformers, document chunking, retrieval
- ✅ **007 - TDD Gap Analysis**: Test coverage achieved across unit, integration, contract tests
- ✅ **008 - Chat Widget**: Chainlit Copilot widget with JWT auth injection
- ✅ **009 - Chat Widget Styling**: Theme synchronization with Indico CSS variables
- ✅ **010 - Chat Pipeline Integration**: Chat service orchestrating NL2SQL and vector search
- ✅ **011 - Realtime Attachment Indexing**: Signal handler for attachment_created with document extraction
- ✅ **012 - Conversation History**: Multi-turn context in NL2SQL with pronoun resolution
- ✅ **013 - NL2SQL Prompt Optimization**: Optimized prompts with examples and constraints

### 2. Configuration Settings Verification

**Decision**: Document all settings from default_settings.py with accurate defaults  
**Rationale**: Users need correct configuration values to avoid trial-and-error  
**Alternatives considered**:
- Link to code only (rejected - reduces accessibility)
- Sample config file (rejected - duplication with settings form)

**Findings** (from `indico_assistant/default_settings.py`):
- Global settings: `enabled`, `llm_provider`, `llm_model`, `llm_base_url`, `llm_api_key`, `llm_timeout`, `llm_max_tokens`
- Chat widget settings: `chat_widget_enabled`, `chainlit_server_url`, `chainlit_auth_secret`
- Event settings: `assistant_enabled`, `system_prompt`, `allowed_tables`
- Observability settings: `langfuse_enabled`, `langfuse_public_key`, `langfuse_secret_key`, `langfuse_host`
- Vector search settings: `vector_search_enabled`, `embedding_model`, `chunk_size`, `chunk_overlap`

### 3. API Endpoint Inventory

**Decision**: Document all public API endpoints from blueprint.py and controllers  
**Rationale**: API-first design means all functionality accessible via REST API  
**Alternatives considered**:
- OpenAPI spec generation (rejected - overkill for plugin, maintain manually)
- Swagger UI integration (rejected - additional dependency)

**Findings** (from `indico_assistant/controllers/`):
- `GET /api/assistant/health` - Health check with status indicators
- `POST /api/assistant/chat/sessions` - Create chat session
- `GET /api/assistant/chat/sessions` - List user sessions
- `POST /api/assistant/chat/sessions/<id>/messages` - Send message
- `GET /api/assistant/chat/sessions/<id>/messages` - Get conversation history
- `POST /api/assistant/feedback` - Submit feedback on responses
- `POST /api/assistant/search` - Vector search query endpoint

### 4. CLI Command Documentation

**Decision**: Document all CLI commands from cli.py with examples  
**Rationale**: CLI provides admin/debug capabilities users need to discover  
**Alternatives considered**:
- Inline --help only (rejected - users won't discover commands)
- Separate CLI docs (rejected - adds friction, README sufficient)

**Findings** (from `indico_assistant/cli.py`):
- `indico assistant health` - Check plugin and service status
- `indico assistant config` - Display current configuration (secrets masked)
- `indico assistant config --show-secrets` - Display config with secrets visible
- `indico assistant test-llm` - Test LLM connectivity
- `indico assistant index-documents` - Manual document indexing trigger

### 5. Dependencies Audit

**Decision**: List all dependencies matching pyproject.toml with versions  
**Rationale**: Users need to understand requirements for deployment planning  
**Alternatives considered**:
- Link to pyproject.toml only (rejected - requires navigation)
- Omit version ranges (rejected - users need minimum versions)

**Findings** (from `pyproject.toml`):
```
indico>=3.3
instructor>=1.0.0
openai>=1.0.0
ollama>=0.3.0
langfuse>=2.0.0
sentence-transformers>=2.2.0
PyPDF2>=3.0.0
python-docx>=0.8.11
pgvector>=0.2.0
PyJWT>=2.8.0
```

### 6. External Documentation Cross-References

**Decision**: Link to all 4 external docs with clear purpose statements  
**Rationale**: Detailed guides exist, README should reference not duplicate  
**Alternatives considered**:
- Inline all content (rejected - README becomes too long)
- Move to wiki (rejected - repo docs easier to maintain)

**Findings**:
- `docs/DEPLOYMENT.md` - Chat widget deployment, JavaScript injection, noscript fallback
- `docs/ACCESSIBILITY.md` - Accessibility features and WCAG compliance
- `docs/LANGFUSE_SETUP.md` - Langfuse cloud setup, API keys, trace viewing
- `docs/VECTOR_SEARCH_SETUP.md` - pgvector extension, embedding model, index creation

### 7. Security Features Documentation

**Decision**: Document security features without exposing implementation details  
**Rationale**: Users need to understand security posture for compliance/audit  
**Alternatives considered**:
- Omit security details (rejected - creates trust issues)
- Detailed implementation (rejected - potential vulnerability disclosure)

**Findings**:
- SQL injection prevention: Parameterized queries, SELECT-only validation
- Permission filtering: Event-based access control, user context validation
- JWT authentication: HS256 signed tokens for chat widget
- Secret handling: Encrypted storage, never logged, masked in config display
- Rate limiting: Per-user limits on API endpoints
- Audit logging: Query logging with user context (privacy-aware)

### 8. README Organization Research

**Decision**: Table of contents with section-based navigation  
**Rationale**: Clarified in spec - balances comprehensiveness with scannability  
**Alternatives considered**: Already evaluated in clarification phase

**Recommended Structure**:
```markdown
# Indico Assistant Plugin

[Version badge: v0.1.0] [Last Updated: YYYY-MM-DD]

## Table of Contents
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Global Settings](#global-settings)
  - [Chat Widget Settings](#chat-widget-settings)
  - [Per-Event Settings](#per-event-settings)
- [Usage](#usage)
  - [NL2SQL Pipeline](#nl2sql-pipeline)
  - [Vector Search](#vector-search)
  - [Chat API](#chat-api)
- [API Endpoints](#api-endpoints)
- [CLI Commands](#cli-commands)
- [Development](#development)
  - [Setup](#setup)
  - [Testing](#testing)
  - [Code Quality](#code-quality)
- [Architecture](#architecture)
- [Security](#security)
- [Documentation](#documentation)
- [License](#license)

## Features

[Inline 2-3 sentence summaries for each of 13 features with links to detailed docs]

...
```

### 9. Code Example Best Practices

**Decision**: Usage examples demonstrating how-to patterns  
**Rationale**: Clarified in spec - focus on user guidance, not test coverage  
**Alternatives considered**: Already evaluated in clarification phase

**Example Patterns Needed**:
- NL2SQL pipeline usage in request handler
- API endpoint curl examples
- CLI command examples with output
- Chat widget configuration in JavaScript

### 10. Validation Methodology

**Decision**: Comparison verification against source files  
**Rationale**: Clarified in spec - systematic cross-reference ensures accuracy  
**Alternatives considered**: Already evaluated in clarification phase

**Verification Checklist**:
- [ ] Settings match `indico_assistant/default_settings.py`
- [ ] Endpoints match `indico_assistant/controllers/*.py`
- [ ] CLI commands match `indico_assistant/cli.py`
- [ ] Dependencies match `pyproject.toml`
- [ ] Feature descriptions match spec summaries
- [ ] Version matches `indico_assistant/version.py`
- [ ] External doc links are valid and current

## Unknowns Resolved

All initial unknowns have been resolved through clarification session:
- ✅ Validation approach: Comparison verification
- ✅ Organization strategy: Section-based with TOC
- ✅ Feature documentation depth: Inline summaries with links
- ✅ Code example quality: Usage examples only
- ✅ Versioning: Version notice at top

## Technology Choices

| Technology | Decision | Rationale |
|------------|----------|-----------|
| **Documentation Format** | Markdown | Standard for README, GitHub-native rendering |
| **TOC Generation** | Manual | Control over structure, no build dependency |
| **Version Badge** | Manual text | Simple, no external service dependency |
| **Code Syntax** | Fenced code blocks | Syntax highlighting, copy-paste friendly |
| **Links** | Relative paths | Repository portability |

## Dependencies & Integration Points

**Internal Dependencies**:
- Existing README.md structure (preserve general flow)
- Spec summaries from specs/001-013 (source of truth for feature descriptions)
- Code files for verification (default_settings.py, cli.py, controllers/, pyproject.toml)

**External Dependencies**:
- docs/ files remain unchanged (DEPLOYMENT.md, ACCESSIBILITY.md, LANGFUSE_SETUP.md, VECTOR_SEARCH_SETUP.md)

**No New Dependencies Required**: This is a pure documentation task.

## Summary

All research complete. No unknowns remain. Ready for Phase 1 design artifacts.
