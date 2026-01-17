"""Contract tests for LLM response models.

Feature: 007-tdd-gap-analysis
GAP: GAP-006 (Critical - Contract Tests)
Tasks: T038-T045

Tests the Pydantic models used for LLM response validation including:
- QueryClassification model validation
- SQLGeneration model validation  
- ResponseSummary model validation
- LLMResponse base model behavior and inheritance
"""

import pytest
from pydantic import ValidationError

from indico_assistant.services.llm.models.base import LLMResponse
from indico_assistant.services.llm.models.classification import (
    Entity,
    TimeRange,
    QueryClassification,
)
from indico_assistant.services.llm.models.sql import (
    SQLGeneration,
    SQLCorrection,
)
from indico_assistant.services.llm.models.summary import ResponseSummary
from indico_assistant.services.llm.errors import LLMError, ErrorType


class TestQueryClassificationModel:
    """Contract tests for QueryClassification model."""

    # =========================================================================
    # T039: test_classification_model_valid
    # =========================================================================

    def test_classification_model_valid_minimal(self):
        """Test QueryClassification accepts minimal valid input."""
        classification = QueryClassification(intent="search_events")
        
        assert classification.intent == "search_events"
        assert classification.entities == []
        assert classification.time_range is None
        assert classification.filters == {}

    def test_classification_model_valid_full(self):
        """Test QueryClassification accepts full valid input."""
        classification = QueryClassification(
            intent="search_events",
            entities=[
                Entity(type="person", value="John Smith", confidence=0.95)
            ],
            time_range=TimeRange(start="2026-01-01", end="2026-01-31"),
            filters={"category": "workshop", "venue": "Room A"}
        )
        
        assert classification.intent == "search_events"
        assert len(classification.entities) == 1
        assert classification.entities[0].type == "person"
        assert classification.time_range.start == "2026-01-01"
        assert classification.filters["category"] == "workshop"

    def test_classification_model_valid_multiple_entities(self):
        """Test QueryClassification with multiple entities."""
        classification = QueryClassification(
            intent="complex_search",
            entities=[
                Entity(type="person", value="Alice", confidence=0.9),
                Entity(type="event", value="Conference 2026", confidence=0.85),
                Entity(type="date", value="next week", confidence=0.7),
            ]
        )
        
        assert len(classification.entities) == 3
        assert classification.entities[0].value == "Alice"
        assert classification.entities[2].confidence == 0.7

    # =========================================================================
    # T040: test_classification_model_invalid
    # =========================================================================

    def test_classification_model_invalid_missing_intent(self):
        """Test QueryClassification rejects missing intent."""
        with pytest.raises(ValidationError) as exc_info:
            QueryClassification()
        
        assert "intent" in str(exc_info.value)

    def test_entity_model_invalid_confidence_range(self):
        """Test Entity rejects confidence outside 0-1 range."""
        with pytest.raises(ValidationError):
            Entity(type="person", value="Test", confidence=1.5)
        
        with pytest.raises(ValidationError):
            Entity(type="person", value="Test", confidence=-0.1)

    def test_entity_model_valid_boundary_confidence(self):
        """Test Entity accepts boundary confidence values."""
        entity_min = Entity(type="person", value="Test", confidence=0.0)
        entity_max = Entity(type="person", value="Test", confidence=1.0)
        
        assert entity_min.confidence == 0.0
        assert entity_max.confidence == 1.0


