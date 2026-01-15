# Feature Specification: Natural Language to SQL Translation Pipeline

**Feature Branch**: `003-nl2sql-pipeline`  
**Created**: 2026-01-14  
**Status**: Draft  
**Input**: User description: "Implement a natural language to SQL translation pipeline that safely converts user questions into database queries"

## Clarifications

### Session 2026-01-14

- Q: How should the system provide database schema context to the LLM? → A: Include schema for relevant tables only (detected from classification).
- Q: Should queries be scoped to a specific event or allow cross-event queries? → A: Allow queries across all events user has access to (cross-event by default).
- Q: How should the system interpret ambiguous time references like "recently" or "soon"? → A: Use sensible defaults (recently = last 7 days, soon = next 7 days, etc.).
- Q: What SQL complexity level should the system support? → A: Single-level queries with JOINs and basic aggregations (no CTEs, subqueries, or window functions).
- Q: Should the system cache query results? → A: Cache identical queries with short TTL (5-15 minutes) to balance performance and data freshness.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask Simple Event Questions (Priority: P1)

As an event manager, I need to ask questions about my events in plain English like "How many people registered for tomorrow's workshop?" and get accurate answers without knowing SQL, so I can quickly get information without technical skills.

**Why this priority**: This is the core value proposition. Without natural language query capability, users must write SQL manually or request data from IT. This single capability enables self-service data access for non-technical users.

**Independent Test**: Can be tested by submitting a natural language question and receiving a correct answer with supporting data. Delivers immediate value by answering the user's question.

**Acceptance Scenarios**:

1. **Given** an event manager with access to event data, **When** they ask "How many registrations does tomorrow's conference have?", **Then** they receive a numerical answer with the event name and registration count.
2. **Given** a user asks about events, **When** the question includes a time reference like "this week" or "next month", **Then** the system correctly interprets and applies the date range filter.
3. **Given** a user asks a question, **When** the generated SQL executes successfully, **Then** results are returned with a natural language summary explaining the findings.

---

### User Story 2 - Automatic Query Error Recovery (Priority: P2)

As a system, when a generated SQL query fails due to syntax errors or schema mismatches, I need to automatically attempt correction so that users get answers even when the initial query generation isn't perfect.

**Why this priority**: LLM-generated SQL won't always be perfect on the first attempt. Error recovery dramatically improves success rate, making the difference between a frustrating and reliable user experience.

**Independent Test**: Can be tested by intentionally generating queries with errors and verifying the system corrects them. Delivers value by increasing query success rate.

**Acceptance Scenarios**:

1. **Given** a generated SQL query with a column name error, **When** the database returns an error, **Then** the system sends the error to the LLM for correction and retries with the fixed query.
2. **Given** a query fails after correction attempt, **When** maximum retries (3) are reached, **Then** the system returns a helpful error message explaining it couldn't answer the question.
3. **Given** a query succeeds after correction, **When** results are returned, **Then** metadata indicates the query was auto-corrected for transparency.

---

### User Story 3 - Complex Multi-Entity Queries (Priority: P2)

As an event manager, I need to ask complex questions involving multiple entities like "Show me all speakers who have contributions in physics workshops this month" so I can get cross-referenced data without multiple queries.

**Why this priority**: Real-world questions often span multiple tables. This capability elevates the system from a simple lookup tool to a genuine data exploration assistant.

**Independent Test**: Can be tested by asking questions that require JOINs across multiple tables. Delivers value by answering complex analytical questions.

**Acceptance Scenarios**:

1. **Given** a question referencing multiple entities (events, registrations, contributions), **When** SQL is generated, **Then** appropriate JOINs are included based on Indico's schema relationships.
2. **Given** a question about speakers and their contributions, **When** results are returned, **Then** data from both entity types is correctly combined.
3. **Given** a question with multiple filters across tables, **When** SQL executes, **Then** all filters are correctly applied with proper table aliases.

---

### User Story 4 - Query Safety Enforcement (Priority: P1)

As a system administrator, I need assurance that user questions can only result in SELECT queries that respect data access permissions, so the system cannot accidentally or maliciously modify data or access unauthorized information.

**Why this priority**: Security is non-negotiable. The system handles production data, and any vulnerability could result in data breaches or corruption. This must be P1 alongside the core functionality.

**Independent Test**: Can be tested by attempting to inject harmful SQL and verifying it's blocked. Delivers value by protecting data integrity and user privacy.

**Acceptance Scenarios**:

