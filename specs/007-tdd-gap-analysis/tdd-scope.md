# TDD Scope Document: Indico Assistant Plugin

**Version**: 1.0.0  
**Created**: 2026-01-16  
**Authority**: Constitution v1.0.0, Principle VI (Test-First Development)

## Purpose

This document defines the test-driven development requirements for each component type in the indico-assistant plugin. It serves as the authoritative reference for what tests are required when adding or modifying code.

---

## Coverage Thresholds

| Test Type | Target Coverage | Applies To | Enforcement |
|-----------|-----------------|------------|-------------|
| Unit Tests | ≥80% | All service modules | CI blocks merge |
| Integration Tests | ≥60% | All API endpoints | CI blocks merge |
| Contract Tests | 100% of models | LLM response models, API schemas | CI blocks merge |

---

## Test Requirements by Component Type

### 1. Services (`indico_assistant/services/`)

**Required**: Unit tests for all public methods

| Module Type | Test File Location | Minimum Tests |
|-------------|-------------------|---------------|
| `service.py` | `tests/unit/services/<module>/test_service.py` | Happy path, error handling, edge cases |
| Supporting modules | `tests/unit/services/<module>/test_<name>.py` | Each public function tested |
| Factory modules | `tests/unit/services/<module>/test_factory.py` | All creation paths |

**Test Pattern**:
```python
# tests/unit/services/<module>/test_<name>.py
import pytest
from unittest.mock import MagicMock, patch

class TestClassName:
    """Tests for ClassName."""
    
    def test_method_happy_path(self):
        """Test normal operation."""
        ...
    
    def test_method_error_handling(self):
        """Test error scenarios."""
        ...
    
    def test_method_edge_cases(self):
        """Test boundary conditions."""
        ...
```

**Fixtures**: Use `mock_llm_service` from `conftest.py` for LLM-dependent tests.

---

### 2. Controllers (`indico_assistant/controllers/`)

**Required**: Integration tests for all endpoints

| Controller | Test File Location | Required Coverage |
|------------|-------------------|-------------------|
| `chat.py` | `tests/integration/chat/test_chat_endpoint.py` | All HTTP methods |
| `sessions.py` | `tests/integration/chat/test_sessions_endpoint.py` | CRUD operations |
| `feedback.py` | `tests/integration/chat/test_feedback_endpoint.py` | Submit, retrieve |
| `health.py` | `tests/integration/test_health.py` | Health check response |
| `admin.py` | `tests/integration/test_settings.py` | Settings CRUD |
| `search.py` | `tests/integration/test_search.py` | Search operations |

**Test Pattern**:
```python
# tests/integration/<area>/test_<name>_endpoint.py
import pytest

class TestEndpointName:
    """Integration tests for /api/assistant/<endpoint>."""
    
    def test_endpoint_success(self, client, auth_headers):
        """Test successful request."""
        response = client.get('/api/assistant/...', headers=auth_headers)
        assert response.status_code == 200
    
    def test_endpoint_unauthorized(self, client):
        """Test without authentication."""
        response = client.get('/api/assistant/...')
        assert response.status_code == 401
    
    def test_endpoint_validation_error(self, client, auth_headers):
        """Test with invalid input."""
        ...
```

**Fixtures**: Use `pytest_plugins = ('indico.testing.fixtures',)` for Indico integration.

---

### 3. Models (`indico_assistant/models/`)

**Required**: Unit tests for model behavior

| Model Type | Test File Location | Required Tests |
|------------|-------------------|----------------|
| SQLAlchemy models | `tests/unit/models/test_<name>.py` | Validation, relationships |

**Test Pattern**:
```python
# tests/unit/models/test_<name>.py
import pytest

class TestModelName:
    """Tests for ModelName database model."""
    
    def test_create_valid(self, db_session):
        """Test creating valid instance."""
        ...
    
    def test_validation_error(self, db_session):
        """Test validation rules."""
        ...
    
    def test_relationships(self, db_session):
        """Test foreign key relationships."""
        ...
```

---

### 4. Schemas (`indico_assistant/schemas/`)

**Required**: Contract tests for all request/response schemas

