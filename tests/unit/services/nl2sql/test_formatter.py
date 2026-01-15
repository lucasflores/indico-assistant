# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Unit tests for ResultFormatter component."""

import json
from unittest.mock import MagicMock

import pytest

from indico_assistant.services.nl2sql.formatter import ResultFormatter


@pytest.fixture
def mock_llm_service() -> MagicMock:
    """Create a mock LLM service."""
    return MagicMock()


@pytest.fixture
def mock_summary_response() -> MagicMock:
    """Create a mock summary response."""
    response = MagicMock()
    response.success = True
    response.data = MagicMock()
    response.data.answer = "There are 5 events in the database."
    response.data.confidence = 0.95
    response.data.sources = []
    return response


@pytest.fixture
def formatter(
    mock_llm_service: MagicMock, mock_summary_response: MagicMock
) -> ResultFormatter:
    """Create a formatter instance."""
    mock_llm_service.generate.return_value = mock_summary_response
    return ResultFormatter(llm_service=mock_llm_service)


@pytest.fixture
def sample_results() -> list[dict]:
    """Create sample query results."""
    return [
        {"id": 1, "title": "Physics Conference", "date": "2024-01-15"},
        {"id": 2, "title": "Math Workshop", "date": "2024-02-20"},
        {"id": 3, "title": "Chemistry Seminar", "date": "2024-03-10"},
    ]


