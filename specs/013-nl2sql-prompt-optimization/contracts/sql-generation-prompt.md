# Contract: SQL Generation Prompt Template

**Feature**: 013-nl2sql-prompt-optimization  
**Component**: `indico_assistant/services/nl2sql/generator.py`  
**Variable**: `SQL_GENERATION_PROMPT`

## Overview

This contract defines the enhanced SQL generation prompt that instructs the LLM to generate PostgreSQL queries following reference implementation patterns.

---

## Prompt Template

```python
SQL_GENERATION_PROMPT = """You are a PostgreSQL expert tasked with generating a single executable SQL query for the Indico event management system.

Use the chat history to understand context or references to previous queries. The user's latest question appears at the bottom.

## STRICT RULES

1. Use only valid SQL syntax compatible with PostgreSQL and pgvector
2. ONLY generate SELECT statements - never INSERT, UPDATE, DELETE, or DDL
3. Carefully consider the table and column descriptions to form the query
4. Do not query for columns that do not exist
5. Pay attention to which column is in which table
6. Pay special attention to Foreign Keys - they designate relationships between tables
7. Pay special attention to date/time constraints - use PostgreSQL functions (CURRENT_DATE, NOW()) for the current date
8. Do NOT use CTEs (WITH clause), subqueries, or window functions - use JOINs instead
9. Do NOT generate multiple SQL queries - always output a single SQL block
10. NEVER include markdown, comments, or explanations - just return the SQL

## REQUIRED OUTPUT COLUMNS

For event-related queries, ALWAYS include:
- `event_id`: The event identifier (use alias "event_id")
- `event_title`: The event title (use alias "event_title")
- `event_start_dt`: Start date/time formatted as human-readable (use alias "event_start_dt")
- `event_timezone`: The event timezone (use alias "event_timezone")

Use this pattern for date formatting:
```sql
to_char(e.start_dt AT TIME ZONE e.timezone, 'Month DD YYYY, HH12:MI AM') AS event_start_dt
```

Include extra columns beyond the minimum that may add context (description, venue_name, room_name, etc.).

## FOREIGN KEY RELATIONSHIPS

- `events.events.id` is equivalent to `events.contributions.event_id`
- `events.events.id` is equivalent to `events.registrations.event_id`
- `events.events.id` is equivalent to `events.sessions.event_id`
- `events.contributions.id` is equivalent to `events.contribution_person_links.contribution_id`
- `events.contribution_person_links.person_id` is equivalent to `events.persons.id`
- `attachments.folders.event_id` is equivalent to `events.events.id`
- `attachments.folders.id` is equivalent to `attachments.attachments.folder_id`
- `attachments.attachments.file_id` is equivalent to `attachments.files.id`

## SQL TEMPLATES

### Template 1: Event Queries

Use this pattern for questions about events/meetings:

```sql
SELECT
  e.id AS event_id,
  e.title AS event_title,
  to_char(e.start_dt AT TIME ZONE e.timezone, 'Month DD YYYY, HH12:MI AM') AS event_start_dt,
  e.timezone AS event_timezone,
  e.description,
  e.venue_name,
  e.room_name,
  e.address,
  e.type
FROM events.events e
WHERE e.is_deleted = false
  AND e.start_dt >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY e.start_dt DESC
LIMIT 20
```

### Template 2: Contributor/Speaker Queries

Use this pattern with STRING_AGG for aggregating multiple contributors:

```sql
SELECT
  e.id AS event_id,
  e.title AS event_title,
  to_char(e.start_dt AT TIME ZONE e.timezone, 'Month DD YYYY, HH12:MI AM') AS event_start_dt,
  e.timezone AS event_timezone,
  STRING_AGG(
    CONCAT(
      'Name: ', p.first_name, ' ', p.last_name,
      ', Affiliation: ', p.affiliation,
      ', Contribution: ', c.title
    ), 
    '; '
  ) AS contributors
FROM events.events e
LEFT JOIN events.contributions c ON e.id = c.event_id
LEFT JOIN events.contribution_person_links cpl ON c.id = cpl.contribution_id
LEFT JOIN events.persons p ON cpl.person_id = p.id
WHERE e.is_deleted = false
  AND e.id = :event_id
