# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Unit tests for ErrorCorrector component."""

from unittest.mock import MagicMock

import pytest

from indico_assistant.services.nl2sql.corrector import ErrorCorrector


@pytest.fixture
def mock_llm_service() -> MagicMock:
    """Create a mock LLM service."""
    return MagicMock()


@pytest.fixture
def mock_schema_context() -> MagicMock:
    """Create a mock schema context."""
    context = MagicMock()
    context.get_tables_for_intent.return_value = ["events.events"]
    context.get_schema_prompt.return_value = """
TABLES:
- events.events: id, title, start_dt, end_dt
"""
    return context


@pytest.fixture
def mock_classification() -> MagicMock:
    """Create a mock classification."""
    classification = MagicMock()
    classification.intent = "event_query"
    classification.entities = []
    return classification


@pytest.fixture
def mock_correction_response() -> MagicMock:
    """Create a mock correction response."""
    response = MagicMock()
    response.success = True
    response.data = MagicMock()
    response.data.corrected_query = "SELECT * FROM events.events"
    response.data.explanation = "Fixed column name typo"
    return response


@pytest.fixture
def corrector(
    mock_llm_service: MagicMock,
    mock_schema_context: MagicMock,
    mock_correction_response: MagicMock,
) -> ErrorCorrector:
    """Create a corrector instance."""
    mock_llm_service.generate.return_value = mock_correction_response
    return ErrorCorrector(
        llm_service=mock_llm_service,
        schema_context=mock_schema_context,
        max_attempts=3,
    )


