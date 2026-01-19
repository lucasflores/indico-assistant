# Feature Specification: Conversation History for NL2SQL Pipeline

**Feature Branch**: `012-conversation-history-nl2sql`  
**Created**: January 19, 2026  
**Status**: Draft  
**Input**: User description: "Conversation history support for NL2SQL pipeline to enable follow-up questions with context awareness"

## Clarifications

### Session 2026-01-19

- Q: Should assistant message metadata (SQL queries, confidence scores, data sources) be included in conversation history passed to the LLM? → A: Include only message text (role + content) without metadata to minimize token usage and keep LLM focused on semantic content
- Q: How should very long assistant responses (>2000 characters) in conversation history be handled? → A: Truncate at 1500 characters with "..." ellipsis indicator
- Q: What format should be used for conversation history in the SQL generation prompt? → A: Numbered chat format with clear separators (e.g., "1. User: <message>\n2. Assistant: <message>")
- Q: Should conversation history be filtered to only include messages from the same event_id when session is event-scoped? → A: No filtering, include all messages from session regardless of event_id
- Q: Where in the SQL generation prompt should the conversation history section be placed? → A: After schema context section, before current user question

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Follow-up Questions with Co-references (Priority: P1)

A user asks a question, receives an answer mentioning specific entities (events, meetings, people), then asks a follow-up question using pronouns or partial references like "the first one", "that meeting", or "those events". The system understands the context from the conversation history and correctly resolves the reference.

**Why this priority**: This is the core value of conversation history - without it, multi-turn conversations are impossible. Users expect natural conversations where they can ask "tell me more about that" without repeating the full entity name. This is the primary user complaint causing this feature.

**Independent Test**: Send two messages in the same session. First message: "What events are happening this week?". Assistant responds with list including "ICHEP 2024". Second message: "tell me more about the first one". Verify the assistant queries for ICHEP 2024 specifically.

**Acceptance Scenarios**:

1. **Given** a user asks "What events are happening this week?", **When** the assistant responds with "ICHEP 2024 and CMS Week", **Then** the user can ask "tell me more about the first one" and the system understands "the first one" refers to ICHEP 2024
2. **Given** the assistant mentions "My Big Beautiful Meeting About Nothing" in a response, **When** the user asks "give me more details about this meeting about nothing", **Then** the system queries for the exact title "My Big Beautiful Meeting About Nothing" (not a partial match like "meeting about nothing")
3. **Given** a user asks about multiple registrations, **When** the assistant lists several people, **Then** the user can ask "show me the third person's details" and the system resolves to the correct person from context

---

### User Story 2 - Contextual Detail Requests (Priority: P1)

A user explores data through a series of questions, each building on the previous answer. The system maintains context so users can request "more details", "break that down", or "what about X" without restating the entire context.

**Why this priority**: Natural conversation flow depends on maintaining context. Users shouldn't have to repeat information in every message. This eliminates a major friction point in multi-turn interactions.

**Independent Test**: Send three messages in sequence: "How many registrations?", "Break that down by country", "Show me the top 3 countries". Each message should build on the previous context.

**Acceptance Scenarios**:

1. **Given** a user asks "How many registrations for ICHEP 2024?", **When** the assistant responds with "1,247 registrations", **Then** the user can ask "break that down by country" and the system knows to query ICHEP 2024 registrations grouped by country
2. **Given** the assistant provides aggregate statistics, **When** the user asks "show me the details", **Then** the system understands what specific query to expand on based on conversation history
3. **Given** a user is exploring event schedules, **When** they ask "what about tomorrow?" after discussing today's schedule, **Then** the system understands the event context from previous messages

---

### User Story 3 - Reference to Previous Results (Priority: P2)

A user can explicitly reference what the assistant said earlier in the conversation, asking questions like "what were the names you mentioned?" or "go back to the previous result".

**Why this priority**: Less critical than implicit context (P1 stories) but still valuable for conversation continuity. Users sometimes want to revisit information without scrolling through chat history.

**Independent Test**: Send message that triggers a list response, then send "what were the items you just listed?" and verify the assistant can recall and repeat the information.

**Acceptance Scenarios**:

