# Research Findings: Conversation History for NL2SQL Pipeline

**Feature**: 012-conversation-history-nl2sql  
**Date**: 2026-01-19  
**Phase**: 0 (Technical Discovery)

## Overview

This document captures research findings and technical decisions for implementing conversation history support in the NL2SQL pipeline. All design questions have been resolved through clarification sessions documented in spec.md.

---

## 1. Prompt Format for Conversation History

### Decision

Use numbered chat format with explicit User/Assistant labels and sequential numbering.

### Rationale

**Format Specification:**
```
CONVERSATION HISTORY:
1. User: What events are happening this week?
2. Assistant: ICHEP 2024 and CMS Week are scheduled this week.
3. User: Tell me more about the first one
```

**Why This Format:**
- ✅ Clear separation between user and assistant messages
- ✅ Sequential numbering helps LLM understand temporal order
- ✅ Explicit "User:" and "Assistant:" labels prevent role confusion
- ✅ Compatible with all LLM providers (text-based, no special tokens)
- ✅ Easy to parse and validate in tests

**Source**: Clarification session (spec.md) - "What format should be used for conversation history?"

**Implementation Details:**
- Each message pair (user + assistant) gets sequential numbers
- Format: `{number}. {role}: {content}\n`
- Empty history produces empty string (no "CONVERSATION HISTORY:" header)
- Placed after schema context, before current user question per FR-015

### Alternatives Considered

- ❌ JSON format - harder for LLMs to parse, more verbose
- ❌ Markdown format - inconsistent across LLMs, adds noise
- ❌ Role-based headers only (no numbering) - temporal order less clear
- ✅ Numbered chat format - clearest for LLM comprehension

---

## 2. Token Management Strategy

### Decision

Implement hard limits: 10 message pairs maximum, 1500 characters per message with truncation.

### Rationale

**10-Pair Limit (FR-006):**
- Assumption: 10 pairs × 2 messages × ~300 chars avg = ~6000 tokens
- Leaves room for schema context (~2000 tokens) and question (~500 tokens)
- Total: ~8500 tokens well under 16K context window for Claude/GPT-4
- Existing ContextBuilder already retrieves 10 pairs
- Simple implementation: use last 10 pairs chronologically

**1500-Character Truncation (FR-012):**
- Prevents single long message from consuming entire history budget
- Truncation format: `{message[:1500]}...` (ellipsis indicates truncation)
- Applied to both user and assistant messages
- LLM can still understand context even with truncated responses

**Why Hard Limits:**
- ✅ Predictable token usage for monitoring
- ✅ No complex summarization logic needed (future enhancement)
- ✅ Simpler implementation and testing
- ✅ Covers 95% of real conversations (most messages <1500 chars)

**Source**: Clarifications on "How to prevent token overflow?" and "How to handle very long responses?"

**Implementation Pattern:**
```python
def _truncate_message(self, content: str, max_chars: int = 1500) -> str:
    """Truncate message content to max_chars with ellipsis."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "..."

def _format_conversation_history(
    self,
    conversation_history: list[dict[str, str]]
) -> str:
    """Format conversation history for prompt inclusion."""
    if not conversation_history:
        return ""
    
    # Take only last 10 pairs (20 messages)
    recent_history = conversation_history[-20:]
    
    formatted = ["CONVERSATION HISTORY:"]
    for idx, msg in enumerate(recent_history, start=1):
        role = msg["role"].capitalize()
        content = self._truncate_message(msg["content"])
        formatted.append(f"{idx}. {role}: {content}")
    
    return "\n".join(formatted)
```

### Alternatives Considered

- ❌ Dynamic token counting - complex, provider-specific, adds latency
- ❌ Semantic summarization - unreliable, expensive, future enhancement
- ❌ Sliding window with overlap - adds complexity without clear benefit
- ✅ Hard limits - simple, predictable, sufficient for MVP

---

