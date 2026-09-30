# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Unit tests for NL2SQLPipeline orchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from indico_assistant.services.nl2sql.models import ExecutionResult, PipelineErrorType
from indico_assistant.services.nl2sql.pipeline import NL2SQLPipeline


@pytest.fixture
def mock_llm_service() -> MagicMock:
    """Create a mock LLM service."""
    return MagicMock()


@pytest.fixture
def mock_schema_context() -> MagicMock:
    """Create a mock schema context."""
    context = MagicMock()
    context.get_tables_for_intent.return_value = ["events.events"]
    context.is_table_allowed.return_value = True
    return context


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Create a mock database session."""
    session = MagicMock()
    result = MagicMock()
    result.keys.return_value = ["id", "title"]
    result.fetchall.return_value = [(1, "Event 1"), (2, "Event 2")]
    session.execute.return_value = result
    return session


@pytest.fixture
def mock_db_session_factory(mock_db_session: MagicMock):
    """Create a mock database session factory."""

    def factory():
        return mock_db_session

    return factory


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create a mock query cache."""
    cache = MagicMock()
    cache.get.return_value = None  # No cached results by default
    return cache


@pytest.fixture
def mock_classification() -> MagicMock:
    """Create a mock classification."""
    classification = MagicMock()
    classification.intent = "event_query"
    classification.entities = []
    classification.time_range = None
    return classification


@pytest.fixture
def mock_classification_response(mock_classification: MagicMock) -> MagicMock:
    """Create a mock classification response."""
    response = MagicMock()
    response.success = True
    response.data = mock_classification
    response.error = None
    return response


@pytest.fixture
def mock_sql_generation() -> MagicMock:
    """Create a mock SQL generation."""
    generation = MagicMock()
    generation.query = "SELECT * FROM events.events"
    generation.tables_used = ["events.events"]
    return generation


@pytest.fixture
def mock_sql_response(mock_sql_generation: MagicMock) -> MagicMock:
    """Create a mock SQL generation response."""
    response = MagicMock()
    response.success = True
    response.data = mock_sql_generation
    response.error = None
    return response


@pytest.fixture
def mock_summary() -> MagicMock:
    """Create a mock response summary."""
    summary = MagicMock()
    summary.answer = "There are 2 events."
    summary.confidence = 0.95
    summary.sources = ["events.events"]
    return summary


@pytest.fixture
def mock_format_response(mock_summary: MagicMock) -> MagicMock:
    """Create a mock format response."""
    response = MagicMock()
    response.success = True
    response.data = mock_summary
    return response


@pytest.fixture
def pipeline(
    mock_llm_service: MagicMock,
    mock_schema_context: MagicMock,
    mock_db_session_factory,
    mock_cache: MagicMock,
) -> NL2SQLPipeline:
    """Create a pipeline instance whose executor returns one row (no database needed)."""
    pipeline = NL2SQLPipeline(
        llm_service=mock_llm_service,
        schema_context=mock_schema_context,
        db_session_factory=mock_db_session_factory,
        cache=mock_cache,
    )
    pipeline._executor.execute = MagicMock(return_value=ExecutionResult(
        success=True, rows=[{"event_id": 1, "title": "Event 1"}], row_count=1,
        columns=["event_id", "title"], execution_time_ms=1))
    return pipeline


class TestNL2SQLPipelineInitialization:
    """Test pipeline initialization."""

    def test_creates_all_components(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_db_session_factory,
    ) -> None:
        """Should create all component instances."""
        pipeline = NL2SQLPipeline(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
            db_session_factory=mock_db_session_factory,
        )

        assert pipeline.classifier is not None
        assert pipeline.generator is not None
        assert pipeline.validator is not None
        assert pipeline.executor is not None
        assert pipeline.corrector is not None
        assert pipeline.formatter is not None

    def test_cache_can_be_disabled(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_db_session_factory,
    ) -> None:
        """Cache should be optional."""
        pipeline = NL2SQLPipeline(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
            db_session_factory=mock_db_session_factory,
            cache=None,
        )

        assert pipeline.cache is None

    def test_custom_parameters_applied(
        self,
        mock_llm_service: MagicMock,
        mock_schema_context: MagicMock,
        mock_db_session_factory,
    ) -> None:
        """Custom parameters should be passed to components."""
        pipeline = NL2SQLPipeline(
            llm_service=mock_llm_service,
            schema_context=mock_schema_context,
            db_session_factory=mock_db_session_factory,
            max_rows=500,
            timeout_seconds=60,
            max_correction_attempts=5,
        )

        assert pipeline.executor.max_rows == 500
        assert pipeline.executor.timeout_seconds == 60


