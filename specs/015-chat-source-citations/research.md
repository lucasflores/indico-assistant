# Research: Chat Source Citations

**Feature**: 015-chat-source-citations  
**Phase**: 0 - Outline & Research  
**Date**: 2026-01-20

## Research Questions

### 1. How does the existing chat pipeline track response sources?

**Finding**: The chat pipeline currently returns metadata in `ChatResponse.metadata` dict with keys:
- `sql_generated`: The SQL query string (for NL2SQL responses)
- `confidence`: LLM confidence score (0-1)
- `data_sources`: List of table names (for NL2SQL responses)

**Source**: `indico_assistant/schemas/chat.py` (line 41), `specs/010-chat-pipeline-integration/contracts/chat-api.md`

**Decision**: Extend `metadata.data_sources` to include full source information (URLs, types) instead of just table names.

**Rationale**: Reusing existing metadata structure minimizes API changes and maintains backwards compatibility.

---

### 2. What metadata is available in vector search results?

**Finding**: `SearchResult` dataclass includes:
- `content`: Matching text
- `similarity`: Cosine similarity score
- `event_id`: Indico event ID
- `attachment_id`: Indico attachment ID  
- `chunk_index`: Position in document
- `metadata`: Dict from `ExtractedDocument.metadata_json`

The `ExtractedDocument` model stores `metadata_json` as JSONB containing:
- `filename`: Original file name
- `page`: Page number (if applicable)
- Other extraction metadata

**Source**: `indico_assistant/services/vector_search/search.py` (line 30), `indico_assistant/models/document.py` (line 93)

**Decision**: Need to ensure `metadata_json` includes full URL components: `event_id`, `contribution_id`, `attachment_id`, `file_id`. Currently only has `event_id` and `attachment_id` directly.

**Rationale**: Missing URL components (`contribution_id`, `file_id`) must be captured during document indexing to construct full attachment URLs.

---

### 3. What is Indico's attachment URL structure?

**Finding**: Based on user requirement and codebase patterns:
- Event page: `http://{base_url}/event/{event_id}/`
- Attachment: `http://{base_url}/event/{event_id}/contributions/{contrib_id}/attachments/{attach_id}/{file_id}/{filename}`

**Source**: User specification (spec.md line 6), Indico URL patterns (standard across all events)

**Decision**: Store base URL in plugin settings (global + per-event override). Extract URL components from Indico's attachment API response during indexing.

**Rationale**: Base URL varies by environment (dev: localhost:8000, prod: custom domain). URL components must be extracted from Indico's native attachment objects.

---

### 4. How does NL2SQL pipeline expose event context?

**Finding**: The NL2SQL pipeline (`create_nl2sql_pipeline()`) accepts `event_id` parameter but doesn't currently track which events contributed to results. The pipeline returns SQL query and results but not event-level sourcing.

**Source**: `indico_assistant/services/nl2sql/__init__.py`, `specs/003-nl2sql-pipeline/`

**Decision**: Modify NL2SQL pipeline to include `event_ids: list[int]` in its response, populated from:
1. Explicit `event_id` parameter (if provided)
2. Event IDs extracted from SQL WHERE clause (if querying specific events)
3. All events in result set (if query spans multiple events)

**Rationale**: Event-level citations require knowing which events contributed to the answer. This must be tracked during query execution.

---

### 5. How to handle streaming responses with incremental citations?

**Finding**: Current implementation uses synchronous response generation (no streaming in backend yet). Chainlit displays full responses after generation completes.

**Source**: `chainlit_app/app_chnlit.py` (line 309), `indico_assistant/controllers/chat.py`

**Decision**: Instruct LLM to embed citations inline using `[source](url)` markdown syntax during response generation. This approach naturally supports both streaming and synchronous responses:
1. Citations embedded directly in text as LLM generates response
2. Backend provides available citation URLs in prompt context
3. Markdown links stream naturally with text (no post-processing needed)
4. Backend validates citation usage after generation

**Rationale**: Inline markdown citations work identically whether text streams incrementally or returns all at once. LLM includes `[source](url)` as it writes, so citations appear with their corresponding content automatically.

---

### 6. Best practices for markdown link generation in Python?

**Finding**: Standard markdown link syntax: `[text](url)`. Python has no built-in markdown library needed; simple f-string formatting suffices.