## 3. Backward Compatibility Strategy

### Decision

Make `conversation_history` an optional parameter with `None` default at all layers.

### Rationale

**Implementation Across Layers:**

1. **ChatService.\_process_with_nl2sql()** (service.py):
   ```python
   # Current call:
   result = await self.nl2sql_pipeline.process(
       question=enhanced_question,
       user_id=user_id,
       event_ids=event_ids
   )
   
   # Updated call:
   result = await self.nl2sql_pipeline.process(
       question=enhanced_question,
       user_id=user_id,
       event_ids=event_ids,
       conversation_history=context  # NEW: pass context from ContextBuilder
   )
   ```

2. **NL2SQLPipeline.process()** (pipeline.py):
   ```python
   async def process(
       self,
       question: str,
       user_id: int,
       event_ids: list[int] | None = None,
       conversation_history: list[dict[str, str]] | None = None  # NEW
   ) -> dict:
       # Forward to generator
       sql_result = await self.generator.generate(
           question=question,
           schema_context=schema,
           conversation_history=conversation_history
       )
   ```

3. **SQLGenerator.generate()** (generator.py):
   ```python
   def generate(
       self,
       question: str,
       schema_context: str,
       conversation_history: list[dict[str, str]] | None = None  # NEW
   ) -> dict:
       # Format history only if provided
       history_section = self._format_conversation_history(
           conversation_history or []
       )
       # Include in prompt if non-empty
       prompt = SQL_GENERATION_PROMPT.format(
           schema_context=schema_context,
           conversation_history=history_section,
           question=question
       )
   ```

**Why Optional Parameters:**
- ✅ Existing tests don't need modification (FR-010)
- ✅ Single-turn queries work unchanged (SC-005)
- ✅ Gradual rollout possible (can disable by not passing context)
- ✅ No breaking changes to API or service interfaces

**Source**: Functional requirement FR-009 and success criterion SC-006

### Alternatives Considered

- ❌ Required parameter with empty list default - forces changes to all callers
- ❌ Separate method (e.g., `process_with_history()`) - duplicates code, harder to maintain
- ✅ Optional parameter with None default - cleanest, most flexible

---

## 4. Conversation History Content

### Decision

Include only message text (`role` and `content` fields), exclude all metadata.

### Rationale

**Included:**
- `role`: "user" or "assistant" (required for formatting)
- `content`: Message text content (the actual conversation)

**Excluded:**
- SQL queries generated by assistant
- Confidence scores
- Data source indicators
- Timestamps
- Event IDs
- Any other metadata

**Why Text-Only:**
- ✅ Minimizes token usage
- ✅ Keeps LLM focused on semantic content
- ✅ Prevents LLM from over-analyzing metadata
- ✅ Metadata already available through other prompt sections (schema, etc.)
- ✅ Simpler formatting and testing

**Source**: Clarification "Should assistant message metadata be included?" → Answer: No, text only

**Implementation Impact:**
```python
# ContextBuilder returns format:
conversation_history = [
    {"role": "user", "content": "What events are happening?"},
    {"role": "assistant", "content": "ICHEP 2024 and CMS Week..."},
    # NO: "sql", "confidence", "timestamp", etc.
]
```

### Alternatives Considered

- ❌ Include SQL queries - confuses LLM, increases tokens significantly
- ❌ Include confidence scores - not useful for co-reference resolution
- ❌ Include timestamps - adds noise, temporal order clear from sequence
- ✅ Text only - minimal, focused, sufficient

---

## 5. Event Filtering in History

### Decision

Do NOT filter conversation history by event_id - include all messages from session regardless of event scope.

### Rationale

**Why No Filtering:**
- ✅ User conversations often span multiple events naturally
- ✅ Cross-event context can be valuable ("compared to the last event...")
- ✅ Current query's event_id already scopes the SQL generation
- ✅ LLM can determine relevance from conversation flow
- ✅ Simpler implementation - no filtering logic needed