1. **Given** the assistant previously listed several meeting names, **When** the user asks "what were the names of the meetings you referenced before?", **Then** the assistant recalls and lists the meeting names from conversation history
2. **Given** the assistant provided statistics about events, **When** the user asks "what was that number you said earlier?", **Then** the system can reference the specific number from the conversation
3. **Given** a multi-turn conversation about different topics, **When** the user asks to "go back to what you said about registrations", **Then** the system can identify and reference the relevant earlier message

---

### Edge Cases

- What happens when conversation history is empty (first message in session)? → System works normally without history section in prompt, no errors
- What happens when conversation history is very long (>10 message pairs)? → Only last 10 message pairs (20 messages) are included per FR-006
- How does system handle very long assistant responses in history? → Messages exceeding 1500 characters are truncated with "..." ellipsis per FR-012
- What if the same entity is mentioned multiple times with slight variations? → LLM uses most recent or most specific mention from context
- How does system behave when user references something never mentioned? → LLM responds it wasn't discussed or asks for clarification
- What happens when conversation switches topics completely? → All history is still included; LLM determines relevance
- How are event-scoped sessions handled? → All messages from session are included in history regardless of event_id per FR-014; event context maintained through current query's event_id parameter

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: NL2SQL pipeline `process()` method MUST accept optional `conversation_history` parameter as a list of dictionaries with 'role' (str) and 'content' (str) keys
- **FR-002**: SQL Generator `generate()` method MUST accept optional `conversation_history` parameter and pass it to prompt formatting
- **FR-003**: SQL generation prompt MUST include a conversation history section when history is provided (non-empty list)
- **FR-004**: Conversation history MUST be formatted chronologically (oldest message first) in prompts to maintain temporal context
- **FR-005**: Chat service `_process_with_nl2sql()` MUST pass the `context` variable (built by ContextBuilder) to the pipeline's `process()` method
- **FR-006**: System MUST limit conversation history to last 10 message pairs (20 messages total) to manage token usage and stay within LLM context windows
- **FR-007**: When no conversation history exists (first message or empty history list), system MUST work normally without history section in prompt
- **FR-008**: Conversation history formatting in prompt MUST clearly distinguish between user and assistant messages for the LLM
- **FR-009**: System MUST handle conversation history parameter as optional with default value of None or empty list
- **FR-010**: All existing tests without conversation history MUST continue to pass without modification
- **FR-011**: Conversation history MUST include only message text (role and content fields) and MUST NOT include assistant message metadata (SQL queries, confidence scores, data sources)
- **FR-012**: Individual messages in conversation history exceeding 1500 characters MUST be truncated with "..." ellipsis appended to indicate truncation
- **FR-013**: Conversation history MUST be formatted in the prompt using numbered chat format: "1. User: <message>\n2. Assistant: <message>\n3. User: <message>" with each exchange numbered sequentially
- **FR-014**: Conversation history MUST include all messages from the session and MUST NOT filter by event_id, even when the current query is event-scoped
- **FR-015**: Conversation history section MUST be placed in the SQL generation prompt after the schema context section and before the current user question section

### Key Entities

- **Conversation History**: Ordered list of previous messages in a chat session, containing role ('user' or 'assistant') and content (message text). Built by ContextBuilder from ChatMessage records, limited to last 10 message pairs.
- **Context Parameter**: The conversation history data structure passed through the service → pipeline → generator → prompt chain. Format: `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]`
- **Enhanced SQL Prompt**: The SQL generation prompt template augmented with a conversation history section that helps the LLM resolve co-references and understand contextual follow-up questions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of follow-up questions with explicit co-references ("the first one", "that meeting") are correctly resolved when the reference exists in conversation history
- **SC-002**: Users can successfully chain at least 3 related questions in a single session without repeating context
- **SC-003**: All three example failures from the Problem Statement (provided in user input) now succeed with correct entity resolution
- **SC-004**: Pipeline latency increase from adding conversation history is less than 100ms (measured as P95 latency)
- **SC-005**: Zero regression in existing non-conversational queries (single-turn questions without history)
- **SC-006**: All existing unit and integration tests pass without modification after implementing optional conversation_history parameter

