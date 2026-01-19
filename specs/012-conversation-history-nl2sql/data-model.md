# Data Model: Conversation History for NL2SQL Pipeline

**Feature**: 012-conversation-history-nl2sql  
**Date**: 2026-01-19  
**Phase**: 1 (Design & Contracts)

## Overview

This document defines the data structures and their relationships for passing conversation history through the NL2SQL pipeline. The feature primarily reuses existing models (ChatMessage, ChatSession) with new parameter types for the pipeline chain.

---

## Core Entities

### 1. Conversation History Message (Data Transfer)

**Source**: ContextBuilder.build_context() return value  
**Lifetime**: Single request scope  
**Purpose**: Carry historical messages from database to prompt formatting

```python
from typing import TypedDict

class ConversationMessage(TypedDict):
    """Single message in conversation history.
    
    Represents one user or assistant message with minimal structure.
    Used for passing context through the pipeline.
    """
    
    role: str  # "user" or "assistant"
    content: str  # Message text content (may be truncated)
```

**Attributes**:
- `role`: Message sender - "user" or "assistant" (lowercase, validated)
- `content`: Message text content, potentially truncated at 1500 characters

**Constraints**:
- `role` MUST be exactly "user" or "assistant" (no "system", "function", etc.)
- `content` MUST be string (empty string allowed, but should not occur in practice)
- `content` MAY be truncated with "..." if original exceeded 1500 characters

**Validation**:
```python
def validate_message(msg: dict) -> bool:
    """Validate single conversation message structure."""
    if not isinstance(msg, dict):
        return False
    if set(msg.keys()) != {"role", "content"}:
        return False
    if msg["role"] not in ("user", "assistant"):
        return False
    if not isinstance(msg["content"], str):
        return False
    return True
```

**Example**:
```python
message = {
    "role": "user",
    "content": "What events are happening this week?"
}
```

---

### 2. Conversation History List

**Source**: Aggregation of ConversationMessage instances  
**Lifetime**: Single request scope  
**Purpose**: Full conversation context passed through pipeline

```python
from typing import List

ConversationHistory = List[ConversationMessage]
```

**Structure**:
```python
conversation_history: ConversationHistory = [
    {"role": "user", "content": "What events are happening this week?"},
    {"role": "assistant", "content": "ICHEP 2024 and CMS Week are scheduled."},
    {"role": "user", "content": "Tell me more about the first one"}
]
```

**Constraints**:
- Ordered chronologically (oldest message first)
- Maximum 20 messages (10 user + 10 assistant pairs) per FR-006
- May be empty list `[]` for first message in session
- Individual messages truncated at 1500 characters per FR-012

**Properties**:
- **Chronological**: Messages MUST maintain temporal order
- **Alternating**: Typically alternates user→assistant→user (but not enforced)
- **Bounded**: Limited to last 10 message pairs (20 messages)
- **Text-only**: No metadata (SQL, confidence, timestamps) per FR-011

---

### 3. Pipeline Method Parameters

**Source**: Method signatures across pipeline chain  
**Lifetime**: Method execution scope  
**Purpose**: Type-safe parameter passing with backward compatibility

#### ChatService._process_with_nl2sql()

```python
async def _process_with_nl2sql(
    self,
    session_id: int,
    question: str,
    user_id: int,
    event_ids: list[int] | None = None
) -> dict:
    """Process question using NL2SQL pipeline with conversation context.
    
    Args:
        session_id: Chat session ID for context retrieval
        question: User's current question
        user_id: User making the request
        event_ids: Optional event scope for query
        
    Returns:
        dict: Pipeline result with SQL and metadata
    """
    # Build conversation context
    context: ConversationHistory = self.context_builder.build_context(session_id)
    
    # Pass to pipeline (NEW: conversation_history parameter)
    result = await self.nl2sql_pipeline.process(
        question=question,
        user_id=user_id,
        event_ids=event_ids,
        conversation_history=context  # NEW
    )
    return result
```

#### NL2SQLPipeline.process()

