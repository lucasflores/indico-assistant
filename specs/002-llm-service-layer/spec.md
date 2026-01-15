# Feature Specification: LLM Service Abstraction Layer

**Feature Branch**: `002-llm-service-layer`  
**Created**: 2026-01-14  
**Status**: Draft  
**Input**: User description: "Build an LLM service abstraction layer using Instructor that supports multiple providers with easy swapping"

## Clarifications

### Session 2025-01-14

- Q: How should API keys be handled in logs and error messages? → A: Never log any portion; only log present/absent.
- Q: How should the LLMService instance be managed within the plugin? → A: One instance per plugin, lazy-initialized on first use.
- Q: What structured logging should the LLM service emit for observability? → A: Metadata only (model, latency, success/fail, retry count) without prompt/response content.
- Q: When configured provider is unavailable, should service attempt fallback? → A: No fallback; return error immediately and let caller decide.
- Q: Which capabilities should be explicitly out of scope? → A: All: streaming, response caching, conversation history, async/parallel calls.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Make Structured LLM Calls (Priority: P1)

As a developer extending the plugin, I need to make LLM calls that return validated, structured responses so I can reliably process LLM outputs without manual parsing or error handling.

**Why this priority**: This is the core functionality - without structured LLM calls, no other assistant features can work. Every downstream feature depends on this abstraction.

**Independent Test**: Can be tested by calling the LLM service with a test prompt and receiving a validated Pydantic model response. Delivers immediate value for any LLM-powered feature development.

**Acceptance Scenarios**:

1. **Given** the plugin is configured with a valid LLM provider, **When** a developer calls `llm_service.generate(prompt, ResponseModel)`, **Then** they receive a validated instance of ResponseModel or a structured error.
2. **Given** the LLM returns invalid data for the schema, **When** the service processes the response, **Then** it automatically retries up to max_retries times before returning a validation error.
3. **Given** the LLM call succeeds on retry, **When** the service completes, **Then** the valid response is returned and retry attempts are logged.

---

### User Story 2 - Switch LLM Providers via Configuration (Priority: P1)

As an administrator, I need to switch between LLM providers (Ollama, HuggingFace, OpenAI-compatible) by only changing plugin settings, so I can adapt to different deployment environments without code changes.

**Why this priority**: Provider flexibility is essential for adoption - different organizations have different LLM infrastructure. This must work alongside US1.

**Independent Test**: Can be tested by changing the provider setting in admin panel and verifying subsequent LLM calls use the new provider. Delivers value by enabling deployment flexibility.

**Acceptance Scenarios**:

1. **Given** the plugin is configured for Ollama, **When** I change settings to HuggingFace and save, **Then** subsequent LLM calls use the HuggingFace provider without restart.
2. **Given** any supported provider is configured, **When** the LLM service is initialized, **Then** it creates the correct Instructor-wrapped client for that provider.
3. **Given** an unsupported provider value is configured, **When** the service initializes, **Then** it logs an error and the health check reports "not_configured".

---

### User Story 3 - Check Provider Health (Priority: P2)

As an administrator, I need to verify that the configured LLM provider is accessible and responsive, so I can diagnose connectivity issues and ensure the assistant is operational.

**Why this priority**: Health checking enables monitoring and troubleshooting. Important for operations but not required for basic functionality.

**Independent Test**: Can be tested by calling the health check endpoint/CLI and receiving connectivity status and latency. Delivers value for operational monitoring.

**Acceptance Scenarios**:

1. **Given** the LLM provider is configured and accessible, **When** I check health via CLI or API, **Then** I see status "connected" with latency in milliseconds.
2. **Given** the LLM provider is unreachable, **When** I check health, **Then** I see status "unavailable" with error details.
3. **Given** the provider is slow to respond, **When** health check exceeds timeout, **Then** I see status "timeout" with the configured timeout duration.

---