1. **Given** a generated SQL query, **When** it contains DDL keywords (CREATE, DROP, ALTER), **Then** the query is rejected before execution.
2. **Given** a generated SQL query, **When** it contains DML keywords (INSERT, UPDATE, DELETE), **Then** the query is rejected before execution.
3. **Given** a query attempts to access a table not in the allowed list, **When** validation runs, **Then** the query is rejected with an appropriate error.
4. **Given** any query execution, **When** the query is about to run, **Then** result set is limited to configured maximum rows (default: 1000).

---

### User Story 5 - Audit Trail for Compliance (Priority: P3)

As a system administrator, I need all natural language queries and their resulting SQL to be logged with user identity and timestamps, so I can audit data access for compliance and security reviews.

**Why this priority**: Important for enterprise deployments but not blocking core functionality. Users can get value from the system while audit logging is added.

**Independent Test**: Can be tested by executing queries and verifying audit logs are created. Delivers value for compliance and security monitoring.

**Acceptance Scenarios**:

1. **Given** a user submits a natural language query, **When** processing begins, **Then** the query is logged with user ID, timestamp, and original question text.
2. **Given** a SQL query is generated and executed, **When** execution completes, **Then** the generated SQL, tables accessed, row count, and execution time are logged.
3. **Given** a query fails or is rejected, **When** the failure occurs, **Then** the failure reason is logged for review.

---

### Edge Cases