```python
from typing import Optional

async def process(
    self,
    question: str,
    user_id: int,
    event_ids: list[int] | None = None,
    conversation_history: ConversationHistory | None = None  # NEW
) -> dict:
    """Process natural language question into SQL query.
    
    Args:
        question: User's current question
        user_id: User making the request  
        event_ids: Optional event scope for query
        conversation_history: Optional conversation context (NEW)
            - None or empty list: First message or no context
            - List of messages: Historical conversation for co-reference resolution
            
    Returns:
        dict: Contains 'sql', 'confidence', 'classification', etc.
    """
    # ... schema retrieval logic ...
    
    # Generate SQL with context (NEW: pass conversation_history)
    sql_result = await self.generator.generate(
        question=question,
        schema_context=schema,
        conversation_history=conversation_history
    )
    return sql_result
```

#### SQLGenerator.generate()

```python
def generate(
    self,
    question: str,
    schema_context: str,
    conversation_history: ConversationHistory | None = None  # NEW
) -> dict:
    """Generate SQL query using LLM with optional conversation history.
    
    Args:
        question: User's current question
        schema_context: Database schema information
        conversation_history: Optional conversation context (NEW)
            - None: No history, first message
            - Empty list []: No history, first message  
            - List of messages: Format and include in prompt
            
    Returns:
        dict: Contains 'sql', 'confidence', 'classification', etc.
    """
    # Format history section (NEW)
    history_section = self._format_conversation_history(
        conversation_history or []
    )
    
    # Build prompt with history
    prompt = SQL_GENERATION_PROMPT.format(
        schema_context=schema_context,
        conversation_history=history_section,
        question=question
    )
    
    # Call LLM
    response = self.llm_service.generate(prompt)
    return self._parse_response(response)
```

---

### 4. Formatted History String (Intermediate)

**Source**: SQLGenerator._format_conversation_history() output  
**Lifetime**: Single prompt generation  
**Purpose**: Prompt-ready string representation of conversation history

```python
FormattedHistory = str  # Multi-line string with numbered messages
```

**Structure**:
```python
formatted_history: FormattedHistory = """CONVERSATION HISTORY:
1. User: What events are happening this week?
2. Assistant: ICHEP 2024 and CMS Week are scheduled this week.
3. User: Tell me more about the first one"""
```

**Properties**:
- Multi-line string with `\n` separators
- Header: "CONVERSATION HISTORY:" (only if messages exist)
- Each message: `{number}. {Role}: {content}`
- Sequential numbering starting from 1
- Empty string if no conversation history

**Generation Logic**:
```python
def _format_conversation_history(
    self,
    conversation_history: ConversationHistory
) -> FormattedHistory:
    """Format conversation history for prompt inclusion.
    
    Args:
        conversation_history: List of conversation messages
        
    Returns:
        Formatted multi-line string, or empty string if no history
    """
    if not conversation_history:
        return ""
    
    # Enforce 10-pair limit (20 messages)
    recent_history = conversation_history[-20:]
    
    formatted = ["CONVERSATION HISTORY:"]
    for idx, msg in enumerate(recent_history, start=1):
        role = msg["role"].capitalize()  # "User" or "Assistant"
        content = self._truncate_message(msg["content"])
        formatted.append(f"{idx}. {role}: {content}")
    
    return "\n".join(formatted)
```

---

### 5. Prompt Template with History

**Source**: SQL_GENERATION_PROMPT constant in generator.py  
**Lifetime**: Entire application lifetime (constant)  
**Purpose**: LLM prompt template with conversation history placeholder

```python
SQL_GENERATION_PROMPT = """You are a SQL query generator for Indico event management system.

AVAILABLE SCHEMA:
{schema_context}

{conversation_history}

USER QUESTION: {question}

CLASSIFICATION:
First, determine if this question requires:
1. SQL query execution (data retrieval)
2. General conversation (no SQL needed)

[Rest of prompt instructions...]
"""
```

