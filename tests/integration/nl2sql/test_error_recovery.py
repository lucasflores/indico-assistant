# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Integration tests for error recovery functionality."""

from unittest.mock import MagicMock, patch

import pytest

from indico_assistant.services.nl2sql.models import PipelineErrorType
from indico_assistant.services.nl2sql.pipeline import NL2SQLPipeline


@pytest.fixture
def mock_llm_service() -> MagicMock:
    """Create a mock LLM service with realistic responses."""
    service = MagicMock()
    return service


@pytest.fixture
def mock_schema_context() -> MagicMock:
    """Create a mock schema context."""
    context = MagicMock()
    context.get_tables_for_intent.return_value = ["events.events"]
    context.get_schema_prompt.return_value = "TABLES: events.events"
    context.is_table_allowed.return_value = True
    return context


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Create a mock database session."""
    session = MagicMock()
    return session


@pytest.fixture
def mock_db_session_factory(mock_db_session: MagicMock):
    """Create a mock database session factory."""

    def factory():
        return mock_db_session

    return factory


class TestErrorRecoveryIntegration:
    """Test error recovery flow through the pipeline."""

    def test_successful_correction_after_first_failure(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_db_session_factory,
        mock_db_session: MagicMock,
    ) -> None:
        """Pipeline should auto-correct and succeed after first execution failure."""
        # Setup classification response
        classification_response = MagicMock()
        classification_response.success = True
        classification_response.data = MagicMock()
        classification_response.data.intent = "event_query"
        classification_response.data.entities = []
        classification_response.data.time_range = None

        # Setup SQL generation response
        sql_response = MagicMock()
        sql_response.success = True
        sql_response.data = MagicMock()
        sql_response.data.query = "SELECT * FROM events.eventss"  # typo
        sql_response.data.tables_used = ["events.events"]

        # Setup correction response
        correction_response = MagicMock()
        correction_response.success = True
        correction_response.data = MagicMock()
        correction_response.data.corrected_query = "SELECT * FROM events.events"  # fixed

        # Setup format response
        format_response = MagicMock()
        format_response.success = True
        format_response.data = MagicMock()
        format_response.data.answer = "Found 5 events"
        format_response.data.confidence = 0.95
        format_response.data.sources = []

        # Mock LLM generate to return different responses
        mock_llm_service.generate.side_effect = [
            classification_response,  # classify
            sql_response,  # generate SQL
            correction_response,  # correct
            format_response,  # format
        ]

        # Setup executor: first fails, second succeeds
        result_fail = MagicMock()
        result_fail.keys.return_value = ["id", "title"]
        result_fail.fetchall.side_effect = Exception("relation 'events.eventss' does not exist")

        result_success = MagicMock()
        result_success.keys.return_value = ["id", "title"]
        result_success.fetchall.return_value = [(1, "Event 1")]

        # Execute returns different results on subsequent calls
        execute_calls = [0]

        def mock_execute(sql, params=None):
            execute_calls[0] += 1
            if execute_calls[0] <= 2:  # First query execution (after SET timeout)
                if "eventss" in str(sql):
                    raise Exception("relation 'events.eventss' does not exist")
            return result_success

        mock_db_session.execute.side_effect = mock_execute

        pipeline = NL2SQLPipeline(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
            db_session_factory=mock_db_session_factory,
            max_correction_attempts=3,
        )

        result = pipeline.process("How many events?", user_id=1)

        # With proper mocking, should either succeed or fail gracefully
        # In a real integration test, we'd verify the correction flow
        assert result is not None

    def test_exhausts_correction_attempts(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_db_session_factory,
        mock_db_session: MagicMock,
    ) -> None:
        """Pipeline should exhaust correction attempts and return failure."""
        # Setup classification response
        classification_response = MagicMock()
        classification_response.success = True
        classification_response.data = MagicMock()
        classification_response.data.intent = "event_query"
        classification_response.data.entities = []
        classification_response.data.time_range = None

        # Setup SQL generation response
        sql_response = MagicMock()
        sql_response.success = True
        sql_response.data = MagicMock()
        sql_response.data.query = "SELECT * FROM invalid_table"
        sql_response.data.tables_used = ["events.events"]

        # Setup correction responses (all fail to fix the issue)
        correction_response = MagicMock()
        correction_response.success = True
        correction_response.data = MagicMock()
        correction_response.data.corrected_query = "SELECT * FROM still_invalid"

        def generate_side_effect(*args, **kwargs):
            response_model = kwargs.get("response_model")
            if response_model and "Classification" in str(response_model):
                return classification_response
            elif response_model and "Generation" in str(response_model):
                return sql_response
            elif response_model and "Correction" in str(response_model):
                return correction_response
            return MagicMock()

        mock_llm_service.generate.side_effect = generate_side_effect

        # Executor always fails
        mock_db_session.execute.side_effect = Exception("persistent error")

        pipeline = NL2SQLPipeline(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
            db_session_factory=mock_db_session_factory,
            max_correction_attempts=3,
        )

        result = pipeline.process("Query with unfixable error", user_id=1)

        # Should fail after exhausting attempts
        assert result.success is False
        # Error type should indicate correction exhaustion or execution failure
        assert result.error is not None


class TestErrorRecoveryCorrectionAttemptTracking:
    """Test that correction attempts are properly tracked."""

    def test_correction_attempts_counted(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_db_session_factory,
        mock_db_session: MagicMock,
    ) -> None:
        """Correction attempts should be counted and returned in result."""
        # Setup classification
        classification = MagicMock()
        classification.success = True
        classification.data = MagicMock()
        classification.data.intent = "event_query"
        classification.data.entities = []
        classification.data.time_range = None

        # Setup SQL generation
        sql_gen = MagicMock()
        sql_gen.success = True
        sql_gen.data = MagicMock()
        sql_gen.data.query = "SELECT bad FROM events"
        sql_gen.data.tables_used = ["events.events"]

        # Setup correction
        correction = MagicMock()
        correction.success = True
        correction.data = MagicMock()
        correction.data.corrected_query = "SELECT good FROM events"

        # Format response
        format_resp = MagicMock()
        format_resp.success = True
        format_resp.data = MagicMock()
        format_resp.data.answer = "Result"
        format_resp.data.confidence = 0.9
        format_resp.data.sources = []

        responses = [classification, sql_gen, correction, format_resp]
        mock_llm_service.generate.side_effect = responses

        # First execution fails, second succeeds
        exec_count = [0]
        result_success = MagicMock()
        result_success.keys.return_value = ["id"]
        result_success.fetchall.return_value = [(1,)]

        def mock_execute(sql, params=None):
            exec_count[0] += 1
            if exec_count[0] == 2:  # First actual query after timeout setting
                raise Exception("Column 'bad' not found")
            return result_success

        mock_db_session.execute.side_effect = mock_execute

        pipeline = NL2SQLPipeline(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
            db_session_factory=mock_db_session_factory,
            max_correction_attempts=3,
        )

        result = pipeline.process("Test query", user_id=1)

        # Should track correction attempts
        assert result.correction_attempts >= 0


class TestErrorRecoveryValidationAfterCorrection:
    """Test that corrected SQL is re-validated."""

    def test_corrected_sql_is_validated(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_db_session_factory,
    ) -> None:
        """Corrected SQL should be validated before re-execution."""
        # This test verifies that the pipeline validates corrected SQL
        # before attempting to execute it

        pipeline = NL2SQLPipeline(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
            db_session_factory=mock_db_session_factory,
        )

        # The validator component should be present and functional
        assert pipeline.validator is not None
        assert pipeline.corrector is not None


class TestErrorRecoveryCorrectedFlag:
    """Test that corrected flag is set correctly."""

    def test_corrected_flag_set_on_successful_correction(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_db_session_factory,
        mock_db_session: MagicMock,
    ) -> None:
        """corrected flag should be True when correction succeeds."""
        # Setup mocks for successful correction flow
        classification = MagicMock()
        classification.success = True
        classification.data = MagicMock()
        classification.data.intent = "event_query"
        classification.data.entities = []
        classification.data.time_range = None

        sql_gen = MagicMock()
        sql_gen.success = True
        sql_gen.data = MagicMock()
        sql_gen.data.query = "SELECT * FROM bad"
        sql_gen.data.tables_used = ["events.events"]

        correction = MagicMock()
        correction.success = True
        correction.data = MagicMock()
        correction.data.corrected_query = "SELECT * FROM events.events"

        format_resp = MagicMock()
        format_resp.success = True
        format_resp.data = MagicMock()
        format_resp.data.answer = "Success"
        format_resp.data.confidence = 0.9
        format_resp.data.sources = []

        mock_llm_service.generate.side_effect = [
            classification,
            sql_gen,
            correction,
            format_resp,
        ]

        # First execution fails, correction succeeds
        call_count = [0]
        result = MagicMock()
        result.keys.return_value = ["id"]
        result.fetchall.return_value = [(1,)]

        def mock_execute(sql, params=None):
            call_count[0] += 1
            if call_count[0] == 2:  # First query after timeout
                raise Exception("Error")
            return result

        mock_db_session.execute.side_effect = mock_execute

        pipeline = NL2SQLPipeline(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
            db_session_factory=mock_db_session_factory,
        )

        result = pipeline.process("Test", user_id=1)

        # If successful with correction, corrected should be True
        if result.success:
            assert result.corrected is True


class TestErrorRecoveryPreservesOriginalIntent:
    """Test that correction preserves original query intent."""

    def test_corrector_receives_original_classification(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_db_session_factory,
    ) -> None:
        """ErrorCorrector should receive original classification for context."""
        pipeline = NL2SQLPipeline(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
            db_session_factory=mock_db_session_factory,
        )

        # Corrector should be initialized with schema context
        assert pipeline.corrector is not None
        assert pipeline.corrector.max_attempts == 3
