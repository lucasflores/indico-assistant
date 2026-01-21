# Quickstart: User ID Passthrough Fix

**Feature**: 016-user-id-passthrough  
**Date**: 2026-01-21

## Overview

This feature fixes the user_id passthrough issue where personalized queries fail because user identity is not properly propagated through the system. It also adds graceful identity prompting when authentication context is unavailable.

## Prerequisites

- Indico installation with Assistant plugin
- PostgreSQL database with `plugin_assistant` schema
- LLM service configured (Ollama or HuggingFace)

## Quick Test

### Test 1: Authenticated Personal Query

1. Log into Indico as a user with event registrations
2. Open the chat assistant widget
3. Ask: "What meetings do I have this week?"
4. **Expected**: Returns list of your meetings (not empty, not error)

### Test 2: Identity Prompting (if testing unauthenticated)

1. Access chat without authentication (if possible in test mode)
2. Ask: "What meetings do I have?"
3. **Expected**: Assistant responds with identity prompt message
4. Reply: "My email is yourname@example.com"
5. **Expected**: Assistant finds your account and returns your meetings

### Test 3: Non-Personal Query (no identity needed)

1. Ask: "What events are happening next week?"
2. **Expected**: Returns public events without requiring identity

## Implementation Checklist

### Phase 1: Fix Core Issue (P1)

- [ ] Debug JWT token extraction in `controllers/base.py`
- [ ] Remove `user_id or 0` fallback in `services/chat/service.py`
- [ ] Add logging to trace user_id through the chain
- [ ] Verify user_id reaches SQL generator

### Phase 2: Identity Prompting (P2)

- [ ] Add personal query detection (`is_personal_query()`)
- [ ] Create `IdentityService` with user lookup methods
- [ ] Add `resolved_user_id` column to ChatSession
- [ ] Implement prompting flow in ChatService
- [ ] Add disclaimer for user-provided identity

### Phase 3: Polish (P3)

- [ ] Add identity_status to response metadata
- [ ] Handle multiple user matches with count
- [ ] Write integration tests
- [ ] Update API documentation

## Key Files to Modify

| File | Change |
|------|--------|
| `controllers/base.py` | Fix JWT user extraction edge cases |
| `services/chat/service.py` | Remove fallback, add identity resolution |
| `services/chat/identity.py` | NEW: Identity resolution service |
| `services/nl2sql/classifier.py` | Add `is_personal_query()` |
| `models/session.py` | Add identity columns |
| `schemas/chat.py` | Add identity_status to response |

## Testing Commands

```bash
# Run unit tests for identity service
pytest tests/unit/services/chat/test_identity.py -v

# Run integration tests
pytest tests/integration/test_user_id_passthrough.py -v

# Run all chat tests
pytest tests/ -k "chat" -v
```

## Troubleshooting

### user_id still null after fix

1. Check JWT token content: `print(payload)` in `_get_user_from_bearer_token()`
2. Verify token has `identifier` or `id` field
3. Check `CHAINLIT_AUTH_SECRET` is configured

### Personal query not detected

1. Check regex patterns in `is_personal_query()`
2. Test with exact phrases: "my meetings", "what do I have"

### User lookup returns empty

1. Verify user exists in Indico database
2. Check email matches exactly (case-insensitive)
3. For names, check both first_name and last_name populated
