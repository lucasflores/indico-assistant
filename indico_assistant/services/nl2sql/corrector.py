# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Error corrector component for NL2SQL pipeline.

Attempts to fix failed queries using LLM analysis of the error
message and original query.
"""

from indico_assistant.services.llm import LLMService
from indico_assistant.services.llm.models import (
    LLMResponse,
    QueryClassification,
    SQLCorrection,
)
from indico_assistant.services.nl2sql.schema import SchemaContext


# Error correction prompt template
CORRECTION_PROMPT = """You are a SQL debugging expert. Analyze the failed SQL query and fix it.

ORIGINAL SQL:
{original_sql}

ERROR MESSAGE:
{error_message}

QUERY INTENT: {intent}
ENTITIES: {entities}

{schema_context}

Common issues to check:
1. Column or table name typos
2. Missing quotes around string values
3. Incorrect date/time format
4. Wrong JOIN conditions
5. Missing WHERE clause conditions
6. Syntax errors

Fix the SQL query. Ensure the corrected query:
1. Is a valid PostgreSQL SELECT statement
2. Uses only allowed tables from the schema
3. Addresses the specific error mentioned
4. Maintains the original query intent

Provide the corrected SQL and explain what was wrong."""


class ErrorCorrector:
    """Corrects failed SQL queries using LLM analysis."""

    def __init__(
        self,
        llm_service: LLMService,
        schema_context: SchemaContext,
        max_attempts: int = 3,
    ) -> None:
        """
        Initialize the corrector.

        Args:
            llm_service: The LLM service for error correction.
            schema_context: Schema context for correction context.
            max_attempts: Maximum correction attempts (FR-037).
        """
        self._llm_service = llm_service
        self._schema_context = schema_context
        self._max_attempts = max_attempts

    def correct(
        self,
        original_sql: str,
        error_message: str,
        classification: QueryClassification,
    ) -> LLMResponse[SQLCorrection]:
        """
        Attempt to correct a failed SQL query.

        Args:
            original_sql: The SQL that failed.
            error_message: The error message from execution.
            classification: The original query classification.

        Returns:
            LLMResponse containing SQLCorrection with corrected SQL.
        """
        # Get relevant tables for schema context
        tables = self._schema_context.get_tables_for_intent(classification.intent)
        schema_prompt = self._schema_context.get_schema_prompt(tables)

        # Format entities for prompt
        entities_str = "None"
        if classification.entities:
            entities_str = ", ".join(
                f"{e.type}: {e.value}" for e in classification.entities
            )

        # Build correction prompt
        prompt = CORRECTION_PROMPT.format(
            original_sql=original_sql,
            error_message=error_message,
            intent=classification.intent,
            entities=entities_str,
            schema_context=schema_prompt,
        )

        # Generate correction using LLM
        return self._llm_service.generate(
            prompt=prompt,
            response_model=SQLCorrection,
        )

    @property
    def max_attempts(self) -> int:
        """Get the maximum correction attempts."""
        return self._max_attempts
