<!--
Sync Impact Report:
- Version change: 0.0.0 → 1.0.0 (initial constitution)
- Modified principles: N/A (new document)
- Added sections: Core Principles (6), Technology Constraints, Development Workflow, Governance
- Removed sections: None
- Templates status:
  - .specify/templates/plan-template.md ✅ (Constitution Check section exists, aligns with principles)
  - .specify/templates/spec-template.md ✅ (User stories & requirements structure compatible)
  - .specify/templates/tasks-template.md ✅ (Phase structure supports test-first, parallel execution)
- Follow-up TODOs: None
-->

# Indico Assistant Plugin Constitution

## Core Principles

### I. Official Indico Plugin Architecture (NON-NEGOTIABLE)

This project MUST be a properly structured Indico plugin that integrates seamlessly with the Indico ecosystem.

- Plugin class MUST subclass `IndicoPlugin` from `indico.core.plugins`
- All routes MUST use `IndicoPluginBlueprint` for URL registration
- Event hooks MUST connect via Indico's `signals` framework (e.g., `signals.plugin.cli`, `signals.event.sidemenu`)
- Configuration MUST use `SettingsForm` with `default_settings` dictionary
- Database models MUST use Indico's `db` instance from `indico.core.db`
- All tables MUST be isolated in `plugin_assistant` schema
- Entry point MUST be registered as `indico.plugins` in `pyproject.toml`

**Rationale**: Official plugin architecture ensures compatibility with Indico upgrades, proper integration with Indico's authentication/authorization, and maintainability by the Indico community.

### II. API-First Design with Optional UI

All functionality MUST be exposed via REST API endpoints before any UI implementation.

- Primary interface: JSON REST API at `/api/assistant/*`
- All API endpoints MUST require Indico authentication
- Event-scoped requests MUST validate user permissions against the event
- UI components (template hooks, widgets) are OPTIONAL enhancements
- UI MUST NOT provide functionality unavailable via API
- API responses MUST include proper error codes and messages

**Rationale**: API-first enables headless integrations, third-party clients, automation, and testing without UI dependencies.

### III. LLM Provider Abstraction (NON-NEGOTIABLE)

LLM interactions MUST use Instructor for structured outputs with swappable providers.

- All LLM calls MUST go through a unified client abstraction using Instructor
- Provider swapping MUST be configuration-driven (no code changes required)
- Supported providers: Ollama (local), HuggingFace Router (cloud), OpenAI-compatible APIs
- All LLM responses MUST be validated via Pydantic models
- Retry logic with automatic validation MUST be built into the abstraction
- Provider configuration MUST be stored in plugin settings

**Rationale**: Instructor provides type-safe structured outputs with automatic retries. Provider abstraction enables self-hosted deployments (Ollama) and cloud options (HuggingFace) without code changes.

### IV. Graceful Degradation (NON-NEGOTIABLE)

The plugin MUST NOT break Indico functionality when external services are unavailable.

- LLM service unavailable: Return clear error message, do not raise unhandled exceptions
- Database connection issues: Use Indico's transaction management, rollback cleanly
- Vector search unavailable: Fall back to basic search or inform user
- All external calls MUST have configurable timeouts
- Health check endpoint MUST report service status accurately
- Plugin MUST be disable-able without affecting Indico core

**Rationale**: Indico is critical infrastructure for event management. The assistant is an enhancement that MUST NOT compromise core functionality.

### V. Configuration Hierarchy

Settings MUST support global defaults with per-event overrides.

- Global settings: Admin-configurable via plugin settings panel
- Event settings: Event managers can override specific settings per event
- Precedence: Event settings > Global settings > Default values
- Sensitive data (API keys): Stored encrypted, never logged or exposed in API
- Configuration changes MUST NOT require plugin restart

**Rationale**: Different events may have different requirements (custom prompts, restricted tables, model preferences). Hierarchy enables flexibility while maintaining sensible defaults.

### VI. Test-First Development

Tests MUST be written before implementation with minimum 80% coverage on services.

- Unit tests: Required for all service methods (≥80% coverage)
- Integration tests: Required for API endpoints (≥60% coverage)
- Contract tests: Required for LLM response models
- Use `pytest` with `indico` fixtures (`pytest_plugins = ('indico',)`)
- Mocking: LLM calls MUST be mockable for deterministic testing
- CI MUST fail if coverage drops below thresholds

**Rationale**: High test coverage ensures reliability, enables confident refactoring, and documents expected behavior.

## Technology Constraints

| Category | Requirement | Rationale |
|----------|-------------|-----------|
| **Python** | 3.11+ | Match Indico's minimum supported version |
| **LLM Framework** | Instructor | Pydantic validation, provider abstraction, automatic retries |
| **LLM Providers** | Ollama, HuggingFace Router | Local + cloud options via `from_provider()` |
| **Database** | PostgreSQL + pgvector | Indico's database; pgvector for RAG embeddings |
| **ORM** | SQLAlchemy (Indico's `db`) | Plugin models use Indico's managed session |
| **Web Framework** | Flask (via Indico) | Blueprints, `RH` request handlers |
| **Testing** | pytest + indico fixtures | `pytest_plugins = ('indico',)` for Indico integration |
| **Linting** | ruff | Fast, comprehensive Python linting |
| **Formatting** | black | Consistent code style |
| **Type Checking** | mypy (strict mode) | Catch type errors before runtime |

## Development Workflow

### Code Quality Gates

All code MUST pass these gates before merge:

1. **Linting**: `ruff check` with zero errors
2. **Formatting**: `black --check` passes
3. **Type checking**: `mypy --strict` on all modules
4. **Tests**: All tests pass, coverage thresholds met
5. **Documentation**: Public APIs have docstrings (Google style)

### Database Changes

- All schema changes MUST use Alembic migrations
- Migrations MUST support both upgrade and downgrade
- Command: `indico db --plugin assistant migrate -m "description"`
- Test migrations against copy of production schema before deployment

### Security Requirements

- SQL injection: All database queries MUST use parameterized statements or ORM
- Generated SQL MUST be validated before execution (no DDL, only SELECT)
- Input sanitization: User inputs sanitized before inclusion in LLM prompts
- Rate limiting: API endpoints MUST be rate-limited per user
- Audit logging: All queries logged with user context (respecting privacy settings)

## Governance

This constitution supersedes all other development practices for this project.

- All PRs MUST include constitution compliance verification
- Complexity beyond these principles MUST be justified in PR description
- Amendments to this constitution require:
  1. Written proposal with rationale
  2. Review of impact on existing code
  3. Migration plan for non-compliant code
  4. Version bump following semantic versioning

**Version**: 1.0.0 | **Ratified**: 2026-01-14 | **Last Amended**: 2026-01-14
