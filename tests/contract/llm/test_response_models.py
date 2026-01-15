"""Contract tests for LLMResponse and HealthStatus models.

These tests verify that the response wrapper models enforce their
consistency rules and can be constructed correctly.
"""

import pytest
from pydantic import BaseModel

from indico_assistant.services.llm.models import LLMResponse, HealthStatus
from indico_assistant.services.llm.errors import LLMError, ErrorType


class MockResponseModel(BaseModel):
    """Mock response model for testing."""
    intent: str
    confidence: float = 0.9


class TestLLMResponseConstruction:
    """Tests for LLMResponse model construction."""
    
    def test_success_response(self):
        """Success response can be created with result."""
        result = MockResponseModel(intent="search")
        response = LLMResponse[MockResponseModel](
            success=True,
            result=result,
            latency_ms=150,
            retries=0
        )
        assert response.success is True
        assert response.result == result
        assert response.error is None
        assert response.latency_ms == 150
        assert response.retries == 0
    
    def test_error_response(self):
        """Error response can be created with error."""
        error = LLMError(
            error_type=ErrorType.TIMEOUT,
            message="Request timed out"
        )
        response = LLMResponse[MockResponseModel](
            success=False,
            error=error,
            latency_ms=30000,
            retries=2
        )
        assert response.success is False
        assert response.result is None
        assert response.error == error
        assert response.latency_ms == 30000
        assert response.retries == 2
    
    def test_success_factory_method(self):
        """success_response factory creates correct response."""
        result = MockResponseModel(intent="query")
        response = LLMResponse.success_response(
            result=result,
            latency_ms=200,
            retries=1
        )
        assert response.success is True
        assert response.result == result
        assert response.error is None
        assert response.latency_ms == 200
        assert response.retries == 1
    
    def test_error_factory_method(self):
        """error_response factory creates correct response."""
        error = LLMError(
            error_type=ErrorType.CONNECTION_ERROR,
            message="Connection failed"
        )
        response = LLMResponse.error_response(
            error=error,
            latency_ms=100,
            retries=3
        )
        assert response.success is False
        assert response.result is None
        assert response.error == error
        assert response.latency_ms == 100
        assert response.retries == 3


class TestLLMResponseConsistencyRules:
    """Tests for LLMResponse consistency invariants."""
    
    def test_success_true_requires_result(self):
        """success=True without result raises error."""
        with pytest.raises(ValueError, match="success=True requires result"):
            LLMResponse[MockResponseModel](
                success=True,
                result=None,
                latency_ms=100
            )
    
    def test_success_false_requires_error(self):
        """success=False without error raises error."""
        with pytest.raises(ValueError, match="success=False requires error"):
            LLMResponse[MockResponseModel](
                success=False,
                error=None,
                latency_ms=100
            )
    
    def test_success_true_cannot_have_error(self):
        """success=True with error raises error."""
        result = MockResponseModel(intent="test")
        error = LLMError(error_type=ErrorType.TIMEOUT, message="Error")
        with pytest.raises(ValueError, match="success=True cannot have an error"):
            LLMResponse[MockResponseModel](
                success=True,
                result=result,
                error=error,
                latency_ms=100
            )
    
    def test_success_false_cannot_have_result(self):
        """success=False with result raises error."""
        result = MockResponseModel(intent="test")
        error = LLMError(error_type=ErrorType.TIMEOUT, message="Error")
        with pytest.raises(ValueError, match="success=False cannot have a result"):
            LLMResponse[MockResponseModel](
                success=False,
                result=result,
                error=error,
                latency_ms=100
            )
    
    def test_latency_must_be_non_negative(self):
        """Negative latency is rejected."""
        result = MockResponseModel(intent="test")
        with pytest.raises(ValueError, match="greater than or equal to 0"):
            LLMResponse[MockResponseModel](
                success=True,
                result=result,
                latency_ms=-1
            )
    
    def test_retries_must_be_non_negative(self):
        """Negative retries is rejected."""
        result = MockResponseModel(intent="test")
        with pytest.raises(ValueError, match="greater than or equal to 0"):
            LLMResponse[MockResponseModel](
                success=True,
                result=result,
                latency_ms=100,
                retries=-1
            )


