# Research: User ID Passthrough Fix

**Feature**: 016-user-id-passthrough  
**Date**: 2026-01-21  
**Status**: Complete

## Research Tasks

### 1. Root Cause Analysis: Why is user_id returning null?

**Investigation**: Traced the user_id flow through the codebase:

1. **Controller layer** (`controllers/base.py`):
   - `_check_access()` attempts to get user from `session.user` first
   - Falls back to `_get_user_from_bearer_token()` for JWT auth
   - JWT extraction looks for `identifier` or `id` field in payload
   - Sets `self._user` if JWT user found

2. **Property access** (`controllers/base.py:126-131`):
   - `user` property returns `self._user` if set, else `session.user`
   - **Issue**: The `_user` attribute is only set when JWT auth succeeds

3. **Chat controller** (`controllers/chat.py:87`):
   - Passes `self.user.id` to `process_message()`
   - If `self.user` is None at this point, it would raise an error earlier in `_check_access()`

4. **Pipeline** (`services/nl2sql/pipeline.py:153`):
   - Receives `user_id: int` but the service passes `user_id or 0` as fallback
   - **Issue found**: `service.py:396` passes `user_id=user_id or 0`

**Root Cause Findings**:
- The `user_id or 0` fallback in `service.py` masks the actual issue
- JWT token may have user identifier in unexpected field names
- Session user may be None when using external widget (Chainlit)

**Decision**: Remove `user_id or 0` fallback; add explicit handling for missing identity

---

### 2. Personal Query Detection Patterns

**Investigation**: How to detect when a query requires user identity?

**Finding**: Use regex pattern matching in classifier or pre-processing:

```python
PERSONAL_PRONOUNS = r'\b(I|me|my|mine|myself)\b'
PERSONAL_PATTERNS = [
    r'\bmy\s+(meetings?|events?|contributions?|registrations?)\b',
    r'\bam\s+I\s+(registered|attending|speaking)\b',
    r'\bwhat\s+.*\s+do\s+I\s+have\b',
    r'\bshow\s+me\s+my\b',
]
```

**Decision**: Add `is_personal_query()` helper in classifier module

---

### 3. User Lookup by Name/Email

**Investigation**: How to find Indico users by name or email?

**Finding**: Indico's User model supports lookups:

```python
from indico.modules.users import User

# By email
user = User.query.filter(User.all_emails.contains(email)).first()

# By name (case-insensitive)
users = User.query.filter(
    db.func.lower(User.first_name) == first_name.lower(),
    db.func.lower(User.last_name) == last_name.lower()
).all()
```

**Decision**: Create `IdentityService` with lookup methods; handle multiple matches per FR-009

---

### 4. Session Persistence for Resolved Identity

**Investigation**: Where to store user-provided identity within a session?

**Options**:
1. Add column to `chat_sessions` table
2. Store in session metadata JSON
3. Store in first message metadata

**Decision**: Add `resolved_user_id` and `identity_source` columns to `ChatSession` model
- `resolved_user_id`: INTEGER nullable (the looked-up user ID)
- `identity_source`: VARCHAR (values: 'authenticated', 'user_provided', null)

This requires a migration but provides clear audit trail.

---

### 5. Identity Prompting Message Format

**Investigation**: What should the prompting message say?

**Requirement**: Per spec, must ask for name, email, or user ID

**Decision**: Use this template:
```
I can't seem to identify who you are right now. To help with your personal query, 
could you please provide one of the following:
- Your full name (e.g., "John Smith")
- Your email address
- Your Indico user ID (preferred for accuracy)

Once you provide this information, I'll be able to answer your question!
```

---

### 6. Trust Level Implementation

**Investigation**: How to implement read-only trust for user-provided identity?

**Finding**: The NL2SQL pipeline only generates SELECT statements (validated in `validator.py`), so the existing validation already ensures read-only. The disclaimer requirement (FR-013) needs to be added to response formatting.

**Decision**: 
- Add `identity_disclaimer` field to response when `identity_source='user_provided'`
- Disclaimer text: "Note: These results are based on the identity you provided. For verified access, please log in."

---

## Summary of Decisions

| Topic | Decision |
|-------|----------|
| Root cause | Remove `user_id or 0` fallback; trace actual None source |
| Personal query detection | Regex patterns for pronouns + context |
| User lookup | Use Indico's User model with email/name filters |
| Session storage | Add `resolved_user_id` + `identity_source` columns |
| Prompting message | Friendly message asking for name/email/ID |
| Trust implementation | Existing SELECT-only validation + disclaimer in response |

## Outstanding Questions

None - all clarifications resolved in spec.
