"""Contract tests for pre-defined LLM response models.

These tests verify that the pre-defined models enforce their
validation rules correctly.
"""

import pytest

from indico_assistant.services.llm.models import (
    Entity,
    TimeRange,
    QueryClassification,
    SQLGeneration,
    SQLCorrection,
    ResponseSummary,
)


class TestQueryClassificationModel:
    """Tests for QueryClassification model."""
    
    def test_minimal_classification(self):
        """Classification can be created with just intent."""
        classification = QueryClassification(intent="search_events")
        
        assert classification.intent == "search_events"
        assert classification.entities == []
        assert classification.time_range is None
        assert classification.filters == {}
    
    def test_full_classification(self):
        """Classification can be created with all fields."""
        classification = QueryClassification(
            intent="search_events",
            entities=[
                Entity(type="person", value="John Smith", confidence=0.95)
            ],
            time_range=TimeRange(start="2026-01-14", end="2026-01-21"),
            filters={"category": "workshop"}
        )
        
        assert classification.intent == "search_events"
        assert len(classification.entities) == 1
        assert classification.entities[0].type == "person"
        assert classification.time_range.start == "2026-01-14"
        assert classification.filters["category"] == "workshop"


class TestEntityModel:
    """Tests for Entity model."""
    
    def test_entity_with_default_confidence(self):
        """Entity uses default confidence when not specified."""
        entity = Entity(type="person", value="John Smith")
        
        assert entity.confidence == 0.9
    
    def test_entity_confidence_bounds(self):
        """Entity confidence must be between 0 and 1."""
        # Valid bounds
        Entity(type="test", value="test", confidence=0.0)
        Entity(type="test", value="test", confidence=1.0)
        Entity(type="test", value="test", confidence=0.5)
        
        # Invalid bounds
        with pytest.raises(ValueError, match="greater than or equal to 0"):
            Entity(type="test", value="test", confidence=-0.1)
        
        with pytest.raises(ValueError, match="less than or equal to 1"):
            Entity(type="test", value="test", confidence=1.1)


class TestSQLGenerationModel:
    """Tests for SQLGeneration model."""
    
    def test_valid_select_query(self):
        """Valid SELECT query is accepted."""
        sql = SQLGeneration(
            query="SELECT e.title FROM events.events e WHERE e.id = 1",
            explanation="Gets event title by ID",
            tables_used=["events.events"]
        )
        
        assert sql.query.startswith("SELECT")
        assert len(sql.tables_used) == 1
    
    def test_query_must_be_select(self):
        """Non-SELECT queries are rejected."""
        with pytest.raises(ValueError, match="SELECT"):
            SQLGeneration(
                query="UPDATE events SET title = 'Hacked'",
                explanation="Test",
                tables_used=["events"]
            )
    
    def test_drop_keyword_rejected(self):
        """DROP keyword in query is rejected."""
        with pytest.raises(ValueError, match="DROP"):
            SQLGeneration(
                query="SELECT * FROM events; DROP TABLE events;--",
                explanation="SQL injection attempt",
                tables_used=["events"]
            )
    
    def test_delete_keyword_rejected(self):
        """DELETE keyword in query is rejected."""
        with pytest.raises(ValueError, match="DELETE"):
            SQLGeneration(
                query="SELECT * FROM events WHERE DELETE = 1",
                explanation="Test",
                tables_used=["events"]
            )
    
    def test_insert_keyword_rejected(self):
        """INSERT keyword in query is rejected."""
        with pytest.raises(ValueError, match="INSERT"):
            SQLGeneration(
                query="SELECT * FROM events; INSERT INTO events VALUES (1);",
                explanation="Test",
                tables_used=["events"]
            )
    
    def test_truncate_keyword_rejected(self):
        """TRUNCATE keyword in query is rejected."""
        with pytest.raises(ValueError, match="TRUNCATE"):
            SQLGeneration(
                query="SELECT * FROM events; TRUNCATE events;",
                explanation="Test",
                tables_used=["events"]
            )
    
    def test_tables_used_required(self):
        """At least one table must be specified."""
        with pytest.raises(ValueError, match="at least 1"):
            SQLGeneration(
                query="SELECT 1",
                explanation="Test",
                tables_used=[]
            )
    
    def test_case_insensitive_safety_check(self):
        """Safety check is case-insensitive."""
        with pytest.raises(ValueError):
            SQLGeneration(
                query="select * from events; drop table events;",
                explanation="Test",
                tables_used=["events"]
            )