- What happens when the user asks a question unrelated to Indico data (e.g., "What's the weather?")? → Return "I can only answer questions about Indico event data."
- What happens when a question is ambiguous (e.g., "Show me the events")? → Generate best-effort query with reasonable defaults (e.g., upcoming events, limited to 50).
- What happens when the question references non-existent entities (e.g., "Show registrations for XYZ event" where XYZ doesn't exist)? → Execute query and return empty results with explanation.
- What happens when query execution exceeds timeout? → Cancel query and return timeout error with suggestion to narrow the question.
- What happens when user lacks permission to access queried event? → Return permission error without revealing existence of data.

## Requirements *(mandatory)*

### Functional Requirements

#### Query Classification Stage
- **FR-001**: System MUST classify user questions into intent categories: event_query, registration_query, contribution_query, attachment_query, general_info, out_of_scope.
- **FR-002**: System MUST extract named entities from questions: event names, people names, room names, category names.
- **FR-003**: System MUST parse time references (today, this week, last month, specific dates) and convert to date ranges.
- **FR-040**: System MUST interpret ambiguous relative time terms using sensible defaults: "recently" = last 7 days, "soon" = next 7 days, "a while ago" = last 30 days.
- **FR-004**: System MUST identify filter conditions mentioned in questions (e.g., "only workshops", "more than 10 registrations").
- **FR-005**: System MUST use the QueryClassification model from the LLM service layer (002-llm-service-layer).

#### SQL Generation Stage
- **FR-006**: System MUST generate PostgreSQL-compatible SELECT statements based on classification results.
- **FR-007**: System MUST use Indico's actual database schema (events.events, events.contributions, events.registrations, etc.).
- **FR-008**: System MUST include appropriate JOINs when query spans multiple tables.
- **FR-009**: System MUST apply date/time filters using Indico's timestamp conventions (UTC storage, timezone-aware columns).
- **FR-010**: System MUST use the SQLGeneration model from the LLM service layer for structured SQL output.
- **FR-011**: System MUST include schema context in LLM prompts for only tables relevant to the classified query intent (not full schema).
- **FR-041**: System MUST limit SQL generation to single-level queries with JOINs and basic aggregations (COUNT, SUM, AVG, MIN, MAX, GROUP BY); CTEs, subqueries, and window functions are not supported.

#### SQL Validation and Safety
- **FR-012**: System MUST parse generated SQL and verify it starts with SELECT.
- **FR-013**: System MUST reject any query containing DDL keywords (CREATE, DROP, ALTER, TRUNCATE).
- **FR-014**: System MUST reject any query containing DML keywords (INSERT, UPDATE, DELETE).
- **FR-015**: System MUST validate that all referenced tables are in the allowed table list.
- **FR-016**: System MUST limit result set size to configurable maximum rows (default: 1000).
- **FR-017**: System MUST apply query execution timeout (configurable, default: 30 seconds).
- **FR-018**: Reuse SQL safety validation from SQLGeneration model validators (002-llm-service-layer).

#### Error Correction Loop
- **FR-019**: System MUST catch database execution errors and send error message + original SQL to LLM for correction.
- **FR-020**: System MUST use the SQLCorrection model from LLM service layer for structured correction output.
- **FR-021**: System MUST retry corrected query up to 3 times (configurable max_correction_attempts).
- **FR-022**: System MUST track correction attempts and include in response metadata.
- **FR-023**: System MUST return structured error after exhausting correction attempts.
- **FR-042**: System SHOULD cache query results for identical SQL queries with a configurable TTL (default: 10 minutes) to improve performance for repeated questions.

#### Result Formatting
- **FR-024**: System MUST convert raw query results to structured response with column headers and typed values.
- **FR-025**: System MUST generate natural language summary of results using ResponseSummary model.
- **FR-026**: System MUST include query metadata: tables accessed, row count, execution time, correction attempts.
- **FR-027**: System MUST handle empty result sets gracefully with appropriate messaging.

#### Security and Permissions
- **FR-028**: System MUST verify user has read permission on queried event(s) before returning data.
- **FR-029**: System MUST NOT reveal existence of events user cannot access (return generic "no results" instead).
- **FR-030**: System MUST support table allowlist configuration stored in plugin settings (`nl2sql_allowed_tables`); per-event overrides via event settings with key `assistant_allowed_tables`.
- **FR-031**: System MUST NOT log sensitive query results, only metadata and query text.
- **FR-039**: System MUST allow cross-event queries, automatically filtering results to only events the user has access to.

#### Audit Logging
- **FR-032**: System MUST log all natural language queries with: user ID, timestamp, question text, event context.
- **FR-033**: System MUST log all generated SQL queries with: tables accessed, row count, execution time, success/failure.
- **FR-034**: System MUST log all query rejections with: reason code, rejected SQL pattern.
- **FR-035**: System MUST log all error corrections with: original error, correction attempt number, success/failure.

#### Integration
- **FR-036**: System MUST integrate with LLMService from 002-llm-service-layer for all LLM calls.
- **FR-037**: System MUST use Indico's database session management for query execution.
- **FR-038**: System MUST expose query functionality via internal Python API (not REST endpoint in this feature).

### Key Entities

- **NL2SQLPipeline**: Main orchestrator that coordinates classification → generation → validation → execution → formatting.
- **QueryClassifier**: Component that classifies natural language input and extracts entities using LLM.
- **SQLGenerator**: Component that generates SQL from classification results using LLM with schema context.
- **SQLValidator**: Component that validates SQL safety (SELECT-only, allowed tables, no dangerous keywords).
- **QueryExecutor**: Component that executes validated SQL against Indico database with timeout and result limiting.
- **ErrorCorrector**: Component that sends failed queries to LLM for correction and manages retry loop.
- **ResultFormatter**: Component that formats raw results and generates natural language summaries.
- **QueryAuditLog**: Record of query execution for compliance (user, timestamp, query, results metadata).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can ask simple questions (single table, basic filters) and receive correct answers within 10 seconds.
- **SC-002**: Query generation achieves 80% first-attempt success rate on common question patterns.
- **SC-003**: Error correction improves overall query success rate to 95% for well-formed questions.
- **SC-004**: 100% of generated queries pass safety validation (no DDL/DML ever reaches database).
- **SC-005**: All query executions are logged with required audit fields for compliance review.
- **SC-006**: Complex multi-table queries (2-3 JOINs) complete within 30 seconds.
- **SC-007**: System correctly rejects 100% of SQL injection attempts in user questions.

## Assumptions

- LLM service layer (002-llm-service-layer) is complete and operational.
- Indico database schema documentation is available for generating schema context prompts.
- Users have existing Indico authentication/authorization mechanisms for permission checks.
- Indico's SQLAlchemy models can be introspected to extract table/column metadata.
- PostgreSQL is the target database (Indico's default).

## Dependencies

- **002-llm-service-layer**: Provides LLMService, QueryClassification, SQLGeneration, SQLCorrection, ResponseSummary models.
- **001-plugin-foundation**: Provides plugin settings infrastructure, database session access.
- **Indico Core**: Provides database models, permission system, user context.

## Out of Scope

The following are explicitly **not** included in this feature:

- **REST API endpoint**: This feature builds internal Python API; REST exposure is a separate feature.
- **Semantic query caching**: No semantic similarity caching; only identical SQL queries are cached (see FR-042).
- **Query optimization/rewriting**: LLM generates SQL directly; no query optimizer.
- **Write operations**: Strictly read-only; no support for INSERT/UPDATE/DELETE even if requested.
- **Cross-event queries for unprivileged users**: Users can only query events they have access to.
- **Real-time streaming results**: All results returned after query completion.
- **Query history UI**: Audit logs are backend-only; no user-facing query history.
