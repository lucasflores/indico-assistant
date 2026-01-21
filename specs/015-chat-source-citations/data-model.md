# Data Model: Chat Source Citations

**Feature**: 015-chat-source-citations  
**Phase**: 1 - Design  
**Date**: 2026-01-20

## Overview

This feature extends the chat service to track and format source citations. No new database tables required; extends existing models and adds citation formatting logic.

---

## Core Entities

### 1. SourceCitation (Pydantic Model)

**Purpose**: Represents a single source citation with URL and metadata.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| type | Literal["event", "document"] | Yes | Source type for proper URL formatting |
| event_id | int | Yes | Indico event ID |
| contribution_id | int \| None | No | Contribution ID (only for documents) |
| attachment_id | int \| None | No | Attachment ID (only for documents) |
| file_id | int \| None | No | File ID (only for documents) |
| filename | str \| None | No | Original filename (only for documents) |
| url | str | Yes | Fully constructed citation URL |
| description | str | Yes | Human-readable source descriptor |

**Validation Rules**:
- `url` must be valid HTTP/HTTPS URL
- For type="document": `attachment_id`, `file_id`, `filename` must all be present
- For type="event": only `event_id` required
- `description` format: "Event: {title}" or "Document: {filename}"

**Example**:
```python
# Event citation
SourceCitation(
    type="event",
    event_id=7,
    url="http://localhost:8000/event/7/",
    description="Event: ICHEP 2024"
)

# Document citation
SourceCitation(
    type="document",
    event_id=7,
    contribution_id=3,
    attachment_id=4,
    file_id=6,
    filename="1706.03762v7.pdf",
    url="http://localhost:8000/event/7/contributions/3/attachments/4/6/1706.03762v7.pdf",
    description="Document: 1706.03762v7.pdf"
)
```

---

### 2. ResponseWithCitations (Pydantic Model)

**Purpose**: LLM response model that includes inline citations in the answer text.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| answer | str | Yes | Response text with embedded markdown `[source](url)` links |
| confidence | float | Yes | Confidence score (0.0-1.0) |
| citations | list[SourceCitation] | Yes | Structured citation metadata for validation |

**Validation Rules**:
- `answer` must not be empty
- `confidence` must be between 0.0 and 1.0
- `citations` list can be empty (for general knowledge responses)
- Each citation in `citations` must have valid URL

**Example**:
```python
ResponseWithCitations(
    answer="The workshop is on January 25th ([source](http://localhost:8000/event/7/)). According to the paper ([source](http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf)), the results show...",
    confidence=0.92,
    citations=[
        SourceCitation(
            type="event",
            event_id=7,
            url="http://localhost:8000/event/7/",
            description="Event: Workshop Series"
        ),
        SourceCitation(
            type="document",
            event_id=7,
            contribution_id=3,
            attachment_id=4,
            file_id=6,
            filename="paper.pdf",
            url="http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf",
            description="Document: paper.pdf"
        )
    ]
)
```

---

### 3. CitationBuilder (Service Class)

**Purpose**: Utility class for constructing citation URLs and markdown links.

| Attribute | Type | Description |
|-----------|------|-------------|
| base_url | str | Indico base URL (from plugin settings) |

| Method | Signature | Description |
|--------|-----------|-------------|
| build_event_citation | `build_event_citation(event_id: int) -> str` | Returns markdown `[source](url)` for event |
| build_document_citation | `build_document_citation(event_id: int, contribution_id: int, attachment_id: int, file_id: int, filename: str) -> str` | Returns markdown `[source](url)` for document |
| build_event_url | `build_event_url(event_id: int) -> str` | Constructs event page URL |
| build_document_url | `build_document_url(...) -> str` | Constructs attachment URL with proper encoding |

**Example**:
```python
builder = CitationBuilder(base_url="http://localhost:8000")

event_citation = builder.build_event_citation(7)
# Returns: "[source](http://localhost:8000/event/7/)"

doc_citation = builder.build_document_citation(
    event_id=7, 
    contribution_id=3,
    attachment_id=4,
    file_id=6,
    filename="paper.pdf"
)
# Returns: "[source](http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf)"
```

---

### 4. Extended ChatResponse Schema

**Purpose**: Existing API response schema with updated metadata structure.

**Changes to existing schema** (`indico_assistant/schemas/chat.py`):

```python
# BEFORE
class ChatResponse(BaseModel):
    response: str
    session_id: UUID
    message_id: UUID
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (sql_generated, confidence, data_sources)"
    )

# AFTER - metadata.data_sources structure changes
# from: ["table1", "table2"]
# to: [{"type": "event", "url": "...", ...}, {"type": "document", "url": "...", ...}]
```

