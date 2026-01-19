# Implementation Plan: Conversation History for NL2SQL Pipeline

**Branch**: `012-conversation-history-nl2sql` | **Date**: 2026-01-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/012-conversation-history-nl2sql/spec.md`

## Phase Status

| Phase | Status | Output |
|-------|--------|--------|
| Phase 0: Research | ✅ Complete | [research.md](research.md) |
| Phase 1: Design | ✅ Complete | [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md) |
| Phase 2: Tasks | ✅ Complete | [tasks.md](tasks.md) |

## Summary

Enable the NL2SQL pipeline to accept and utilize conversation history when generating SQL queries, allowing users to ask follow-up questions with pronouns and contextual references (e.g., "tell me more about the first one", "break that down by country"). The system will pass the last 10 message pairs from the current chat session to the SQL generator, which will include this history in the LLM prompt to enable co-reference resolution. Implementation involves adding an optional `conversation_history` parameter through the pipeline chain (chat service → pipeline → generator → prompt), formatting history as numbered messages, and maintaining backward compatibility with existing non-conversational queries.

## Technical Context

**Language/Version**: Python 3.11+ (matching Indico requirements)  
**Primary Dependencies**: 
- Existing `ContextBuilder` service (`indico_assistant/services/chat/context_builder.py`)
- NL2SQL Pipeline (`indico_assistant/services/nl2sql/pipeline.py`)
- SQL Generator (`indico_assistant/services/nl2sql/generator.py`)
- LLM Service for prompt processing
- ChatMessage model for conversation storage

**Storage**: PostgreSQL (`plugin_assistant.chat_messages` table - already exists)  
**Testing**: pytest with Indico fixtures and mocked conversation history  
**Target Platform**: Linux server running Indico instance  
**Project Type**: Single project (Indico plugin)  
**Performance Goals**: 
- Pipeline latency increase <100ms P95 when history included
- Zero regression in single-turn (non-conversational) queries
- 100% co-reference resolution for references in history

**Constraints**: 
- Conversation history limited to 10 message pairs (20 messages) for token management
- Messages truncated at 1500 characters with "..." ellipsis
- Must maintain backward compatibility (history is optional parameter)
- No metadata (SQL, confidence) in history - text only

**Scale/Scope**: 
- 3 files to modify (service.py, pipeline.py, generator.py)
- 5 new functional requirements to implement
- No database schema changes needed
- Affects all NL2SQL queries but optional parameter ensures compatibility

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Official Indico Plugin Architecture ✅ PASS
- ✅ Uses existing Indico plugin structure
- ✅ No new routes or controllers needed
- ✅ Modifies existing services only
- ✅ Uses existing database models (ChatMessage)

### II. API-First Design with Optional UI ✅ PASS  
- ✅ No API changes (internal service enhancement)
- ✅ Existing chat API already handles sessions and messages
- ✅ Changes are transparent to API consumers

### III. LLM Provider Abstraction ✅ PASS
- ✅ Uses existing LLMService abstraction
- ✅ Only modifies prompt content, not LLM integration
- ✅ Prompt changes are provider-agnostic

### IV. Graceful Degradation ✅ PASS
- ✅ Conversation history is optional parameter (defaults to None/empty)
- ✅ System works normally when history is empty (first message)
- ✅ No errors when ContextBuilder returns empty list
- ✅ Backward compatible with all existing tests

### V. Configuration Hierarchy ✅ PASS
- ✅ No new configuration needed
- ✅ Uses existing chat session infrastructure
- ✅ 10-pair limit hardcoded (can be made configurable later if needed)

### VI. Test-First Development ✅ PASS (Planned)
- ✅ Unit tests for prompt formatting with/without history
- ✅ Integration tests for pipeline with mock history
- ✅ E2E tests for three failing examples from spec
- ✅ Regression tests ensure existing tests still pass

**GATE RESULT**: ✅ **ALL GATES PASS** - Ready for Phase 0

## Project Structure

### Documentation (this feature)

```text
specs/012-conversation-history-nl2sql/
├── plan.md              # This file
├── research.md          # Phase 0 output (minimal - mostly implementation decisions)
├── data-model.md        # Phase 1 output (conversation history data structure)
├── quickstart.md        # Phase 1 output (implementation guide)
├── contracts/           # Phase 1 output (prompt template examples)
└── tasks.md             # Phase 2 output (detailed implementation tasks)
```

### Source Code (repository root)

```text
indico_assistant/
├── services/
│   ├── chat/
│   │   ├── context_builder.py    # [READ ONLY] Already builds history
│   │   └── service.py             # [MODIFY] Pass context to pipeline
│   └── nl2sql/
│       ├── pipeline.py            # [MODIFY] Add conversation_history param
│       └── generator.py           # [MODIFY] Add history to prompt
tests/
├── unit/
│   └── services/
│       └── nl2sql/
│           ├── test_pipeline.py           # [MODIFY] Test with history param
│           └── test_generator.py          # [MODIFY] Test prompt formatting
├── integration/
│   └── nl2sql/
│       └── test_pipeline_with_history.py  # [NEW] Integration tests
└── e2e/
    └── test_conversation_flow.py          # [NEW] End-to-end tests
