# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
SQL generator component for NL2SQL pipeline.

Generates SQL queries from classified questions using LLM with
schema context.
"""

from datetime import datetime

from indico_assistant.services.llm import LLMService
from indico_assistant.services.llm.models import (
    LLMResponse,
    QueryClassification,
    SQLGeneration,
)
from indico_assistant.services.nl2sql.schema import SchemaContext


# SQL generation prompt template (T041-T042: enhanced for multi-table queries)
# Feature 012: conversation history placeholder added (T005)
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
8. Do NOT use CTEs (WITH clause), subqueries (nested SELECT in parentheses), or window functions (OVER clause)
   - Instead of subqueries for filtering, use JOINs with appropriate WHERE conditions
   - Instead of scalar subqueries like (SELECT x FROM y WHERE...), JOIN the table and filter in WHERE
   - Example BAD: WHERE id NOT IN (SELECT id FROM table WHERE condition)
   - Example GOOD: LEFT JOIN table t ON main.id = t.id WHERE t.id IS NULL OR NOT t.condition
9. Do NOT generate multiple SQL queries - always output a single SQL block
10. NEVER include markdown, comments, or explanations - just return the SQL

**IMPORTANT**: 
   - Only add date/time filters if explicitly requested by the user (e.g., "last week", "upcoming", "in January").
{context_section}


## TEXT MATCHING RULES

- Avoid exact equality for names/titles unless the user explicitly requests an exact match
- Prefer case-insensitive partial matching with ILIKE and wildcards for names and titles
- For a single person name (e.g., "Bob"), match against first_name OR last_name
- For full names (e.g., "Bob Smith"), match both first_name and last_name with ILIKE

## CURRENT USER FILTERING

- If the question refers to "I", "me", or "my", filter using `events.persons.user_id = :user_id`
- Do NOT use subqueries or `current_user` to resolve identity
- Join `events.persons` and filter by `:user_id` instead

## EVENT CONTEXT

- If the request is scoped to a specific event, use `event_id = :event_id`
- Prefer `:event_id` for references like "this meeting" or "this event"

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
ORDER BY e.start_dt DESC
LIMIT 20
```

**MEETING MINUTES/NOTES**: For questions about meeting minutes, notes, or summaries, JOIN events.notes:
```sql
SELECT e.id, e.title, n.html AS notes
FROM events.events e
LEFT JOIN events.notes n ON e.id = n.event_id AND n.is_deleted = false
WHERE e.is_deleted = false
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

## ALTERNATIVE PATTERNS (NO CTEs/SUBQUERIES)

- Use JOINs to combine tables instead of CTEs or subqueries
- For "top N" or ranking requests, use ORDER BY + LIMIT (no window functions)
- For aggregations, use GROUP BY with aggregate functions (STRING_AGG, COUNT, SUM)

These restrictions minimize risk and keep queries safe and efficient.

{schema_context}

{conversation_history}

## USER QUESTION

{question}

{permission_filter}

Generate a single SQL query that:
1. Answers the user's question accurately
2. Uses only the tables and columns from the schema above
3. Follows the appropriate template based on query intent
4. Includes required output columns for event queries
5. Uses JOINs (not subqueries) when combining tables
6. If a Time Range is provided, use it exactly in a BETWEEN filter
7. Is safe and efficient"""

### CLASSIFICATION
#
#- Intent: {intent}
#- Time Range: {time_range}
#- Entities: {entities}
#- Filters: {filters}