class TestNL2SQLPipelineSuccessfulFlow:
    """Test successful pipeline execution flow."""

    def test_returns_successful_result(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_format_response: MagicMock,
    ) -> None:
        """Successful flow should return success=True."""
        # Setup mocks
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        pipeline._formatter.format = MagicMock(return_value=mock_format_response)

        result = pipeline.process("How many events?", user_id=1)

        assert result.success is True

    def test_returns_answer(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_format_response: MagicMock,
    ) -> None:
        """Result should include formatted answer."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        pipeline._formatter.format = MagicMock(return_value=mock_format_response)

        result = pipeline.process("How many events?", user_id=1)

        assert result.answer == "There are 2 events."

    def test_returns_confidence(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_format_response: MagicMock,
    ) -> None:
        """Result should include confidence score."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        pipeline._formatter.format = MagicMock(return_value=mock_format_response)

        result = pipeline.process("How many events?", user_id=1)

        assert result.confidence == 0.95

    def test_records_timing_info(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_format_response: MagicMock,
    ) -> None:
        """Result should include timing information."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        pipeline._formatter.format = MagicMock(return_value=mock_format_response)

        result = pipeline.process("How many events?", user_id=1)

        assert result.total_time_ms >= 0
        assert result.classification_time_ms >= 0
        assert result.generation_time_ms >= 0

    def test_records_generated_sql(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_format_response: MagicMock,
    ) -> None:
        """Result should include generated SQL."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        pipeline._formatter.format = MagicMock(return_value=mock_format_response)

        result = pipeline.process("How many events?", user_id=1)

        assert result.generated_sql == "SELECT * FROM events.events"


class TestNL2SQLPipelineClassificationFailure:
    """Test handling of classification failures."""

    def test_classification_error_returns_failure(
        self, pipeline: NL2SQLPipeline
    ) -> None:
        """Classification error should return failure result."""
        failed_response = MagicMock()
        failed_response.success = False
        failed_response.data = None
        failed_response.error = "Classification error"
        pipeline._classifier.classify = MagicMock(return_value=failed_response)

        result = pipeline.process("What is the weather?", user_id=1)

        assert result.success is False
        assert result.error.error_type == PipelineErrorType.CLASSIFICATION_FAILED

    def test_classification_error_user_message(
        self, pipeline: NL2SQLPipeline
    ) -> None:
        """User message should be friendly on classification error."""
        failed_response = MagicMock()
        failed_response.success = False
        failed_response.data = None
        failed_response.error = "Internal error"
        pipeline._classifier.classify = MagicMock(return_value=failed_response)

        result = pipeline.process("What is 2+2?", user_id=1)

        assert "couldn't understand" in result.error.user_message.lower()


class TestNL2SQLPipelineWriteRequest:
    """Feature 019: a change request is handed to the chat-action planner, with no SQL at all."""

    def test_write_request_stops_after_classification(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification: MagicMock,
        mock_classification_response: MagicMock,
    ) -> None:
        mock_classification.intent = "write_request"
        mock_classification_response.data = mock_classification
        pipeline._classifier.classify = MagicMock(return_value=mock_classification_response)
        pipeline._generator.generate = MagicMock()

        result = pipeline.process("Create a meeting tomorrow at 2pm", user_id=1)

        assert result.success is True and result.write_request is True and result.generated_sql is None
        pipeline._generator.generate.assert_not_called()


