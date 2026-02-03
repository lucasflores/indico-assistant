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

from datetime import datetime
import json
from typing import Any

from indico_assistant.services.llm import LLMService
from indico_assistant.services.llm.models import LLMResponse, ResponseSummary


# Result formatting prompt template
# Feature 015: T015 - Updated to include citation instructions
FORMAT_PROMPT = """You are a helpful assistant that summarizes database query results in natural language.

{context_section}

USER'S ORIGINAL QUESTION: {question}

TABLES USED: {tables}

QUERY RESULTS ({row_count} rows):
{results_preview}

{citation_instructions}

Generate a natural, conversational response that:
1. Directly answers the user's question with COMPREHENSIVE detail
2. Includes specific numbers, names, dates, and ALL relevant information from the results
3. Is THOROUGH and COMPLETE - provide rich detail rather than brief summaries
4. Presents information in an engaging, narrative style when appropriate
5. If multiple items exist, describe each one with sufficient detail
6. If no results were found, explains that politely
7. Does NOT mention SQL, databases, or technical details
8. If a contributors field is present and already aggregated, present it clearly without duplicating entries

**IMPORTANT**: Provide detailed, informative responses. Users prefer comprehensive answers over brief summaries.

Respond with a confidence score based on:
- 0.9-1.0: Results directly answer the question
- 0.7-0.9: Results partially answer the question
- 0.5-0.7: Results may be relevant but don't fully answer
- Below 0.5: Results don't seem to answer the question

{conversation_history_section}

**REQUIRED**: You MUST suggest exactly 2-3 relevant follow-up actions that:
- Are UNIQUE and SPECIFIC to the actual data in THIS response - DO NOT use generic suggestions
- Build DIRECTLY on specific details mentioned in your answer (names, dates, topics, etc.)
- Offer logical next steps the user might want based on what you just told them
- Are phrased as helpful actions YOU can perform (active voice, first person)
- Use natural, conversational language (e.g., "getting you...", "showing you...", "listing...")
- NEVER repeat suggestions from previous responses in the conversation
- Consider what information is MISSING from the current answer that the user might want

**CRITICAL**: Generate follow-ups based on the ACTUAL CONTENT of your answer. For example:
- If you mentioned a person → offer to show their other contributions or contact info
- If you mentioned a date → offer to show what else is happening that day
- If you mentioned a topic → offer to find related events or documents
- If you mentioned participants → offer to list their roles or affiliations
- If you answered about one event → offer details about its sessions, materials, or organizers

DO NOT use these generic examples verbatim:
- "showing you who's presenting" (too generic)
- "summarizing the documents" (too generic)
- "getting you the full agenda" (too generic)

Instead, be SPECIFIC like:
- "listing the 3 speakers you'll hear from on April 18th"
- "showing you Dr. Smith's other presentations this month"
- "finding the materials uploaded for the Physics Workshop"

This is a REQUIRED field - you must always provide 2-3 UNIQUE, CONTEXTUAL follow-up action offers."""


class ResultFormatter:
    """Formats query results with natural language summaries."""

    # Maximum number of result rows to include in the prompt
    MAX_PREVIEW_ROWS = 50
    
    # Maximum length for string values (increased to show full descriptions)
    MAX_STRING_LENGTH = 10000

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
        citations: list[str] | None = None,  # Feature 015: T015
        user_id: int | None = None,
        event_id: int | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> LLMResponse[ResponseSummary]:
        """
        Format query results into a natural language summary.

        Args:
            question: The original user question.
            results: The query result rows.
            tables_used: Tables accessed by the query.
            citations: Optional list of markdown citation links (Feature 015).
            user_id: Optional user ID for context.
            event_id: Optional event ID for context.
            conversation_history: Previous messages for context-aware follow-ups.

        Returns:
            LLMResponse containing ResponseSummary with formatted answer.
        """
        # Format results preview for the prompt
        results_preview = self._format_results_preview(results)
        
        # Build context section with available metadata
        context_lines = [f"TODAY'S DATE: {datetime.now().strftime('%Y-%m-%d')}"]
        if user_id is not None:
            context_lines.append(f"CURRENT USER ID: {user_id}")
        if event_id is not None:
            context_lines.append(f"CURRENT EVENT ID: {event_id}")
        context_section = "\n".join(context_lines)
        
        # Feature 015: T015 - Include citation instructions if available
        citation_instructions = ""
        if citations:
            citation_list = "\n".join(f"- {citation}" for citation in citations)
            citation_instructions = f"""
            AVAILABLE EVENT CITATIONS:
            {citation_list}
            
            When referencing data from these events in your response, include the appropriate citation link inline.
            For example: "The event on [topic] had 42 participants [Event: 123](/event/123)."
            """
        
        # Build conversation history section for contextual follow-ups
        conversation_history_section = ""
        if conversation_history:
            # Include recent history to avoid repetitive suggestions
            recent_history = conversation_history[-6:]  # Last 3 exchanges
            history_lines = []
            for msg in recent_history:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")[:500]  # Truncate for prompt efficiency
                history_lines.append(f"{role}: {content}")
            
            if history_lines:
                conversation_history_section = f"""CONVERSATION HISTORY (for context - DO NOT repeat previous follow-up suggestions):
{chr(10).join(history_lines)}

Based on this history, generate NEW follow-up suggestions that haven't been offered before."""
        
        # Build the prompt
        prompt = FORMAT_PROMPT.format(
            question=question,
            context_section=context_section,
            tables=", ".join(tables_used) if tables_used else "unknown",
            row_count=len(results),
            results_preview=results_preview,
            citation_instructions=citation_instructions,
            conversation_history_section=conversation_history_section,
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
            # Truncate excessively long string values (but allow full descriptions)
            truncated_rows = []
            for row in preview_rows:
                truncated_row = {}
                for key, value in row.items():
                    if isinstance(value, str) and len(value) > self.MAX_STRING_LENGTH:
                        truncated_row[key] = value[:self.MAX_STRING_LENGTH] + "..."
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