### User Story 4 - Handle LLM Errors Gracefully (Priority: P2)

As a developer, I need the LLM service to handle errors (timeouts, rate limits, connection failures) gracefully with informative error responses, so my code can respond appropriately without crashing.

**Why this priority**: Robust error handling is critical for production reliability but builds on top of the core call functionality.

**Independent Test**: Can be tested by simulating error conditions (network disconnect, timeout) and verifying structured error responses are returned.

**Acceptance Scenarios**:

1. **Given** an LLM call times out, **When** the timeout duration is exceeded, **Then** a structured error is returned with error_type="timeout" and the configured timeout value.
2. **Given** the LLM provider returns a rate limit error, **When** the service detects it, **Then** a structured error is returned with error_type="rate_limit" and suggested retry_after if available.
3. **Given** a connection error occurs, **When** the service catches it, **Then** a structured error is returned with error_type="connection_error" and the underlying error message.

---

### User Story 5 - Use Pre-defined Response Models (Priority: P3)

As a developer, I need pre-defined Pydantic models for common LLM tasks (query classification, SQL generation, response summarization), so I can quickly build features without defining schemas from scratch.

**Why this priority**: Convenience models accelerate development but are not strictly required - developers could define their own models.

**Independent Test**: Can be tested by importing and using provided models in LLM calls. Delivers value by reducing boilerplate for common use cases.

**Acceptance Scenarios**:

1. **Given** I need to classify a user query, **When** I use QueryClassification model, **Then** I receive structured intent, entities, time_range, and filters.
2. **Given** I need to generate SQL, **When** I use SQLGeneration model, **Then** I receive query, explanation, and tables_used fields.
3. **Given** I need to summarize results, **When** I use ResponseSummary model, **Then** I receive answer, confidence, and sources fields.

---

### Edge Cases

- What happens when provider credentials are invalid? → Return "authentication_error" with masked credential hint.
- What happens when the model name doesn't exist on the provider? → Return "model_not_found" error with available models if possible.
- What happens when max_retries is set to 0? → Execute exactly once with no retry on validation failure.
- What happens when response exceeds max_tokens? → Provider handles truncation; no special handling in service layer.
- How does system handle concurrent LLM calls? → Each call is independent; no shared state between calls.

## Requirements *(mandatory)*

### Functional Requirements

#### LLM Client Factory
- **FR-001**: System MUST provide a factory function that creates Instructor-wrapped LLM clients based on plugin settings.
- **FR-002**: System MUST support Ollama provider via the ollama Python library.
- **FR-003**: System MUST support HuggingFace provider via OpenAI-compatible endpoint (HF Router).
- **FR-004**: System MUST support any OpenAI-compatible API endpoint via base_url configuration.
- **FR-005**: System MUST use settings from the plugin (provider, model, base_url, api_key, timeout, max_tokens).

#### Structured Response Generation
- **FR-006**: System MUST accept a Pydantic model class and return validated instances of that model.
- **FR-007**: System MUST automatically retry on validation failures up to max_retries (from plugin settings).
- **FR-008**: System MUST log each retry attempt with validation error details.
- **FR-009**: System MUST return a structured LLMError if all retries are exhausted.

#### Provider Health Checking
- **FR-010**: System MUST provide a health_check() method that tests provider connectivity.
- **FR-011**: Health check MUST return status (connected/unavailable/timeout), latency_ms, and error details if applicable.
- **FR-012**: Health check MUST respect the configured timeout_seconds setting.

#### Error Handling
- **FR-013**: System MUST catch and wrap timeout errors with error_type="timeout".
- **FR-014**: System MUST catch and wrap connection errors with error_type="connection_error".
- **FR-015**: System MUST detect rate limit responses and return error_type="rate_limit".
- **FR-016**: System MUST catch authentication errors and return error_type="authentication_error".
- **FR-017**: All errors MUST be returned as structured LLMError objects, never raised as exceptions to callers.

