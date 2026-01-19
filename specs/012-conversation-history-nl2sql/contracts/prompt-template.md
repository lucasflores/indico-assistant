# Prompt Template Contract: SQL Generation with Conversation History

**Feature**: 012-conversation-history-nl2sql  
**Component**: SQL Generator Prompt Template  
**File**: `indico_assistant/services/nl2sql/generator.py`

## Overview

This contract defines the enhanced SQL generation prompt template that includes conversation history for co-reference resolution.

---

## Prompt Template Structure

### Full Template

```python
SQL_GENERATION_PROMPT = """You are a SQL query generator for the Indico event management system.

AVAILABLE SCHEMA:
{schema_context}

{conversation_history}

USER QUESTION: {question}

CLASSIFICATION:
First, determine if this question requires:
1. SQL query execution (data retrieval)
2. General conversation (no SQL needed)

If SQL is needed, generate a query following these guidelines:
- Use only tables and columns from the AVAILABLE SCHEMA above
- If CONVERSATION HISTORY is provided, use it to resolve pronouns and references
  (e.g., "the first one", "that meeting", "those events")
- Ensure the query returns results relevant to the USER QUESTION
- Include appropriate WHERE clauses, JOINs, and aggregations

Return your response in JSON format:
{{
  "classification": "sql" or "conversation",
  "sql": "SELECT ... (if classification=sql, otherwise null)",
  "confidence": 0.0-1.0,
  "explanation": "Brief explanation of the query or response"
}}
"""
```

---

## Template Variables

### 1. schema_context (Required)

**Type**: `str`  
**Source**: Schema retrieval service  
**Description**: Database schema information including tables, columns, relationships

**Example**:
```
Table: events
  - id (integer, primary key)
  - title (varchar)
  - start_date (timestamp)
  - end_date (timestamp)

Table: registrations
  - id (integer, primary key)
  - event_id (integer, foreign key → events.id)
  - user_id (integer)
  - country (varchar)
  - created_at (timestamp)

Relationships:
  - registrations.event_id → events.id (many-to-one)
```

---

### 2. conversation_history (Optional, NEW)

**Type**: `str`  
**Source**: `SQLGenerator._format_conversation_history()`  
**Description**: Formatted conversation history with numbered messages

**Format**: Numbered chat format with User/Assistant labels

**Example (with history)**:
```
CONVERSATION HISTORY:
1. User: What events are happening this week?
2. Assistant: ICHEP 2024 and CMS Week are scheduled this week.
3. User: Tell me more about the first one
```

**Example (empty)**:
```
(empty string - no content)
```

**Constraints**:
- Maximum 20 messages (10 user + 10 assistant pairs)
- Each message truncated at 1500 characters with "..." if exceeded
- Chronologically ordered (oldest first)
- Conditionally included (empty if no history)

**Placement**: After `schema_context`, before `question`

---

### 3. question (Required)

**Type**: `str`  
**Source**: User input  
**Description**: Current user question that may contain co-references

**Examples**:
```
"What events are happening this week?"
"Tell me more about the first one"
"Break that down by country"
```

---

## Before/After Examples

### Example 1: First Message (No History)

**Before (Current)**:
```
You are a SQL query generator for the Indico event management system.

AVAILABLE SCHEMA:
Table: events (id, title, start_date, end_date)


USER QUESTION: What events are happening this week?

CLASSIFICATION:
...
```

**After (With Empty History Variable)**:
```
You are a SQL query generator for the Indico event management system.

AVAILABLE SCHEMA:
Table: events (id, title, start_date, end_date)


USER QUESTION: What events are happening this week?

CLASSIFICATION:
...
```

*(Same as before - empty history produces empty string)*

---

### Example 2: Follow-up Question (With History)

**Before (Current - FAILS)**:
```
You are a SQL query generator for the Indico event management system.

AVAILABLE SCHEMA:
Table: events (id, title, start_date, end_date)


USER QUESTION: Tell me more about the first one

CLASSIFICATION:
...
```

**LLM Response (Current)**:
```json
{
  "classification": "sql",
  "sql": "SELECT * FROM events WHERE title LIKE '%first%' OR title LIKE '%one%'",
  "confidence": 0.3,
  "explanation": "Query searches for 'first' or 'one' in event titles"
}
```
❌ **Problem**: LLM has no context for "the first one", generates incorrect query

---

