# Quickstart: TDD Gap Analysis

**Time to complete**: ~30 minutes to address first gap

---

## Prerequisites

1. Python 3.11+ installed
2. Plugin development environment set up
3. pytest and pytest-cov installed

```bash
cd /path/to/indico_assistant_plugin
pip install -e ".[dev]"
```

---

## Step 1: Verify Current Coverage

```bash
# Run existing tests to establish baseline
pytest tests/ --cov=indico_assistant --cov-report=term-missing

# Generate HTML report for detailed view
pytest tests/ --cov=indico_assistant --cov-report=html
open htmlcov/index.html
```

---

## Step 2: Pick a Gap to Address

See [gap-report.md](gap-report.md) for prioritized list.

**Recommended first gap**: `GAP-001: embedding/service.py` (Critical priority)

---

## Step 3: Create Test File

```bash
# Create test directory structure
mkdir -p tests/unit/services/embedding
touch tests/unit/services/embedding/__init__.py
touch tests/unit/services/embedding/test_service.py
```

---

## Step 4: Write Tests

Copy the template from [test-templates.md](test-templates.md):

```python
# tests/unit/services/embedding/test_service.py
"""Unit tests for EmbeddingService."""

import pytest
from unittest.mock import MagicMock, patch

from indico_assistant.services.embedding.service import EmbeddingService


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    @pytest.fixture
    def mock_llm_service(self):
        """Mock LLM service."""
        mock = MagicMock()
        mock.create_embedding.return_value = [0.1] * 384
        return mock

    @pytest.fixture
    def service(self, mock_llm_service):
        """Create service instance."""
        return EmbeddingService(llm_service=mock_llm_service)

    def test_create_embedding_success(self, service):
        """Test creating embedding for valid text."""
        # Arrange
        text = "Test document content"
        
        # Act
        result = service.create_embedding(text)
        
        # Assert
        assert result is not None
        assert len(result) == 384  # Expected dimension

    def test_create_embedding_empty_text(self, service):
        """Test handling empty text input."""
        # Arrange
        text = ""
        
        # Act & Assert
        with pytest.raises(ValueError):
            service.create_embedding(text)
```

---

## Step 5: Run Tests

```bash
# Run only your new tests
pytest tests/unit/services/embedding/test_service.py -v

# Check coverage of the specific module
pytest tests/unit/services/embedding/ \
    --cov=indico_assistant/services/embedding \
    --cov-report=term-missing
```

---

## Step 6: Iterate Until Coverage Met

1. Add tests for untested methods
2. Run coverage report
3. Repeat until ≥80% coverage on the module

---

## Step 7: Mark Gap Complete

Update [gap-report.md](gap-report.md):
- [x] GAP-001: embedding/service.py

---

## Quick Reference

| Task | Command |
|------|---------|
| Run all tests | `pytest tests/` |
| Run unit tests only | `pytest tests/unit/` |
| Run with coverage | `pytest --cov=indico_assistant` |
| Run specific test file | `pytest tests/unit/services/embedding/test_service.py` |
| Run specific test | `pytest tests/unit/services/embedding/test_service.py::TestEmbeddingService::test_create_embedding_success` |
| Coverage HTML report | `pytest --cov-report=html` |

---

## Common Issues

### Import Errors
Ensure the package is installed in development mode:
```bash
pip install -e .
```

### Fixture Not Found
Check that `conftest.py` is in the correct location and fixtures are properly scoped.

### Mocking LLM Calls
Use the `mock_llm_service` fixture from `tests/conftest.py`:
```python
def test_with_llm(mock_llm_service):
    mock_llm_service.generate.return_value = ...
```

---

## Next Steps

After completing your first gap:
1. Commit the new test file
2. Move to the next gap in [gap-report.md](gap-report.md)
3. Repeat the process

Target: Complete all Critical (6) and High (7) priority gaps.
