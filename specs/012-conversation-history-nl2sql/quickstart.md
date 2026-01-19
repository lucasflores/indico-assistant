# Quickstart: Conversation History for NL2SQL Pipeline

**Feature**: 012-conversation-history-nl2sql  
**Audience**: Developers  
**Time**: 20 minutes

## Overview

This guide shows how to implement conversation history support in the NL2SQL pipeline step-by-step, test it locally, and verify co-reference resolution works correctly.

---

## Prerequisites

- Indico development environment running
- Plugin installed and enabled
- Existing chat sessions with multiple messages
- Python 3.11+ with type hints
- Familiarity with NL2SQL pipeline structure

---

## Implementation Guide (15 minutes)

### Step 1: Add Parameter to Generator (5 minutes)

**File**: `indico_assistant/services/nl2sql/generator.py`

**1.1 Add helper methods at the bottom of the SQLGenerator class:**

```python
def _truncate_message(self, content: str, max_chars: int = 1500) -> str:
    """Truncate message content to maximum length with ellipsis.
    
    Args:
        content: Original message content
        max_chars: Maximum characters (default 1500 per FR-012)
        
    Returns:
        Original content if under limit, or truncated with "..."
    """
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "..."

def _format_conversation_history(
    self,
    conversation_history: list[dict[str, str]] | None
) -> str:
    """Format conversation history for prompt inclusion.
    
    Args:
        conversation_history: List of messages with 'role' and 'content' keys
        
    Returns:
        Formatted string with numbered messages, or empty string if no history
    """
    if not conversation_history:
        return ""
    
    # Enforce 10-pair (20 message) limit
    recent_history = conversation_history[-20:]
    
    formatted = ["CONVERSATION HISTORY:"]
    for idx, msg in enumerate(recent_history, start=1):
        role = msg["role"].capitalize()  # "User" or "Assistant"
        content = self._truncate_message(msg["content"])
        formatted.append(f"{idx}. {role}: {content}")
    
    return "\n".join(formatted)
```

**1.2 Update SQL_GENERATION_PROMPT template (around line 24):**

Find the current template and add `{conversation_history}` line:

```python
SQL_GENERATION_PROMPT = """You are a SQL query generator for Indico...

AVAILABLE SCHEMA:
{schema_context}

{conversation_history}

USER QUESTION: {question}

CLASSIFICATION:
..."""
```

**1.3 Update generate() method signature (around line 89):**

```python
def generate(
    self,
    question: str,
    schema_context: str,
    conversation_history: list[dict[str, str]] | None = None  # ADD THIS
) -> dict:
    """Generate SQL query using LLM with optional conversation history.
    
    Args:
        question: User's current question
        schema_context: Database schema information
        conversation_history: Optional list of prior messages
    """
    # Format conversation history
    history_section = self._format_conversation_history(
        conversation_history or []
    )
    
    # Build prompt
    prompt = SQL_GENERATION_PROMPT.format(
        schema_context=schema_context,
        conversation_history=history_section,  # ADD THIS
        question=question
    )
    
    # Rest of method unchanged...
```

---

### Step 2: Update Pipeline (3 minutes)

**File**: `indico_assistant/services/nl2sql/pipeline.py`

**2.1 Update process() method signature (around line 144):**

```python
async def process(
    self,
    question: str,
    user_id: int,
    event_ids: list[int] | None = None,
    conversation_history: list[dict[str, str]] | None = None  # ADD THIS
) -> dict:
    """Process natural language question into SQL query.
    
    Args:
        question: User's current question
        user_id: User making the request
        event_ids: Optional event scope for query
        conversation_history: Optional conversation context
    """
    # ... existing schema retrieval logic ...
    
    # Update generator call to include conversation_history
    sql_result = await self.generator.generate(
        question=question,
        schema_context=schema,
        conversation_history=conversation_history  # ADD THIS
    )
    
    return sql_result
```

---

### Step 3: Update Chat Service (2 minutes)

**File**: `indico_assistant/services/chat/service.py`

**3.1 Update _process_with_nl2sql() method (around line 150):**

Find the pipeline.process() call and add conversation_history parameter:

