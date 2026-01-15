# Quickstart: Chat REST API

**Feature**: 004-chat-api | **Branch**: `004-chat-api`

## Overview

This guide covers implementing REST API endpoints for conversational chat with session persistence and feedback collection.

## Prerequisites

- Feature 003 NL2SQL Pipeline implemented and working
- PostgreSQL with `plugin_assistant` schema
- Redis running (optional, falls back to in-memory rate limiting)
- Indico development environment

## Quick Reference

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/assistant/chat` | Send message, get AI response |
| GET | `/api/assistant/sessions` | List user's sessions (paginated) |
| GET | `/api/assistant/sessions/{id}` | Get session with message history |
| DELETE | `/api/assistant/sessions/{id}` | Delete a session |
| POST | `/api/assistant/feedback` | Submit feedback on response |

### Rate Limits

- Chat endpoint: 60 requests/minute
- Read endpoints: 200 requests/minute

## File Structure

```
indico_assistant/
├── models/
│   ├── __init__.py          # Export all models
│   ├── session.py           # ChatSession model
│   ├── message.py           # ChatMessage model
│   └── feedback.py          # FeedbackEntry model
├── services/
│   ├── chat/
│   │   ├── __init__.py
│   │   ├── handler.py       # ChatHandler orchestration
│   │   ├── context.py       # Context window management
│   │   └── rate_limit.py    # Rate limiting service
│   └── feedback/
│       ├── __init__.py
│       └── collector.py     # Feedback persistence
├── controllers/
│   ├── __init__.py
│   ├── chat.py              # RHChat handler
│   ├── sessions.py          # RHSessionList, RHSessionDetail, RHSessionDelete
│   └── feedback.py          # RHFeedback handler
├── schemas/
│   ├── __init__.py
│   ├── chat.py              # Pydantic: ChatRequest, ChatResponse
│   ├── session.py           # Pydantic: SessionListResponse, etc.
│   └── feedback.py          # Pydantic: FeedbackRequest, FeedbackResponse
└── tasks/
    ├── __init__.py
    └── cleanup.py           # Celery task for 90-day cleanup
```

## Implementation Steps

### Step 1: Database Migration

Create migration `002_create_chat_tables.py`:

```bash
cd indico_assistant_plugin
indico db upgrade  # After adding migration
```

### Step 2: Models

```python
# models/session.py
from indico.core.db import db
from sqlalchemy.dialects.postgresql import UUID, JSONB

class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'
    __table_args__ = {'schema': 'plugin_assistant'}
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    event_id = db.Column(db.Integer, nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    messages = db.relationship('ChatMessage', backref='session', lazy='dynamic', cascade='all, delete-orphan')
```

### Step 3: Controllers (Indico RH Pattern)

```python
# controllers/chat.py
from indico.web.rh import RH

class RHChat(RH):
    """POST /api/assistant/chat"""
    
    def _process(self):
        # 1. Validate request
        data = ChatRequest(**request.json)
        
        # 2. Check rate limit
        rate_limiter.check_or_raise(session.user.id, 'chat')
        
        # 3. Validate session ownership if provided
        if data.session_id:
            chat_session = ChatSession.query.get_or_404(data.session_id)
            if chat_session.user_id != session.user.id:
                raise Forbidden("Session belongs to another user")
        
        # 4. Validate event access if provided
        if data.event_id:
            event = Event.get_or_404(data.event_id)
            if not event.can_access(session.user):
                raise Forbidden("No access to this event")
        
        # 5. Process chat
        result = chat_handler.process(data, session.user)
        
        # 6. Return response
        return jsonify(ChatResponse(**result).dict())
```

### Step 4: Context Window

```python
# services/chat/context.py
def get_conversation_context(session_id: UUID, limit: int = 10) -> list[dict]:
    """Get last N message pairs for context."""
    messages = ChatMessage.query.filter_by(session_id=session_id)\
        .order_by(ChatMessage.created_at.desc())\
        .limit(limit * 2)\  # pairs = user + assistant
        .all()
    return [{"role": m.role, "content": m.content} for m in reversed(messages)]
```

### Step 5: Rate Limiting

```python
# services/chat/rate_limit.py
class RateLimiter:
    LIMITS = {
        'chat': (60, 60),      # 60 requests per 60 seconds
        'read': (200, 60),     # 200 requests per 60 seconds
    }
    
    def check_or_raise(self, user_id: int, endpoint_type: str):
        limit, window = self.LIMITS[endpoint_type]
        key = f"rate:{user_id}:{endpoint_type}"
        
        # Redis or in-memory implementation
        if self._is_rate_limited(key, limit, window):
            raise RateLimitExceeded(retry_after=window)
```

### Step 6: Blueprint Registration

```python
# blueprint.py
@blueprint.route('/chat', methods=['POST'])
def chat():
    return RHChat().process()

@blueprint.route('/sessions', methods=['GET'])
def list_sessions():
    return RHSessionList().process()

@blueprint.route('/sessions/<uuid:session_id>', methods=['GET'])
def get_session(session_id):
    return RHSessionDetail().process()

@blueprint.route('/sessions/<uuid:session_id>', methods=['DELETE'])
def delete_session(session_id):
    return RHSessionDelete().process()

@blueprint.route('/feedback', methods=['POST'])
def submit_feedback():
    return RHFeedback().process()
```

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_chat_api.py -v

# Run with coverage
pytest tests/ --cov=indico_assistant --cov-report=html
```

### Test Scenarios

```python
# tests/test_chat_api.py
def test_chat_new_session(client, authenticated_user):
    response = client.post('/api/assistant/chat', json={
        'message': 'How many events?'
    })
    assert response.status_code == 200
    assert 'session_id' in response.json
    assert 'response' in response.json

def test_chat_continue_session(client, authenticated_user, existing_session):
    response = client.post('/api/assistant/chat', json={
        'message': 'Break that down by category',
        'session_id': str(existing_session.id)
    })
    assert response.status_code == 200

def test_session_ownership(client, authenticated_user, other_users_session):
    response = client.post('/api/assistant/chat', json={
        'message': 'Test',
        'session_id': str(other_users_session.id)
    })
    assert response.status_code == 403
```

## Configuration

```python
# config.py
CHAT_API_CONFIG = {
    'context_window_size': 10,          # Message pairs
    'max_message_length': 10000,        # Characters
    'session_retention_days': 90,
    'rate_limit_chat': 60,              # Per minute
    'rate_limit_read': 200,             # Per minute
}
```

## Error Handling

All endpoints return consistent error format:

```json
{
    "error": "ERROR_CODE",
    "message": "Human-readable message",
    "details": { "field": "value" }
}
```

Error codes:
- `VALIDATION_ERROR` - Invalid request data
- `UNAUTHORIZED` - Not authenticated
- `FORBIDDEN` - Access denied
- `NOT_FOUND` - Resource not found
- `UNPROCESSABLE_QUERY` - NL2SQL failed
- `RATE_LIMITED` - Too many requests
- `INTERNAL_ERROR` - Server error

## Common Issues

### Issue: Session not found after creation
**Cause**: Transaction not committed
**Solution**: Ensure `db.session.commit()` after creating session

### Issue: Rate limit not working
**Cause**: Redis not connected
**Solution**: Check Redis connection, falls back to in-memory

### Issue: Event access check failing
**Cause**: User lacks event permissions
**Solution**: Verify user has at least read access to event

## Next Steps

After implementing the Chat API:

1. Run all tests to verify functionality
2. Test manually via Postman/curl
3. Update frontend to use new endpoints
4. Monitor Langfuse for query patterns