class TestNL2SQLPipelineKnowledge:
    """Spec 022: a knowledge question gets the knowledge answer, with no SQL at all."""

    def test_knowledge_stops_after_classification(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification: MagicMock,
        mock_classification_response: MagicMock,
    ) -> None:
        mock_classification.intent = "knowledge"
        mock_classification_response.data = mock_classification
        pipeline._classifier.classify = MagicMock(return_value=mock_classification_response)
        pipeline._generator.generate = MagicMock()

        result = pipeline.process("How do I lock my event?", user_id=1)

        assert result.success is True and result.knowledge_request is True and result.generated_sql is None
        assert result.write_request is False
        pipeline._generator.generate.assert_not_called()


class TestNL2SQLPipelineRoutedByJev:
    """Spec 022: Jev decided the route and the kind of question; the classifier is not called."""

    def test_a_given_intent_skips_the_classifier(self, pipeline: NL2SQLPipeline) -> None:
        pipeline._classifier.classify = MagicMock()
        pipeline._generator.generate = MagicMock(return_value=MagicMock(success=False, data=None, error="stop here"))

        pipeline.process("Who speaks at Q3 planning?", user_id=1, intent="speaker_query", intent_confidence=0.97)

        pipeline._classifier.classify.assert_not_called()
        classification = pipeline._generator.generate.call_args.args[1]
        assert classification.intent == "speaker_query" and classification.confidence == 0.97
        assert classification.entities == [] and classification.time_range is None  # the generator reads them

    def test_a_given_intent_still_gets_its_dates(self, pipeline: NL2SQLPipeline) -> None:
        """(review, PR #15) "last week" -> dates is plain code, not the classifier's model call: it still runs"""
        pipeline._classifier.classify = MagicMock()
        pipeline._generator.generate = MagicMock(return_value=MagicMock(success=False, data=None, error="stop here"))

        pipeline.process("Which meetings did I have last week?", user_id=1, intent="event_query")

        pipeline._classifier.classify.assert_not_called()
        assert pipeline._generator.generate.call_args.args[1].time_range is not None

    def test_the_chat_intent_stops_after_classification(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification: MagicMock,
        mock_classification_response: MagicMock,
    ) -> None:
        mock_classification.intent = "chat"
        mock_classification_response.data = mock_classification
        pipeline._classifier.classify = MagicMock(return_value=mock_classification_response)
        pipeline._generator.generate = MagicMock()

        result = pipeline.process("thanks!", user_id=1)

        assert result.success is True and result.chat_request is True and result.generated_sql is None
        pipeline._generator.generate.assert_not_called()


class TestNL2SQLPipelineOutOfScope:
    """Test handling of out-of-scope queries."""

    def test_out_of_scope_returns_failure(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification: MagicMock,
        mock_classification_response: MagicMock,
    ) -> None:
        """Out-of-scope query should return failure."""
        mock_classification.intent = "out_of_scope"
        mock_classification_response.data = mock_classification
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._classifier.is_out_of_scope = MagicMock(return_value=True)

        result = pipeline.process("What is the meaning of life?", user_id=1)

        assert result.success is False
        assert result.error.error_type == PipelineErrorType.OUT_OF_SCOPE

    def test_out_of_scope_user_message(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification: MagicMock,
        mock_classification_response: MagicMock,
    ) -> None:
        """User message should explain scope limitations."""
        mock_classification.intent = "out_of_scope"
        mock_classification_response.data = mock_classification
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._classifier.is_out_of_scope = MagicMock(return_value=True)

        result = pipeline.process("Make me coffee", user_id=1)

        assert "events" in result.error.user_message.lower()


