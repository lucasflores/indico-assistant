# Implementation Plan: Plugin Foundation

**Branch**: `001-plugin-foundation` | **Date**: 2025-01-14 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/001-plugin-foundation/spec.md`

## Summary

Create the foundational infrastructure for the Indico Assistant plugin, including the plugin class (subclassing `IndicoPlugin`), global settings form, per-event settings, health check API endpoint, and CLI commands. The plugin must load gracefully even when LLM services are unavailable and support runtime configuration changes.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: Indico 3.3+, Flask (via Indico), WTForms (via Indico), SQLAlchemy (via Indico)  
**Storage**: PostgreSQL (Indico's database), plugin settings stored via Indico's built-in mechanism  
**Testing**: pytest with `indico` fixtures (`pytest_plugins = ('indico',)`)  
**Target Platform**: Linux server (same as Indico deployment)  
**Project Type**: Indico plugin (single package)  
**Performance Goals**: Health endpoint < 500ms, settings save < 1s  
**Constraints**: Must not break Indico if LLM unavailable, no custom encryption  
**Scale/Scope**: Single plugin, ~10 source files, supports any Indico installation

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Official Indico Plugin Architecture** | ✅ PASS | Plugin subclasses `IndicoPlugin`, uses `IndicoPluginBlueprint`, registers via `indico.plugins` entry point |
| **II. API-First Design** | ✅ PASS | Health endpoint is REST API at `/api/assistant/health`; no UI in this feature |
| **III. LLM Provider Abstraction** | ⏸️ N/A | No LLM calls in this foundation feature (settings only) |
| **IV. Graceful Degradation** | ✅ PASS | FR-002 requires plugin loads even when LLM unavailable |
| **V. Configuration Hierarchy** | ✅ PASS | Global settings + per-event overrides via `event_settings` |
| **VI. Test-First Development** | ✅ PASS | Testing with pytest + indico fixtures specified |

**Gate Result**: ✅ PASS - Proceed to Phase 0

## Project Structure

### Documentation (this feature)

```text
specs/001-plugin-foundation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI spec)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
indico_assistant/
├── __init__.py              # Package init, exports plugin class
├── plugin.py                # AssistantPlugin class (IndicoPlugin subclass)
├── blueprint.py             # IndicoPluginBlueprint, route registration
├── controllers.py           # RH request handlers (RHHealth, etc.)
├── forms.py                 # SettingsForm, EventSettingsForm
├── cli.py                   # CLI commands (health, config)
├── default_settings.py      # Default configuration values
└── version.py               # Version check utility

tests/
├── conftest.py              # pytest fixtures, indico plugin registration
├── unit/
│   ├── test_plugin.py       # Plugin initialization tests
│   ├── test_forms.py        # Settings validation tests
│   └── test_version.py      # Version check tests
├── integration/
│   ├── test_health.py       # Health endpoint integration tests
│   └── test_settings.py     # Settings persistence tests
└── contract/
    └── test_api_health.py   # API contract tests

pyproject.toml               # Package config with indico.plugins entry point
```

**Structure Decision**: Standard Indico plugin structure with flat module layout. No deep nesting since this is a focused foundation feature. Tests organized by type (unit/integration/contract) per constitution.

## Complexity Tracking

> No violations - all requirements align with constitution principles.