## Scope & Boundaries *(mandatory)*

### In Scope

- Adding conversation_history parameter to pipeline.process() method
- Adding conversation_history parameter to generator.generate() method
- Updating SQL_GENERATION_PROMPT template to include conversation history section
- Passing context from chat service to NL2SQL pipeline
- Formatting conversation history chronologically in prompts
- Maintaining backward compatibility (history is optional parameter)
- Testing with mock conversation history data

### Out of Scope

- Conversation summarization for very long sessions (future enhancement)
- Multi-turn clarification dialogs or back-and-forth refinement (future enhancement)
- Context compression or semantic filtering of history (future enhancement)
- Cross-session conversation memory (different session = no shared context)
- Including assistant message metadata (SQL, confidence, data sources) in conversation history (explicitly excluded per clarification)
- Optimizing token usage through intelligent history truncation (use fixed 10-pair limit for now)
- RAG-enhanced conversation context (separate feature)

## Assumptions *(mandatory)*

1. **ContextBuilder Implementation**: The `ContextBuilder.build_context()` method is already implemented and returns properly formatted conversation history as list of dicts
2. **Token Limits**: 10 message pairs (20 messages) of conversation history fits within LLM context window for all supported LLM providers
3. **Message Length**: Individual messages in history are reasonably sized (<2000 chars each on average); messages exceeding 1500 characters are truncated per FR-012
4. **Chronological Order**: ContextBuilder returns messages in chronological order (oldest first)
5. **Session Isolation**: Conversations don't span multiple sessions; each session has independent history
6. **Format Stability**: The `{"role": "...", "content": "..."}` format for conversation history aligns with LLM API expectations
7. **Performance Baseline**: Current pipeline can handle additional prompt content without significant latency impact
8. **Error Handling**: Malformed conversation history (missing keys, wrong types) is rare and can fail fast with clear error messages

## Dependencies *(mandatory)*

### Internal Dependencies

- **ContextBuilder** (`indico_assistant/services/chat/context_builder.py`): Provides `build_context()` method that retrieves conversation history from database
- **ChatService** (`indico_assistant/services/chat/service.py`): Orchestrates chat flow and calls `_process_with_nl2sql()` where context needs to be passed
- **NL2SQL Pipeline** (`indico_assistant/services/nl2sql/pipeline.py`): Main pipeline orchestrator that needs conversation_history parameter
- **SQL Generator** (`indico_assistant/services/nl2sql/generator.py`): Generates SQL with prompt template that needs history section
- **LLM Service** (`indico_assistant/services/llm/`): Underlying LLM provider that processes enhanced prompts

### External Dependencies

- **Feature 003** (NL2SQL Pipeline): Core pipeline implementation must be stable
- **Feature 004** (Chat API): Context builder and session management must be working
- **Feature 002** (LLM Service): LLM integration for processing prompts

### Configuration Dependencies

None - this feature uses existing configuration.

## Risks & Mitigations *(mandatory)*

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Conversation history exceeds LLM token limits | Pipeline fails with token limit errors | Low | Enforce 10-pair limit in ContextBuilder; add token counting if needed; log warnings when approaching limits |
| Performance degradation from larger prompts | Slower query responses, poor UX | Medium | Benchmark with realistic history sizes; set P95 latency budget <100ms increase; monitor in production |
| LLM misinterprets conversation context | Incorrect query results despite context | Medium | Include clear formatting and instructions in prompt; test with diverse conversation patterns; iterate on prompt design |
| Breaking changes to existing code | Test failures, regression bugs | Low | Make conversation_history optional (default None); maintain backward compatibility; run full test suite |
| Conversation history format mismatch | Runtime errors, failed queries | Low | Validate history format at pipeline entry; fail fast with clear error; document expected format |
| Very long individual messages consume tokens | Effective history becomes shorter than 10 pairs | Low | Document assumption; defer truncation logic to future enhancement; monitor message lengths |
| Context switching mid-conversation confuses LLM | Irrelevant history pollutes prompt | Medium | Accept as known limitation; future enhancement for smart filtering; test cross-topic conversations |
