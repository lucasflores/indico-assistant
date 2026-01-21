# Data Model: User ID Passthrough Fix

**Feature**: 016-user-id-passthrough  
**Date**: 2026-01-21

## Entity Changes

### ChatSession (Modified)

**Table**: `plugin_assistant.chat_sessions`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | UUID | NO | Primary key |
| user_id | INTEGER | NO | Authenticated user ID (existing) |
| event_id | INTEGER | YES | Event scope (existing) |
| **resolved_user_id** | INTEGER | YES | **NEW**: User ID resolved from user-provided identity |
| **identity_source** | VARCHAR(20) | YES | **NEW**: How identity was determined |
| created_at | TIMESTAMP | NO | Session creation (existing) |
| updated_at | TIMESTAMP | NO | Last activity (existing) |

**Identity Source Values**:
- `authenticated` - User ID from session/JWT authentication
- `user_provided` - User ID resolved from name/email provided by user
- `null` - Identity not yet determined

**Relationships**: No changes to existing relationships

---

### IdentityResolution (New Concept - Not Persisted)

This is a runtime data structure, not a database entity.

```python
@dataclass
class IdentityResolution:
    """Result of identity resolution attempt."""
    user_id: int | None
    source: str  # 'authenticated', 'user_provided', 'unknown'
    confidence: str  # 'high' (authenticated), 'medium' (exact match), 'low' (partial)
    disclaimer: str | None  # Disclaimer text if user_provided
    needs_clarification: bool  # True if multiple matches found
    match_count: int  # Number of users matched (for disambiguation)
```

---

## State Transitions

### Identity Resolution Flow

```
┌─────────────────┐
│   START         │
│ (New Message)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     YES    ┌─────────────────┐
│ Session has     ├───────────►│ Use existing    │
│ resolved_user_id│            │ identity        │
└────────┬────────┘            └─────────────────┘
         │ NO
         ▼
┌─────────────────┐     YES    ┌─────────────────┐
│ User is         ├───────────►│ Set source =    │
│ authenticated?  │            │ 'authenticated' │
└────────┬────────┘            └─────────────────┘
         │ NO
         ▼
┌─────────────────┐     NO     ┌─────────────────┐
│ Is personal     ├───────────►│ Process query   │
│ query?          │            │ without user_id │
└────────┬────────┘            └─────────────────┘
         │ YES
         ▼
┌─────────────────┐     YES    ┌─────────────────┐
│ Previous        ├───────────►│ Lookup user by  │
│ identity info   │            │ provided info   │
│ in context?     │            └────────┬────────┘
└────────┬────────┘                     │
         │ NO                           ▼
         ▼                    ┌─────────────────┐
┌─────────────────┐           │ Found exactly   │
│ Return identity │     YES   │ 1 match?        │
│ prompt message  │◄──────────┤                 │
└─────────────────┘     NO    └────────┬────────┘
                                       │ YES
                                       ▼
                              ┌─────────────────┐
                              │ Set resolved_   │
                              │ user_id, source │
                              │ = 'user_provided'│
                              └─────────────────┘
```

---

## Validation Rules

1. `resolved_user_id` must reference a valid Indico user ID
2. `identity_source` must be one of: 'authenticated', 'user_provided', or null
3. If `identity_source` = 'user_provided', response must include disclaimer
4. If `identity_source` = null and query is personal, return prompting message

---

## Migration Required

**Migration**: `005_add_identity_columns.py`

```sql
ALTER TABLE plugin_assistant.chat_sessions 
ADD COLUMN resolved_user_id INTEGER;

ALTER TABLE plugin_assistant.chat_sessions 
ADD COLUMN identity_source VARCHAR(20);

-- Index for potential queries by resolved_user_id
CREATE INDEX ix_chat_sessions_resolved_user_id 
ON plugin_assistant.chat_sessions (resolved_user_id);
```
