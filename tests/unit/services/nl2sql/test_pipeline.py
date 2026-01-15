# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""Unit tests for NL2SQLPipeline orchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from indico_assistant.services.nl2sql.models import PipelineErrorType
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
    """Create a pipeline instance."""
    return NL2SQLPipeline(
        llm_service=mock_llm_service,
        schema_context=mock_schema_context,
        db_session_factory=mock_db_session_factory,
        cache=mock_cache,
    )


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

        result = pipeline.process("How many events?", user_id=1)

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

        result = pipeline.process("Bad query", user_id=1)

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
        result_mock = MagicMock()
        result_mock.keys.return_value = ["id"]
        result_mock.fetchall.return_value = []
        mock_db_session.execute.return_value = result_mock

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