For URL encoding:
```python
from urllib.parse import quote
safe_url = f"http://base/{quote(filename)}"
```

**Source**: Python stdlib `urllib.parse`, Markdown spec

**Decision**: Use f-strings with `urllib.parse.quote()` for filenames. Template:
```python
event_citation = f"[source](http://{base}/{event_id}/)"
doc_citation = f"[source](http://{base}/event/{event_id}/contributions/{contrib_id}/attachments/{attach_id}/{file_id}/{quote(filename)})"
```

**Rationale**: Simple, no external dependencies, standard Python approach.

---

### 7. How to integrate citations with existing LLM response models?

**Finding**: Existing `ResponseSummary` model has:
```python
class ResponseSummary(BaseModel):
    answer: str
    confidence: float
    sources: list[str]  # Currently just table names
```

**Source**: `indico_assistant/services/llm/models/summary.py` (line 12)

**Decision**: Create new response model `ResponseWithCitations(BaseModel)` that extends `ResponseSummary`:
```python
class SourceCitation(BaseModel):
    type: Literal["event", "document"]
    url: str
    description: str  # "Event: Title" or "Document: filename"

class ResponseWithCitations(BaseModel):
    answer: str  # Text with embedded [source](url) links
    confidence: float
    citations: list[SourceCitation]  # For validation/metadata
```

**Rationale**: Separates citation metadata from response text, enables validation, maintains backwards compatibility by extending existing models.

---

### 8. Error handling strategy for missing metadata?

**Finding**: Current error handling follows graceful degradation principle (Constitution IV). Services return success/error wrapped responses.

**Source**: Constitution.md, `indico_assistant/services/llm/errors.py`

**Decision**: Citation generation failures MUST NOT break responses:
1. If URL components missing → skip citation (no link)
2. If base URL not configured → skip citation
3. If citation formatting fails → log warning, continue without citation

Return response with partial/no citations rather than failing.

**Rationale**: Citations enhance transparency but aren't critical to core functionality. Users get response even if citations unavailable.

---

## Technology Choices

### Citation Formatting

**Chosen**: Pure Python string formatting with `urllib.parse`

**Alternatives Considered**:
- Markdown library (python-markdown): Overkill for simple link generation
- Template engine (Jinja2): Unnecessary complexity

**Rationale**: Simple URL construction doesn't need external dependencies.

---

### Source Tracking Data Structure

**Chosen**: Extend existing `ChatResponse.metadata` dict:
```python
metadata = {
    "sql_generated": "SELECT ...",
    "confidence": 0.9,
    "data_sources": [
        {
            "type": "event",
            "event_id": 7,
            "url": "http://localhost:8000/event/7/"
        },
        {
            "type": "document",
            "event_id": 7,
            "filename": "paper.pdf",
            "url": "http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf"
        }
    ]
}
```

**Alternatives Considered**:
- New top-level field in ChatResponse: More invasive API change
- Separate `/api/assistant/chat/citations` endpoint: Adds complexity

**Rationale**: Leverages existing extensible metadata structure.

---

### Markdown Link Placement

**Chosen**: Inline markdown links embedded in LLM response text: `The workshop is on January 25th ([source](http://localhost:8000/event/7/))`

**Alternatives Considered**:
- HTML links: Would require HTML rendering in chat widget (not currently supported)
- Footnote-style references: Clarification session decided against this (always prefer inline)

**Rationale**: Markdown links work in Chainlit and most chat UIs, inline placement per user preference (clarification Q4).

---

## Implementation Approach

### Phase Breakdown

**Phase 0** (this document): Research complete ✅

**Phase 1**: Design
- Data model for source tracking
- Pydantic contracts for citation models
- API documentation

**Phase 2**: Implementation
1. Extend NL2SQL pipeline to return event_ids
2. Ensure vector search metadata includes all URL components
3. Implement citation formatter service
4. Integrate citations into chat service
5. Update ChatResponse schema

**Phase 3**: Testing
- Unit tests for citation formatting
- Integration tests for source tracking
- Contract tests for response models
- E2E tests with both NL2SQL and RAG sources

---

## Open Questions Resolved

All research questions from Technical Context have been resolved. No `NEEDS CLARIFICATION` markers remain.

**Verification**: ✅ Ready for Phase 1 (Design)
