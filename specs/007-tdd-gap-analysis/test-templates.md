# Test Templates: Indico Assistant Plugin

**Purpose**: Reusable test patterns for unit, integration, and contract tests  
**Created**: 2026-01-16

---

## Unit Test Template

### Service Unit Test

```python
"""Unit tests for <ModuleName>."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from indico_assistant.services.<module>.<name> import ClassName


class TestClassName:
    """Tests for ClassName."""

    @pytest.fixture
    def instance(self, mock_llm_service):
        """Create instance with mocked dependencies."""
        return ClassName(llm_service=mock_llm_service)

    # Happy Path Tests
    def test_method_success(self, instance):
        """Test <method> with valid input returns expected result."""
        # Arrange
        input_data = {"key": "value"}
        
        # Act
        result = instance.method(input_data)
        
        # Assert
        assert result is not None
        assert result.status == "success"

    # Error Handling Tests
    def test_method_handles_error(self, instance, mock_llm_service):
        """Test <method> handles <ErrorType> gracefully."""
        # Arrange
        mock_llm_service.generate.side_effect = RuntimeError("LLM unavailable")
        
        # Act & Assert
        with pytest.raises(ServiceError) as exc_info:
            instance.method({})
        
        assert "LLM unavailable" in str(exc_info.value)

    # Edge Case Tests
    def test_method_empty_input(self, instance):
        """Test <method> with empty input."""
        # Arrange
        input_data = {}
        
        # Act
        result = instance.method(input_data)
        
        # Assert
        assert result.data == []

    def test_method_large_input(self, instance):
        """Test <method> with large input."""
        # Arrange
        input_data = {"items": list(range(10000))}
        
        # Act
        result = instance.method(input_data)
        
        # Assert
        assert result is not None

    # Boundary Tests
    def test_method_max_length(self, instance):
        """Test <method> at maximum allowed length."""
        # Arrange
        input_data = "x" * 10000  # Max length
        
        # Act
        result = instance.method(input_data)
        
        # Assert
        assert len(result) <= 10000
```

---

### LLM-Dependent Service Test

```python
"""Unit tests for LLM-dependent service."""

import pytest
from unittest.mock import MagicMock, patch

from indico_assistant.services.llm import LLMService
from indico_assistant.services.llm.models import LLMResponse
from indico_assistant.services.<module>.<name> import ClassName


class TestClassNameWithLLM:
    """Tests for ClassName that uses LLM."""

    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM service."""
        mock = MagicMock(spec=LLMService)
        mock.generate.return_value = LLMResponse(
            success=True,
            data={"result": "test output"},
            error=None,
            latency_ms=100,
            model="test-model",
            tokens_used=50,
        )
        return mock

    @pytest.fixture
    def instance(self, mock_llm_service):
        """Create instance with mocked LLM."""
        return ClassName(llm_service=mock_llm_service)

    def test_llm_call_made(self, instance, mock_llm_service):
        """Test that LLM service is called with correct parameters."""
        # Arrange
        prompt = "Test prompt"
        
        # Act
        instance.process(prompt)
        
        # Assert
        mock_llm_service.generate.assert_called_once()
        call_args = mock_llm_service.generate.call_args
        assert prompt in str(call_args)

    def test_llm_failure_handled(self, instance, mock_llm_service):
        """Test graceful handling of LLM failure."""
        # Arrange
        mock_llm_service.generate.return_value = LLMResponse(
            success=False,
            data=None,
            error="Model timeout",
            latency_ms=30000,
            model="test-model",
            tokens_used=0,
        )
        
        # Act
        result = instance.process("test")
        
        # Assert
        assert result.success is False
        assert "timeout" in result.error.lower()

    def test_llm_retry_on_validation_error(self, instance, mock_llm_service):
        """Test retry behavior on validation failure."""
        # Arrange
        mock_llm_service.generate.side_effect = [
            LLMResponse(success=False, data=None, error="Invalid JSON", 
                       latency_ms=100, model="test", tokens_used=10),
            LLMResponse(success=True, data={"result": "valid"}, error=None,
                       latency_ms=150, model="test", tokens_used=20),
        ]
        
        # Act
        result = instance.process_with_retry("test")
        
        # Assert
        assert result.success is True
        assert mock_llm_service.generate.call_count == 2
```