```

**Structure Decision**: Single project modification pattern. This feature modifies existing services without adding new components. The change flows through three layers: ChatService receives context from ContextBuilder and passes it to the pipeline; NL2SQLPipeline accepts the optional parameter and forwards it to the generator; SQLGenerator formats history into the prompt. No database, API, or UI changes needed.

## Complexity Tracking

> No constitution violations - this section not applicable.

---

## Phase 0: Research & Technical Discovery

**Goal**: Resolve any NEEDS CLARIFICATION items and research implementation approach

### Research Questions

1. **Prompt Format Research**
   - **Question**: What's the optimal format for conversation history in LLM prompts for SQL generation?
   - **Decision**: Use numbered chat format per clarification: "1. User: <msg>\n2. Assistant: <msg>"
   - **Source**: Clarification session 2026-01-19

2. **Token Management**
   - **Question**: How to prevent token overflow with conversation history?
   - **Decision**: 
     - Limit to 10 message pairs (20 messages) per FR-006
     - Truncate individual messages at 1500 chars per FR-012
     - Place history after schema, before question per FR-015
   - **Source**: Clarifications + existing ContextBuilder implementation

3. **Backward Compatibility**
   - **Question**: How to ensure existing tests don't break?
   - **Decision**: Make conversation_history optional parameter with None/empty list default per FR-009
   - **Source**: Functional requirements + test impact analysis

### Implementation Decisions

1. **Parameter Passing Strategy**
   - **Decision**: Add `conversation_history: list[dict[str, str]] | None = None` parameter to:
     - `NL2SQLPipeline.process()`
     - `SQLGenerator.generate()`
   - **Rationale**: Optional parameter maintains backward compatibility

2. **History Formatting in Prompt**
   - **Decision**: Create `_format_conversation_history()` helper method in SQLGenerator
   - **Format**: Numbered list with clear User/Assistant labels
   - **Example**:
     ```
     CONVERSATION HISTORY:
     1. User: What events are happening this week?
     2. Assistant: ICHEP 2024 and CMS Week are scheduled.
     3. User: Tell me more about the first one
     ```

3. **Context Passing in ChatService**
   - **Decision**: Modify `_process_with_nl2sql()` to pass `context` variable to `pipeline.process()`
   - **Current**: `pipeline.process(question=enhanced_question, user_id=user_id, event_ids=...)`
   - **Updated**: `pipeline.process(question=enhanced_question, user_id=user_id, event_ids=..., conversation_history=context)`

**Output**: research.md with implementation decisions

---

## Phase 1: Design & Contracts

**Goal**: Define data structures, prompt templates, and implementation patterns

### Data Model

**Conversation History Structure** (already exists via ContextBuilder):
```python
conversation_history: list[dict[str, str]] = [
    {"role": "user", "content": "What events are happening?"},
    {"role": "assistant", "content": "ICHEP 2024 and CMS Week..."},
    {"role": "user", "content": "Tell me more about the first one"}
]
```

**Prompt Template Enhancement**:
```python
# Current SQL_GENERATION_PROMPT
SQL_GENERATION_PROMPT = """You are a SQL query generator...
{schema_context}

USER QUESTION: {question}

CLASSIFICATION:
..."""

