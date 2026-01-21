# API Contract: Chat Endpoint Identity Enhancement

**Feature**: 016-user-id-passthrough  
**Endpoint**: `POST /api/assistant/chat`  
**Date**: 2026-01-21

## Request Schema

No changes to request schema - existing `ChatRequest` remains unchanged.

```json
{
  "message": "string (required)",
  "session_id": "string (optional, UUID)",
  "event_id": "integer (optional)"
}
```

## Response Schema Enhancement

### ChatResponse (Enhanced)

```json
{
  "session_id": "string (UUID)",
  "message_id": "string (UUID)",
  "response": "string",
  "metadata": {
    "sql_generated": "string | null",
    "confidence": "number | null",
    "data_sources": "array",
    "identity_status": {
      "source": "authenticated | user_provided | unknown",
      "disclaimer": "string | null"
    }
  }
}
```

### New Fields

| Field | Type | Description |
|-------|------|-------------|
| `metadata.identity_status` | object | Identity resolution status |
| `metadata.identity_status.source` | string | How user was identified |
| `metadata.identity_status.disclaimer` | string | Disclaimer for user_provided identity |

## Response Scenarios

### Scenario 1: Authenticated User - Personal Query

**Request**:
```json
{
  "message": "What meetings do I have this week?"
}
```

**Response** (200 OK):
```json
{
  "session_id": "...",
  "message_id": "...",
  "response": "You have 3 meetings this week:\n1. Team Standup (Mon 9am)\n...",
  "metadata": {
    "sql_generated": "SELECT ... WHERE p.user_id = :user_id",
    "confidence": 0.95,
    "identity_status": {
      "source": "authenticated",
      "disclaimer": null
    }
  }
}
```

### Scenario 2: Unauthenticated - Personal Query - Prompting

**Request**:
```json
{
  "message": "What meetings do I have?"
}
```

**Response** (200 OK):
```json
{
  "session_id": "...",
  "message_id": "...",
  "response": "I can't seem to identify who you are right now. To help with your personal query, could you please provide one of the following:\n- Your full name (e.g., \"John Smith\")\n- Your email address\n- Your Indico user ID (preferred for accuracy)\n\nOnce you provide this information, I'll be able to answer your question!",
  "metadata": {
    "identity_status": {
      "source": "unknown",
      "disclaimer": null
    }
  }
}
```

### Scenario 3: User Provides Identity - Successful Lookup

**Request** (follow-up):
```json
{
  "message": "My email is john.smith@cern.ch",
  "session_id": "..."
}
```

**Response** (200 OK):
```json
{
  "session_id": "...",
  "message_id": "...",
  "response": "Thanks! I found your account. You have 3 meetings this week:\n1. Team Standup...\n\n*Note: These results are based on the identity you provided. For verified access, please log in.*",
  "metadata": {
    "sql_generated": "SELECT ... WHERE p.user_id = :user_id",
    "identity_status": {
      "source": "user_provided",
      "disclaimer": "Note: These results are based on the identity you provided. For verified access, please log in."
    }
  }
}
```

### Scenario 4: Multiple Users Found - Disambiguation

**Request**:
```json
{
  "message": "My name is John Smith",
  "session_id": "..."
}
```

**Response** (200 OK):
```json
{
  "session_id": "...",
  "message_id": "...",
  "response": "I found 3 users with the name John Smith. Could you please provide your email address or user ID so I can identify you correctly?",
  "metadata": {
    "identity_status": {
      "source": "unknown",
      "disclaimer": null
    }
  }
}
```

### Scenario 5: Non-Personal Query - No Identity Needed

**Request**:
```json
{
  "message": "What events are happening next week?"
}
```

**Response** (200 OK):
```json
{
  "session_id": "...",
  "message_id": "...",
  "response": "Here are the upcoming events next week:\n1. Physics Conference...",
  "metadata": {
    "sql_generated": "SELECT ... FROM events.events",
    "identity_status": {
      "source": "unknown",
      "disclaimer": null
    }
  }
}
```

## Error Responses

No new error codes. Existing error handling remains unchanged.