class TestNL2SQLPipelineGenerationFailure:
    """Test handling of SQL generation failures."""

    def test_generation_error_returns_failure(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
    ) -> None:
        """SQL generation error should return failure."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )

        failed_response = MagicMock()
        failed_response.success = False
        failed_response.data = None
        failed_response.error = "Generation failed"
        pipeline._generator.generate = MagicMock(return_value=failed_response)

        result = pipeline.process("Complex query", user_id=1)

        assert result.success is False
        assert result.error.error_type == PipelineErrorType.GENERATION_FAILED


class TestNL2SQLPipelineValidationFailure:
    """Test handling of validation failures."""

    def test_validation_failure_returns_failure(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
    ) -> None:
        """Validation failure should return failure result."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)

        # Make validator fail
        failed_validation = MagicMock()
        failed_validation.valid = False
        failed_validation.violations = ["SQL contains forbidden keyword"]
        pipeline._validator.validate = MagicMock(return_value=failed_validation)

        result = pipeline.process("DROP TABLE events", user_id=1)

        assert result.success is False
        assert result.error.error_type == PipelineErrorType.VALIDATION_FAILED


class TestNL2SQLPipelineCaching:
    """Test query caching behavior."""

    def test_cache_hit_returns_cached_result(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        """Cache hit should return cached result."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)

        # Make validator succeed
        valid_result = MagicMock()
        valid_result.valid = True
        pipeline._validator.validate = MagicMock(return_value=valid_result)

        # Setup cache hit
        cached_result = MagicMock()
        cached_result.result = MagicMock()
        cached_result.result.model_copy.return_value = MagicMock(
            success=True,
            answer="Cached answer",
            from_cache=True,
        )
        mock_cache.get.return_value = cached_result

        result = pipeline.process("How many events?", user_id=1)

        assert result.from_cache is True

    def test_cache_miss_executes_query(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_format_response: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        """Cache miss should execute query normally."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        pipeline._formatter.format = MagicMock(return_value=mock_format_response)

        # Make validator succeed
        valid_result = MagicMock()
        valid_result.valid = True
        pipeline._validator.validate = MagicMock(return_value=valid_result)

        # Setup cache miss
        mock_cache.get.return_value = None

        result = pipeline.process("How many events?", user_id=1)

        assert result.from_cache is False

    def test_result_cached_after_execution(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_format_response: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        """Result should be cached after successful execution."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        pipeline._formatter.format = MagicMock(return_value=mock_format_response)

        # Make validator succeed
        valid_result = MagicMock()
        valid_result.valid = True
        pipeline._validator.validate = MagicMock(return_value=valid_result)

        mock_cache.get.return_value = None

        pipeline.process("How many events?", user_id=1)

        mock_cache.set.assert_called_once()


class TestNL2SQLPipelineErrorCorrection:
    """Test error correction flow."""

    def test_correction_attempted_on_execution_error(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        """Correction should be attempted on execution error."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        mock_cache.get.return_value = None

        # Make validator succeed
        valid_result = MagicMock()
        valid_result.valid = True
        pipeline._validator.validate = MagicMock(return_value=valid_result)

        # Make executor fail then succeed
        failed_exec = MagicMock()
        failed_exec.success = False
        failed_exec.error_message = "Column not found"
        failed_exec.rows = []

        success_exec = MagicMock()
        success_exec.success = True
        success_exec.rows = [{"id": 1}]
        success_exec.error_message = None

        pipeline._executor.execute = MagicMock(
            side_effect=[failed_exec, success_exec]
        )

        # Make correction succeed
        correction_response = MagicMock()
        correction_response.success = True
        correction_response.data = MagicMock()
        correction_response.data.corrected_query = "SELECT id FROM events.events"
        pipeline._corrector.correct = MagicMock(return_value=correction_response)

        # Setup formatter
        format_response = MagicMock()
        format_response.success = True
        format_response.data = MagicMock()
        format_response.data.answer = "Found 1 event"
        format_response.data.confidence = 0.9
        format_response.data.sources = []
        pipeline._formatter.format = MagicMock(return_value=format_response)

        result = pipeline.process("How many events?", user_id=1, user=MagicMock(id=1, is_admin=False))

        # Correction should have been attempted
        pipeline._corrector.correct.assert_called()
        assert result.corrected is True

    def test_correction_exhaustion_returns_failure(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        """Exhausted corrections should return failure."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        mock_cache.get.return_value = None

        # Make validator succeed
        valid_result = MagicMock()
        valid_result.valid = True
        pipeline._validator.validate = MagicMock(return_value=valid_result)

        # Make executor always fail
        failed_exec = MagicMock()
        failed_exec.success = False
        failed_exec.error_message = "Persistent error"
        failed_exec.rows = []
        pipeline._executor.execute = MagicMock(return_value=failed_exec)

        # Make correction return new SQL (but execution still fails)
        correction_response = MagicMock()
        correction_response.success = True
        correction_response.data = MagicMock()
        correction_response.data.corrected_query = "SELECT 1"
        pipeline._corrector.correct = MagicMock(return_value=correction_response)

        result = pipeline.process("Bad query", user_id=1, user=MagicMock(id=1, is_admin=False))

        assert result.success is False
        assert result.error.error_type == PipelineErrorType.CORRECTION_EXHAUSTED


class TestNL2SQLPipelinePermissionFiltering:
    """Test permission filtering."""

    def test_uses_provided_event_ids(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_format_response: MagicMock,
    ) -> None:
        """Should use provided event_ids for filtering."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)

        # Mock validator
        valid_result = MagicMock()
        valid_result.valid = True
        valid_result.errors = []
        pipeline._validator.validate = MagicMock(return_value=valid_result)

        # Mock executor
        exec_result = MagicMock()
        exec_result.success = True
        exec_result.rows = [{"id": 1}]
        exec_result.error_message = None
        pipeline._executor.execute = MagicMock(return_value=exec_result)

        # Mock formatter
        pipeline._formatter.format = MagicMock(return_value=mock_format_response)

        event_ids = [1, 2, 3]

        # Generator should receive allowed_event_ids
        pipeline.process("List events", user_id=1, event_ids=event_ids)

        # Check that generator was called with event_ids
        call_args = pipeline._generator.generate.call_args
        assert call_args[0][2] == event_ids  # Third positional arg


class TestNL2SQLPipelineEmptyResults:
    """Test handling of empty results."""

    def test_empty_results_formatted_correctly(
        self,
        pipeline: NL2SQLPipeline,
        mock_classification_response: MagicMock,
        mock_sql_response: MagicMock,
        mock_db_session: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        """Empty results should use format_empty_response."""
        pipeline._classifier.classify = MagicMock(
            return_value=mock_classification_response
        )
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        mock_cache.get.return_value = None

        # Make validator succeed
        valid_result = MagicMock()
        valid_result.valid = True
        pipeline._validator.validate = MagicMock(return_value=valid_result)

        # Make execution return empty results
        pipeline._executor.execute = MagicMock(return_value=ExecutionResult(
            success=True, rows=[], row_count=0, columns=["id"], execution_time_ms=1))

        empty_summary = MagicMock()
        empty_summary.answer = "No results found"
        empty_summary.confidence = 0.95
        empty_summary.sources = []
        pipeline._formatter.format_empty_response = MagicMock(
            return_value=empty_summary
        )

        result = pipeline.process("Find nonexistent event", user_id=1)

        pipeline._formatter.format_empty_response.assert_called()


class TestNL2SQLPipelineComponentAccess:
    """Test component access properties."""

    def test_classifier_property(self, pipeline: NL2SQLPipeline) -> None:
        """Should expose classifier via property."""
        assert pipeline.classifier is not None

    def test_generator_property(self, pipeline: NL2SQLPipeline) -> None:
        """Should expose generator via property."""
        assert pipeline.generator is not None

    def test_validator_property(self, pipeline: NL2SQLPipeline) -> None:
        """Should expose validator via property."""
        assert pipeline.validator is not None

    def test_executor_property(self, pipeline: NL2SQLPipeline) -> None:
        """Should expose executor via property."""
        assert pipeline.executor is not None

    def test_corrector_property(self, pipeline: NL2SQLPipeline) -> None:
        """Should expose corrector via property."""
        assert pipeline.corrector is not None

    def test_formatter_property(self, pipeline: NL2SQLPipeline) -> None:
        """Should expose formatter via property."""
        assert pipeline.formatter is not None

    def test_cache_property(
        self, pipeline: NL2SQLPipeline, mock_cache: MagicMock
    ) -> None:
        """Should expose cache via property."""
        assert pipeline.cache is mock_cache


class TestNL2SQLPipelineErrorResult:
    """Test _error_result helper method."""

    def test_creates_failure_result(
        self, pipeline: NL2SQLPipeline
    ) -> None:
        """_error_result should create failure result."""
        result = pipeline._error_result(
            PipelineErrorType.CLASSIFICATION_FAILED,
            "Internal error",
            "User friendly message",
        )

        assert result.success is False
        assert result.error is not None
        assert result.error.error_type == PipelineErrorType.CLASSIFICATION_FAILED

    def test_includes_timing_info(
        self, pipeline: NL2SQLPipeline
    ) -> None:
        """Error result should include timing info."""
        result = pipeline._error_result(
            PipelineErrorType.EXECUTION_FAILED,
            "Error",
            "Message",
            total_time_ms=100,
            classification_time_ms=20,
            generation_time_ms=30,
            execution_time_ms=50,
        )

        assert result.total_time_ms == 100
        assert result.classification_time_ms == 20
        assert result.generation_time_ms == 30
        assert result.execution_time_ms == 50

    def test_includes_sql_info_when_available(
        self, pipeline: NL2SQLPipeline
    ) -> None:
        """Error result should include SQL info when available."""
        result = pipeline._error_result(
            PipelineErrorType.VALIDATION_FAILED,
            "Validation error",
            "Message",
            generated_sql="SELECT * FROM secret_table",
            tables_accessed=["secret_table"],
        )

        assert result.generated_sql == "SELECT * FROM secret_table"
        assert "secret_table" in result.tables_accessed


def test_result_lists_the_llm_calls_made_for_the_question(pipeline):
    """Each question's cost travels with its result (the shared call_log mixes concurrent requests)."""
    from unittest.mock import MagicMock

    from indico_assistant.services.llm.service import LLMService
    from indico_assistant.services.nl2sql.models import PipelineResult

    llm = LLMService(MagicMock())

    def answer(*args, **kwargs):
        llm._store([], {"stage": "QueryClassification", "cost_usd": "0.00010"})
        llm._store([], {"stage": "SQLGeneration", "cost_usd": "0.00020"})
        return PipelineResult(success=True, answer="Two events.")

    pipeline._process = answer
    result = pipeline.process("How many events?", user_id=1)
    assert [c["stage"] for c in result.llm_calls] == ["QueryClassification", "SQLGeneration"]
    assert len(pipeline.process("Again?", user_id=1).llm_calls) == 2  # not 4: a fresh list per question


class TestNL2SQLPipelineAccessContext:
    """Phase 0: the executor gets the authenticated user's context; timeouts are not corrected."""

    def _run(self, pipeline, mock_classification_response, mock_sql_response, mock_format_response, **kwargs):
        pipeline._classifier.classify = MagicMock(return_value=mock_classification_response)
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        pipeline._formatter.format = MagicMock(return_value=mock_format_response)
        pipeline._validator.validate = MagicMock(return_value=MagicMock(valid=True, violations=[]))
        return pipeline.process("How many events?", **kwargs)

    def test_context_is_the_authenticated_user_and_scope(self, pipeline, mock_classification_response,
                                                         mock_sql_response, mock_format_response):
        user = MagicMock(id=7, is_admin=False)
        self._run(pipeline, mock_classification_response, mock_sql_response, mock_format_response,
                  user_id=99, user=user, event_ids=[42])  # user_id=99: a claimed identity, not the viewer
        context = pipeline._executor.execute.call_args.kwargs["context"]
        assert (context.user_id, context.event_id, context.is_admin) == (7, 42, False)

    def test_no_user_no_context(self, pipeline, mock_classification_response, mock_sql_response,
                                mock_format_response):
        pipeline._executor.execute = MagicMock(return_value=ExecutionResult(
            success=False, rows=[], row_count=0, columns=[], execution_time_ms=0,
            error_message="A user context is required to query event data", correctable=False))
        pipeline._corrector.correct = MagicMock()
        self._run(pipeline, mock_classification_response, mock_sql_response, mock_format_response, user_id=1)
        assert pipeline._executor.execute.call_args.kwargs["context"] is None
        pipeline._corrector.correct.assert_not_called()  # no paid rewrite for a query that can never run

    def test_timeout_is_not_sent_to_the_corrector(self, pipeline, mock_classification_response,
                                                  mock_sql_response, mock_format_response):
        pipeline._executor.execute = MagicMock(return_value=ExecutionResult(
            success=False, rows=[], row_count=0, columns=[], execution_time_ms=10000,
            error_message="Query timed out after 30 seconds", correctable=False))
        pipeline._corrector.correct = MagicMock()
        self._run(pipeline, mock_classification_response, mock_sql_response, mock_format_response,
                  user_id=1, user=MagicMock(id=1, is_admin=False))
        pipeline._corrector.correct.assert_not_called()
        assert pipeline._executor.execute.call_count == 1


def test_topic_keyword_is_escaped_inside_the_like_literal(pipeline):
    """A keyword from the question ("O'Brien", "100%") must not break or widen the generated SQL."""
    from types import SimpleNamespace

    sql = "SELECT e.id FROM events.events e WHERE e.title ILIKE '%x%'"
    for value, literal in (("O'Brien", "O''Brien"), ("100%", "100\\%"), ("snake_case", "snake\\_case")):
        classification = SimpleNamespace(entities=[SimpleNamespace(type="topic", value=value)], time_range=None)
        fixed = pipeline._fix_topic_search_sql(sql, classification)
        assert f"e.title ILIKE '%{literal}%'" in fixed


@pytest.mark.parametrize(("old", "start", "end"), [
    ("e.start_dt BETWEEN '2026-10-02' AND '2026-10-02'", "2026-10-02", "2026-10-02"),  # midnight UTC only
    ("e.start_dt BETWEEN '2026-10-02' AND '2026-10-02 23:59:59'", "2026-10-02", "2026-10-02"),  # a UTC day
    ("e.start_dt BETWEEN '2026-10-02 00:00:00' AND '2026-10-04 23:59:59'", "2026-10-02", "2026-10-04"),
    ("E.START_DT between '2026-10-02' and '2026-10-04'", "2026-10-02", "2026-10-04"),
])
def test_a_day_filter_is_the_events_local_day(pipeline, old, start, end):
    """Issue #4 (Copilot review, PR #7): the model's UTC day filters become the local-date filter, whether or not
    the classifier found the range. (US/Pacific 5 PM on Oct 1 is 00:00 UTC on Oct 2: a UTC day wrongly counts it.)"""
    from types import SimpleNamespace

    from indico_assistant.services.nl2sql.pipeline import LOCAL_EVENT_DATE

    sql = f"SELECT e.id FROM events.events e WHERE e.is_deleted = false AND {old} AND e.title ILIKE '%x%'"
    classification = SimpleNamespace(entities=[SimpleNamespace(type="topic", value="x")], time_range=None)
    fixed = pipeline._fix_topic_search_sql(sql, classification)
    assert f"{LOCAL_EVENT_DATE} BETWEEN '{start}' AND '{end}'" in fixed
    assert "e.start_dt BETWEEN" not in fixed.replace("E.START_DT", "e.start_dt")


def test_a_topic_search_routed_by_jev_is_broadened_too(pipeline):
    """(review, PR #15) Jev gives no entities: the term the model searched is the keyword, and the days are local"""
    from types import SimpleNamespace

    from indico_assistant.services.nl2sql.pipeline import LOCAL_EVENT_DATE

    sql = ("SELECT e.id, e.title FROM events.events e WHERE e.title ILIKE '%Catalyst%' "
           "AND e.start_dt BETWEEN '2026-09-01' AND '2026-09-30' ORDER BY e.start_dt")
    fixed = pipeline._fix_topic_search_sql(sql, SimpleNamespace(entities=[], time_range=None))
    assert "n.html ILIKE '%Catalyst%'" in fixed and "LEFT JOIN events.contributions c" in fixed
    assert "GROUP BY e.id" in fixed  # (fresh review) one row per event once the joins are injected
    counted = pipeline._fix_topic_search_sql(
        "SELECT COUNT(*) FROM events.events e WHERE e.title ILIKE '%Catalyst%' LIMIT 1",
        SimpleNamespace(entities=[], time_range=None))
    assert "GROUP BY" not in counted  # (never around an aggregate)
    assert f"{LOCAL_EVENT_DATE} BETWEEN '2026-09-01' AND '2026-09-30'" in fixed
    days_only = "SELECT e.id FROM events.events e WHERE e.start_dt BETWEEN '2026-09-01' AND '2026-09-30'"
    assert LOCAL_EVENT_DATE in pipeline._fix_topic_search_sql(days_only, SimpleNamespace(entities=[], time_range=None))


def test_a_filter_with_real_times_is_left_alone(pipeline):
    from types import SimpleNamespace

    sql = ("SELECT e.id FROM events.events e WHERE e.start_dt BETWEEN '2026-10-02 09:00:00' AND "
           "'2026-10-02 17:00:00' AND e.title ILIKE '%x%'")
    classification = SimpleNamespace(entities=[SimpleNamespace(type="topic", value="x")], time_range=None)
    assert "BETWEEN '2026-10-02 09:00:00' AND '2026-10-02 17:00:00'" in pipeline._fix_topic_search_sql(
        sql, classification)


class TestNL2SQLPipelineEvidence:
    """Spec 021 R5: every result carries the intent, its confidence and the last rejection, which the answer
    records as the evidence triage reads (the query log has no link to answers)."""

    def test_a_good_answer_carries_its_intent(
        self, pipeline, mock_classification, mock_classification_response, mock_sql_response, mock_format_response
    ) -> None:
        mock_classification.confidence = 0.87
        pipeline._classifier.classify = MagicMock(return_value=mock_classification_response)
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        pipeline._formatter.format = MagicMock(return_value=mock_format_response)

        result = pipeline.process("How many events?", user_id=1)

        assert (result.intent, result.intent_confidence, result.validation_rejection) == ("event_query", 0.87, None)

    def test_an_early_return_carries_it_too(
        self, pipeline, mock_classification, mock_classification_response
    ) -> None:
        mock_classification.intent, mock_classification.confidence = "out_of_scope", 0.99
        pipeline._classifier.classify = MagicMock(return_value=mock_classification_response)
        pipeline._classifier.is_out_of_scope = MagicMock(return_value=True)

        result = pipeline.process("Make me coffee", user_id=1)

        assert result.success is False and (result.intent, result.intent_confidence) == ("out_of_scope", 0.99)

    def test_a_failed_classification_has_no_intent(self, pipeline) -> None:
        failed = MagicMock(success=False, data=None, error="Classification error")
        pipeline._classifier.classify = MagicMock(return_value=failed)

        result = pipeline.process("?", user_id=1)

        assert (result.intent, result.intent_confidence) == (None, None)

    def test_a_rejected_query_carries_the_rejection(
        self, pipeline, mock_classification, mock_classification_response, mock_sql_response
    ) -> None:
        mock_classification.confidence = 0.5
        pipeline._classifier.classify = MagicMock(return_value=mock_classification_response)
        pipeline._generator.generate = MagicMock(return_value=mock_sql_response)
        pipeline._validator.validate = MagicMock(return_value=MagicMock(valid=False, violations=["forbidden keyword"]))

        result = pipeline.process("DROP TABLE events", user_id=1)

        assert result.error.error_type == PipelineErrorType.VALIDATION_FAILED
        assert "forbidden keyword" in result.validation_rejection