```python
async def _process_with_nl2sql(self, ...):
    # ... existing context building logic ...
    
    # Context is already built around line 148:
    context = self.context_builder.build_context(session_id)
    
    # Update this call (around line 150-152):
    result = await self.nl2sql_pipeline.process(
        question=enhanced_question,
        user_id=user_id,
        event_ids=event_ids,
        conversation_history=context  # ADD THIS
    )
    
    return result
```

---

### Step 4: Verify Implementation (5 minutes)

**4.1 Check syntax:**

```bash
cd /Users/lucasflores/dev2/indico/plugins_lucas/indico_assistant_plugin

# Check for syntax errors
python3 -m py_compile indico_assistant/services/nl2sql/generator.py
python3 -m py_compile indico_assistant/services/nl2sql/pipeline.py
python3 -m py_compile indico_assistant/services/chat/service.py
```

**4.2 Run existing tests (should pass unchanged):**

```bash
# Run existing pipeline tests
pytest tests/unit/services/nl2sql/test_generator.py -v
pytest tests/unit/services/nl2sql/test_pipeline.py -v

# Expected: All existing tests pass (backward compatibility)
```

---

## Quick Test (5 minutes)

### Test 1: Co-reference Resolution

**Via Python REPL:**

```python
from indico_assistant.services.nl2sql.generator import SQLGenerator

generator = SQLGenerator(...)

# Test formatting
history = [
    {"role": "user", "content": "What events are happening this week?"},
    {"role": "assistant", "content": "ICHEP 2024 and CMS Week are scheduled."},
    {"role": "user", "content": "Tell me more about the first one"}
]

formatted = generator._format_conversation_history(history)
print(formatted)

# Expected output:
# CONVERSATION HISTORY:
# 1. User: What events are happening this week?
# 2. Assistant: ICHEP 2024 and CMS Week are scheduled.
# 3. User: Tell me more about the first one
```

### Test 2: Empty History (Backward Compatibility)

```python
# Test with None
formatted = generator._format_conversation_history(None)
assert formatted == ""

# Test with empty list
formatted = generator._format_conversation_history([])
assert formatted == ""
```

### Test 3: Message Truncation

```python
# Test long message truncation
long_message = "A" * 2000
history = [{"role": "user", "content": long_message}]

formatted = generator._format_conversation_history(history)
assert "..." in formatted
assert len(formatted) < 2000  # Truncated
```

---

## End-to-End Test (via Chat UI)

### Scenario: Follow-up Question with Co-reference

**1. Start a new chat session:**
```
Navigate to: http://localhost:8000/assistant/chat
```

**2. Send first message:**
```
User: What events are happening this week?
```

**Expected Response:**
```
Assistant: ICHEP 2024 and CMS Week are scheduled this week.
[Shows event details...]
```

**3. Send follow-up with co-reference:**
```
User: Tell me more about the first one
```

**Expected Response (BEFORE this feature):**
```
Assistant: I'm not sure what "the first one" refers to.
[Generic response or incorrect query]
```

**Expected Response (AFTER this feature):**
```
Assistant: ICHEP 2024 is...
[Shows details specifically about ICHEP 2024]
```

✅ **Success**: Assistant correctly resolves "the first one" to "ICHEP 2024"

---

## Verify in Logs

**Watch for conversation history in prompts:**

```bash
tail -f logs/indico.log | grep "CONVERSATION HISTORY"

# Expected output when follow-up question is asked:
# DEBUG indico_assistant.services.nl2sql.generator - Prompt includes:
# CONVERSATION HISTORY:
# 1. User: What events are happening this week?
# 2. Assistant: ICHEP 2024 and CMS Week...
```

---

## Troubleshooting

### Issue 1: Tests Fail with "Missing Parameter" Error

**Symptom**:
```
TypeError: process() missing 1 required positional argument: 'conversation_history'
```

**Fix**: Ensure conversation_history has default value `= None` in all signatures

```python
# WRONG
def process(..., conversation_history: list[dict[str, str]]):

# CORRECT
def process(..., conversation_history: list[dict[str, str]] | None = None):
```

---

### Issue 2: History Not Showing in Prompt

**Symptom**: Follow-up questions still fail to resolve co-references