**Template Variables**:
- `{schema_context}`: Database schema and available tables (required)
- `{conversation_history}`: Formatted history string (NEW - may be empty)
- `{question}`: User's current question (required)

**Conditional Rendering**:
- If `conversation_history` is empty string: Section omitted (blank line remains)
- If `conversation_history` has content: Full formatted history included

**Example Rendered Prompt (with history)**:
```
You are a SQL query generator for Indico event management system.

AVAILABLE SCHEMA:
Table: events (id, title, start_date, end_date)
Table: registrations (id, event_id, user_id, country)

CONVERSATION HISTORY:
1. User: What events are happening this week?
2. Assistant: ICHEP 2024 and CMS Week are scheduled this week.
3. User: Tell me more about the first one

USER QUESTION: Tell me more about the first one

CLASSIFICATION:
...
```

**Example Rendered Prompt (without history)**:
```
You are a SQL query generator for Indico event management system.

AVAILABLE SCHEMA:
Table: events (id, title, start_date, end_date)
Table: registrations (id, event_id, user_id, country)


USER QUESTION: What events are happening this week?

CLASSIFICATION:
...
```

---

## Helper Functions

### _truncate_message()

**Purpose**: Enforce 1500-character limit with ellipsis indicator

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
        Original content if under limit, or truncated content with "..."
    """
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "..."
```

**Examples**:
```python
# Short message - no truncation
_truncate_message("Hello world")
# Returns: "Hello world"

# Long message - truncated
_truncate_message("A" * 2000)
# Returns: "AAA...AAA..." (1500 A's + "...")
```

---

## Data Flow

### End-to-End Data Flow

```
1. User sends question in existing chat session
   ↓
2. ChatService retrieves session context via ContextBuilder
   context: ConversationHistory = [
       {"role": "user", "content": "What events..."},
       {"role": "assistant", "content": "ICHEP 2024..."},
   ]
   ↓
3. ChatService passes context to NL2SQL Pipeline
   pipeline.process(..., conversation_history=context)
   ↓
4. Pipeline forwards context to SQL Generator
   generator.generate(..., conversation_history=context)
   ↓
5. Generator formats history into prompt string
   formatted = "CONVERSATION HISTORY:\n1. User: ...\n2. Assistant: ..."
   ↓
6. Generator builds full prompt with formatted history
   prompt = SQL_GENERATION_PROMPT.format(
       schema_context=schema,
       conversation_history=formatted,
       question=question
   )
   ↓
7. LLM receives prompt with conversation context
   ↓
8. LLM generates SQL using history for co-reference resolution
   ↓
9. SQL executed and results returned to user
```

### State Management

**Stateless Design**:
- No new persistent state - reuses existing ChatMessage table
- Conversation history built fresh per request
- No caching of formatted history (changes every turn)
- All history data sourced from database via ContextBuilder

**Existing Database Schema** (unchanged):
```sql
-- Already exists from Feature 004
CREATE TABLE plugin_assistant.chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES plugin_assistant.chat_sessions(id),
    role VARCHAR(20) NOT NULL,  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**ContextBuilder Query** (existing, unchanged):
```python
def build_context(self, session_id: int) -> ConversationHistory:
    """Retrieve last 10 message pairs from session.
    
    Returns chronologically ordered list of messages.
    """
    messages = (
        ChatMessage.query
        .filter_by(session_id=session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)  # 10 pairs
        .all()
    )
    
    return [
        {"role": msg.role, "content": msg.content}
        for msg in reversed(messages)  # Chronological order
    ]
```

---

## Type Definitions Summary

```python
# Type aliases for clarity
from typing import TypedDict, List, Optional

class ConversationMessage(TypedDict):
    """Single message in conversation history."""
    role: str  # "user" or "assistant"
    content: str  # Message text

ConversationHistory = List[ConversationMessage]
FormattedHistory = str  # Multi-line numbered format

# Example usage in type hints
def example_function(
    conversation_history: Optional[ConversationHistory] = None
) -> FormattedHistory:
    """Example showing type usage."""
    pass
```

---

## Validation Rules

### Input Validation (at pipeline entry)

```python
def validate_conversation_history(
    conversation_history: Optional[ConversationHistory]
) -> None:
    """Validate conversation history structure.
    
    Raises:
        ValueError: If history format is invalid
    """
    if conversation_history is None:
        return  # None is valid (no history)
    
    if not isinstance(conversation_history, list):
        raise ValueError("conversation_history must be a list")
    
    for idx, msg in enumerate(conversation_history):
        if not isinstance(msg, dict):
            raise ValueError(f"Message {idx} must be a dict")
        
        if set(msg.keys()) != {"role", "content"}:
            raise ValueError(
                f"Message {idx} must have exactly 'role' and 'content' keys"
            )
        
        if msg["role"] not in ("user", "assistant"):
            raise ValueError(
                f"Message {idx} has invalid role: {msg['role']}"
            )
        
        if not isinstance(msg["content"], str):
            raise ValueError(
                f"Message {idx} content must be string"
            )
```

---

## Edge Cases

### Empty or Missing History

```python
# Case 1: None (no history parameter passed)
conversation_history = None
formatted = _format_conversation_history(conversation_history or [])
# Result: ""

# Case 2: Empty list (first message in session)
conversation_history = []
formatted = _format_conversation_history(conversation_history)
# Result: ""

# Case 3: Single user message (waiting for response)
conversation_history = [{"role": "user", "content": "Hello"}]
formatted = _format_conversation_history(conversation_history)
# Result: "CONVERSATION HISTORY:\n1. User: Hello"
```

### History Exceeding Limits

```python
# Case 4: More than 20 messages (exceeds 10-pair limit)
conversation_history = [
    {"role": "user", "content": f"Question {i}"}
    for i in range(30)  # 30 messages
]
formatted = _format_conversation_history(conversation_history)
# Result: Only last 20 messages included (messages 11-30)

# Case 5: Message exceeding 1500 characters
long_message = "A" * 2000
conversation_history = [{"role": "user", "content": long_message}]
formatted = _format_conversation_history(conversation_history)
# Result: "CONVERSATION HISTORY:\n1. User: AAA...AAA... (1500 A's + '...')"
```

---

## Relationships to Existing Models

### ChatMessage (existing, unchanged)

**Source**: `indico_assistant/models/message.py`  
**Relationship**: ConversationMessage is a simplified DTO derived from ChatMessage

```python
# Existing ChatMessage model
class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    __table_args__ = {"schema": "plugin_assistant"}
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("plugin_assistant.chat_sessions.id"))
    role = db.Column(db.String(20))  # "user" or "assistant"
    content = db.Column(db.Text)  # Full message text
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Metadata fields (NOT included in ConversationMessage)
    sql_query = db.Column(db.Text, nullable=True)
    confidence_score = db.Column(db.Float, nullable=True)
```

**Mapping**:
```python
# ChatMessage → ConversationMessage
def to_conversation_message(chat_message: ChatMessage) -> ConversationMessage:
    """Convert ChatMessage to ConversationMessage DTO."""
    return {
        "role": chat_message.role,
        "content": chat_message.content
        # Excludes: id, session_id, created_at, sql_query, confidence_score
    }
```

---

## Summary

**Key Data Structures**:
1. **ConversationMessage**: `{"role": str, "content": str}` - single message
2. **ConversationHistory**: `List[ConversationMessage]` - full context
3. **FormattedHistory**: Multi-line string for prompt inclusion

**Data Flow**:
- ChatMessage (DB) → ConversationHistory (DTO) → FormattedHistory (string) → Prompt

**Key Properties**:
- Chronological ordering (oldest first)
- 20-message limit (10 pairs)
- 1500-character truncation per message
- Text-only (no metadata)
- Optional parameter (backward compatible)

**No New Tables**: All data sourced from existing `chat_messages` table

---

**Status**: ✅ Complete - Data model defined, ready for contracts and quickstart
