# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Result formatter component for NL2SQL pipeline.

Formats query results into natural language summaries using LLM.
"""

import json
from typing import Any

from indico_assistant.services.llm import LLMService
from indico_assistant.services.llm.models import LLMResponse, ResponseSummary


# Result formatting prompt template
FORMAT_PROMPT = """You are a helpful assistant that summarizes database query results in natural language.

USER'S ORIGINAL QUESTION: {question}

TABLES USED: {tables}

QUERY RESULTS ({row_count} rows):
{results_preview}

Generate a natural, conversational response that:
1. Directly answers the user's question
2. Includes specific numbers, names, or dates from the results
3. Is concise but complete
4. If no results were found, explains that politely
5. Does NOT mention SQL, databases, or technical details

Respond with a confidence score based on:
- 0.9-1.0: Results directly answer the question
- 0.7-0.9: Results partially answer the question
- 0.5-0.7: Results may be relevant but don't fully answer
- Below 0.5: Results don't seem to answer the question"""


class ResultFormatter:
    """Formats query results with natural language summaries."""

    # Maximum number of result rows to include in the prompt
    MAX_PREVIEW_ROWS = 20

    def __init__(self, llm_service: LLMService) -> None:
        """
        Initialize the formatter.

        Args:
            llm_service: The LLM service for result summarization.
        """
        self._llm_service = llm_service

    def format(
        self,
        question: str,
        results: list[dict[str, Any]],
        tables_used: list[str],
    ) -> LLMResponse[ResponseSummary]:
        """
        Format query results into a natural language summary.

        Args:
            question: The original user question.
            results: The query result rows.
            tables_used: Tables accessed by the query.

        Returns:
            LLMResponse containing ResponseSummary with formatted answer.
        """
        # Format results preview for the prompt
        results_preview = self._format_results_preview(results)

        # Build the prompt
        prompt = FORMAT_PROMPT.format(
            question=question,
            tables=", ".join(tables_used) if tables_used else "unknown",
            row_count=len(results),
            results_preview=results_preview,
        )

        # Generate summary using LLM
        response = self._llm_service.generate(
            prompt=prompt,
            response_model=ResponseSummary,
        )

        # Ensure sources are set
        if response.success and response.data and not response.data.sources:
            response.data.sources = tables_used

        return response

    def _format_results_preview(
        self, results: list[dict[str, Any]]
    ) -> str:
        """
        Format results as a preview string for the prompt.

        Limits the number of rows and truncates long values for
        efficient prompt usage.

        Args:
            results: The query result rows.

        Returns:
            Formatted string preview of results.
        """
        if not results:
            return "No results found."

        # Limit rows
        preview_rows = results[: self.MAX_PREVIEW_ROWS]

        # Format as JSON for clarity
        try:
            # Truncate long string values
            truncated_rows = []
            for row in preview_rows:
                truncated_row = {}
                for key, value in row.items():
                    if isinstance(value, str) and len(value) > 100:
                        truncated_row[key] = value[:100] + "..."
                    else:
                        truncated_row[key] = value
                truncated_rows.append(truncated_row)

            formatted = json.dumps(truncated_rows, indent=2, default=str)

            if len(results) > self.MAX_PREVIEW_ROWS:
                formatted += f"\n... and {len(results) - self.MAX_PREVIEW_ROWS} more rows"

            return formatted

        except Exception:
            # Fallback to simple string representation
            return str(preview_rows)

    def format_empty_response(self, question: str) -> ResponseSummary:
        """
        Create a response for empty query results.

        Args:
            question: The original user question.

        Returns:
            ResponseSummary indicating no results found.
        """
        return ResponseSummary(
            answer=(
                "I couldn't find any results matching your question. "
                "This might mean there's no data available for what you're "
                "looking for, or the query criteria were too specific."
            ),
            confidence=0.95,  # High confidence it's empty
            sources=[],
        )

    def format_error_response(
        self, question: str, error_message: str
    ) -> ResponseSummary:
        """
        Create a response for query errors.

        Args:
            question: The original user question.
            error_message: The error that occurred (for logging, not shown).

        Returns:
            ResponseSummary with a user-friendly error message.
        """
        return ResponseSummary(
            answer=(
                "I'm sorry, I wasn't able to retrieve that information. "
                "Please try rephrasing your question or asking about "
                "something more specific."
            ),
            confidence=0.0,
            sources=[],
        )
