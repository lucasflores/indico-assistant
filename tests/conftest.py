"""Pytest configuration and fixtures for Indico Assistant plugin tests."""

import pytest

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
    }


@pytest.fixture
def mock_llm_response():
    """Fixture providing a mock LLM response for testing."""
    return {
        "status": "connected",
        "model": "llama3.2",
        "response_time_ms": 150,
    }
