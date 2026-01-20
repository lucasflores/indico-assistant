# Contract: Query Classification Prompt Template

**Feature**: 013-nl2sql-prompt-optimization  
**Component**: `indico_assistant/services/nl2sql/classifier.py`  
**Variable**: `CLASSIFICATION_PROMPT`

## Overview

This contract defines the enhanced query classification prompt that routes user questions to the appropriate SQL generation template, including the new `document_content_query` intent for vector search.

---

## Prompt Template

```python
CLASSIFICATION_PROMPT = """You are a query classifier for the Indico event management system.
Analyze the user's question and classify it into one of these intents:

## INTENTS

- **event_query**: Questions about events, conferences, meetings (count, list, search, basic info)
- **registration_query**: Questions about event registrations, participants, check-ins
- **contribution_query**: Questions about talks, presentations, contributions, papers
- **speaker_query**: Questions about speakers, presenters, authors of contributions
- **session_query**: Questions about conference sessions, tracks, time blocks
- **attendee_query**: Questions about who attended events or registrations with personal details
- **schedule_query**: Questions about event schedules, timetables, timing of contributions
- **attachment_query**: Questions about file metadata (filenames, types, storage locations)
- **document_content_query**: Questions about the CONTENT within files (what slides say, paper contents)
- **general_info**: General questions about the system or unclear queries
- **out_of_scope**: Questions not related to events/registrations/contributions/documents

## CLASSIFICATION HINTS

### Intent Selection Rules

1. Use **speaker_query** if asking about WHO is presenting or authored something
2. Use **session_query** if asking about tracks, session blocks, or session times
3. Use **attendee_query** if asking about WHO attended or registered with personal details
4. Use **schedule_query** if asking about WHEN things happen or timetable entries
5. Use **contribution_query** for questions about talks/papers without speaker focus

### attachment_query vs document_content_query (IMPORTANT)

- Use **attachment_query** for FILE METADATA questions:
  - "What files are attached to event X?"
  - "List the PDFs uploaded to this meeting"
  - "How many attachments does this contribution have?"

- Use **document_content_query** for CONTENT questions:
  - "What does the presentation say about machine learning?"
  - "According to the paper, what is the main conclusion?"
  - "What topics are discussed in the slides?"
  - "Find documents that mention quantum computing"

**Key Indicators for document_content_query**:
- "says", "mentions", "according to", "talks about", "discusses"
- "what does the [file] say about"
- "content of", "written in", "stated in"
- "find documents about", "search files for"

## TIME REFERENCE DEFAULTS

When the user says:
- "recently", "lately" → last 7 days
- "soon", "upcoming" → next 7 days
- "a while ago", "some time ago" → last 30 days
- "this week" → current week (Monday to Sunday)
- "this month" → current calendar month
- "last week" → previous week
- "next week" → coming week

## EXTRACTION RULES

Extract the following from the question:
1. **Entities**: Event names, person names, file types, categories
2. **Time constraints**: Date ranges, relative time references
3. **Filters**: Any specific criteria (e.g., "only physics events", "speakers from CERN")

## INPUT

USER QUESTION: {question}

TODAY'S DATE: {today}

## OUTPUT

Respond with the classification in the exact format expected by the Pydantic model."""
```

---

## Template Variables

| Variable | Type | Source | Description |
|----------|------|--------|-------------|
| `question` | str | User input | The question to classify |
| `today` | str | `datetime.now().strftime("%Y-%m-%d")` | Current date for time reference resolution |

---

## Expected Output

The LLM MUST return a Pydantic-validated `QueryClassification` object:

```python
class QueryClassification(BaseModel):
    intent: str                      # One of the defined intents
    confidence: float                # 0.0-1.0 confidence in classification
    entities: list[Entity] | None    # Extracted entities
    time_range: TimeRange | None     # Extracted time constraints
    filters: dict[str, Any] | None   # Additional filters

class Entity(BaseModel):
    type: str   # "event", "person", "file_type", "category"
    value: str  # The extracted value

class TimeRange(BaseModel):
    start: str  # ISO date string
    end: str    # ISO date string
```

---

## Intent Routing

| Intent | SQL Template | Vector Search |
|--------|-------------|---------------|
| `event_query` | Template 1: Event Queries | No |
| `registration_query` | Custom (registrations table) | No |
| `contribution_query` | Template 2: Contributor/Speaker | No |
| `speaker_query` | Template 2: Contributor/Speaker | No |
| `session_query` | Custom (sessions table) | No |
| `attendee_query` | Custom (registrations + persons) | No |
| `schedule_query` | Custom (timetable_entries) | No |
| `attachment_query` | Template 3: Attachment/Material | No |
| `document_content_query` | Template 4: Vector Search | **Yes** |
| `general_info` | None (conversational response) | No |
| `out_of_scope` | None (rejection message) | No |

---

## Contract Tests

### Test 1: File Metadata → attachment_query

**Input**: "What files are attached to event 123?"
**Expected**:
- `intent`: "attachment_query"
- NOT "document_content_query"

### Test 2: File Content → document_content_query

**Input**: "What does the presentation say about machine learning?"
**Expected**:
- `intent`: "document_content_query"

### Test 3: "According to" → document_content_query

**Input**: "According to the slides, what was the main finding?"
**Expected**:
- `intent`: "document_content_query"

### Test 4: "Find documents about" → document_content_query

**Input**: "Find documents that mention ATLAS detector"
**Expected**:
- `intent`: "document_content_query"
- `entities`: Contains entity with type "topic" or similar

### Test 5: Speaker Question → speaker_query

**Input**: "Who presented at ICHEP 2024?"
**Expected**:
- `intent`: "speaker_query"
- `entities`: Contains event entity "ICHEP 2024"

### Test 6: Time Reference Resolution

**Input**: "What events happened this week?"
**Today**: 2026-01-19
**Expected**:
- `intent`: "event_query"
- `time_range.start`: "2026-01-13" (Monday)
- `time_range.end`: "2026-01-19" (Sunday)

### Test 7: Out of Scope

**Input**: "What's the weather like today?"
**Expected**:
- `intent`: "out_of_scope"