class TestSQLCorrectionModel:
    """Tests for SQLCorrection model."""
    
    def test_valid_correction(self):
        """Valid correction is accepted."""
        correction = SQLCorrection(
            corrected_query="SELECT e.title FROM events.events e",
            error_analysis="Changed 'name' to 'title'",
            changes_made=["Changed column name"]
        )
        
        assert correction.corrected_query.startswith("SELECT")
        assert len(correction.changes_made) >= 1
    
    def test_correction_safety_validation(self):
        """Corrected query must also pass safety validation."""
        with pytest.raises(ValueError, match="SELECT"):
            SQLCorrection(
                corrected_query="DELETE FROM events WHERE id = 1",
                error_analysis="Test",
                changes_made=["Changed query type"]
            )
    
    def test_changes_made_required(self):
        """At least one change must be listed."""
        with pytest.raises(ValueError, match="at least 1"):
            SQLCorrection(
                corrected_query="SELECT * FROM events",
                error_analysis="Analysis",
                changes_made=[]
            )


class TestResponseSummaryModel:
    """Tests for ResponseSummary model."""
    
    def test_valid_summary(self):
        """Valid summary is accepted."""
        summary = ResponseSummary(
            answer="There are 5 workshops scheduled.",
            confidence=0.92,
            sources=["events.events"]
        )
        
        assert summary.answer == "There are 5 workshops scheduled."
        assert summary.confidence == 0.92
        assert "events.events" in summary.sources
    
    def test_confidence_bounds(self):
        """Confidence must be between 0 and 1."""
        # Valid bounds
        ResponseSummary(answer="Test", confidence=0.0, sources=[])
        ResponseSummary(answer="Test", confidence=1.0, sources=[])
        
        # Invalid bounds
        with pytest.raises(ValueError, match="greater than or equal to 0"):
            ResponseSummary(answer="Test", confidence=-0.1, sources=[])
        
        with pytest.raises(ValueError, match="less than or equal to 1"):
            ResponseSummary(answer="Test", confidence=1.1, sources=[])
    
    def test_answer_required(self):
        """Answer cannot be empty."""
        with pytest.raises(ValueError, match="at least 1"):
            ResponseSummary(answer="", confidence=0.9, sources=[])
    
    def test_empty_sources_allowed(self):
        """Empty sources list is allowed."""
        summary = ResponseSummary(
            answer="No results found.",
            confidence=1.0,
            sources=[]
        )
        
        assert summary.sources == []


class TestModelSerialization:
    """Tests for model serialization."""
    
    def test_query_classification_to_dict(self):
        """QueryClassification can be serialized to dict."""
        classification = QueryClassification(
            intent="search",
            entities=[Entity(type="person", value="John", confidence=0.9)]
        )
        
        data = classification.model_dump()
        assert data["intent"] == "search"
        assert len(data["entities"]) == 1
        assert data["entities"][0]["type"] == "person"
    
    def test_sql_generation_to_dict(self):
        """SQLGeneration can be serialized to dict."""
        sql = SQLGeneration(
            query="SELECT * FROM events",
            explanation="Gets all events",
            tables_used=["events"]
        )
        
        data = sql.model_dump()
        assert data["query"] == "SELECT * FROM events"
        assert "events" in data["tables_used"]
    
    def test_response_summary_to_dict(self):
        """ResponseSummary can be serialized to dict."""
        summary = ResponseSummary(
            answer="Answer text",
            confidence=0.85,
            sources=["source1"]
        )
        
        data = summary.model_dump()
        assert data["answer"] == "Answer text"
        assert data["confidence"] == 0.85
