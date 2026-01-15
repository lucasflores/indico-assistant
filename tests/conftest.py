"""Pytest configuration and fixtures for Indico Assistant plugin tests."""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, create_autospec

import pytest
import yaml

# Register Indico's pytest plugin for test fixtures
pytest_plugins = ("indico.testing.fixtures",)


@pytest.fixture
def plugin_settings():
    """Fixture providing default plugin settings for testing."""
    return {
        "enabled": True,
        "llm_provider": "ollama",
        "llm_model": "llama3.2",
        "llm_base_url": "http://localhost:11434",
        "llm_api_key": None,
        "timeout_seconds": 30,
        "max_tokens": 2048,
        # NL2SQL settings
        "nl2sql_enabled": True,
        "nl2sql_timeout": 30,
        "nl2sql_max_rows": 1000,
        "nl2sql_max_corrections": 3,
        "nl2sql_cache_ttl": 600,
        "nl2sql_allowed_tables": None,
    }


@pytest.fixture
def mock_llm_response():
    """Fixture providing a mock LLM response for testing."""
    return {
        "status": "connected",
        "model": "llama3.2",
        "response_time_ms": 150,
    }


# =============================================================================
# NL2SQL Pipeline Fixtures (003-nl2sql-pipeline)
# =============================================================================


@pytest.fixture
def mock_llm_service():
    """
    Fixture providing a mock LLMService for NL2SQL testing.
    
    Use this fixture to test NL2SQL components without making actual LLM calls.
    
    Example:
        def test_classifier(mock_llm_service):
            classifier = QueryClassifier(mock_llm_service)
            # Configure mock responses
            mock_llm_service.generate.return_value = ...
    """
    from indico_assistant.services.llm import LLMService
    from indico_assistant.services.llm.models import LLMResponse
    
    mock = create_autospec(LLMService, instance=True)
    
    # Configure default behavior
    mock.generate.return_value = LLMResponse(
        success=True,
        data=None,
        error=None,
        latency_ms=100,
        model="test-model",
        tokens_used=50,
    )
    
    return mock


@pytest.fixture
def sample_schema_content():
    """
    Fixture providing sample schema content for testing.
    
    Contains a minimal but realistic schema for events, registrations,
    and contributions tables.
    """
    return {
        "events.events": {
            "description": "Core events table storing all Indico events",
            "columns": {
                "id": {"type": "integer", "nullable": False, "description": "Primary key"},
                "title": {"type": "varchar(255)", "nullable": False, "description": "Event title"},
                "description": {"type": "text", "nullable": True, "description": "Event description"},
                "start_dt": {"type": "timestamp", "nullable": False, "description": "Event start datetime"},
                "end_dt": {"type": "timestamp", "nullable": True, "description": "Event end datetime"},
                "category_id": {"type": "integer", "nullable": True, "description": "Parent category ID"},
            },
            "relationships": [
                "categories.categories via category_id",
                "events.registrations via event_id",
                "events.contributions via event_id",
            ],
        },
        "events.registrations": {
            "description": "Event registrations linking users to events",
            "columns": {
                "id": {"type": "integer", "nullable": False, "description": "Primary key"},
                "event_id": {"type": "integer", "nullable": False, "description": "Event ID (FK)"},
                "user_id": {"type": "integer", "nullable": True, "description": "User ID if registered user"},
                "email": {"type": "varchar(255)", "nullable": False, "description": "Registrant email"},
                "first_name": {"type": "varchar(255)", "nullable": True, "description": "First name"},
                "last_name": {"type": "varchar(255)", "nullable": True, "description": "Last name"},
                "state": {"type": "varchar(20)", "nullable": False, "description": "Registration state"},
            },
            "relationships": ["events.events via event_id"],
        },
        "events.contributions": {
            "description": "Event contributions (talks, presentations)",
            "columns": {
                "id": {"type": "integer", "nullable": False, "description": "Primary key"},
                "event_id": {"type": "integer", "nullable": False, "description": "Event ID (FK)"},
                "title": {"type": "varchar(255)", "nullable": False, "description": "Contribution title"},
                "description": {"type": "text", "nullable": True, "description": "Contribution description"},
                "duration": {"type": "interval", "nullable": True, "description": "Duration"},
            },
            "relationships": [
                "events.events via event_id",
                "events.contribution_person_links via contribution_id",
            ],
        },
        "events.persons": {
            "description": "Persons associated with events (speakers, authors)",
            "columns": {
                "id": {"type": "integer", "nullable": False, "description": "Primary key"},
                "event_id": {"type": "integer", "nullable": False, "description": "Event ID (FK)"},
                "first_name": {"type": "varchar(255)", "nullable": False, "description": "First name"},
                "last_name": {"type": "varchar(255)", "nullable": False, "description": "Last name"},
                "email": {"type": "varchar(255)", "nullable": True, "description": "Email address"},
                "affiliation": {"type": "varchar(255)", "nullable": True, "description": "Organization"},
            },
            "relationships": ["events.contribution_person_links via person_id"],
        },
        "categories.categories": {
            "description": "Category hierarchy for organizing events",
            "columns": {
                "id": {"type": "integer", "nullable": False, "description": "Primary key"},
                "parent_id": {"type": "integer", "nullable": True, "description": "Parent category ID"},
                "title": {"type": "varchar(255)", "nullable": False, "description": "Category title"},
            },
            "relationships": ["events.events via category_id"],
        },
    }


