# Chat API Contract

**Endpoint**: `POST /api/assistant/chat`  
**Feature**: 010-chat-pipeline-integration

## Request

```json
{
  "message": "How many events are scheduled next week?",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_id": 123
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | User's natural language question (1-10,000 chars) |
| `session_id` | UUID | No | Continue existing conversation session |
| `event_id` | integer | No | Scope queries to a specific event |

### Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <jwt_token>` |
| `Content-Type` | Yes | `application/json` |

## Response (Success)

**Status**: 200 OK (existing session) or 201 Created (new session)

```json
{
  "response": "There are 15 events scheduled for next week, including 3 conferences and 12 meetings.",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "metadata": {
    "sql_generated": "SELECT COUNT(*) FROM events WHERE start_date BETWEEN '2026-01-19' AND '2026-01-25'",
    "confidence": 0.92,
    "data_sources": ["events"]
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `response` | string | Assistant's natural language response |
| `session_id` | UUID | Session ID (new or existing) |
| `message_id` | UUID | Unique ID of this response message |
| `metadata.sql_generated` | string | SQL query that was executed (if applicable) |
| `metadata.confidence` | number | Model confidence score (0-1) |
| `metadata.data_sources` | array | Tables/sources used in query |

## Response (Error)

### 401 Unauthorized
```json
{
  "error": "AUTHENTICATION_REQUIRED",
  "message": "Valid authentication token required"
}
```

### 403 Forbidden
```json
{
  "error": "ACCESS_DENIED",
  "message": "Access denied to event 123"
}
```

### 404 Not Found
```json
{
  "error": "SESSION_NOT_FOUND",
  "message": "Session not found"
}
```

### 422 Validation Error
```json
{
  "error": "VALIDATION_ERROR",
  "message": "Invalid request body"
}
```

### 429 Rate Limited
```json
{
  "error": "RATE_LIMIT_EXCEEDED",
  "message": "Too many requests",
  "retry_after": 60
}
```

### 500 Internal Error
```json
{
  "error": "QUERY_PROCESSING_ERROR",
  "message": "Failed to process query",
  "details": "Unable to generate valid SQL after 3 attempts"
}
```

## Chainlit Integration Notes

When Chainlit calls this API:
1. Forward the original JWT token in `Authorization` header
2. Store returned `session_id` for subsequent messages
3. Handle errors gracefully with user-friendly messages
4. Use async HTTP client (httpx) for non-blocking calls