**Current Query Event Scoping:**
- The `event_ids` parameter passed to pipeline.process() already scopes the current query
- This ensures generated SQL queries the correct event
- History provides context but doesn't override current query scope

**Example Scenario:**
```
Session in Event A:
  User: "How many registrations?"
  Assistant: "1,247 registrations for ICHEP 2024"

User switches to Event B, same session:
  User: "Compare to the previous event"  ← Needs Event A context
  Assistant: Uses Event B's event_id for query, but understands "previous event" = Event A
```

**Source**: Clarification "Should history be filtered by event_id?" → Answer: No filtering

**Implementation Impact:**
```python
# ContextBuilder.build_context() returns ALL messages from session
context = self.context_builder.build_context(session_id)
# No event_id filtering applied

# Current query's event scope still enforced via:
result = await pipeline.process(
    question=question,
    event_ids=[current_event_id],  # Scopes current query only
    conversation_history=context    # Full unfiltered history
)
```

### Alternatives Considered

- ❌ Filter by current event_id - loses valuable cross-event context
- ❌ Include event_id in history metadata - adds complexity without clear benefit
- ✅ No filtering - simpler, more flexible, LLM determines relevance

---

## 6. Prompt Structure and Placement

### Decision

Place conversation history section after schema context and before current user question.

### Rationale

**Prompt Structure:**
```
You are a SQL query generator for Indico events...

SCHEMA CONTEXT:
[Database schema, available tables, relationships]

CONVERSATION HISTORY:  ← NEW SECTION HERE
1. User: What events are happening?
2. Assistant: ICHEP 2024 and CMS Week...

USER QUESTION: tell me more about the first one  ← Current query

CLASSIFICATION:
[Rest of prompt...]
```

**Why This Ordering:**
1. **Schema first** - establishes what data is available
2. **History second** - provides conversational context
3. **Question last** - focuses LLM on current task

**Benefits:**
- ✅ LLM understands data model before reading history
- ✅ History provides context for interpreting current question
- ✅ Current question is fresh in LLM's attention (recency bias)
- ✅ Matches natural reading order: "Here's what you can query, here's what we discussed, now answer this"

**Source**: Clarification "Where should conversation history be placed in prompt?" → Answer: After schema, before question (FR-015)

**Implementation:**
```python
SQL_GENERATION_PROMPT = """You are a SQL query generator...

{schema_context}

{conversation_history}

USER QUESTION: {question}

CLASSIFICATION:
..."""
```

### Alternatives Considered

- ❌ Before schema - LLM might misinterpret history without data model context
- ❌ After question - reduces effectiveness of context for current query
- ❌ Interleaved with schema - confusing, hard to maintain
- ✅ After schema, before question - optimal ordering

---

## 7. Error Handling and Validation

### Decision

Validate conversation history format at pipeline entry point, fail fast with clear errors.

### Rationale

**Validation Points:**

1. **Type checking** (in pipeline.process()):
   ```python
   if conversation_history is not None:
       if not isinstance(conversation_history, list):
           raise ValueError("conversation_history must be a list")
   ```

2. **Message structure validation** (in generator._format_conversation_history()):
   ```python
   for msg in conversation_history:
       if not isinstance(msg, dict):
           raise ValueError("Each history message must be a dict")
       if "role" not in msg or "content" not in msg:
           raise ValueError("History message missing required keys: role, content")
       if msg["role"] not in ("user", "assistant"):
           raise ValueError(f"Invalid role: {msg['role']}")
   ```