class TestSQLGenerationModel:
    """Contract tests for SQLGeneration model."""

    # =========================================================================
    # T041: test_sql_model_valid
    # =========================================================================

    def test_sql_model_valid_simple_query(self):
        """Test SQLGeneration accepts valid SELECT query."""
        sql = SQLGeneration(
            query="SELECT id, title FROM events.events WHERE category_id = 1",
            explanation="Retrieves event IDs and titles for category 1",
            tables_used=["events.events"]
        )
        
        assert "SELECT" in sql.query
        assert sql.tables_used == ["events.events"]

    def test_sql_model_valid_complex_query(self):
        """Test SQLGeneration accepts complex valid query."""
        sql = SQLGeneration(
            query="""
                SELECT e.title, COUNT(r.id) as reg_count
                FROM events.events e
                LEFT JOIN events.registrations r ON r.event_id = e.id
                WHERE e.start_dt > '2026-01-01'
                GROUP BY e.id, e.title
                ORDER BY reg_count DESC
            """,
            explanation="Counts registrations per event after 2026",
            tables_used=["events.events", "events.registrations"]
        )
        
        assert len(sql.tables_used) == 2
        assert "LEFT JOIN" in sql.query

    # =========================================================================
    # T042: test_sql_model_invalid
    # =========================================================================

    def test_sql_model_invalid_not_select(self):
        """Test SQLGeneration rejects non-SELECT queries."""
        with pytest.raises(ValidationError) as exc_info:
            SQLGeneration(
                query="UPDATE events.events SET title = 'Hacked'",
                explanation="Trying to update",
                tables_used=["events.events"]
            )
        
        assert "SELECT" in str(exc_info.value)

    def test_sql_model_invalid_drop_keyword(self):
        """Test SQLGeneration rejects DROP keyword."""
        with pytest.raises(ValidationError) as exc_info:
            SQLGeneration(
                query="SELECT * FROM events.events; DROP TABLE events.events;",
                explanation="SQL injection attempt",
                tables_used=["events.events"]
            )
        
        assert "DROP" in str(exc_info.value)

    def test_sql_model_invalid_delete_keyword(self):
        """Test SQLGeneration rejects DELETE keyword."""
        with pytest.raises(ValidationError):
            SQLGeneration(
                query="DELETE FROM events.events WHERE id = 1",
                explanation="Delete attempt",
                tables_used=["events.events"]
            )

    def test_sql_model_invalid_insert_keyword(self):
        """Test SQLGeneration rejects INSERT keyword."""
        with pytest.raises(ValidationError):
            SQLGeneration(
                query="INSERT INTO events.events (title) VALUES ('Hacked')",
                explanation="Insert attempt",
                tables_used=["events.events"]
            )

    def test_sql_model_invalid_empty_tables(self):
        """Test SQLGeneration rejects empty tables_used list."""
        with pytest.raises(ValidationError):
            SQLGeneration(
                query="SELECT 1",
                explanation="No tables",
                tables_used=[]
            )

    def test_sql_correction_model_valid(self):
        """Test SQLCorrection accepts valid corrected query."""
        correction = SQLCorrection(
            corrected_query="SELECT title FROM events.events WHERE id = 1",
            error_analysis="Original query used non-existent column 'name'",
            changes_made=["Changed 'name' to 'title'"]
        )
        
        assert "SELECT" in correction.corrected_query
        assert len(correction.changes_made) == 1


class TestResponseSummaryModel:
    """Contract tests for ResponseSummary model."""

    # =========================================================================
    # T043: test_summary_model_valid
    # =========================================================================

    def test_summary_model_valid_minimal(self):
        """Test ResponseSummary accepts minimal valid input."""
        summary = ResponseSummary(
            answer="There are 5 events scheduled for next week.",
            confidence=0.85
        )
        
        assert summary.answer == "There are 5 events scheduled for next week."
        assert summary.confidence == 0.85
        assert summary.sources == []

    def test_summary_model_valid_with_sources(self):
        """Test ResponseSummary accepts input with sources."""
        summary = ResponseSummary(
            answer="The workshop has 50 registered participants.",
            confidence=0.92,
            sources=["events.events", "events.registrations"]
        )
        
        assert len(summary.sources) == 2
        assert "events.registrations" in summary.sources

    def test_summary_model_valid_boundary_confidence(self):
        """Test ResponseSummary accepts boundary confidence values."""
        summary_low = ResponseSummary(answer="Test", confidence=0.0)
        summary_high = ResponseSummary(answer="Test", confidence=1.0)
        
        assert summary_low.confidence == 0.0
        assert summary_high.confidence == 1.0

    def test_summary_model_invalid_empty_answer(self):
        """Test ResponseSummary rejects empty answer."""
        with pytest.raises(ValidationError):
            ResponseSummary(answer="", confidence=0.5)

    def test_summary_model_invalid_confidence_range(self):
        """Test ResponseSummary rejects confidence outside 0-1."""
        with pytest.raises(ValidationError):
            ResponseSummary(answer="Test", confidence=1.5)
        
        with pytest.raises(ValidationError):
            ResponseSummary(answer="Test", confidence=-0.1)