# Enhanced with history section
SQL_GENERATION_PROMPT = """You are a SQL query generator...
{schema_context}

{conversation_history}  # NEW: Conditionally included

USER QUESTION: {question}

CLASSIFICATION:
..."""
```

**Output**: 
- data-model.md with conversation history structure
- contracts/prompt-template.md with before/after examples
- quickstart.md with step-by-step implementation guide

---

## Phase 2: Implementation Tasks

**Goal**: Break down into atomic, testable tasks

Tasks will be generated by `/speckit.tasks` command and include:

### Core Implementation Tasks (Priority: P1)
- Update `ChatService._process_with_nl2sql()` to pass context to pipeline
- Add `conversation_history` parameter to `NL2SQLPipeline.process()`
- Add `conversation_history` parameter to `SQLGenerator.generate()`
- Implement `_format_conversation_history()` helper in SQLGenerator
- Update `SQL_GENERATION_PROMPT` template with history section
- Add message truncation logic (1500 chars) in generator

### Testing Tasks (Priority: P1)
- Unit test: Generator formats history correctly
- Unit test: Generator handles empty/None history
- Unit test: Message truncation at 1500 chars
- Integration test: Pipeline with mock conversation history
- E2E test: Three failing examples from spec now pass
- Regression test: Existing tests still pass

### Documentation Tasks (Priority: P2)
- Update generator.py docstrings with history parameter
- Update pipeline.py docstrings with history parameter
- Add code comments explaining history formatting

**Output**: tasks.md with detailed task breakdown

---

## Implementation Notes

### Key Files to Modify

1. **indico_assistant/services/chat/service.py** (~415 lines)
   - Line ~150: `_process_with_nl2sql()` method
   - Change: Add `conversation_history=context` to `pipeline.process()` call
   - Impact: 1 line change

2. **indico_assistant/services/nl2sql/pipeline.py** (~581 lines)
   - Line ~144: `process()` method signature
   - Change: Add `conversation_history` parameter with default None
   - Line ~XXX: Pass to `generator.generate()`
   - Impact: 2-3 line changes

3. **indico_assistant/services/nl2sql/generator.py** (~210 lines)
   - Line ~24: `SQL_GENERATION_PROMPT` template
   - Line ~89: `generate()` method signature
   - NEW: `_format_conversation_history()` helper method (~15 lines)
   - Impact: ~30 lines total (template update + new method)

### Testing Strategy

**Unit Tests** (new):
- `test_generator_formats_history_correctly()`
- `test_generator_handles_empty_history()`
- `test_generator_truncates_long_messages()`
- `test_generator_numbers_messages_sequentially()`

**Integration Tests** (new):
- `test_pipeline_with_conversation_history()`
- `test_pipeline_resolves_coreferences()`

**E2E Tests** (new):
- `test_followup_question_with_coreference()`
- `test_contextual_detail_request()`
- `test_reference_to_previous_results()`

**Regression Tests** (verify):
- All existing `test_pipeline*.py` tests pass
- All existing `test_generator*.py` tests pass

### Risk Mitigation

1. **Token Overflow Risk**
   - Mitigation: Enforce 10-pair + 1500-char limits strictly
   - Monitoring: Log warning when approaching limits

2. **LLM Confusion Risk**
   - Mitigation: Clear numbered format with User/Assistant labels
   - Testing: Test with diverse conversation patterns

3. **Backward Compatibility Risk**
   - Mitigation: Optional parameter with None default
   - Testing: Run full existing test suite

---

## Success Criteria Mapping

| Success Criterion | Implementation Verification |
|-------------------|----------------------------|
| SC-001: 100% co-reference resolution | E2E tests with "the first one", "that meeting" references |
| SC-002: Chain 3+ questions | E2E test with sequential context-dependent questions |
| SC-003: Fix three failing examples | Specific E2E tests for each example from spec |
| SC-004: <100ms latency increase | Performance benchmarking before/after |
| SC-005: Zero regression | Full existing test suite passes |
| SC-006: Tests pass unmodified | Verify no test changes needed |

---

## Next Steps

1. **Phase 0**: Create research.md with implementation decisions (mostly complete via clarifications)
2. **Phase 1**: Create data-model.md, contracts/, and quickstart.md
3. **Phase 2**: Run `/speckit.tasks` to generate detailed task breakdown
4. **Implementation**: Follow quickstart.md and tasks.md
5. **Testing**: Verify all success criteria met
6. **Review**: Code review focusing on backward compatibility and performance