class TestErrorCorrectorBasicCorrection:
    """Test basic error correction functionality."""

    def test_correct_calls_llm(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Should call LLM to generate correction."""
        corrector.correct(
            original_sql="SELECT * FROM events.eventss",  # typo
            error_message="relation 'events.eventss' does not exist",
            classification=mock_classification,
        )

        mock_llm_service.generate.assert_called_once()

    def test_correct_returns_response(
        self,
        corrector: ErrorCorrector,
        mock_classification: MagicMock,
    ) -> None:
        """Should return LLM response."""
        result = corrector.correct(
            original_sql="SELECT * FROM events.events WHERE titl = 'test'",
            error_message="column 'titl' does not exist",
            classification=mock_classification,
        )

        assert result.success is True
        assert result.data is not None

    def test_correct_uses_correct_response_model(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Should use SQLCorrection response model."""
        corrector.correct(
            original_sql="SELECT * FROM events",
            error_message="Error",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        assert "response_model" in call_args[1]


class TestErrorCorrectorPromptConstruction:
    """Test prompt construction for error correction."""

    def test_includes_original_sql(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Original SQL should be in prompt."""
        original_sql = "SELECT * FROM events.eventss WHERE id = 1"
        corrector.correct(
            original_sql=original_sql,
            error_message="relation does not exist",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert original_sql in prompt

    def test_includes_error_message(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Error message should be in prompt."""
        error_msg = "column 'titl' does not exist"
        corrector.correct(
            original_sql="SELECT titl FROM events.events",
            error_message=error_msg,
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert error_msg in prompt

    def test_includes_query_intent(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Query intent should be in prompt."""
        mock_classification.intent = "registration_query"
        corrector.correct(
            original_sql="SELECT * FROM events",
            error_message="Error",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "registration_query" in prompt

    def test_includes_schema_context(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Schema context should be included."""
        corrector.correct(
            original_sql="SELECT * FROM events",
            error_message="Error",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "events.events" in prompt

    def test_gets_tables_for_intent(
        self,
        corrector: ErrorCorrector,
        mock_schema_context: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Should get tables based on classification intent."""
        mock_classification.intent = "contribution_query"
        corrector.correct(
            original_sql="SELECT * FROM contributions",
            error_message="Error",
            classification=mock_classification,
        )

        mock_schema_context.get_tables_for_intent.assert_called_with(
            "contribution_query"
        )

    def test_includes_entities_in_prompt(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Classification entities should be in prompt."""
        entity = MagicMock()
        entity.type = "event_name"
        entity.value = "Physics Conference"
        mock_classification.entities = [entity]

        corrector.correct(
            original_sql="SELECT * FROM events",
            error_message="Error",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "event_name" in prompt
        assert "Physics Conference" in prompt

    def test_handles_no_entities(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Should handle classification with no entities."""
        mock_classification.entities = []

        # Should not raise
        corrector.correct(
            original_sql="SELECT * FROM events",
            error_message="Error",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "None" in prompt


class TestErrorCorrectorMaxAttempts:
    """Test max_attempts configuration."""

    def test_max_attempts_property(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
    ) -> None:
        """max_attempts property should return configured value."""
        corrector = ErrorCorrector(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
            max_attempts=5,
        )

        assert corrector.max_attempts == 5

    def test_default_max_attempts(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
    ) -> None:
        """Default max_attempts should be 3."""
        corrector = ErrorCorrector(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
        )

        assert corrector.max_attempts == 3


class TestErrorCorrectorPromptGuidance:
    """Test that prompt includes proper guidance."""

    def test_prompt_includes_common_issues(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Prompt should list common SQL issues."""
        corrector.correct(
            original_sql="SELECT * FROM events",
            error_message="Error",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "typo" in prompt.lower()
        assert "syntax" in prompt.lower()

    def test_prompt_requires_valid_postgresql(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Prompt should require PostgreSQL compatibility."""
        corrector.correct(
            original_sql="SELECT * FROM events",
            error_message="Error",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "PostgreSQL" in prompt

    def test_prompt_requires_select_only(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Prompt should require SELECT statements only."""
        corrector.correct(
            original_sql="SELECT * FROM events",
            error_message="Error",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "SELECT" in prompt


class TestErrorCorrectorFailedResponse:
    """Test handling of failed LLM responses."""

    def test_returns_failed_response(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Failed LLM response should be returned."""
        failed_response = MagicMock()
        failed_response.success = False
        failed_response.data = None
        failed_response.error = "LLM error"
        mock_llm_service.generate.return_value = failed_response

        corrector = ErrorCorrector(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
        )

        result = corrector.correct(
            original_sql="SELECT * FROM events",
            error_message="Error",
            classification=mock_classification,
        )

        assert result.success is False


class TestErrorCorrectorRealErrorScenarios:
    """Test correction with realistic error scenarios."""

    def test_column_not_found_error(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Should handle column not found errors."""
        corrector.correct(
            original_sql="SELECT titl FROM events.events",
            error_message="column 'titl' does not exist, did you mean 'title'?",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "titl" in prompt
        assert "title" in prompt

    def test_table_not_found_error(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Should handle table not found errors."""
        corrector.correct(
            original_sql="SELECT * FROM event.events",
            error_message="relation 'event.events' does not exist",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "event.events" in prompt

    def test_syntax_error(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Should handle syntax errors."""
        corrector.correct(
            original_sql="SELECT * FORM events.events",
            error_message="syntax error at or near 'FORM'",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "syntax error" in prompt
        assert "FORM" in prompt

    def test_date_format_error(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Should handle date format errors."""
        corrector.correct(
            original_sql="SELECT * FROM events.events WHERE start_dt > '2024/01/01'",
            error_message="invalid input syntax for type date",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "date" in prompt.lower()


class TestErrorCorrectorMultipleEntities:
    """Test handling of multiple entities."""

    def test_multiple_entities_in_prompt(
        self,
        corrector: ErrorCorrector,
        mock_llm_service: MagicMock,
        mock_classification: MagicMock,
    ) -> None:
        """Multiple entities should be comma-separated."""
        entity1 = MagicMock()
        entity1.type = "event_name"
        entity1.value = "CHEP"
        entity2 = MagicMock()
        entity2.type = "date"
        entity2.value = "2024-06-01"
        mock_classification.entities = [entity1, entity2]

        corrector.correct(
            original_sql="SELECT * FROM events",
            error_message="Error",
            classification=mock_classification,
        )

        call_args = mock_llm_service.generate.call_args
        prompt = call_args[1]["prompt"]
        assert "CHEP" in prompt
        assert "2024-06-01" in prompt