class TestLLMResponseBaseModel:
    """Contract tests for LLMResponse base model."""

    # =========================================================================
    # T044: test_base_model_inheritance
    # =========================================================================

    def test_base_model_success_response(self):
        """Test LLMResponse wraps successful result correctly."""
        result = QueryClassification(intent="test")
        
        response = LLMResponse[QueryClassification](
            success=True,
            result=result,
            latency_ms=100,
            retries=0
        )
        
        assert response.success is True
        assert response.result.intent == "test"
        assert response.error is None
        assert response.latency_ms == 100

    def test_base_model_error_response(self):
        """Test LLMResponse wraps error correctly."""
        error = LLMError(
            error_type=ErrorType.TIMEOUT,
            message="Request timed out"
        )
        
        response = LLMResponse[QueryClassification](
            success=False,
            error=error,
            latency_ms=30000,
            retries=3
        )
        
        assert response.success is False
        assert response.result is None
        assert response.error.error_type == ErrorType.TIMEOUT
        assert response.retries == 3

    def test_base_model_factory_success(self):
        """Test LLMResponse.success_response factory method."""
        result = ResponseSummary(answer="Test answer", confidence=0.9)
        
        response = LLMResponse.success_response(
            result=result,
            latency_ms=150,
            retries=1
        )
        
        assert response.success is True
        assert response.result.answer == "Test answer"
        assert response.retries == 1

    def test_base_model_factory_error(self):
        """Test LLMResponse.error_response factory method."""
        error = LLMError(
            error_type=ErrorType.VALIDATION_ERROR,
            message="Invalid response format"
        )
        
        response = LLMResponse.error_response(
            error=error,
            latency_ms=50,
            retries=0
        )
        
        assert response.success is False
        assert response.error.message == "Invalid response format"

    def test_base_model_invariant_success_requires_result(self):
        """Test LLMResponse invariant: success=True requires result."""
        with pytest.raises(ValidationError) as exc_info:
            LLMResponse[QueryClassification](
                success=True,
                result=None,  # Invalid: success needs result
                latency_ms=100
            )
        
        assert "result" in str(exc_info.value).lower()

    def test_base_model_invariant_failure_requires_error(self):
        """Test LLMResponse invariant: success=False requires error."""
        with pytest.raises(ValidationError) as exc_info:
            LLMResponse[QueryClassification](
                success=False,
                error=None,  # Invalid: failure needs error
                latency_ms=100
            )
        
        assert "error" in str(exc_info.value).lower()

    def test_base_model_invariant_success_no_error(self):
        """Test LLMResponse invariant: success=True cannot have error."""
        with pytest.raises(ValidationError):
            LLMResponse[QueryClassification](
                success=True,
                result=QueryClassification(intent="test"),
                error=LLMError(code="X", message="X", retryable=False),
                latency_ms=100
            )

    def test_base_model_invariant_failure_no_result(self):
        """Test LLMResponse invariant: success=False cannot have result."""
        with pytest.raises(ValidationError):
            LLMResponse[QueryClassification](
                success=False,
                result=QueryClassification(intent="test"),
                error=LLMError(code="X", message="X", retryable=False),
                latency_ms=100
            )

    def test_base_model_latency_non_negative(self):
        """Test LLMResponse latency_ms must be non-negative."""
        with pytest.raises(ValidationError):
            LLMResponse[QueryClassification](
                success=True,
                result=QueryClassification(intent="test"),
                latency_ms=-1
            )

    def test_base_model_retries_non_negative(self):
        """Test LLMResponse retries must be non-negative."""
        with pytest.raises(ValidationError):
            LLMResponse[QueryClassification](
                success=True,
                result=QueryClassification(intent="test"),
                latency_ms=100,
                retries=-1
            )


class TestModelSerialization:
    """Tests for model serialization (model_dump)."""

    def test_query_classification_serialization(self):
        """Test QueryClassification serializes correctly."""
        classification = QueryClassification(
            intent="search",
            entities=[Entity(type="person", value="John", confidence=0.9)],
            time_range=TimeRange(start="2026-01-01"),
            filters={"key": "value"}
        )
        
        data = classification.model_dump()
        
        assert data["intent"] == "search"
        assert len(data["entities"]) == 1
        assert data["entities"][0]["type"] == "person"
        assert data["time_range"]["start"] == "2026-01-01"

    def test_sql_generation_serialization(self):
        """Test SQLGeneration serializes correctly."""
        sql = SQLGeneration(
            query="SELECT * FROM events.events",
            explanation="Get all events",
            tables_used=["events.events"]
        )
        
        data = sql.model_dump()
        
        assert "query" in data
        assert data["tables_used"] == ["events.events"]

    def test_response_summary_serialization(self):
        """Test ResponseSummary serializes correctly."""
        summary = ResponseSummary(
            answer="Answer text",
            confidence=0.88,
            sources=["source1", "source2"]
        )
        
        data = summary.model_dump()
        
        assert data["answer"] == "Answer text"
        assert data["confidence"] == 0.88
        assert len(data["sources"]) == 2

    def test_llm_response_serialization(self):
        """Test LLMResponse serializes correctly."""
        response = LLMResponse.success_response(
            result=QueryClassification(intent="test"),
            latency_ms=200,
            retries=1
        )
        
        data = response.model_dump()
        
        assert data["success"] is True
        assert data["result"]["intent"] == "test"
        assert data["latency_ms"] == 200