#### Security & Credential Handling
- **FR-025**: System MUST NOT log any portion of API keys; only log whether a key was present or absent.
- **FR-026**: Error messages returned to callers MUST mask or omit credentials entirely.

#### Observability & Logging
- **FR-029**: System MUST log call metadata: provider, model, latency_ms, success/failure status, retry count.
- **FR-030**: System MUST NOT log prompt content or LLM response content (privacy protection).
- **FR-031**: System MUST log health check results with status and latency.

#### Pre-defined Response Models
- **FR-018**: System MUST provide QueryClassification model with: intent, entities, time_range, filters fields.
- **FR-019**: System MUST provide SQLGeneration model with: query, explanation, tables_used fields.
- **FR-020**: System MUST provide SQLCorrection model with: corrected_query, error_analysis, changes_made fields.
- **FR-021**: System MUST provide ResponseSummary model with: answer, confidence, sources fields.

#### Design Constraints
- **FR-022**: LLM service MUST be injectable/mockable for testing (no module-level singletons).
- **FR-023**: All LLM interactions in the plugin MUST go through this service abstraction.
- **FR-024**: Provider switching MUST require only configuration changes, no code modifications.
- **FR-027**: LLMService MUST use a lazy-initialized singleton pattern per plugin instance.
- **FR-028**: LLMService instance MUST be replaceable for testing via dependency injection.
- **FR-032**: System MUST NOT implement automatic provider fallback; errors are returned to caller for handling.

### Key Entities

- **LLMService**: The main service class that wraps Instructor client and provides generate() and health_check() methods.
- **LLMError**: Structured error response with error_type, message, details, and optional retry_after.
- **LLMResponse**: Generic wrapper that contains either a successful result or an LLMError.
- **QueryClassification**: Pydantic model for classifying user query intent and extracting entities.
- **SQLGeneration**: Pydantic model for LLM-generated SQL with explanation.
- **SQLCorrection**: Pydantic model for correcting invalid SQL queries.
- **ResponseSummary**: Pydantic model for natural language response with confidence scoring.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can make structured LLM calls with a single method call and receive validated responses.
- **SC-002**: Provider switching requires changing only plugin settings (provider, base_url, api_key) with no code changes.
- **SC-003**: 100% of LLM errors are returned as structured LLMError objects (no unhandled exceptions leak to callers).
- **SC-004**: Health check accurately reports provider status within 5 seconds of configuration change.
- **SC-005**: Retry logic successfully recovers from transient validation failures at least 80% of the time (when LLM output is close to valid).
- **SC-006**: All pre-defined response models are importable and usable without additional configuration.

## Assumptions

- Instructor library is compatible with all target providers (Ollama, HuggingFace, OpenAI-compatible).
- Plugin settings from 001-plugin-foundation are available and provide: llm_provider, llm_model, llm_base_url, llm_api_key, timeout_seconds, max_tokens, max_retries.
- Developers using this service are familiar with Pydantic models.
- HuggingFace uses OpenAI-compatible API via their Router endpoint (not the Inference API directly).

## Dependencies

- **001-plugin-foundation**: Provides plugin settings infrastructure and health endpoint framework.
- **instructor**: Python library for structured LLM outputs (external dependency).
- **pydantic**: Data validation library (already available via Indico).
- **ollama**: Python library for Ollama provider (external dependency).
- **openai**: Python library for OpenAI-compatible APIs (external dependency).

## Out of Scope

The following capabilities are explicitly **not** included in this feature and may be addressed in future iterations:

- **Streaming responses**: Real-time token streaming; all calls are synchronous request/response.
- **Response caching**: No caching layer for LLM responses; each call hits the provider.
- **Conversation history**: No built-in conversation context management; each call is stateless.
- **Async/parallel calls**: No asyncio support; calls are blocking/synchronous.
- **Provider fallback**: No automatic failover to backup providers on error.
