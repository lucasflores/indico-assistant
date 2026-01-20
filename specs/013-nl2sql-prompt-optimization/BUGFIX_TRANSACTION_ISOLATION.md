## Bug Fixes: Transaction Isolation and Event Context

**Feature:** 013-nl2sql-prompt-optimization  
**Date:** 2025-01-21

### Issue 1: Foreign Key Violation on Chat Message Persistence

**Symptom:**
```
(psycopg2.errors.ForeignKeyViolation) insert or update on table "chat_messages" 
violates foreign key constraint "fk_chat_messages_session_id_chat_sessions"
DETAIL: Key (session_id)=(cbebcb1f-f0e6-4187-973f-7751fc9806f0) is not present 
in table "chat_sessions".
```

**Root Cause:**
The `QueryExecutor` was calling `session.rollback()` on the main `db.session` when SQL queries 
failed. Since the NL2SQL pipeline and chat service both use the same database session 
(`indico.core.db.session`), this rollback was undoing the entire transaction including:
1. Chat session creation (via `ChatSession.create()`)
2. User message creation (via `ChatMessage.create()`)

Then when the chat service tried to save the error response as an assistant message, the 
session_id foreign key reference was invalid because the session had been rolled back.

**Fix:**
Modified `indico_assistant/services/nl2sql/executor.py` to use **nested transactions** (SAVEPOINTs):

```python
with session.begin_nested():
    # Execute SQL query
    # Set timeout, execute, fetch results
```

Benefits:
- Query execution is isolated in a SAVEPOINT
- If SQL fails, only the nested transaction rolls back
- Parent transaction (session/message creation) remains intact
- No explicit `session.rollback()` needed - handled automatically

**Files Changed:**
- `indico_assistant/services/nl2sql/executor.py` (lines 54-180)
- `tests/unit/services/nl2sql/test_executor_transaction.py` (new file)

**Test Coverage:**
- `test_sql_error_does_not_rollback_parent_transaction()` - Verifies no explicit rollback
- `test_successful_query_uses_nested_transaction()` - Ensures consistency
- `test_execution_error_does_not_call_rollback()` - Covers validation errors
- `test_generic_exception_does_not_call_rollback()` - Covers unexpected errors

All 29 existing executor tests still pass.

---

### Issue 2: Missing Event Context for NL2SQL Queries

**Symptom:**
When users asked "what is the event id of this meeting?" from an event page 
(`/event/123/manage/...`), the NL2SQL pipeline couldn't determine the event_id because:
1. The chat widget JavaScript didn't extract event_id from the URL
2. The Chainlit backend app didn't receive event context
3. The `/api/assistant/chat` endpoint didn't get event_id in the request body

**Root Cause:**
The Chainlit copilot widget is a generic third-party component that doesn't know about 
Indico's URL structure. The payload sent to `/api/assistant/chat` only included:
```json
{
  "message": "user message",
  "session_id": "uuid (optional)"
}
```

No `event_id` field was being populated.

**Fix:**
Modified `chainlit_app/app_chnlit.py` to extract event_id from the HTTP Referer header:

```python
# Extract event_id from Referer header if present
# Indico event URLs follow pattern: /event/{event_id}/...
event_id = cl.user_session.get("indico_event_id")
if event_id is None:
    try:
        context = getattr(cl, "context", None)
        request = getattr(context, "current_request", None) if context else None
        if request and hasattr(request, "headers"):
            referer = request.headers.get("Referer") or request.headers.get("referer", "")
            if referer:
                import re
                match = re.search(r'/event/(\d+)/', referer)
                if match:
                    event_id = int(match.group(1))
                    cl.user_session.set("indico_event_id", event_id)
    except Exception:
        logger.debug("Unable to extract event_id from Referer", exc_info=True)

if event_id:
    payload["event_id"] = event_id
```

**How It Works:**
1. When the Chainlit copilot widget is loaded on an Indico event page, the browser sends 
   the Referer header with the full page URL (e.g., `https://indico.cern.ch/event/123/manage/...`)
2. Chainlit backend extracts `event_id` from the Referer using regex `/event/(\d+)/`
3. Stores it in the user session for subsequent messages
4. Includes it in the payload to `/api/assistant/chat`
5. Chat service passes it to NL2SQL pipeline
6. Generator injects `:event_id` parameter and `CURRENT EVENT ID: 123` context

**Files Changed:**
- `chainlit_app/app_chnlit.py` (lines 218-240)

**Limitations:**
- Only works when the widget is accessed from an event page (has `/event/{id}/` in URL)
- Relies on browser sending Referer header (most browsers do, some privacy extensions block it)
- If user navigates between events, event_id is cached until session restart

**Alternative Approaches Considered:**
1. **Modify JWT token to include event_id** - Rejected because JWT is generated once per 
   user session and reused across pages. Would require regenerating on every navigation.
2. **Custom JavaScript widget modification** - Rejected because we're using the third-party 
   Chainlit copilot widget which we don't control.
3. **WebSocket message metadata** - Rejected because Chainlit copilot doesn't expose hooks 
   to inject custom metadata into messages.

---

### Testing

**Unit Tests:**
```bash
pytest tests/unit/services/nl2sql/test_executor_transaction.py -v
# 4 tests pass
```

**Integration Tests:**
To verify the fixes work end-to-end:
1. Start Chainlit backend: `cd chainlit_app && chainlit run app_chnlit.py`
2. Navigate to event page: `/event/123/manage/...`
3. Open chat widget
4. Ask: "what is the event id of this meeting?"
5. Expected: SQL should include `WHERE event_id = :event_id` with event_id=123
6. Ask a query that triggers SQL error (e.g., "show me data from nonexistent_table")
7. Expected: Error message displayed, session still valid for next message

**Regression Tests:**
```bash
pytest tests/unit/services/nl2sql/test_executor.py -v
# 29 tests pass - no regressions
```

---

### Impact

**Transaction Isolation Fix:**
- **Severity:** Critical - Was causing data loss (audit logs) and user-facing errors
- **Affected Users:** Any user whose NL2SQL query triggered SQL errors
- **Fix Confidence:** High - Uses standard SQLAlchemy nested transaction pattern

**Event Context Fix:**
- **Severity:** Medium - Feature degradation, queries lacked necessary scope
- **Affected Users:** Users asking event-specific questions from event pages
- **Fix Confidence:** Medium - Relies on Referer header which may be blocked by privacy tools

---

### Related Tasks

**Completed:**
- T001-T050: All NL2SQL prompt optimization tasks except T049 (manual validation)

**Remaining:**
- T049: Manual quickstart validation (deferred until transaction fixes confirmed in production)

**Future Improvements:**
1. Consider adding event_id to JWT token for more reliable event context
2. Add telemetry to track how often Referer extraction fails
3. Implement fallback: prompt user to select event if context missing
