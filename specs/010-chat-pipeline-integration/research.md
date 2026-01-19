# Research: Chat Pipeline Integration

**Feature**: 010-chat-pipeline-integration  
**Date**: 2026-01-18  
**Status**: Complete

## Research Tasks

### 1. Root Cause Analysis: Why is the chat returning mock responses?

**Task**: Identify why `_process_with_nl2sql` falls into the mock path

**Findings**:

The chat service at [indico_assistant/services/chat/service.py](../../indico_assistant/services/chat/service.py#L306) attempts to import a class that doesn't exist:

```python
from indico_assistant.services.nl2sql import NL2SQLService  # WRONG - doesn't exist

service = NL2SQLService()  # Would fail
```

The NL2SQL package actually exports `NL2SQLPipeline`, not `NL2SQLService`. This can be seen in the [nl2sql/__init__.py](../../indico_assistant/services/nl2sql/__init__.py) which only has:

```python
__all__ = [
    "NL2SQLPipeline",
    "create_nl2sql_pipeline",
    "create_nl2sql_pipeline_from_plugin",
    # ... other exports, but NO NL2SQLService
]
```

**Decision**: Replace the broken import with the correct factory pattern using `create_nl2sql_pipeline_from_plugin(plugin)`

**Rationale**: The factory function properly configures the pipeline with plugin settings and handles all dependencies.

**Alternatives considered**: 
- Creating an `NL2SQLService` wrapper class → Rejected because the factory already exists and works

---

### 2. Chainlit-to-Indico Communication Pattern

**Task**: Research best practices for Chainlit calling external REST APIs

**Findings**:

Chainlit's `@cl.on_message` handler is async, so we need an async HTTP client. Options:
1. **httpx** (recommended) - Modern async HTTP client, similar API to requests
2. **aiohttp** - More complex but powerful
3. **requests** with `run_in_executor` - Sync wrapped in async, less efficient

The existing Chainlit app already handles JWT auth in `header_auth_callback`. The token is available on the Chainlit user object.

**Decision**: Use `httpx.AsyncClient` for HTTP calls to Indico

**Rationale**: httpx is modern, well-maintained, has a simple API similar to requests, and is designed for async use.

**Alternatives considered**:
- aiohttp → More complex API for simple REST calls
- Direct Python import → Would require shared process, breaks separation

---

### 3. JWT Token Forwarding

**Task**: Research how to forward the JWT token from Chainlit to Indico

**Findings**:

The Chainlit user metadata stores authentication info from the JWT payload:
```python
user = cl.User(
    identifier=identifier,
    metadata={
        "name": meta.get("name", ""),
        "email": meta.get("email", ""),
        "authenticated": True,
        "source": "indico",
    },
)
```

However, the **original JWT token** is not stored - only the decoded payload. For Indico API calls, we need the original token.

**Decision**: Store the original JWT token in user metadata for forwarding

**Rationale**: The Indico API expects the same JWT for authentication; re-encoding would require the secret key.

**Alternatives considered**:
- Re-create token from payload → Would require secret key access, security risk
- Internal service-to-service auth → Overcomplicates architecture

---

### 4. Error Handling in Async Context

**Task**: Research Chainlit error handling patterns

**Findings**:

Chainlit provides error handling via:
- `@cl.on_error` decorator for global error handling
- Try/catch in `@cl.on_message` for message-specific errors
- `cl.Message` can display error states to users

For HTTP errors from Indico:
- 401/403: Re-authentication needed
- 422: Validation error (show user-friendly message)
- 500: Backend error (show generic error)

**Decision**: Implement error handling in `on_message` with user-friendly messages

**Rationale**: Keeps error handling close to the action, allows message-specific recovery

---

### 5. Session Management Between Chainlit and Indico

**Task**: Research how to maintain session_id across Chainlit/Indico boundary

**Findings**:

The Indico chat API returns `session_id` on every response. Chainlit has its own session via `cl.user_session`.

We can store the Indico `session_id` in `cl.user_session` after the first message and pass it back on subsequent messages.

```python
# First message - no session_id sent
# Response includes session_id: "abc-123"
# Store in cl.user_session.set("indico_session_id", "abc-123")
# Second message - send session_id: "abc-123"
```

**Decision**: Use `cl.user_session` to persist Indico session_id across messages

**Rationale**: Natural fit with Chainlit's session model; maintains conversation continuity

---

## Summary of Decisions

| Area | Decision | 
|------|----------|
| NL2SQL Integration | Use `create_nl2sql_pipeline_from_plugin(plugin)` factory |
| HTTP Client | Use `httpx.AsyncClient` for async Indico API calls |
| JWT Forwarding | Store original token in Chainlit user metadata |
| Error Handling | Handle in `on_message` with user-friendly messages |
| Session Persistence | Use `cl.user_session` for Indico session_id |

## Unresolved Questions

None - all clarifications have been resolved.