class SQLGenerator:
    """Generates SQL queries from classified questions."""

    # Multi-entity intent list (T041: JOINs needed)
    MULTI_ENTITY_INTENTS = {
        "contribution_query",
        "speaker_query",
        "session_query",
        "attendee_query",
        "schedule_query",
    }

    def __init__(
        self,
        llm_service: LLMService,
        schema_context: SchemaContext,
    ) -> None:
        """
        Initialize the generator.

        Args:
            llm_service: The LLM service for SQL generation.
            schema_context: Schema context provider.
        """
        self._llm_service = llm_service
        self._schema_context = schema_context

    def generate(
        self,
        question: str,
        classification: QueryClassification,
        allowed_event_ids: list[int] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        user_id: int | None = None,
        event_id: int | None = None,        validation_feedback: str | None = None,    ) -> LLMResponse[SQLGeneration]:
        """
        Generate SQL from a classified question.

        Args:
            question: The original natural language question.
            classification: The query classification result.
            allowed_event_ids: Optional list of event IDs the user can access.
                If provided, the generated SQL will be filtered to only
                these events.
            conversation_history: Optional conversation history for context.
                List of message dicts with 'role' and 'content' keys.
                Limited to last 10 message pairs (20 messages).

        Returns:
            LLMResponse containing SQLGeneration with generated SQL.
        """
        # Get relevant tables based on intent
        tables = self._schema_context.get_tables_for_intent(classification.intent)

        # Build schema context prompt - use enhanced version with JOIN hints
        # for multi-entity intents (T041-T042)
        if classification.intent in self.MULTI_ENTITY_INTENTS:
            schema_prompt = self._schema_context.get_schema_prompt_with_joins(tables)
        else:
            schema_prompt = self._schema_context.get_schema_prompt(tables)

        # Build permission filter instruction
        permission_filter = self._build_permission_filter(allowed_event_ids)

        # Format time range for prompt
        time_range_str = "None"
        if classification.time_range:
            time_range_str = f"From {classification.time_range.start} to {classification.time_range.end}"

        # Format entities for prompt
        entities_str = "None"
        if classification.entities:
            entities_str = ", ".join(
                f"{e.type}: {e.value}" for e in classification.entities
            )

        # Format filters for prompt
        filters_str = str(classification.filters) if classification.filters else "None"

        # Format conversation history (Feature 012: T003)
        history_prompt = self._format_conversation_history(conversation_history)

        # Format context section with conditional event_id (Feature 013: event context)
        # Only include CURRENT EVENT ID line if event_id is actually available
        today_str = datetime.now().strftime("%Y-%m-%d")
        user_id_str = str(user_id) if user_id is not None else "unknown"
        
        context_lines = [
            f"   - TODAY'S DATE: {today_str}",
            f"   - CURRENT USER ID: {user_id_str}",
        ]
        
        if event_id is not None:
            context_lines.append(f"   - CURRENT EVENT ID: {event_id}")
        
        context_section = "\n".join(context_lines)

        # Build the full prompt
        prompt = SQL_GENERATION_PROMPT.format(
            schema_context=schema_prompt,
            conversation_history=history_prompt,
            question=question,
            intent=classification.intent,
            time_range=time_range_str,
            entities=entities_str,
            filters=filters_str,
            permission_filter=permission_filter,
            context_section=context_section,
        )

        # Append validation feedback if this is a retry
        if validation_feedback:
            prompt += f"\n\n## VALIDATION FEEDBACK\n{validation_feedback}\n"

        # Generate SQL using LLM
        return self._llm_service.generate(
            prompt=prompt,
            response_model=SQLGeneration,
        )

    def is_multi_entity_intent(self, intent: str) -> bool:
        """
        Check if an intent requires multi-table JOINs.

        Args:
            intent: The query intent

        Returns:
            True if the intent typically needs JOINs.
        """
        return intent in self.MULTI_ENTITY_INTENTS

    def _build_permission_filter(
        self, allowed_event_ids: list[int] | None
    ) -> str:
        """
        Build permission filter instruction for the prompt.

        Args:
            allowed_event_ids: List of event IDs the user can access.

        Returns:
            Permission filter instruction string.
        """
        if allowed_event_ids is None:
            return ""

        if not allowed_event_ids:
            return (
                "PERMISSION FILTER: User has no accessible events. "
                "Return an empty result set."
            )

        # For large lists, use a general instruction
        if len(allowed_event_ids) > 100:
            return (
                "PERMISSION FILTER: Include a WHERE clause filtering "
                "event_id to only user-accessible events. "
                "Use event_id IN (:allowed_event_ids) with the parameter."
            )

        # For a single event, use parameterized event_id
        if len(allowed_event_ids) == 1:
            event_id = allowed_event_ids[0]
            return (
                "PERMISSION FILTER: CRITICAL - Scope results to the current event. "
                "Use event_id = :event_id in the WHERE clause. "
                f"Current event_id: {event_id}"
            )

        # For smaller lists, include the actual IDs
        ids_str = ", ".join(str(id) for id in allowed_event_ids[:50])
        if len(allowed_event_ids) > 50:
            ids_str += f" ... and {len(allowed_event_ids) - 50} more"

        return (
            f"PERMISSION FILTER: CRITICAL - Filter results to ONLY these "
            f"event IDs: {ids_str}\n"
            f"Add WHERE event_id IN ({', '.join(str(id) for id in allowed_event_ids)}) "
            f"to any query involving events."
        )

    @property
    def schema_context(self) -> SchemaContext:
        """Get the schema context."""
        return self._schema_context

    def _truncate_message(self, content: str, max_chars: int = 15000) -> str:
        """Truncate message content to maximum length with ellipsis.
        
        Feature 012: Prevent token overflow in conversation history (T004, FR-012).
        
        Args:
            content: Original message content
            max_chars: Maximum characters (default 1500)
            
        Returns:
            Original content if under limit, or truncated with "..."
        """
        if len(content) <= max_chars:
            return content
        return content[:max_chars] + "..."

    def _format_conversation_history(
        self,
        conversation_history: list[dict[str, str]] | None
    ) -> str:
        """Format conversation history for prompt inclusion.
        
        Feature 012: Enable co-reference resolution and contextual queries (T003, FR-013).
        Formats history as numbered messages in chronological order.
        
        Args:
            conversation_history: List of messages with 'role' and 'content' keys.
                Expected format: [{"role": "user", "content": "..."}, ...]
                
        Returns:
            Formatted string with numbered messages, or empty string if no history.
            
        Example output:
            CONVERSATION HISTORY:
            1. User: What events are happening this week?
            2. Assistant: Found 3 events: Meeting A, Conference B, Workshop C
            3. User: Tell me more about the first one
        """
        if not conversation_history:
            return ""
        
        # Enforce 10-pair (20 message) limit (FR-006)
        recent_history = conversation_history[-20:]
        
        formatted = ["CONVERSATION HISTORY:"]
        for idx, msg in enumerate(recent_history, start=1):
            role = msg["role"].capitalize()  # "User" or "Assistant"
            content = self._truncate_message(msg["content"])
            formatted.append(f"{idx}. {role}: {content}")
        
        return "\n".join(formatted)
