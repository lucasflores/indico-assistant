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

from indico_assistant.services.llm import LLMService
from indico_assistant.services.llm.models import (
    LLMResponse,
    QueryClassification,
    SQLGeneration,
)
from indico_assistant.services.nl2sql.schema import SchemaContext


# SQL generation prompt template (T041-T042: enhanced for multi-table queries)
SQL_GENERATION_PROMPT = """You are a SQL query generator for the Indico event management system.
Generate a PostgreSQL SELECT query to answer the user's question.

STRICT RULES:
1. ONLY generate SELECT statements - never INSERT, UPDATE, DELETE, or DDL
2. Use ONLY the tables listed in the schema below
3. Use proper table aliases for clarity (see suggested aliases in schema)
4. Include appropriate WHERE clauses for filtering
5. Use literal values when filtering (avoid parameter placeholders)
6. Limit results appropriately (use LIMIT if returning many rows)
7. Do NOT use CTEs (WITH clause), subqueries, or window functions
8. Use JOINs ONLY when the question requires data from multiple tables
9. When JOINing tables, use the JOIN hints provided below
10. Always use LEFT JOIN unless data from both tables is strictly required
11. If a time range is provided, use a range filter (BETWEEN or >= / <=) on date/time columns;
    avoid exact timestamp equality unless the user asked for a specific moment.

{schema_context}

USER QUESTION: {question}

CLASSIFICATION:
- Intent: {intent}
- Time Range: {time_range}
- Entities: {entities}
- Filters: {filters}

{permission_filter}

Generate a SQL query that:
1. Answers the user's question accurately
2. Uses only allowed tables
3. Includes appropriate filters based on the classification
4. Uses correct JOIN conditions from the hints above
5. Is safe and efficient"""


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
    ) -> LLMResponse[SQLGeneration]:
        """
        Generate SQL from a classified question.

        Args:
            question: The original natural language question.
            classification: The query classification result.
            allowed_event_ids: Optional list of event IDs the user can access.
                If provided, the generated SQL will be filtered to only
                these events.

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

        # Build the full prompt
        prompt = SQL_GENERATION_PROMPT.format(
            schema_context=schema_prompt,
            question=question,
            intent=classification.intent,
            time_range=time_range_str,
            entities=entities_str,
            filters=filters_str,
            permission_filter=permission_filter,
        )

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
