# Contract: API Endpoints Section

## Section Requirements

**Location**: After Configuration section  
**Purpose**: Document all REST API endpoints with request/response formats  
**Format**: Subsections by endpoint group with code examples

## Content Structure

### Main Header
```markdown
## API Endpoints
```

### Intro Paragraph
Brief statement that all functionality is exposed via REST API at `/api/assistant/*` requiring Indico authentication.

---

### Health Check Endpoint

```markdown
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

**Status values**:
- `healthy`: All services operational
- `degraded`: Plugin functional but LLM unavailable
- `unhealthy`: Plugin disabled or critical error
```

**Verification**: Endpoint exists in `indico_assistant/controllers/health.py`, response format matches actual implementation

---

### Chat Endpoints

```markdown
### Chat Endpoints

#### Create Chat Session
```bash
POST /api/assistant/chat/sessions
```

**Request**:
```json
{
  "event_id": 123,
  "context": "optional initial context"
}
```

**Response**:
```json
{
  "session_id": "uuid-here",
  "created_at": "2026-01-20T10:00:00Z"
}
```

#### List User Sessions
```bash
GET /api/assistant/chat/sessions
```

Returns array of user's active chat sessions.

#### Send Message
```bash
POST /api/assistant/chat/sessions/<session_id>/messages
```

**Request**:
```json
{
  "content": "How many events this week?",
  "event_id": 123
}
```

**Response**:
```json
{
  "message_id": "uuid",
  "content": "There are 5 events this week...",
  "timestamp": "2026-01-20T10:01:00Z",
  "sources": ["nl2sql", "vector_search"]
}
```

#### Get Conversation History
```bash
GET /api/assistant/chat/sessions/<session_id>/messages
```

Returns array of messages in chronological order.
```

**Verification**: All endpoints exist in `indico_assistant/controllers/chat.py`, request/response formats match schemas in `indico_assistant/schemas/chat.py`

---

### Search Endpoint

```markdown
### Search Endpoint

```bash
POST /api/assistant/search
```

Perform semantic search across indexed documents.

**Request**:
```json
{
  "query": "budget planning",
  "event_id": 123,
  "top_k": 5
}
```

**Response**:
```json
{
  "results": [
    {
      "document_id": "uuid",
      "filename": "budget.pdf",
      "chunk_text": "...",
      "similarity_score": 0.89
    }
  ]
}
```
```

**Verification**: Endpoint exists in `indico_assistant/controllers/search.py`, format matches implementation

---

### Feedback Endpoint

```markdown
### Feedback Endpoint

```bash
POST /api/assistant/feedback
```

Submit feedback on assistant responses.

**Request**:
```json
{
  "message_id": "uuid",
  "rating": "positive",
  "comment": "Very helpful!"
}
```

**Response**:
```json
{
  "feedback_id": "uuid",
  "timestamp": "2026-01-20T10:02:00Z"
}
```

**Rating values**: `positive`, `negative`
```

**Verification**: Endpoint exists in `indico_assistant/controllers/feedback.py`

---

## Content Requirements

1. **HTTP Method + Path**: Clearly stated for each endpoint
2. **Request format**: JSON with field descriptions
3. **Response format**: JSON with example values
4. **Status codes** (if relevant): Document error responses
5. **Authentication**: Note that all endpoints require Indico auth
6. **Code blocks**: Use ```bash for endpoints, ```json for payloads

## Verification Checklist

- [ ] All endpoints from `indico_assistant/controllers/*.py` included
- [ ] HTTP methods correct (GET/POST)
- [ ] Paths match blueprint routes
- [ ] Request schemas match `indico_assistant/schemas/*.py`
- [ ] Response schemas match actual responses
- [ ] JSON syntax valid (test with parser)
- [ ] Authentication requirement stated

## Success Criteria

- API consumers can implement clients from this documentation alone
- All endpoints discoverable
- Request/response formats are accurate
- Examples are realistic (not placeholder data)