class TestHealthStatusConstruction:
    """Tests for HealthStatus model construction."""
    
    def test_connected_status(self):
        """Connected status with latency."""
        status = HealthStatus(
            status="connected",
            latency_ms=150,
            provider="ollama",
            model="llama3.2"
        )
        assert status.status == "connected"
        assert status.latency_ms == 150
        assert status.provider == "ollama"
        assert status.model == "llama3.2"
        assert status.error is None
    
    def test_unavailable_status(self):
        """Unavailable status with error."""
        status = HealthStatus(
            status="unavailable",
            provider="ollama",
            model="llama3.2",
            error="Connection refused"
        )
        assert status.status == "unavailable"
        assert status.latency_ms is None
        assert status.error == "Connection refused"
    
    def test_timeout_status(self):
        """Timeout status with error."""
        status = HealthStatus(
            status="timeout",
            provider="huggingface",
            model="llama-3-8b",
            error="Request timed out after 5s"
        )
        assert status.status == "timeout"
        assert status.error == "Request timed out after 5s"
    
    def test_not_configured_status(self):
        """Not configured status."""
        status = HealthStatus(
            status="not_configured",
            provider="none",
            model="none"
        )
        assert status.status == "not_configured"
        assert status.latency_ms is None
        assert status.error is None


class TestHealthStatusValidation:
    """Tests for HealthStatus validation rules."""
    
    def test_connected_requires_latency(self):
        """Connected status without latency raises error."""
        with pytest.raises(ValueError, match="connected status requires latency_ms"):
            HealthStatus(
                status="connected",
                provider="ollama",
                model="llama3.2"
            )
    
    def test_unavailable_requires_error(self):
        """Unavailable status without error raises error."""
        with pytest.raises(ValueError, match="should have an error message"):
            HealthStatus(
                status="unavailable",
                provider="ollama",
                model="llama3.2"
            )
    
    def test_timeout_requires_error(self):
        """Timeout status without error raises error."""
        with pytest.raises(ValueError, match="should have an error message"):
            HealthStatus(
                status="timeout",
                provider="ollama",
                model="llama3.2"
            )
    
    def test_latency_must_be_non_negative(self):
        """Negative latency is rejected."""
        with pytest.raises(ValueError, match="greater than or equal to 0"):
            HealthStatus(
                status="connected",
                latency_ms=-100,
                provider="ollama",
                model="llama3.2"
            )
    
    def test_invalid_status_rejected(self):
        """Invalid status string is rejected."""
        with pytest.raises(ValueError):
            HealthStatus(
                status="invalid",  # type: ignore
                provider="ollama",
                model="llama3.2"
            )


class TestHealthStatusSerialization:
    """Tests for HealthStatus serialization."""
    
    def test_to_dict(self):
        """Health status can be serialized to dict."""
        status = HealthStatus(
            status="connected",
            latency_ms=150,
            provider="ollama",
            model="llama3.2"
        )
        data = status.model_dump()
        assert data["status"] == "connected"
        assert data["latency_ms"] == 150
        assert data["provider"] == "ollama"
        assert data["model"] == "llama3.2"
        assert data["error"] is None
    
    def test_from_dict(self):
        """Health status can be deserialized from dict."""
        data = {
            "status": "unavailable",
            "provider": "huggingface",
            "model": "llama-3-8b",
            "error": "Service unavailable"
        }
        status = HealthStatus.model_validate(data)
        assert status.status == "unavailable"
        assert status.provider == "huggingface"
        assert status.model == "llama-3-8b"
        assert status.error == "Service unavailable"
