# Implementation Plan: Chat Source Citations

**Branch**: `015-chat-source-citations` | **Date**: 2026-01-20 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/015-chat-source-citations/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Add automatic source citations to chat responses, linking back to event pages for NL2SQL-derived information and attachment URLs for RAG-derived content. Citations appear inline as markdown links, incrementally as responses stream, with each source reference getting its own citation link.

**Technical approach**: Extend the chat service pipeline to track source metadata during NL2SQL and vector search retrieval, implement a citation formatter that generates markdown links using Indico URL patterns, and integrate citation generation into the LLM response streaming flow.

## Technical Context

**Language/Version**: Python 3.11+ (match Indico minimum)  
**Primary Dependencies**: 
- Instructor (existing LLM abstraction with structured outputs)
- SQLAlchemy (existing ORM via Indico's db)
- Pydantic (existing schema validation)
- pgvector (existing vector search)  
**Storage**: PostgreSQL with plugin_assistant schema (existing)  
**Testing**: pytest with indico fixtures (`pytest_plugins = ('indico',)`)  
**Target Platform**: Linux server (Indico plugin)  
**Project Type**: Single project (Indico plugin)  
**Performance Goals**: <200ms citation generation overhead per response  
**Constraints**: 
- Must preserve existing streaming response functionality
- Must not break responses if citation generation fails
- Citations must work with both NL2SQL and vector search sources  
**Scale/Scope**: 
- 15 functional requirements
- 2 service layers (chat, vector_search)
- 1 new LLM response model with citations
- Extends existing chat pipeline

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Official Indico Plugin Architecture** | ✅ PASS | No plugin structure changes required; extends existing chat service |
| **II. API-First Design** | ✅ PASS | Citations added to existing `/api/assistant/chat` response; no new endpoints |
| **III. LLM Provider Abstraction** | ✅ PASS | Uses existing Instructor-based LLMService; no provider changes |
| **IV. Graceful Degradation** | ✅ PASS | Citation generation failures must not break responses (FR-010) |
| **V. Configuration Hierarchy** | ✅ PASS | Base URL configurable via plugin settings (Assumption #3) |
| **VI. Test-First Development** | ✅ PASS | Tests required for citation formatting, source tracking, and integration |

**Verdict**: ✅ **APPROVED** - All constitutional principles satisfied. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/015-chat-source-citations/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   └── citation-response.md  # Pydantic model contract for citations
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
indico_assistant/
├── services/
│   ├── chat/
│   │   ├── __init__.py
│   │   ├── service.py        # MODIFY: Add source tracking and citation generation
│   │   └── citations.py      # NEW: Citation formatting utilities
│   └── vector_search/
│       ├── rag.py            # MODIFY: Return source metadata with context
│       └── search.py         # (existing: already returns metadata)
├── schemas/
│   └── chat.py               # MODIFY: Add sources to ChatResponse metadata
└── models/
    └── document.py           # (existing: ExtractedDocument already has metadata_json)

tests/
├── unit/
│   └── services/
│       └── chat/
│           ├── test_citations.py          # NEW: Citation formatting tests
│           └── test_service_citations.py  # NEW: Integration tests
├── integration/
│   └── test_chat_citations.py            # NEW: End-to-end citation tests
└── contract/
    └── test_citation_models.py           # NEW: Pydantic model validation
```

**Structure Decision**: Extends existing single-project structure. Citations are a chat service concern, so they live in `services/chat/citations.py`. Vector search already returns metadata, NL2SQL pipeline needs minor updates to include event_id tracking.

## Complexity Tracking

No constitution violations. This section is not applicable.

---

## Planning Complete ✅

### Phase 0: Research (Complete)

All technical unknowns resolved in [research.md](research.md):
- ✅ Chat pipeline source tracking mechanism identified
- ✅ Vector search metadata structure analyzed
- ✅ Indico URL patterns documented
- ✅ NL2SQL event context requirements defined
- ✅ Streaming citation strategy determined
- ✅ Citation format standards established
- ✅ Error handling approach defined

**Key Findings**:
- Existing `ChatResponse.metadata` structure supports citation data
- Vector search already returns necessary metadata (needs minor additions)
- NL2SQL pipeline needs `source_event_ids` field added
- Markdown links work with existing chat client
- Post-processing approach for initial implementation

### Phase 1: Design (Complete)

Detailed design artifacts created:

1. **[data-model.md](data-model.md)**: Entity definitions
   - `SourceCitation`: Pydantic model for citation metadata
   - `ResponseWithCitations`: LLM response model with embedded citations
   - `CitationBuilder`: Service class for URL construction
   - Extended `ChatResponse` schema documentation
   - Extended `NL2SQLResponse` with source tracking

2. **[contracts/citation-models.md](contracts/citation-models.md)**: API contracts
   - Complete Pydantic schemas with validation rules
   - `CitationBuilder` class API documentation
   - Usage examples and test patterns
   - Type signatures and docstrings

3. **[quickstart.md](quickstart.md)**: Developer guide
   - Quick start examples
   - Common integration patterns
   - Configuration instructions
   - Troubleshooting guide

### Re-evaluation of Constitution Check

✅ **PASS** - Design phase confirms no violations:
- Extends existing chat service (Principle I: Plugin Architecture)
- Uses existing `/api/assistant/chat` endpoint (Principle II: API-First)
- No changes to LLM provider abstraction (Principle III)
- Graceful error handling documented (Principle IV)
- Base URL configuration via settings (Principle V)
- Test patterns documented in contracts (Principle VI)

### Next Steps

**Ready for `/speckit.tasks`** - Implementation can begin.

Key implementation sequence:
1. Implement `CitationBuilder` utility class
2. Update NL2SQL pipeline to return `source_event_ids`
3. Enhance document indexing to capture full URL metadata
4. Integrate citation generation into chat service
5. Add comprehensive test coverage

**Estimated Effort**: 
- Core implementation: ~3-4 days
- Testing & integration: ~2-3 days
- Documentation & polish: ~1 day
- **Total**: ~6-8 days

**Branch**: `015-chat-source-citations` (already created)  
**Files Generated**:
- ✅ plan.md (this file)
- ✅ research.md
- ✅ data-model.md
- ✅ contracts/citation-models.md
- ✅ quickstart.md

**Agent Context**: ✅ Updated (GitHub Copilot instructions)