@pytest.fixture
def sample_schema_context(sample_schema_content, tmp_path):
    """
    Fixture providing a SchemaContext with sample schema loaded.
    
    Creates a temporary YAML schema file and initializes SchemaContext
    with it for testing.
    
    Example:
        def test_generator(sample_schema_context):
            generator = SQLGenerator(mock_llm, sample_schema_context)
            # Test with real schema context
    """
    from indico_assistant.services.nl2sql.schema import SchemaContext
    
    schema_file = tmp_path / "test_schema.yaml"
    with open(schema_file, "w") as f:
        yaml.dump(sample_schema_content, f)
    
    return SchemaContext(str(schema_file))


@pytest.fixture
def sample_query_cache():
    """
    Fixture providing a QueryCache instance for testing.
    
    Configured with short TTL for testing expiration behavior.
    """
    from indico_assistant.services.nl2sql.cache import QueryCache
    
    return QueryCache(ttl_seconds=60, max_entries=100)


@pytest.fixture
def mock_db_session():
    """
    Fixture providing a mock database session for testing QueryExecutor.
    
    Returns a MagicMock that simulates SQLAlchemy session behavior.
    """
    session = MagicMock()
    session.execute.return_value.fetchall.return_value = []
    session.execute.return_value.keys.return_value = []
    return session


@pytest.fixture
def mock_db_session_factory(mock_db_session):
    """
    Fixture providing a factory function that returns the mock session.
    """
    def factory() -> Any:
        return mock_db_session
    return factory


@pytest.fixture
def sample_pipeline_result():
    """
    Fixture providing a sample successful PipelineResult.
    """
    from indico_assistant.services.nl2sql.models import PipelineResult
    
    return PipelineResult(
        success=True,
        answer="There are 5 events this week.",
        confidence=0.95,
        generated_sql="SELECT COUNT(*) FROM events.events WHERE start_dt >= NOW() AND start_dt < NOW() + INTERVAL '7 days'",
        tables_accessed=["events.events"],
        row_count=1,
        total_time_ms=250,
        classification_time_ms=50,
        generation_time_ms=100,
        execution_time_ms=20,
        from_cache=False,
    )


@pytest.fixture
def sample_error_result():
    """
    Fixture providing a sample failed PipelineResult with error.
    """
    from indico_assistant.services.nl2sql.models import (
        PipelineError,
        PipelineErrorType,
        PipelineResult,
    )
    
    return PipelineResult(
        success=False,
        error=PipelineError(
            error_type=PipelineErrorType.VALIDATION_FAILED,
            message="Table 'users' not in allowlist",
            user_message="I can't access that information. Please ask about events, registrations, or contributions.",
        ),
    )
