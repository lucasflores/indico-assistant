# Contract: Development Section

## Section Requirements

**Location**: After CLI Commands section  
**Purpose**: Enable contributors to set up development environment and run tests  
**Format**: Three subsections with command examples

## Content Structure

### Main Header
```markdown
## Development
```

---

### Subsection 1: Setup

```markdown
### Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev]"
```

**Development dependencies include**: pytest, pytest-cov, ruff, black, mypy
```

**Verification**: Commands match actual requirements in `pyproject.toml` [project.optional-dependencies.dev]

---

### Subsection 2: Testing

```markdown
### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=indico_assistant --cov-report=html

# Run specific test types
pytest tests/unit/
pytest tests/integration/
pytest tests/contract/

# Run with specific markers
pytest -m contract  # Contract tests only
pytest -m integration  # Integration tests only
```

**Test organization**:
- `tests/unit/`: Fast, isolated unit tests
- `tests/integration/`: Tests requiring database/external services
- `tests/contract/`: LLM response model validation tests
- `tests/e2e/`: End-to-end tests (if applicable)

**Coverage goals**: ≥80% on services, ≥60% on controllers
```

**Verification**: 
- Commands match pytest configuration in `pyproject.toml` [tool.pytest.ini_options]
- Test organization matches actual `tests/` directory structure
- Coverage goals match constitution requirements

---

### Subsection 3: Code Quality

```markdown
### Code Quality

```bash
# Linting
ruff check .

# Formatting
black .

# Type checking
mypy indico_assistant
```

**Pre-commit checklist**:
- [ ] All tests pass
- [ ] Ruff reports no errors
- [ ] Black formatting applied
- [ ] Mypy passes (if strict mode enabled)
- [ ] Coverage thresholds met
```

**Verification**:
- Tools match those listed in `pyproject.toml` dev dependencies
- Configuration sections exist ([tool.ruff], [tool.black], [tool.mypy])

---

## Additional Subsection (Optional): Database Migrations

```markdown
### Database Migrations

If you modify database models, create a migration:

```bash
# Create migration
indico db --plugin assistant migrate -m "Description of change"

# Apply migration
indico db --plugin assistant upgrade

# Rollback migration  
indico db --plugin assistant downgrade
```

**Migration files**: Located in `indico_assistant/migrations/versions/`
```

**Include only if**: Plugin uses Alembic migrations

---

## Content Requirements

1. **Commands MUST be copy-pasteable**: Test each command
2. **Virtual environment activation**: Include both Unix and Windows commands
3. **Development dependencies**: List key tools installed
4. **Test organization**: Explain directory structure
5. **Coverage goals**: State numeric thresholds from constitution
6. **Tool configuration**: Reference pyproject.toml sections

## Verification Checklist

- [ ] All commands tested in actual environment
- [ ] Development dependencies match `pyproject.toml` [dev]
- [ ] Test directory structure matches actual layout
- [ ] pytest markers match `pyproject.toml` configuration
- [ ] Coverage thresholds match constitution (80%/60%)
- [ ] Tool commands (ruff, black, mypy) work as documented
- [ ] Migration commands accurate (if included)

## Success Criteria

- New contributor can set up environment in <10 minutes
- All commands work without modification
- Test execution and code quality checks are clear
- Coverage requirements are explicit