class TestResultFormatterBasicFormatting:
    """Test basic formatting functionality."""

    def test_format_calls_llm(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
        sample_results: list[dict],
    ) -> None:
        """Should call LLM to generate summary."""
        formatter.format(
            question="How many events?",
            results=sample_results,
            tables_used=["events.events"],
        )

        mock_llm_service.generate.assert_called_once()

    def test_format_returns_response(
        self, formatter: ResultFormatter, sample_results: list[dict]
    ) -> None:
        """Should return LLM response."""
        result = formatter.format(
            question="How many events?",
            results=sample_results,
            tables_used=["events.events"],
        )

        assert result.success is True
        assert result.data is not None

    def test_format_includes_question_in_prompt(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
        sample_results: list[dict],
    ) -> None:
        """Question should be included in the prompt."""
        question = "List all physics conferences"
        formatter.format(
            question=question,
            results=sample_results,
            tables_used=["events.events"],
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert question in prompt

    def test_format_includes_tables_in_prompt(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
        sample_results: list[dict],
    ) -> None:
        """Tables used should be in prompt."""
        tables = ["events.events", "events.contributions"]
        formatter.format(
            question="List talks",
            results=sample_results,
            tables_used=tables,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "events.events" in prompt
        assert "events.contributions" in prompt

    def test_format_includes_row_count(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
        sample_results: list[dict],
    ) -> None:
        """Row count should be in prompt."""
        formatter.format(
            question="How many events?",
            results=sample_results,
            tables_used=["events.events"],
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "3 rows" in prompt


class TestResultFormatterSourcesHandling:
    """Test sources field handling."""

    def test_sets_sources_when_empty(
        self,
        mock_llm_service: MagicMock,
        sample_results: list[dict],
    ) -> None:
        """Should set sources from tables_used if response sources empty."""
        response = MagicMock()
        response.success = True
        response.data = MagicMock()
        response.data.sources = []
        mock_llm_service.generate.return_value = response
        formatter = ResultFormatter(llm_service=mock_llm_service)

        result = formatter.format(
            question="List events",
            results=sample_results,
            tables_used=["events.events"],
        )

        assert result.data.sources == ["events.events"]

    def test_preserves_existing_sources(
        self,
        mock_llm_service: MagicMock,
        sample_results: list[dict],
    ) -> None:
        """Should not overwrite non-empty sources."""
        response = MagicMock()
        response.success = True
        response.data = MagicMock()
        response.data.sources = ["existing.source"]
        mock_llm_service.generate.return_value = response
        formatter = ResultFormatter(llm_service=mock_llm_service)

        result = formatter.format(
            question="List events",
            results=sample_results,
            tables_used=["events.events"],
        )

        assert result.data.sources == ["existing.source"]


class TestResultFormatterResultsPreview:
    """Test results preview formatting."""

    def test_empty_results_preview(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
    ) -> None:
        """Empty results should show 'No results found'."""
        formatter.format(
            question="Find events",
            results=[],
            tables_used=["events.events"],
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "No results found" in prompt

    def test_results_formatted_as_json(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
    ) -> None:
        """Results should be formatted as JSON."""
        results = [{"id": 1, "name": "Test"}]
        formatter.format(
            question="Find events",
            results=results,
            tables_used=["events.events"],
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        # JSON formatting includes quotes
        assert '"id"' in prompt
        assert '"name"' in prompt

    def test_limits_preview_rows(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
    ) -> None:
        """Should limit rows in preview to MAX_PREVIEW_ROWS."""
        results = [{"id": i} for i in range(50)]
        formatter.format(
            question="List all",
            results=results,
            tables_used=["events.events"],
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        # Should indicate more rows
        assert "more rows" in prompt

    def test_truncates_long_string_values(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
    ) -> None:
        """Long string values should be truncated."""
        long_value = "A" * 200
        results = [{"description": long_value}]
        formatter.format(
            question="Get description",
            results=results,
            tables_used=["events.events"],
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        # Should not contain full 200 chars
        assert long_value not in prompt
        assert "..." in prompt


class TestResultFormatterEmptyResponse:
    """Test format_empty_response method."""

    def test_returns_response_summary(
        self, formatter: ResultFormatter
    ) -> None:
        """Should return ResponseSummary."""
        result = formatter.format_empty_response("Find events")

        assert hasattr(result, "answer")
        assert hasattr(result, "confidence")
        assert hasattr(result, "sources")

    def test_indicates_no_results(
        self, formatter: ResultFormatter
    ) -> None:
        """Answer should indicate no results found."""
        result = formatter.format_empty_response("Find physics events")

        assert "couldn't find" in result.answer.lower()

    def test_high_confidence_for_empty(
        self, formatter: ResultFormatter
    ) -> None:
        """Should have high confidence (we're sure it's empty)."""
        result = formatter.format_empty_response("Find events")

        assert result.confidence >= 0.9

    def test_empty_sources(
        self, formatter: ResultFormatter
    ) -> None:
        """Sources should be empty for empty response."""
        result = formatter.format_empty_response("Find events")

        assert result.sources == []


class TestResultFormatterErrorResponse:
    """Test format_error_response method."""

    def test_returns_response_summary(
        self, formatter: ResultFormatter
    ) -> None:
        """Should return ResponseSummary."""
        result = formatter.format_error_response(
            "Find events", "Database error"
        )

        assert hasattr(result, "answer")
        assert hasattr(result, "confidence")

    def test_user_friendly_message(
        self, formatter: ResultFormatter
    ) -> None:
        """Answer should be user-friendly, not technical."""
        result = formatter.format_error_response(
            "Find events",
            "SQLSTATE[42P01]: undefined_table: 7 ERROR",
        )

        # Should not expose technical error
        assert "42P01" not in result.answer
        assert "SQLSTATE" not in result.answer
        # Should be apologetic
        assert "sorry" in result.answer.lower()

    def test_zero_confidence_for_error(
        self, formatter: ResultFormatter
    ) -> None:
        """Should have zero confidence on error."""
        result = formatter.format_error_response(
            "Find events", "Error occurred"
        )

        assert result.confidence == 0.0

    def test_empty_sources_on_error(
        self, formatter: ResultFormatter
    ) -> None:
        """Sources should be empty on error."""
        result = formatter.format_error_response(
            "Find events", "Error"
        )

        assert result.sources == []


class TestResultFormatterPromptGuidance:
    """Test that prompt includes proper guidance."""

    def test_prompt_asks_for_conversational_response(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
        sample_results: list[dict],
    ) -> None:
        """Prompt should request conversational response."""
        formatter.format(
            question="How many events?",
            results=sample_results,
            tables_used=["events.events"],
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "natural" in prompt.lower() or "conversational" in prompt.lower()

    def test_prompt_asks_to_hide_technical_details(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
        sample_results: list[dict],
    ) -> None:
        """Prompt should ask to hide SQL/technical details."""
        formatter.format(
            question="List events",
            results=sample_results,
            tables_used=["events.events"],
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "SQL" in prompt or "technical" in prompt.lower()

    def test_prompt_includes_confidence_guidance(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
        sample_results: list[dict],
    ) -> None:
        """Prompt should include confidence scoring guidance."""
        formatter.format(
            question="List events",
            results=sample_results,
            tables_used=["events.events"],
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "confidence" in prompt.lower()


class TestResultFormatterEdgeCases:
    """Test edge cases."""

    def test_empty_tables_list(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
        sample_results: list[dict],
    ) -> None:
        """Should handle empty tables list gracefully."""
        formatter.format(
            question="List events",
            results=sample_results,
            tables_used=[],
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        # Should have some fallback text
        assert "unknown" in prompt.lower()

    def test_results_with_none_values(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
    ) -> None:
        """Should handle None values in results."""
        results = [{"id": 1, "name": None, "value": None}]
        formatter.format(
            question="Find events",
            results=results,
            tables_used=["events.events"],
        )

        # Should not raise
        mock_llm_service.generate.assert_called_once()

    def test_results_with_complex_types(
        self,
        formatter: ResultFormatter,
        mock_llm_service: MagicMock,
    ) -> None:
        """Should handle complex types in results."""
        from datetime import datetime

        results = [{"id": 1, "created": datetime(2024, 1, 1), "data": {"nested": "value"}}]

        # Should not raise
        formatter.format(
            question="Find events",
            results=results,
            tables_used=["events.events"],
        )

        mock_llm_service.generate.assert_called_once()


class TestResultFormatterFailedResponse:
    """Test handling of failed LLM responses."""

    def test_returns_failed_response(
        self, mock_llm_service: MagicMock
    ) -> None:
        """Failed LLM response should be returned."""
        failed_response = MagicMock()
        failed_response.success = False
        failed_response.data = None
        failed_response.error = "LLM error"
        mock_llm_service.generate.return_value = failed_response
        formatter = ResultFormatter(llm_service=mock_llm_service)

        result = formatter.format(
            question="List events",
            results=[{"id": 1}],
            tables_used=["events.events"],
        )

        assert result.success is False


class TestResultFormatterConstants:
    """Test formatter constants."""

    def test_max_preview_rows_is_reasonable(self) -> None:
        """MAX_PREVIEW_ROWS should be a reasonable value."""
        assert ResultFormatter.MAX_PREVIEW_ROWS >= 10
        assert ResultFormatter.MAX_PREVIEW_ROWS <= 100
