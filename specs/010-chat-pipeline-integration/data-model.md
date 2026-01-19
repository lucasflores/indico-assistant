# Data Model: Chat Pipeline Integration

**Feature**: 010-chat-pipeline-integration  
**Date**: 2026-01-18

## Overview

This feature is primarily an **integration fix** - it connects existing components without introducing new data models. The key entities already exist from previous features.

## Existing Entities (No Changes)

### ChatSession (from 004-chat-api)
- `id`: UUID primary key
- `user_id`: Integer FK to Indico user
- `event_id`: Optional integer FK to event
- `created_at`: Timestamp
- `updated_at`: Timestamp

### ChatMessage (from 004-chat-api)
- `id`: UUID primary key
- `session_id`: UUID FK to ChatSession
- `role`: Enum (user, assistant)
- `content`: Text
- `metadata`: JSONB
- `created_at`: Timestamp

### NL2SQLPipeline (from 003-nl2sql-pipeline)
- Orchestrator class, not a database model
- Configured via `create_nl2sql_pipeline_from_plugin()`

## New Configuration (Environment Variables)

### Chainlit App Configuration

| Variable | Type | Description | Example |
|----------|------|-------------|---------|
| `INDICO_API_URL` | string | Base URL for Indico API | `https://indico.example.com` |
| `CHAINLIT_AUTH_SECRET` | string | JWT secret (shared with plugin) | (generated) |

These are **runtime configuration**, not database models.

## Data Flow

```
┌─────────────┐     JWT Token    ┌─────────────────┐
│   Widget    │ ───────────────► │   Chainlit      │
│ (Browser)   │                  │   (app_chnlit)  │
└─────────────┘                  └────────┬────────┘
                                          │ HTTP POST
                                          │ /api/assistant/chat
                                          │ + Authorization: Bearer <jwt>
                                          ▼
                                 ┌─────────────────┐
                                 │  Indico Plugin  │
                                 │  (ChatService)  │
                                 └────────┬────────┘
                                          │
                                          ▼
                                 ┌─────────────────┐
                                 │ NL2SQLPipeline  │
                                 │ (via factory)   │
                                 └────────┬────────┘
                                          │
                                          ▼
                                 ┌─────────────────┐
                                 │   PostgreSQL    │
                                 │   (Indico DB)   │
                                 └─────────────────┘
```

## Schema Impact

**No database migrations required** - this feature only fixes wiring between existing components.
