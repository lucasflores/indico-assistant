# Feature Specification: Langfuse Observability

**Feature Branch**: `005-langfuse-observability`  
**Created**: 2026-01-15  
**Status**: Ready for Tasks  
**Input**: User description: "Implement observability features using Langfuse for LLM tracing, performance monitoring, and usage analytics"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - LLM Call Tracing (Priority: P1)

As an administrator, I want all LLM calls to be automatically traced so that I can monitor model performance, debug failures, and understand response latencies without modifying application code.

**Why this priority**: This is the core observability capability. Without tracing LLM calls, administrators have no visibility into the most expensive and variable component of the system. This enables debugging production issues and understanding costs.

**Independent Test**: Can be fully tested by making a chat request and verifying the trace appears in Langfuse dashboard with input/output/latency captured.

**Acceptance Scenarios**:

1. **Given** Langfuse is configured and enabled, **When** a user sends a chat message, **Then** a trace is created in Langfuse capturing the prompt, response, model, latency, and token counts.
2. **Given** Langfuse is configured but unreachable, **When** a user sends a chat message, **Then** the request completes normally and a warning is logged (graceful degradation).
3. **Given** Langfuse is disabled in settings, **When** a user sends a chat message, **Then** no tracing occurs and no performance penalty is incurred.
4. **Given** privacy level is "metadata", **When** a trace is created, **Then** only timing, success/failure, and model info are captured—no prompt or response content.

---

### User Story 2 - Pipeline Span Tracking (Priority: P2)

As an administrator, I want to see detailed timing breakdowns for each stage of the NL2SQL pipeline so that I can identify bottlenecks and optimize performance.

**Why this priority**: Understanding where time is spent in the multi-stage pipeline is critical for optimization. This builds on basic tracing to provide granular insights into query_classification, sql_generation, sql_execution, and response_summarization stages.

**Independent Test**: Can be tested by making a complex query and verifying span hierarchy in Langfuse shows nested spans for each pipeline stage with individual durations.

**Acceptance Scenarios**:

1. **Given** a user submits a query, **When** it goes through the NL2SQL pipeline, **Then** separate spans are created for query_classification, sql_generation, sql_execution, and response_summarization.
2. **Given** SQL execution fails and triggers a retry, **When** the correction occurs, **Then** an additional sql_correction span is created showing the retry attempt.
3. **Given** any pipeline stage fails, **When** viewing the trace, **Then** the failing span shows error status with exception details.
4. **Given** spans are nested under a parent trace, **When** viewing in Langfuse, **Then** the span hierarchy correctly shows parent-child relationships.

---

### User Story 3 - Admin Statistics Dashboard (Priority: P3)

As an administrator, I want API endpoints that provide aggregated usage statistics so that I can monitor system health and understand usage patterns without directly accessing Langfuse.

**Why this priority**: Provides quick access to key metrics without requiring Langfuse dashboard access. Useful for building custom dashboards or alerting systems. Depends on tracing data being collected first.

**Independent Test**: Can be tested by calling GET /api/assistant/admin/stats endpoint and verifying JSON response contains query counts, latency averages, and error rates.

**Acceptance Scenarios**:

1. **Given** I am an admin user, **When** I call GET /api/assistant/admin/stats, **Then** I receive aggregated metrics including total queries, average latency, and error rate.
2. **Given** I am a non-admin user, **When** I call GET /api/assistant/admin/stats, **Then** I receive a 403 Forbidden response.
3. **Given** I am an admin user, **When** I call GET /api/assistant/admin/errors, **Then** I receive a list of recent errors with timestamps, error types, and correlation IDs.
4. **Given** the system has been running for a week, **When** I request stats with period=week, **Then** metrics are aggregated for the past 7 days.

---

### User Story 4 - Privacy-Aware Tracing (Priority: P4)

As an administrator, I want to configure what data is captured in traces so that I can balance debugging needs with user privacy requirements.

**Why this priority**: Privacy compliance is important but not blocking for initial deployment. Administrators can start with "metadata" level and adjust as needed based on organizational policies.

**Independent Test**: Can be tested by configuring each privacy level and verifying trace content matches expectations in Langfuse.

**Acceptance Scenarios**:

1. **Given** privacy level is "full", **When** a trace is created, **Then** complete prompt and response content is captured.
2. **Given** privacy level is "masked", **When** a trace is created, **Then** PII (emails, names) in prompts/responses is replaced with placeholders like [EMAIL], [NAME].
3. **Given** privacy level is "metadata", **When** a trace is created, **Then** no prompt or response content is captured, only timing and status.
4. **Given** privacy level is changed at runtime, **When** new requests are made, **Then** new traces use the updated privacy level.

---

### Edge Cases

- What happens when Langfuse credentials are invalid? System logs error at startup, continues without tracing, and surfaces configuration error in admin stats.
- What happens when Langfuse rate limits are hit? Traces are dropped silently, warning logged, user requests unaffected.
- How does system handle very large prompts/responses? Content is truncated to configurable max length before sending to Langfuse.
- What happens if tracing async task queue backs up? Queue has bounded size; oldest items dropped with warning logged.
- How are traces correlated across multiple LLM calls in a single request? All spans share a parent trace ID linked to the user's session/request.

## Requirements *(mandatory)*

### Functional Requirements