---

## Integration Test Template

### API Endpoint Integration Test

```python
"""Integration tests for <endpoint> API."""

import pytest
from flask import url_for


class TestEndpointIntegration:
    """Integration tests for /api/assistant/<endpoint>."""

    @pytest.fixture
    def auth_headers(self, dummy_user):
        """Get authentication headers for test user."""
        return {"Authorization": f"Bearer {dummy_user.token}"}

    # Success Cases
    def test_endpoint_get_success(self, client, auth_headers):
        """Test GET /api/assistant/<endpoint> returns 200."""
        # Act
        response = client.get(
            "/api/assistant/<endpoint>",
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert "data" in data

    def test_endpoint_post_success(self, client, auth_headers):
        """Test POST /api/assistant/<endpoint> creates resource."""
        # Arrange
        payload = {"field": "value"}
        
        # Act
        response = client.post(
            "/api/assistant/<endpoint>",
            json=payload,
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 201
        data = response.get_json()
        assert data["id"] is not None

    # Authentication Tests
    def test_endpoint_requires_auth(self, client):
        """Test endpoint returns 401 without authentication."""
        # Act
        response = client.get("/api/assistant/<endpoint>")
        
        # Assert
        assert response.status_code == 401

    # Validation Tests
    def test_endpoint_validates_input(self, client, auth_headers):
        """Test endpoint returns 400 for invalid input."""
        # Arrange
        invalid_payload = {"invalid_field": "value"}
        
        # Act
        response = client.post(
            "/api/assistant/<endpoint>",
            json=invalid_payload,
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    # Permission Tests
    def test_endpoint_event_scoped(self, client, auth_headers, event):
        """Test endpoint respects event permissions."""
        # Arrange - user does not have access to event
        
        # Act
        response = client.get(
            f"/api/assistant/events/{event.id}/<endpoint>",
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 403
```

---

## Contract Test Template

### Pydantic Model Contract Test

```python
"""Contract tests for <ModelName>."""

import pytest
from pydantic import ValidationError

from indico_assistant.schemas.<module> import ModelName


class TestModelNameContract:
    """Contract tests for ModelName schema."""

    # Valid Input Tests
    def test_valid_minimal_input(self):
        """Test model accepts minimal valid input."""
        # Arrange
        data = {"required_field": "value"}
        
        # Act
        model = ModelName(**data)
        
        # Assert
        assert model.required_field == "value"

    def test_valid_full_input(self):
        """Test model accepts all fields."""
        # Arrange
        data = {
            "required_field": "value",
            "optional_field": "optional",
            "numeric_field": 42,
        }
        
        # Act
        model = ModelName(**data)
        
        # Assert
        assert model.required_field == "value"
        assert model.optional_field == "optional"
        assert model.numeric_field == 42

    # Required Field Tests
    def test_missing_required_field(self):
        """Test model rejects missing required field."""
        # Arrange
        data = {"optional_field": "value"}
        
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            ModelName(**data)
        
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("required_field",) for e in errors)

    # Type Validation Tests
    def test_wrong_type_rejected(self):
        """Test model rejects wrong type for field."""
        # Arrange
        data = {"required_field": "value", "numeric_field": "not a number"}
        
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            ModelName(**data)
        
        errors = exc_info.value.errors()
        assert any(e["type"] == "int_parsing" for e in errors)

    # Constraint Tests
    def test_min_length_constraint(self):
        """Test model enforces minimum length."""
        # Arrange
        data = {"required_field": ""}  # Empty string
        
        # Act & Assert
        with pytest.raises(ValidationError):
            ModelName(**data)

    def test_max_length_constraint(self):
        """Test model enforces maximum length."""
        # Arrange
        data = {"required_field": "x" * 1001}  # Too long
        
        # Act & Assert
        with pytest.raises(ValidationError):
            ModelName(**data)

    # Serialization Tests
    def test_model_dump(self):
        """Test model serializes correctly."""
        # Arrange
        model = ModelName(required_field="value")
        
        # Act
        data = model.model_dump()
        
        # Assert
        assert isinstance(data, dict)
        assert "required_field" in data
        assert data["required_field"] == "value"

    def test_model_dump_excludes_none(self):
        """Test model_dump excludes None values when configured."""
        # Arrange
        model = ModelName(required_field="value", optional_field=None)
        
        # Act
        data = model.model_dump(exclude_none=True)
        
        # Assert
        assert "optional_field" not in data

    # Default Value Tests
    def test_optional_field_default(self):
        """Test optional field uses default value."""
        # Arrange
        data = {"required_field": "value"}
        
        # Act
        model = ModelName(**data)
        
        # Assert
        assert model.optional_field is None  # or default value
```

