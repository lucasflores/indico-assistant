# Feature Specification: Plugin Foundation

**Feature Branch**: `001-plugin-foundation`  
**Created**: 2026-01-14  
**Status**: Draft  
**Input**: Create the foundation for an official Indico plugin called "indico-assistant" that provides AI-powered assistance capabilities.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install and Enable Plugin (Priority: P1)

As an Indico administrator, I want to install the assistant plugin and enable it so that the AI assistant capabilities become available to my Indico instance.

**Why this priority**: This is the foundational capability - nothing else works without the plugin being installable and loadable. It's the absolute minimum viable product.

**Independent Test**: Can be fully tested by installing the plugin via pip and verifying Indico starts without errors. Delivers value by confirming the plugin integrates correctly with Indico.

**Acceptance Scenarios**:

1. **Given** the plugin package is installed via pip, **When** Indico starts, **Then** the plugin appears in the admin plugins list without errors
2. **Given** the plugin is installed, **When** the LLM service is unavailable, **Then** Indico still starts successfully and the plugin shows as "degraded" status
3. **Given** the plugin is listed in admin panel, **When** admin enables the plugin, **Then** the plugin status changes to "enabled" without requiring Indico restart

---

### User Story 2 - Configure Global Settings (Priority: P1)

As an Indico administrator, I want to configure the LLM provider settings (provider type, model, API endpoint, credentials) so that the plugin knows how to connect to the AI service.

**Why this priority**: Without configuration, the plugin cannot function. This is required before any AI features can work.

**Independent Test**: Can be fully tested by accessing the plugin settings form, entering configuration values, saving, and verifying they persist across page reloads.

**Acceptance Scenarios**:

1. **Given** the plugin is enabled, **When** admin navigates to plugin settings, **Then** a settings form is displayed with all configurable options
2. **Given** the settings form is displayed, **When** admin selects "ollama" as LLM provider and enters base URL, **Then** the settings are saved successfully
3. **Given** the settings form is displayed, **When** admin enters an API key for HuggingFace provider, **Then** the key is stored securely (encrypted) and not displayed in plain text
4. **Given** settings have been saved, **When** admin changes the LLM model setting, **Then** the new setting takes effect immediately without Indico restart

---

### User Story 3 - Check Service Health (Priority: P2)

As an Indico administrator, I want to check the health status of the assistant plugin so that I can verify the LLM service is reachable and diagnose connection issues.

**Why this priority**: Health checking is essential for operations but the plugin can technically function (in degraded mode) without it. Important for production readiness.

**Independent Test**: Can be fully tested by calling the health endpoint and verifying it returns accurate status for each dependency (LLM service, database).

**Acceptance Scenarios**:

1. **Given** the plugin is enabled and configured, **When** I call GET /api/assistant/health, **Then** I receive a JSON response with `status`, `llm_status`, `plugin_version`, and `settings_valid` fields
2. **Given** the LLM service is running, **When** health check runs, **Then** the response shows `"llm_status": "connected"`
3. **Given** the LLM service is unreachable, **When** health check runs, **Then** the response shows `"llm_status": "unavailable"` and `"status": "degraded"`
4. **Given** the LLM is not configured, **When** health check runs, **Then** the response shows `"llm_status": "not_configured"`

---

### User Story 4 - Configure Per-Event Settings (Priority: P2)

As an event manager, I want to customize assistant settings for my specific event so that I can add event-specific context and restrict which data the assistant can access.

**Why this priority**: Per-event customization adds significant value but is not required for basic operation. Global settings alone provide a working system.

**Independent Test**: Can be fully tested by accessing event management, finding assistant settings, configuring overrides, and verifying they apply only to that event.

**Acceptance Scenarios**:

1. **Given** the plugin is enabled globally, **When** event manager opens event settings, **Then** an "Assistant" settings section is available
2. **Given** event assistant settings are displayed, **When** manager disables assistant for this event, **Then** assistant features are unavailable for this event only
3. **Given** event assistant settings are displayed, **When** manager adds a custom system prompt, **Then** that prompt is included in AI interactions for this event
4. **Given** event assistant settings are displayed, **When** manager restricts allowed tables, **Then** queries for this event can only access those tables

---

### User Story 5 - Run Admin CLI Commands (Priority: P3)

As an Indico administrator, I want to run assistant-related commands from the command line so that I can perform maintenance tasks and diagnostics without using the web UI.