| Schema Type | Test File Location | Required Tests |
|-------------|-------------------|----------------|
| Request schemas | `tests/contract/<area>/test_<name>_contracts.py` | Validation, required fields |
| Response schemas | `tests/contract/<area>/test_<name>_contracts.py` | Serialization, types |
| Error schemas | `tests/contract/test_error_contracts.py` | Error codes, messages |

**Test Pattern**:
```python
# tests/contract/<area>/test_<name>_contracts.py
import pytest
from pydantic import ValidationError

class TestSchemaContract:
    """Contract tests for SchemaName."""
    
    def test_valid_input(self):
        """Test schema accepts valid data."""
        schema = SchemaName(field1="value", field2=123)
        assert schema.field1 == "value"
    
    def test_required_fields(self):
        """Test required field validation."""
        with pytest.raises(ValidationError):
            SchemaName()  # Missing required fields
    
    def test_type_coercion(self):
        """Test type conversion behavior."""
        ...
    
    def test_serialization(self):
        """Test model_dump() output."""
        schema = SchemaName(...)
        data = schema.model_dump()
        assert "field1" in data
```

---

### 5. LLM Response Models (`indico_assistant/services/llm/models/`)

**Required**: Contract tests for all Pydantic models (Constitution mandated)

| Model | Test File Location | Critical Tests |
|-------|-------------------|----------------|
| `base.py` | `tests/contract/llm/test_models.py` | Base validation |
| `classification.py` | `tests/contract/llm/test_models.py` | Classification outputs |
| `sql.py` | `tests/contract/llm/test_models.py` | SQL generation outputs |
| `summary.py` | `tests/contract/llm/test_models.py` | Summary outputs |

**Test Pattern**:
```python
# tests/contract/llm/test_models.py
import pytest
from pydantic import ValidationError

class TestLLMResponseModel:
    """Contract tests for LLM response models."""
    
    def test_valid_llm_response(self):
        """Test model parses valid LLM output."""
        ...
    
    def test_malformed_response(self):
        """Test model rejects malformed output."""
        ...
    
    def test_optional_fields(self):
        """Test optional field defaults."""
        ...
    
    def test_instructor_compatibility(self):
        """Test model works with instructor extraction."""
        ...
```

---

## Priority Matrix

When writing tests for a new component, follow this priority:

| Priority | Component Type | Rationale |
|----------|---------------|-----------|
| P1 | LLM integration services | Highest variability, hardest to debug |
| P1 | Security-sensitive code (permissions, auth) | Security bugs are critical |
| P2 | Data persistence services | Data integrity is important |
| P2 | API endpoint integration | User-facing functionality |
| P3 | Pure business logic | Lower risk, easier to test |
| P3 | Observability/metrics | Ops concerns, lower user impact |

---

## Mocking Guidelines

### LLM Calls
```python
# Use the mock_llm_service fixture
def test_with_llm(mock_llm_service):
    mock_llm_service.generate.return_value = LLMResponse(
        success=True,
        data={"result": "test"},
        error=None,
        latency_ms=100,
        model="test-model",
        tokens_used=50,
    )
    # ... test code
```

### Database
```python
# Use Indico's db fixtures
def test_with_db(db_session):
    # db_session provides a clean database transaction
    ...
```

### External Services
```python
# Always mock external calls
@patch('indico_assistant.services.embedding.service.create_embedding')
def test_external_service(mock_create):
    mock_create.return_value = [0.1, 0.2, 0.3]
    ...
```

---

## Enforcement

1. **Pre-commit**: Run `pytest tests/unit/` on staged files
2. **CI Pipeline**: Full test suite with coverage report
3. **Merge Block**: Coverage below thresholds blocks PR merge
4. **Code Review**: Reviewer verifies test coverage for new code

---

## Exemptions

Components exempt from testing requirements:

| Component | Reason | Approved By |
|-----------|--------|-------------|
| `__init__.py` files | Import-only, no logic | Convention |
| `base.py` abstract classes | Tested via concrete implementations | Convention |
| Type stubs (`.pyi`) | No runtime behavior | Convention |

To request an exemption, document in PR with justification.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-16 | Initial document |