**After (With History - SUCCEEDS)**:
```
You are a SQL query generator for the Indico event management system.

AVAILABLE SCHEMA:
Table: events (id, title, start_date, end_date)

CONVERSATION HISTORY:
1. User: What events are happening this week?
2. Assistant: ICHEP 2024 and CMS Week are scheduled this week.
3. User: Tell me more about the first one

USER QUESTION: Tell me more about the first one

CLASSIFICATION:
...
```

**LLM Response (Enhanced)**:
```json
{
  "classification": "sql",
  "sql": "SELECT * FROM events WHERE title = 'ICHEP 2024'",
  "confidence": 0.95,
  "explanation": "User is asking about 'ICHEP 2024', the first event mentioned in conversation history"
}
```
✅ **Success**: LLM resolves "the first one" to "ICHEP 2024" from conversation history

---

### Example 3: Contextual Detail Request

**Before (Current - FAILS)**:
```
You are a SQL query generator for the Indico event management system.

AVAILABLE SCHEMA:
Table: registrations (id, event_id, country)


USER QUESTION: Break that down by country

CLASSIFICATION:
...
```

**LLM Response (Current)**:
```json
{
  "classification": "conversation",
  "sql": null,
  "confidence": 0.2,
  "explanation": "Cannot determine what 'that' refers to without context"
}
```
❌ **Problem**: LLM cannot determine what to "break down"

---

**After (With History - SUCCEEDS)**:
```
You are a SQL query generator for the Indico event management system.

AVAILABLE SCHEMA:
Table: registrations (id, event_id, country)

CONVERSATION HISTORY:
1. User: How many registrations for ICHEP 2024?
2. Assistant: There are 1,247 registrations for ICHEP 2024.
3. User: Break that down by country

USER QUESTION: Break that down by country

CLASSIFICATION:
...
```

**LLM Response (Enhanced)**:
```json
{
  "classification": "sql",
  "sql": "SELECT country, COUNT(*) FROM registrations WHERE event_id = (SELECT id FROM events WHERE title = 'ICHEP 2024') GROUP BY country ORDER BY COUNT(*) DESC",
  "confidence": 0.92,
  "explanation": "Breaking down ICHEP 2024 registrations by country as requested"
}
```
✅ **Success**: LLM understands "that" = "ICHEP 2024 registrations" from context

---

## Formatting Implementation

### Helper Method: _format_conversation_history()

```python
def _format_conversation_history(
    self,
    conversation_history: list[dict[str, str]] | None
) -> str:
    """Format conversation history for prompt inclusion.
    
    Args:
        conversation_history: List of messages with 'role' and 'content' keys,
            or None/empty for no history
            
    Returns:
        Formatted string with numbered messages, or empty string if no history
        
    Example:
        Input: [
            {"role": "user", "content": "What events?"},
            {"role": "assistant", "content": "ICHEP 2024"}
        ]
        Output: "CONVERSATION HISTORY:\n1. User: What events?\n2. Assistant: ICHEP 2024"
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

### Helper Method: _truncate_message()

```python
def _truncate_message(
    self,
    content: str,
    max_chars: int = 1500
) -> str:
    """Truncate message content to maximum length.
    
    Args:
        content: Original message content
        max_chars: Maximum characters (default 1500 per FR-012)
        
    Returns:
        Original content if under limit, or truncated with "..."
        
    Example:
        Input: "A" * 2000
        Output: "AAA...AAA..." (1500 A's + "...")
    """
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "..."
```

---

## Prompt Assembly

### generate() Method Enhancement

```python
def generate(
    self,
    question: str,
    schema_context: str,
    conversation_history: list[dict[str, str]] | None = None
) -> dict:
    """Generate SQL query using LLM with optional conversation history.
    
    Args:
        question: User's current question
        schema_context: Database schema information
        conversation_history: Optional list of prior messages (NEW)
        
    Returns:
        dict with 'sql', 'confidence', 'classification', etc.
    """
    # Format conversation history (NEW)
    history_section = self._format_conversation_history(
        conversation_history or []
    )
    
    # Build prompt with all sections
    prompt = SQL_GENERATION_PROMPT.format(
        schema_context=schema_context,
        conversation_history=history_section,  # May be empty string
        question=question
    )
    
    # Call LLM
    response = self.llm_service.generate(prompt)
    return self._parse_response(response)
```

---

## Test Cases for Prompt Formatting

### Test 1: Empty History

```python
def test_format_empty_history():
    generator = SQLGenerator(...)
    
    # Test with None
    result = generator._format_conversation_history(None)
    assert result == ""
    
    # Test with empty list
    result = generator._format_conversation_history([])
    assert result == ""