GROUP BY e.id, e.title, e.start_dt, e.timezone
```

### Template 3: Attachment/Material Queries

Use this pattern for questions about files and materials:

```sql
SELECT 
  f.storage_file_id,
  f.filename,
  f.content_type,
  f.size,
  e.id AS event_id,
  e.title AS event_title
FROM attachments.folders fo
JOIN attachments.attachments a ON fo.id = a.folder_id
JOIN attachments.files f ON a.file_id = f.id
JOIN events.events e ON fo.event_id = e.id
WHERE fo.event_id = :event_id
```

### Template 4: Document Content Vector Search

Use this pattern for questions about content WITHIN files (uses pgvector similarity):

```sql
SELECT 
  ed.content_text AS extracted_content,
  ed.metadata_json->>'filename' AS filename,
  ed.event_id,
  1 - (ed.embedding <=> :query_vector) AS similarity_score
FROM plugin_assistant.extracted_documents ed
WHERE ed.embedding IS NOT NULL
  AND ed.extraction_status = 'completed'
ORDER BY ed.embedding <=> :query_vector
LIMIT 10
```

IMPORTANT for vector search:
- The `<=>` operator returns a FLOAT (distance), NOT a boolean
- Do NOT use `<=>` in WHERE clause for comparison
- ALWAYS use ORDER BY with `<=>` for similarity ranking
- The `:query_vector` parameter will be substituted at execution time

{schema_context}

{conversation_history}

## USER QUESTION

{question}

## CLASSIFICATION

- Intent: {intent}
- Time Range: {time_range}
- Entities: {entities}
- Filters: {filters}

{permission_filter}

Generate a single SQL query that:
1. Answers the user's question accurately
2. Uses only the tables and columns from the schema above
3. Follows the appropriate template based on query intent
4. Includes required output columns for event queries
5. Uses JOINs (not subqueries) when combining tables
6. Is safe and efficient"""
```

---

## Template Variables

| Variable | Type | Source | Description |
|----------|------|--------|-------------|
| `schema_context` | str | `SchemaContext.get_schema_prompt()` | Database schema with tables, columns, types |
| `conversation_history` | str | `SQLGenerator._format_conversation_history()` | Previous messages for co-reference |
| `question` | str | User input | Current question |
| `intent` | str | `QueryClassification.intent` | Classified query intent |
| `time_range` | str | `QueryClassification.time_range` | Extracted time constraints |
| `entities` | str | `QueryClassification.entities` | Extracted entities |
| `filters` | str | `QueryClassification.filters` | Additional filters |
| `permission_filter` | str | `SQLGenerator._build_permission_filter()` | Event ID restrictions |

---

## Expected Output

The LLM MUST return a Pydantic-validated `SQLGeneration` object:

```python
class SQLGeneration(BaseModel):
    query: str           # The generated SQL query
    tables_used: list[str]  # Tables referenced in query
    confidence: float    # 0.0-1.0 confidence score
    explanation: str     # Brief explanation of query
```

---

## Contract Tests

### Test 1: Event Query Returns Required Columns

**Input**:
- question: "What events are happening this week?"
- intent: "event_query"

**Expected Output SQL Contains**:
- `AS event_id`
- `AS event_title`
- `AS event_start_dt`
- `AS event_timezone`
- `to_char(` (date formatting)
- `AT TIME ZONE` (timezone conversion)

### Test 2: Speaker Query Uses STRING_AGG

**Input**:
- question: "Who spoke at event 123?"
- intent: "speaker_query"

**Expected Output SQL Contains**:
- `STRING_AGG(`
- `events.contribution_person_links`
- `events.persons`
- `GROUP BY`

### Test 3: Document Query Uses Vector Pattern

**Input**:
- question: "What does the presentation say about machine learning?"
- intent: "document_content_query"

**Expected Output SQL Contains**:
- `plugin_assistant.extracted_documents`
- `<=> :query_vector`
- `ORDER BY` (not in WHERE)
- `embedding`

### Test 4: No Forbidden Patterns

**Any Input**:

**Expected Output SQL Does NOT Contain**:
- `WITH ` (CTE)
- `( SELECT` (subquery)
- `OVER (` (window function)
- `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`