**Configuration & Initialization**
- **FR-001**: System MUST provide plugin settings for Langfuse configuration (enabled, public_key, secret_key, host).
- **FR-002**: System MUST validate Langfuse credentials on plugin startup and log clear error if invalid.
- **FR-003**: System MUST gracefully degrade when Langfuse is unavailable (log warning, continue without tracing).
- **FR-004**: System MUST support runtime configuration changes for privacy level without restart.

**Tracing & Spans**
- **FR-005**: System MUST automatically trace all LLM service method calls without requiring code changes to callers.
- **FR-006**: System MUST capture for each LLM trace: input prompt, output response, model identifier, latency (ms), input/output token counts.
- **FR-007**: System MUST create separate spans for pipeline stages: query_classification, sql_generation, sql_execution, sql_correction (if retry), response_summarization.
- **FR-008**: System MUST link all traces/spans to user session ID for correlation (without capturing PII at metadata level).
- **FR-009**: System MUST include correlation IDs in all traces to enable request flow tracking.

**Privacy Controls**
- **FR-010**: System MUST support three privacy levels: "metadata" (timing only), "masked" (PII redacted), "full" (complete content).
- **FR-011**: System MUST redact standard PII patterns when privacy level is "masked": email addresses (regex `\b[\w.-]+@[\w.-]+\.\w+\b`) and @username mentions (regex `@\w+`). Note: Common name pattern detection deferred to future enhancement.
- **FR-012**: System MUST NOT capture prompt/response content when privacy level is "metadata".

**Admin API**
- **FR-013**: System MUST provide GET /api/assistant/admin/stats endpoint returning usage statistics.
- **FR-014**: System MUST provide GET /api/assistant/admin/errors endpoint returning recent errors.
- **FR-015**: System MUST require admin permission for all /admin/* endpoints.
- **FR-016**: System MUST support time period filtering for stats (day, week, month).

**Performance & Reliability**
- **FR-017**: System MUST perform tracing asynchronously to minimize impact on user-facing latency.
- **FR-018**: System MUST bound async tracing queue size to prevent memory exhaustion.
- **FR-019**: System MUST NOT fail user requests due to tracing failures.

**Logging**
- **FR-020**: System MUST use structured logging format for all observability events.
- **FR-021**: System MUST support configurable log levels (DEBUG, INFO, WARNING, ERROR).

**Local Metrics Storage**
- **FR-022**: System MUST store aggregated usage statistics locally in PostgreSQL for offline availability.
- **FR-023**: System MUST periodically sync metrics from Langfuse to local storage (configurable interval, default: hourly).
- **FR-024**: System MUST serve admin stats from local storage to ensure availability when Langfuse is unreachable.

### Key Entities

- **Trace**: Represents a complete user interaction; contains session_id, correlation_id, timestamp, duration, status, user_id (hashed at metadata level).
- **Span**: Represents a pipeline stage within a trace; contains trace_id, span_name, start_time, end_time, status, error_details, parent_span_id.
- **LLMMetrics**: Captured data for LLM calls; contains model, input_tokens, output_tokens, latency_ms, prompt_hash (at metadata level), response_hash (at metadata level).
- **UsageStats**: Aggregated statistics stored locally in PostgreSQL; contains period, total_queries, avg_latency_ms, error_count, error_rate, queries_by_intent, last_synced_at.
- **ErrorRecord**: Recent error for debugging stored locally in PostgreSQL; contains timestamp, correlation_id, error_type, error_message, stack_trace (at full level).
- **MetricsSyncLog**: Tracks sync status with Langfuse; contains sync_id, started_at, completed_at, records_synced, status, error_message.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All LLM calls are traced with less than 5ms added latency to user-facing requests.
- **SC-002**: Administrators can identify the slowest pipeline stage for any request within 30 seconds using Langfuse dashboard.
- **SC-003**: 100% of user requests complete successfully even when Langfuse is unavailable.
- **SC-004**: Admin stats endpoint returns response within 500ms for up to 30 days of data.
- **SC-005**: Privacy level "metadata" captures zero prompt/response content (verifiable by audit).
- **SC-006**: Administrators can filter errors by type and time range to debug issues within 1 minute.

## Assumptions

- Langfuse Python SDK is available and compatible with the project's Python version (3.11+).
- Langfuse SDK's built-in async batching is sufficient for non-blocking trace submission (no external queue like Redis required).
- Admin users are identified via Indico's existing permission system.
- The NL2SQL pipeline from Feature 003 exposes hookable entry/exit points for span instrumentation.
- Reasonable defaults: privacy_level="metadata", max_content_length=10000 chars, async_queue_size=1000.

## Out of Scope

- Real-time alerting based on metrics (can be built on top of admin API later).
- Custom Langfuse dashboard creation (administrators use Langfuse's native UI).
- Cost tracking/billing based on token usage (future enhancement).
- Historical data migration from existing logs to Langfuse.

## Clarifications

### Session 2026-01-15

- Q: Where should aggregated statistics for admin dashboard be persisted? → A: Store aggregated metrics locally in PostgreSQL with periodic sync from Langfuse (works offline, more resilient).
- Q: What PII patterns should be detected for "masked" privacy level? → A: Standard patterns only: email regex (`\b[\w.-]+@[\w.-]+\.\w+\b`) and @username mentions (`@\w+`). Common name patterns deferred to future enhancement due to complexity and false-positive risk.