**Debug**:
```python
# Add logging in generator.py
logger.debug(f"Conversation history: {conversation_history}")
logger.debug(f"Formatted history: {history_section}")
logger.debug(f"Full prompt: {prompt[:500]}...")
```

**Check**:
1. Is `context` being built in ChatService? (Should have messages)
2. Is `context` being passed to pipeline? (Check service.py line ~152)
3. Is pipeline forwarding to generator? (Check pipeline.py)
4. Is generator formatting history? (Check _format_conversation_history call)

---

### Issue 3: Empty History Even When Messages Exist

**Symptom**: `conversation_history` is always empty or None

**Fix**: Verify ContextBuilder is being called correctly

```python
# In service.py, verify this line exists:
context = self.context_builder.build_context(session_id)

# Check context_builder.py - should return list of dicts:
def build_context(self, session_id: int) -> list[dict[str, str]]:
    messages = ChatMessage.query.filter_by(session_id=session_id).limit(20).all()
    return [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]
```

---

### Issue 4: Messages in Wrong Order

**Symptom**: Newest messages appear first in history

**Fix**: ContextBuilder should return chronological order (oldest first)

```python
# In context_builder.py:
messages = (
    ChatMessage.query
    .filter_by(session_id=session_id)
    .order_by(ChatMessage.created_at.desc())  # Newest first from DB
    .limit(20)
    .all()
)

return [
    {"role": msg.role, "content": msg.content}
    for msg in reversed(messages)  # Reverse to chronological order
]
```

---

## Validation Checklist

After implementation, verify:

- [ ] Generator has `_format_conversation_history()` method
- [ ] Generator has `_truncate_message()` method
- [ ] `SQL_GENERATION_PROMPT` includes `{conversation_history}` placeholder
- [ ] Generator.generate() accepts `conversation_history` parameter
- [ ] Pipeline.process() accepts `conversation_history` parameter
- [ ] ChatService passes `context` to pipeline
- [ ] All existing tests pass unchanged
- [ ] Empty history produces empty string (no errors)
- [ ] Follow-up questions resolve co-references correctly
- [ ] Messages truncate at 1500 characters
- [ ] Only last 20 messages included in history

---

## Next Steps After Implementation

1. **Add Unit Tests** (see tasks.md T012-T014):
   - Test `_format_conversation_history()` formatting
   - Test `_truncate_message()` truncation
   - Test empty history handling

2. **Add Integration Tests** (see tasks.md T015):
   - Test pipeline with mock conversation history
   - Test multi-turn conversations

3. **Add E2E Tests** (see tasks.md T016-T018):
   - Test "the first one" scenario from spec
   - Test "meeting about nothing" scenario from spec
   - Test "third person" scenario from spec

4. **Performance Validation** (see tasks.md T039-T040):
   - Benchmark P95 latency with/without history
   - Verify <100ms increase

5. **Production Deployment**:
   - Deploy to staging environment
   - Monitor conversation success rates
   - Collect user feedback on follow-up question accuracy

---

## Files Modified Summary

| File | Changes | Lines Changed |
|------|---------|---------------|
| `generator.py` | Add helper methods, update template, update generate() | ~40 lines |
| `pipeline.py` | Add parameter, forward to generator | ~3 lines |
| `service.py` | Pass context to pipeline | ~1 line |
| **Total** | | **~44 lines** |

---

## Time Estimate

- **Implementation**: 15 minutes
- **Quick Testing**: 5 minutes
- **E2E Validation**: 10 minutes
- **Total**: ~30 minutes for MVP implementation

---

## Common Mistakes to Avoid

1. ❌ **Forgetting default parameter**: All layers need `= None` default
2. ❌ **Wrong parameter order**: conversation_history should be last parameter
3. ❌ **Not handling empty history**: Check for None/empty before formatting
4. ❌ **Incorrect history format**: Must be `[{"role": str, "content": str}]`
5. ❌ **Breaking existing tests**: Make sure optional parameter maintains backward compatibility

---

**Status**: ✅ Quickstart complete - Follow these steps for successful implementation

**Reference**: See [tasks.md](tasks.md) for detailed task breakdown and test requirements
