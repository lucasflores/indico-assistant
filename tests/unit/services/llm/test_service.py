"""Unit tests for LLMService class.

These tests verify the LLMService behavior using mocked Instructor clients
to avoid actual LLM calls.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pydantic import BaseModel

from indico_assistant.services.llm.service import LLMService, create_llm_service
from indico_assistant.services.llm.models import LLMResponse, HealthStatus
from indico_assistant.services.llm.errors import LLMError, ErrorType


class MockResponseModel(BaseModel):
    """Mock response model for testing."""
    intent: str
    confidence: float = 0.9


class MockPlugin:
    """Mock plugin for testing."""
    
    def __init__(self, settings: dict = None):
        self._settings = settings or {
            "llm_provider": "ollama",
            "llm_model": "llama3.2",
            "llm_base_url": "http://localhost:11434",
            "llm_api_key": None,
            "timeout_seconds": 30,
            "max_tokens": 2048,
            "max_retries": 2,
        }
    
    @property
    def settings(self):
        return MockSettings(self._settings)


class MockSettings:
    """Mock settings object."""
    
    def __init__(self, data: dict):
        self._data = data
    
    def get(self, key, default=None):
        return self._data.get(key, default)


class TestLLMServiceGenerate:
    """Tests for LLMService.generate() method."""
    
    def test_generate_success_path(self):
        """generate() returns success response with validated result."""
        plugin = MockPlugin()
        service = LLMService(plugin)
        
        # Mock the instructor client
        mock_client = MagicMock()
        mock_result = MockResponseModel(intent="search", confidence=0.95)
        mock_client.chat.completions.create.return_value = mock_result
        
        with patch.object(service, "_create_client", return_value=mock_client):
            response = service.generate(
                prompt="What events are today?",
                response_model=MockResponseModel
            )
        
        assert response.success is True
        assert response.result is not None
        assert response.result.intent == "search"
        assert response.result.confidence == 0.95
        assert response.error is None
        assert response.latency_ms >= 0
        assert response.retries == 0
    
    def test_generate_retry_on_validation_failure(self):
        """generate() returns error after max retries on validation failure."""
        plugin = MockPlugin()
        service = LLMService(plugin)
        
        # Mock the instructor client to raise validation error
        mock_client = MagicMock()
        
        # Create a mock exception that looks like instructor retry exception
        class MockRetryException(Exception):
            pass
        MockRetryException.__module__ = "instructor.exceptions"
        MockRetryException.__name__ = "InstructorRetryException"
        
        mock_client.chat.completions.create.side_effect = MockRetryException("Retries exhausted")
        
        with patch.object(service, "_create_client", return_value=mock_client):
            response = service.generate(
                prompt="Test prompt",
                response_model=MockResponseModel
            )
        
        assert response.success is False
        assert response.result is None
        assert response.error is not None
        assert response.error.error_type == ErrorType.VALIDATION_ERROR
    
    def test_generate_returns_error_after_max_retries(self):
        """generate() returns LLMError after exhausting max retries."""
        plugin = MockPlugin()
        service = LLMService(plugin)
        
        # Mock validation failure
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Invalid schema")
        
        with patch.object(service, "_create_client", return_value=mock_client):
            response = service.generate(
                prompt="Test prompt",
                response_model=MockResponseModel,
                max_retries=0
            )
        
        assert response.success is False
        assert response.error is not None
        # Unknown error for generic ValueError
        assert response.error.error_type in [ErrorType.VALIDATION_ERROR, ErrorType.UNKNOWN_ERROR]
    
    def test_generate_with_system_prompt(self):
        """generate() includes system prompt in messages."""
        plugin = MockPlugin()
        service = LLMService(plugin)
        
        mock_client = MagicMock()
        mock_result = MockResponseModel(intent="help", confidence=0.9)
        mock_client.chat.completions.create.return_value = mock_result
        
        with patch.object(service, "_create_client", return_value=mock_client):
            response = service.generate(
                prompt="Help me",
                response_model=MockResponseModel,
                system_prompt="You are a helpful assistant"
            )
        
        # Verify the call was made
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant"
        assert messages[1]["role"] == "user"
    
    def test_generate_timeout_override(self):
        """generate() respects timeout override."""
        plugin = MockPlugin()
        service = LLMService(plugin)
        
        mock_client = MagicMock()
        mock_result = MockResponseModel(intent="test", confidence=0.8)
        mock_client.chat.completions.create.return_value = mock_result
        
        with patch.object(service, "_create_client", return_value=mock_client):
            service.generate(
                prompt="Test",
                response_model=MockResponseModel,
                timeout=60.0
            )
        
        # Verify timeout was passed
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs.get("timeout") == 60.0
    
    def test_generate_not_configured(self):
        """generate() returns not_configured error when provider is not set."""
        plugin = MockPlugin(settings={
            "llm_provider": None,
            "llm_model": None,
            "llm_base_url": None,
            "llm_api_key": None,
            "timeout_seconds": 30,
            "max_tokens": 2048,
            "max_retries": 2,
        })
        service = LLMService(plugin)
        
        response = service.generate(
            prompt="Test",
            response_model=MockResponseModel
        )
        
        assert response.success is False
        assert response.error.error_type == ErrorType.NOT_CONFIGURED


class TestLLMServiceHealthCheck:
    """Tests for LLMService.health_check() method."""
    
    def test_health_check_connected(self):
        """health_check() returns connected status on success."""
        plugin = MockPlugin()
        service = LLMService(plugin)
        
        mock_client = MagicMock()
        # The health check uses a simple model internally
        mock_client.chat.completions.create.return_value = Mock(status="ok")
        
        with patch.object(service, "_create_client", return_value=mock_client):
            status = service.health_check()
        
        assert status.status == "connected"
        assert status.latency_ms is not None
        assert status.latency_ms >= 0
        assert status.provider == "ollama"
        assert status.model == "llama3.2"
        assert status.error is None
    
    def test_health_check_unavailable_on_connection_error(self):
        """health_check() returns unavailable on connection error."""
        plugin = MockPlugin()
        service = LLMService(plugin)
        
        mock_client = MagicMock()
        
        # Create a mock connection error
        class MockConnectionError(Exception):
            pass
        MockConnectionError.__module__ = "openai"
        MockConnectionError.__name__ = "APIConnectionError"
        
        mock_client.chat.completions.create.side_effect = MockConnectionError("Connection refused")
        
        with patch.object(service, "_create_client", return_value=mock_client):
            status = service.health_check()
        
        assert status.status == "unavailable"
        assert status.error is not None
        assert status.latency_ms is None
    
    def test_health_check_timeout(self):
        """health_check() returns timeout status on timeout."""
        plugin = MockPlugin()
        service = LLMService(plugin)
        
        mock_client = MagicMock()
        
        # Create a mock timeout error
        class MockTimeoutError(Exception):
            pass
        MockTimeoutError.__module__ = "openai"
        MockTimeoutError.__name__ = "APITimeoutError"
        
        mock_client.chat.completions.create.side_effect = MockTimeoutError("Timeout")
        
        with patch.object(service, "_create_client", return_value=mock_client):
            status = service.health_check()
        
        assert status.status == "timeout"
        assert status.error is not None
    
    def test_health_check_not_configured(self):
        """health_check() returns not_configured when provider not set."""
        plugin = MockPlugin(settings={
            "llm_provider": None,
            "llm_model": None,
            "llm_base_url": None,
            "llm_api_key": None,
            "timeout_seconds": 30,
            "max_tokens": 2048,
            "max_retries": 2,
        })
        service = LLMService(plugin)
        
        status = service.health_check()
        
        assert status.status == "not_configured"
        assert status.provider == "none"
        assert status.model == "none"


class TestCreateLLMService:
    """Tests for create_llm_service factory function."""
    
    def test_creates_service_instance(self):
        """create_llm_service() returns an LLMService instance."""
        plugin = MockPlugin()
        service = create_llm_service(plugin)
        
        assert isinstance(service, LLMService)
    
    def test_service_has_plugin_reference(self):
        """Created service maintains plugin reference."""
        plugin = MockPlugin()
        service = create_llm_service(plugin)
        
        assert service._plugin is plugin