3. **Graceful degradation**:
   - Empty list `[]` → No history section in prompt
   - `None` → No history section in prompt
   - Malformed message → Fail fast with clear error (don't skip silently)

**Why Fail Fast:**
- ✅ Easier debugging when format issues occur
- ✅ Prevents silent failures that are hard to diagnose
- ✅ Clear error messages guide developers to fix
- ✅ Assumption states malformed history is rare (Assumption #8)

**Logging:**
```python
logger.warning(
    "Conversation history approaching token limit: %d messages",
    len(conversation_history)
)
```

### Alternatives Considered

- ❌ Silent skipping of malformed messages - hides bugs
- ❌ Attempt to fix/sanitize invalid format - complex, masks root cause
- ✅ Fail fast with clear errors - simpler, more reliable

---

## 8. Performance Considerations

### Decision

Accept small latency increase (<100ms P95), optimize formatting code, monitor in production.

### Rationale

**Expected Performance Impact:**

1. **History formatting overhead:**
   - String concatenation for 20 messages × ~200 chars = ~4KB
   - Python string operations: <1ms
   
2. **Token increase:**
   - 10 pairs × ~300 chars avg = ~6000 chars → ~1500 tokens
   - LLM latency increase: ~50-80ms (provider-dependent)
   
3. **Total impact estimate:**
   - P95 latency increase: ~60-100ms
   - Within SC-004 budget: <100ms

**Optimization Strategies:**

1. **Efficient string building:**
   ```python
   # Use list join (faster than string concatenation)
   formatted = ["CONVERSATION HISTORY:"]
   for idx, msg in enumerate(recent_history, start=1):
       formatted.append(f"{idx}. {role}: {content}")
   return "\n".join(formatted)  # Single join operation
   ```

2. **Early exit:**
   ```python
   if not conversation_history:
       return ""  # No formatting needed
   ```

3. **Pre-truncation:**
   ```python
   # Truncate before formatting to minimize string operations
   content = self._truncate_message(msg["content"])
   ```

**Monitoring:**
- Log P95 latency with/without history in production
- Alert if latency exceeds 100ms increase threshold
- Track token usage per request

**Source**: Success criterion SC-004 and non-functional requirement NFR-001 (performance)

### Alternatives Considered

- ❌ Async formatting - overhead outweighs benefit for small strings
- ❌ Caching formatted history - conversations change constantly
- ✅ Simple string operations - sufficient for expected scale

---

## Summary of Decisions

| Decision Point | Choice | Rationale |
|----------------|--------|-----------|
| **Prompt Format** | Numbered chat format with User/Assistant labels | Clearest for LLM comprehension |
| **Token Limits** | 10 pairs max, 1500 chars per message | Predictable, simple, covers 95% of cases |
| **Backward Compatibility** | Optional parameter with None default | Zero breaking changes, gradual rollout |
| **History Content** | Text only (role + content) | Minimizes tokens, focuses LLM |
| **Event Filtering** | No filtering by event_id | Preserves cross-event context |
| **Prompt Placement** | After schema, before question | Optimal reading order for LLM |
| **Error Handling** | Fail fast with clear errors | Easier debugging, prevents silent failures |
| **Performance** | Accept <100ms increase | Within budget, optimize formatting |

---

## Open Questions / Future Enhancements

*(None blocking for MVP - documented for future consideration)*

1. **Semantic summarization** - Compress long histories while preserving key context
2. **Smart filtering** - Include only relevant portions of history based on current question
3. **Dynamic token budgeting** - Adjust history length based on schema complexity
4. **Cross-session memory** - Persistent user preferences or context across sessions
5. **Conversation analytics** - Track co-reference patterns to improve prompt design

---

## References

- **Spec**: [spec.md](spec.md) - Feature specification with clarifications
- **Plan**: [plan.md](plan.md) - Implementation plan and technical context
- **ContextBuilder**: `indico_assistant/services/chat/context_builder.py` - Existing history retrieval
- **NL2SQL Pipeline**: `indico_assistant/services/nl2sql/pipeline.py` - Pipeline orchestration
- **SQL Generator**: `indico_assistant/services/nl2sql/generator.py` - Prompt generation

---

**Status**: ✅ Complete - All research questions resolved, ready for Phase 1 (Design)