**Updated metadata structure**:
```python
{
    "sql_generated": "SELECT * FROM events.events WHERE ...",
    "confidence": 0.92,
    "data_sources": [
        {
            "type": "event",
            "event_id": 7,
            "url": "http://localhost:8000/event/7/",
            "description": "Event: ICHEP 2024"
        },
        {
            "type": "document",
            "event_id": 7,
            "attachment_id": 4,
            "filename": "paper.pdf",
            "url": "http://localhost:8000/event/7/contributions/3/attachments/4/6/paper.pdf",
            "description": "Document: paper.pdf"
        }
    ]
}
```

**Backwards Compatibility**: Consumers expecting `data_sources: list[str]` will need updates. Consider deprecation period with both formats.

---

### 5. Extended NL2SQLResponse

**Purpose**: Add source tracking to NL2SQL pipeline response.

**Addition to existing response**:

| Field | Type | Description |
|-------|------|-------------|
| source_event_ids | list[int] | Event IDs that contributed to the result |

**Example**:
```python
{
    "success": True,
    "sql": "SELECT title FROM events.events WHERE id = 7",
    "results": [...],
    "confidence": 0.9,
    "source_event_ids": [7]  # NEW FIELD
}
```

---

## Data Flow

### Citation Generation Flow

```
1. User Query → ChatService.send_message()

2A. NL2SQL Path:
   ├─ NL2SQLPipeline.execute() → Returns SQL + results + source_event_ids
   ├─ For each event_id → CitationBuilder.build_event_citation()
   └─ Collect event citations

2B. Vector Search Path:
   ├─ RAGService.get_context() → Returns SearchResult[] with metadata
   ├─ For each result → Extract (event_id, contribution_id, attachment_id, file_id, filename)
   ├─ CitationBuilder.build_document_citation()
   └─ Collect document citations

3. Build LLM Prompt:
   ├─ Include context + available citations
   ├─ Instruct LLM to use [source](url) markdown syntax
   └─ LLMService.generate(prompt, ResponseWithCitations)

4. Validate Response:
   ├─ Check citations[] against URLs in answer text
   ├─ Gracefully handle missing citations (FR-010)
   └─ Return ChatResponse with response + metadata.data_sources

5. Client Renders:
   └─ Markdown links displayed as clickable hyperlinks
```

---

### Source Metadata Extraction

**From NL2SQL**:
```python
# Current: Only table names tracked
data_sources = ["events.events", "events.contributions"]

# New: Event IDs extracted from:
# 1. Explicit event_id parameter
# 2. SQL WHERE clause (event_id = X)
# 3. Result set analysis (which events returned)
source_event_ids = [7, 12, 45]
```

**From Vector Search**:
```python
# Current: SearchResult has event_id, attachment_id directly
# Needed: Extract contribution_id, file_id from metadata_json

search_result.metadata = {
    "filename": "paper.pdf",
    "page": 5,
    "contribution_id": 3,  # MUST be added during indexing
    "file_id": 6            # MUST be added during indexing
}
```

---

## Index & Query Patterns

No new database indexes required. Citations are generated in-memory during request processing.

---

## Migration Notes

**No database migrations required**.

**Code changes only**:

1. **Document Indexing** (`indico_assistant/tasks/indexing.py`):
   - Ensure `metadata_json` includes `contribution_id` and `file_id`
   - Extract these from Indico's attachment API response

2. **NL2SQL Pipeline** (`indico_assistant/services/nl2sql/`):
   - Add `source_event_ids` to response
   - Track event IDs during query execution

3. **Citation Builder** (new file `indico_assistant/services/chat/citations.py`):
   - Implement URL construction utilities

4. **Chat Service** (`indico_assistant/services/chat/service.py`):
   - Integrate citation generation
   - Update metadata.data_sources format

---

## Validation Strategy

### Pydantic Validation

All citation models use Pydantic validation:
- URL format validation (must be valid HTTP/HTTPS)
- Required fields enforcement
- Type checking

### Citation Consistency Check

Before returning response:
```python
def validate_citations(response: ResponseWithCitations) -> bool:
    """Verify all citations in metadata appear in answer text."""
    for citation in response.citations:
        if citation.url not in response.answer:
            logger.warning(f"Citation {citation.url} not found in answer")
            # Continue anyway (graceful degradation)
    return True
```

---

## Error Handling

Per Constitution Principle IV (Graceful Degradation):

| Error Scenario | Handling |
|----------------|----------|
| Base URL not configured | Skip citations, log warning, return response without links |
| metadata_json missing URL components | Skip that citation, include others |
| URL encoding fails | Skip that citation, log error |
| LLM doesn't include citations | Return response as-is (citations metadata still available) |
| Citation validation fails | Log warning, return response with partial citations |

**Key Principle**: Citation failures MUST NOT break responses (FR-010).