```

### Test 2: Single Message

```python
def test_format_single_message():
    generator = SQLGenerator(...)
    history = [{"role": "user", "content": "Hello"}]
    
    result = generator._format_conversation_history(history)
    
    expected = "CONVERSATION HISTORY:\n1. User: Hello"
    assert result == expected
```

### Test 3: Multiple Messages

```python
def test_format_multiple_messages():
    generator = SQLGenerator(...)
    history = [
        {"role": "user", "content": "What events?"},
        {"role": "assistant", "content": "ICHEP 2024"},
        {"role": "user", "content": "Tell me more"}
    ]
    
    result = generator._format_conversation_history(history)
    
    expected = """CONVERSATION HISTORY:
1. User: What events?
2. Assistant: ICHEP 2024
3. User: Tell me more"""
    assert result == expected
```

### Test 4: Message Truncation

```python
def test_format_truncates_long_messages():
    generator = SQLGenerator(...)
    long_content = "A" * 2000
    history = [{"role": "user", "content": long_content}]
    
    result = generator._format_conversation_history(history)
    
    assert "A" * 1500 in result
    assert result.endswith("...")
    assert len(result.split("\n")[1]) <= 1510  # "1. User: " + 1500 chars + "..."
```

### Test 5: 10-Pair Limit Enforcement

```python
def test_format_enforces_10_pair_limit():
    generator = SQLGenerator(...)
    # Create 30 messages (15 pairs)
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
        for i in range(30)
    ]
    
    result = generator._format_conversation_history(history)
    
    # Should only include last 20 messages
    lines = result.split("\n")
    assert lines[0] == "CONVERSATION HISTORY:"
    assert len(lines) == 21  # Header + 20 messages
    assert "Message 10" in lines[1]  # First included message
    assert "Message 29" in lines[-1]  # Last included message
    assert "Message 0" not in result  # Oldest messages excluded
```

---

## Integration with Existing Prompt

**Current SQL_GENERATION_PROMPT** (simplified):
```python
SQL_GENERATION_PROMPT = """You are a SQL query generator...

AVAILABLE SCHEMA:
{schema_context}

USER QUESTION: {question}

CLASSIFICATION:
...
"""
```

**Enhanced SQL_GENERATION_PROMPT**:
```python
SQL_GENERATION_PROMPT = """You are a SQL query generator...

AVAILABLE SCHEMA:
{schema_context}

{conversation_history}

USER QUESTION: {question}

CLASSIFICATION:
...
"""
```

**Key Changes**:
1. Added `{conversation_history}` variable after schema
2. Added blank line before/after for spacing
3. No other changes to existing prompt structure

---

## Expected LLM Behavior

### With Conversation History

**Input**:
```
CONVERSATION HISTORY:
1. User: What events are happening this week?
2. Assistant: ICHEP 2024 and CMS Week are scheduled.
3. User: Tell me more about the first one

USER QUESTION: Tell me more about the first one
```

**Expected LLM Reasoning**:
1. Reads conversation history
2. Identifies "the first one" refers to "ICHEP 2024" (first event mentioned)
3. Generates query: `SELECT * FROM events WHERE title = 'ICHEP 2024'`

### Without Conversation History

**Input**:
```

USER QUESTION: What events are happening this week?
```

**Expected LLM Reasoning**:
1. No conversation history available
2. Treats as standalone question
3. Generates query: `SELECT * FROM events WHERE start_date BETWEEN NOW() AND NOW() + INTERVAL '7 days'`

---

## Performance Considerations

**Token Count Estimation**:
- Schema context: ~2000 tokens
- Conversation history (max): ~1500 tokens (20 messages × ~75 tokens each)
- Current question: ~100 tokens
- Prompt template: ~300 tokens
- **Total**: ~3900 tokens (well under 16K context window)

**Latency Impact**:
- Additional tokens: +1500 max
- Expected latency increase: 50-80ms
- Within SC-004 budget: <100ms P95

---

## Status

✅ **Contract Complete** - Prompt template structure defined with conversation history integration

**Next Steps**:
- Implement `_format_conversation_history()` in generator.py
- Implement `_truncate_message()` in generator.py
- Update `SQL_GENERATION_PROMPT` constant
- Add unit tests for formatting logic
- Verify LLM behavior with history in E2E tests
