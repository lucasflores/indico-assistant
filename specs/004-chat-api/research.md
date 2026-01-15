# Research: Chat REST API

**Feature**: 004-chat-api | **Date**: 2026-01-14

## Research Tasks

### 1. Indico RH Pattern for Authenticated JSON APIs

**Decision**: Use Indico's `RH` base class with `_check_access()` for authentication

**Rationale**: 
- Indico's `RH` (Request Handler) provides built-in authentication via `session.user`
- Override `_check_access()` to enforce login requirement
- Use `@jsonify_data` decorator or `return jsonify(data)` for JSON responses
- Access current user via `session.user.id` and `session.user.email`

**Implementation Pattern**:
```python
from indico.web.rh import RH
from flask import jsonify, session

class RHChatBase(RH):
    """Base class for authenticated chat endpoints."""
    
    def _check_access(self):
        if session.user is None:
            raise Unauthorized()  # Returns 401
```

**Alternatives Considered**:
- Flask-Login: Rejected - Indico has its own auth system
- Custom JWT: Rejected - Would bypass Indico's session management

---

### 2. Rate Limiting in Indico Plugins

**Decision**: Use Redis-backed token bucket with in-memory fallback

**Rationale**:
- Redis provides distributed rate limiting across workers
- In-memory fallback ensures degraded operation if Redis unavailable
- Token bucket algorithm allows bursts while enforcing average rate
- Per-user limits keyed by `user_id`

**Implementation Pattern**:
```python
class RateLimiter:
    def __init__(self, redis_client=None, default_rate=60, window_seconds=60):
        self._redis = redis_client
        self._memory_store = {}  # Fallback
        
    def check_rate(self, user_id: int, rate: int = None) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
```

**Alternatives Considered**:
- Flask-Limiter: Rejected - Not integrated with Indico's Redis
- Nginx rate limiting: Rejected - Can't do per-user limiting at proxy level

---

### 3. Session Cleanup Strategy

**Decision**: Scheduled Celery task for 90-day cleanup

**Rationale**:
- Indico uses Celery for background tasks
- Daily cleanup task deletes sessions with `updated_at < now - 90 days`
- Batch deletion to avoid long transactions
- Cascade delete handles messages and feedback

**Implementation Pattern**:
```python
@celery.task
def cleanup_expired_sessions():
    """Delete sessions older than 90 days."""
    cutoff = datetime.utcnow() - timedelta(days=90)
    ChatSession.query.filter(ChatSession.updated_at < cutoff).delete()
```

**Alternatives Considered**:
- PostgreSQL TTL/partitioning: Rejected - Adds complexity, Celery already available
- On-access lazy deletion: Rejected - Doesn't free storage proactively

---

### 4. Conversation Context Window

**Decision**: Include last 10 message pairs (20 messages) in LLM context

**Rationale**:
- 10 pairs provides sufficient context for follow-up questions
- Keeps token count manageable (~4K tokens typical)
- Newer messages prioritized (oldest truncated first if needed)
- Context formatted as chat history for LLM

**Implementation Pattern**:
```python
class ContextBuilder:
    MAX_PAIRS = 10
    
    def build_context(self, session_id: UUID) -> list[dict]:
        messages = ChatMessage.query.filter_by(session_id=session_id)\
            .order_by(ChatMessage.created_at.desc())\
            .limit(self.MAX_PAIRS * 2)\
            .all()
        return [{"role": m.role, "content": m.content} for m in reversed(messages)]
```

**Alternatives Considered**:
- Sliding window with summarization: Rejected - Adds latency, complexity
- All messages: Rejected - Token limits, cost concerns

---

### 5. Event Access Validation

**Decision**: Use Indico's `can_access()` method on Event objects

**Rationale**:
- Indico's Event model has built-in ACL checking
- `event.can_access(user)` returns True/False based on permissions
- Handles all permission types (public, protected, private)
- Consistent with Indico's security model

**Implementation Pattern**:
```python
from indico.modules.events import Event

def validate_event_access(user, event_id: int) -> bool:
    event = Event.get_or_404(event_id)
    return event.can_access(user)
```

**Alternatives Considered**:
- Custom ACL queries: Rejected - Would duplicate Indico's logic
- Cache permissions: Rejected - ACLs can change, freshness matters

---

### 6. Error Response Format

**Decision**: Consistent JSON format: `{"error": "code", "message": "text", "details": {...}}`

**Rationale**:
- Simple, predictable structure for frontend developers
- `error` code for programmatic handling
- `message` for user display
- `details` for additional context (optional)

**Implementation Pattern**:
```python
def error_response(code: str, message: str, details: dict = None, status: int = 400):
    response = {"error": code, "message": message}
    if details:
        response["details"] = details
    return jsonify(response), status
```

**Error Codes**:
- `validation_error`: Invalid input (400)
- `unauthorized`: Not authenticated (401)
- `forbidden`: No access to resource (403)
- `not_found`: Resource doesn't exist (404)
- `rate_limited`: Too many requests (429)
- `pipeline_error`: NL2SQL processing failed (500)

---

### 7. Database Transaction Patterns

**Decision**: Use Indico's `db.session` with explicit commits

**Rationale**:
- Indico manages the SQLAlchemy session
- Use `db.session.add()` and `db.session.commit()` for writes
- Use `db.session.rollback()` in exception handlers
- Avoid long transactions (commit after each logical operation)

**Implementation Pattern**:
```python
from indico.core.db import db

def create_session(user_id: int, event_id: int = None) -> ChatSession:
    session = ChatSession(user_id=user_id, event_id=event_id)
    db.session.add(session)
    db.session.commit()
    return session
```

**Alternatives Considered**:
- Context manager transactions: Rejected - Indico's patterns don't use this
- Autocommit: Rejected - Need explicit control for error handling

---

## Dependency Versions

| Dependency | Version | Purpose |
|------------|---------|---------|
| Flask | (via Indico) | Web framework, request handling |
| SQLAlchemy | (via Indico) | ORM, database models |
| Pydantic | 2.x | Request/response validation |
| Redis | 4.x+ | Rate limiting, caching |
| Celery | (via Indico) | Background tasks |

## Open Questions (Resolved)

All open questions from specification have been resolved through clarification process:
- ✅ Session retention: 90 days
- ✅ Context window: 10 message pairs
- ✅ Access revocation: Sessions visible, queries blocked
- ✅ Error format: Simple JSON
- ✅ Session deletion: Individual via DELETE endpoint