**Why this priority**: CLI commands are useful for automation and scripting but web UI covers most admin needs. This is a convenience enhancement.

**Independent Test**: Can be fully tested by running CLI commands in terminal and verifying expected output/behavior.

**Acceptance Scenarios**:

1. **Given** the plugin is installed, **When** I run `indico assistant --help`, **Then** I see available assistant commands listed
2. **Given** the plugin is configured, **When** I run `indico assistant health`, **Then** I see the same health status as the API endpoint
3. **Given** the plugin is enabled, **When** I run `indico assistant config show`, **Then** I see current configuration (with secrets masked)

---

### Edge Cases

- What happens when admin saves invalid LLM base URL format? → Validation error shown, settings not saved
- What happens when API key is empty for a provider that requires it? → Warning shown but settings saved (may fail at runtime)
- What happens when two admins edit settings simultaneously? → Last save wins, no conflict detection needed for MVP
- What happens when event settings conflict with global settings? → Event settings always take precedence
- What happens when plugin is disabled while requests are in flight? → Pending requests complete, new requests rejected

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Plugin MUST subclass IndicoPlugin and register via indico.plugins entry point
- **FR-002**: Plugin MUST load successfully even when LLM service is unreachable
- **FR-003**: Plugin MUST provide a SettingsForm for global configuration accessible to Indico admins
- **FR-004**: Plugin MUST store API keys securely via Indico's built-in settings storage, never exposing them in logs or API responses
- **FR-005**: Plugin MUST register a blueprint at /api/assistant/ for REST API endpoints
- **FR-006**: Plugin MUST provide GET /api/assistant/health endpoint returning JSON status
- **FR-007**: Health endpoint MUST report status of: plugin version, Indico version, LLM service connectivity (as `llm_status`), and settings validity
- **FR-008**: Plugin MUST allow per-event settings that override global defaults
- **FR-009**: Per-event settings MUST include: enabled toggle, custom system prompt, allowed tables list
- **FR-010**: Settings changes MUST take effect immediately without Indico restart
- **FR-011**: Plugin MUST register CLI commands via signals.plugin.cli
- **FR-012**: CLI MUST provide at minimum: health check command, config display command
- **FR-013**: Plugin MUST use Indico's authentication for all API endpoints except health check
- **FR-014**: Health endpoint (`/api/assistant/health`) MUST be publicly accessible without authentication for monitoring tools
- **FR-015**: Plugin settings form MUST validate inputs (URL format, required fields)
- **FR-016**: Plugin MUST check Indico version on load and fail with clear error message if version < 3.3
- **FR-017**: Per-event settings MUST use Indico's standard `event_settings` plugin property

### Key Entities

- **PluginSettings**: Global configuration for the assistant (provider, model, credentials, timeouts)
- **EventSettings**: Per-event overrides (enabled, custom_prompt, allowed_tables)
- **HealthStatus**: Runtime status of plugin dependencies (not persisted, computed on request)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Plugin installs via pip and Indico starts in under 30 seconds with plugin enabled
- **SC-002**: Admin can configure all settings and save in under 2 minutes on first use
- **SC-003**: Health check endpoint responds in under 500ms when all services are healthy
- **SC-004**: Health check endpoint responds in under 5 seconds when LLM service is unreachable (timeout)
- **SC-005**: Settings changes reflect immediately - verified by making change and seeing effect within 1 second
- **SC-006**: Plugin disabled/enabled state change takes effect without any Indico restart or reload
- **SC-007**: Event managers can find and configure event-specific settings within 3 clicks from event management page

## Assumptions

- Indico version 3.3+ is the target platform (minimum supported version)
- PostgreSQL is the database backend (as required by Indico)
- Administrators have basic familiarity with Indico's plugin system
- At least one LLM provider (Ollama, HuggingFace, or OpenAI-compatible) will be available
- Plugin will be distributed via PyPI or private package index
- API key encryption will use Indico's built-in secure settings storage mechanisms (no custom encryption)

## Clarifications

### Session 2026-01-14

- Q: How should API keys be encrypted/stored securely? → A: Use Indico's built-in secure settings storage (if available)
- Q: How should per-event settings be stored? → A: Use Indico's standard `event_settings` plugin property (JSON in database, keyed by event ID)
- Q: How to handle Indico version compatibility? → A: Target Indico 3.3+ only; fail fast with clear error if older version detected