---

### LLM Response Model Contract Test

```python
"""Contract tests for LLM response models."""

import pytest
from pydantic import ValidationError

from indico_assistant.services.llm.models import (
    ClassificationResponse,
    SQLGenerationResponse,
    SummaryResponse,
)


class TestClassificationResponseContract:
    """Contract tests for ClassificationResponse."""

    def test_valid_classification(self):
        """Test valid classification response."""
        # Arrange
        data = {
            "query_type": "data_retrieval",
            "confidence": 0.95,
            "reasoning": "Query asks for specific data",
        }
        
        # Act
        model = ClassificationResponse(**data)
        
        # Assert
        assert model.query_type == "data_retrieval"
        assert model.confidence == 0.95

    def test_confidence_range(self):
        """Test confidence must be between 0 and 1."""
        # Arrange
        data = {"query_type": "data_retrieval", "confidence": 1.5}
        
        # Act & Assert
        with pytest.raises(ValidationError):
            ClassificationResponse(**data)

    def test_valid_query_types(self):
        """Test only valid query types accepted."""
        valid_types = ["data_retrieval", "aggregation", "comparison", "unknown"]
        
        for query_type in valid_types:
            model = ClassificationResponse(
                query_type=query_type,
                confidence=0.8,
            )
            assert model.query_type == query_type


class TestSQLGenerationResponseContract:
    """Contract tests for SQLGenerationResponse."""

    def test_valid_sql_response(self):
        """Test valid SQL generation response."""
        # Arrange
        data = {
            "sql": "SELECT * FROM events WHERE id = 1",
            "explanation": "Query retrieves event by ID",
            "tables_used": ["events"],
        }
        
        # Act
        model = SQLGenerationResponse(**data)
        
        # Assert
        assert "SELECT" in model.sql
        assert model.tables_used == ["events"]

    def test_sql_required(self):
        """Test SQL field is required."""
        # Arrange
        data = {"explanation": "Some explanation"}
        
        # Act & Assert
        with pytest.raises(ValidationError):
            SQLGenerationResponse(**data)
```

---

## Fixture Patterns

### Common Fixtures

```python
# conftest.py additions

import pytest
from unittest.mock import MagicMock, create_autospec

from indico_assistant.services.llm import LLMService
from indico_assistant.services.llm.models import LLMResponse


@pytest.fixture
def mock_llm_service():
    """Mock LLM service for unit tests."""
    mock = create_autospec(LLMService, instance=True)
    mock.generate.return_value = LLMResponse(
        success=True,
        data={"result": "test"},
        error=None,
        latency_ms=100,
        model="test-model",
        tokens_used=50,
    )
    return mock


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service for vector tests."""
    mock = MagicMock()
    mock.create_embedding.return_value = [0.1] * 384  # Standard dimension
    return mock


@pytest.fixture
def sample_document():
    """Sample document for testing."""
    return {
        "id": "doc-123",
        "title": "Test Document",
        "content": "This is test content for the document.",
        "metadata": {"type": "test", "event_id": 1},
    }


@pytest.fixture
def sample_chunks():
    """Sample document chunks for testing."""
    return [
        {"id": "chunk-1", "text": "First chunk", "embedding": [0.1] * 384},
        {"id": "chunk-2", "text": "Second chunk", "embedding": [0.2] * 384},
    ]
```

---

## Running Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific service tests
pytest tests/unit/services/embedding/ -v

# Run with coverage
pytest tests/unit/ --cov=indico_assistant/services --cov-report=html

# Run contract tests
pytest tests/contract/ -v

# Run integration tests
pytest tests/integration/ -v

# Run all tests with coverage report
pytest --cov=indico_assistant --cov-report=term-missing
```
