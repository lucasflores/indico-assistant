# Feature Specification: Chat REST API

**Feature Branch**: `004-chat-api`  
**Created**: 2026-01-14  
**Status**: Draft  
**Input**: User description: "Build the REST API endpoints for conversational chat with session persistence and feedback collection"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Send a Chat Message and Get Response (Priority: P1)

A user sends a natural language question through the chat endpoint and receives an AI-generated response based on Indico data.

**Why this priority**: This is the core functionality - without chat capability, no other features matter. Every user interaction starts here.

**Independent Test**: Can be fully tested by sending a POST request to `/api/assistant/chat` with a message and verifying a response is returned with answer text and metadata.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they POST a message to `/api/assistant/chat` without a session_id, **Then** a new session is created and the response includes session_id, message_id, and response text
2. **Given** an authenticated user with an existing session, **When** they POST a follow-up message with the session_id, **Then** the response uses conversation context from previous messages
3. **Given** an authenticated user, **When** they POST a message with an event_id they have access to, **Then** the response is scoped to that event's data
4. **Given** an authenticated user, **When** they POST a message with an event_id they do NOT have access to, **Then** they receive a 403 Forbidden error

---

### User Story 2 - View Chat Session History (Priority: P2)

A user can view their previous chat sessions and the messages within them to continue conversations or reference past answers.

**Why this priority**: Users need to access previous conversations to build on prior work and avoid repeating questions. Essential for productivity but chat must work first.

**Independent Test**: Can be tested by calling GET `/api/assistant/sessions` to list sessions, then GET `/api/assistant/sessions/{id}` to view message history.

**Acceptance Scenarios**:

1. **Given** an authenticated user with multiple sessions, **When** they GET `/api/assistant/sessions`, **Then** they receive a paginated list of their sessions with metadata (created_at, last_message_at, message_count)
2. **Given** an authenticated user, **When** they GET `/api/assistant/sessions/{id}` for their own session, **Then** they receive all messages in chronological order with role, content, and timestamp
3. **Given** an authenticated user, **When** they GET `/api/assistant/sessions/{id}` for another user's session, **Then** they receive a 403 Forbidden error
4. **Given** an authenticated user, **When** they GET `/api/assistant/sessions` with event_id filter, **Then** only sessions for that event are returned

---

### User Story 3 - Provide Feedback on Responses (Priority: P3)

A user can provide feedback (thumbs up/down, rating, comments) on assistant responses to help improve the system.

**Why this priority**: Feedback is crucial for system improvement but is not required for basic functionality. Users can chat effectively without feedback capability.

**Independent Test**: Can be tested by sending POST `/api/assistant/feedback` with a message_id and feedback data, then verifying the feedback is stored.

**Acceptance Scenarios**:

1. **Given** an authenticated user who received a response, **When** they POST feedback with thumbs_up for that message_id, **Then** the feedback is stored and linked to the message
2. **Given** an authenticated user, **When** they POST a rating (1-5) for a message, **Then** the rating is stored with the correct value
3. **Given** an authenticated user, **When** they POST a comment for a message, **Then** the text comment is stored
4. **Given** an authenticated user, **When** they POST feedback for a message they didn't receive (another user's session), **Then** they receive a 403 Forbidden error

---

### Edge Cases

- What happens when a user sends an empty message? → Return 400 Bad Request with validation error
- What happens when session_id is invalid UUID format? → Return 400 Bad Request with validation error
- What happens when session_id doesn't exist? → Return 404 Not Found
- How does system handle very long messages? → Enforce max message length (10,000 characters), return 400 if exceeded
- What happens when the NL2SQL pipeline fails? → Return error response with user-friendly message, log details internally
- What happens when user has no sessions? → Return empty list (not error)
- How does system handle rate limiting exceeded? → Return 429 Too Many Requests with Retry-After header
- What happens when feedback is submitted twice for same message? → Update existing feedback (last write wins)

## Requirements *(mandatory)*

### Functional Requirements

#### Chat Endpoint
- **FR-001**: System MUST accept POST requests at `/api/assistant/chat` with JSON body containing `message` (required string)
- **FR-002**: System MUST accept optional `session_id` (UUID) to continue existing conversation
- **FR-003**: System MUST accept optional `event_id` (integer) to scope queries to a specific event
- **FR-004**: System MUST create a new session when no valid session_id is provided
- **FR-005**: System MUST return JSON response containing: `response` (string), `session_id` (UUID), `message_id` (UUID), `metadata` (object)
- **FR-006**: System MUST process messages through the NL2SQL pipeline from feature 003
- **FR-007**: System MUST include up to the last 10 message pairs (20 messages) as conversation context when processing follow-up messages
- **FR-008**: System MUST validate user has access to event before processing event-scoped requests
- **FR-034**: System MUST allow users to view their event-scoped sessions even after losing event access, but MUST block new queries with "access denied" error

#### Session Management
- **FR-009**: System MUST store sessions in `plugin_assistant.chat_sessions` table
- **FR-010**: System MUST store messages in `plugin_assistant.chat_messages` table
- **FR-011**: System MUST associate sessions with authenticated user (user_id from Indico auth)
- **FR-012**: System MUST track session metadata: created_at, updated_at timestamps
- **FR-013**: System MUST track message metadata: role (user/assistant), content, created_at, optional metadata JSON
- **FR-033**: System MUST automatically delete sessions and associated messages after 90 days of inactivity (no new messages)

#### Session Listing
- **FR-014**: System MUST accept GET requests at `/api/assistant/sessions` to list user's sessions
- **FR-015**: System MUST support pagination via `limit` (default 20, max 100) and `offset` query parameters
- **FR-016**: System MUST support filtering by `event_id` query parameter
- **FR-017**: System MUST return session list with: session_id, created_at, last_message_at, message_count, event_id
- **FR-018**: System MUST order sessions by last_message_at descending (most recent first)

#### Session History
- **FR-019**: System MUST accept GET requests at `/api/assistant/sessions/{session_id}` to retrieve session details
- **FR-020**: System MUST return all messages in the session ordered by created_at ascending
- **FR-021**: System MUST include for each message: message_id, role, content, created_at, metadata
- **FR-022**: System MUST validate requesting user owns the session before returning data
- **FR-036**: System MUST accept DELETE requests at `/api/assistant/sessions/{session_id}` to remove a session
- **FR-037**: System MUST delete all associated messages and feedback when a session is deleted
- **FR-038**: System MUST validate requesting user owns the session before allowing deletion

#### Feedback Collection
- **FR-023**: System MUST accept POST requests at `/api/assistant/feedback` with JSON body
- **FR-024**: System MUST require `message_id` (UUID) identifying the assistant response
- **FR-025**: System MUST require `feedback_type` enum: thumbs_up, thumbs_down, rating, comment
- **FR-026**: System MUST require `value` appropriate to type: boolean for thumbs, integer 1-5 for rating, string for comment
- **FR-027**: System MUST store feedback in `plugin_assistant.feedback_entries` table
- **FR-028**: System MUST validate user owns the session containing the message before accepting feedback

#### Security & Rate Limiting
- **FR-029**: All endpoints MUST require Indico authentication (return 401 if not authenticated)
- **FR-030**: System MUST implement rate limiting per user (default: 60 requests/minute for chat, 200/minute for read operations)
- **FR-031**: System MUST return 429 with Retry-After header when rate limit exceeded
- **FR-032**: System MUST sanitize all user input to prevent injection attacks
- **FR-035**: All error responses MUST use JSON format: `{"error": "<code>", "message": "<human readable>", "details": {...}}`

### Key Entities

- **ChatSession**: Represents a conversation thread. Contains id, user_id, event_id (optional), created_at, updated_at. Belongs to one user, optionally scoped to one event.
- **ChatMessage**: Represents a single message in a conversation. Contains id, session_id, role (user/assistant), content, metadata_json, created_at. Belongs to one session.
- **FeedbackEntry**: Represents user feedback on an assistant response. Contains id, message_id, user_id, feedback_type, value, created_at. Links to one message.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can send a chat message and receive a response within 5 seconds (95th percentile)
- **SC-002**: Users can retrieve their session list within 500ms
- **SC-003**: Users can view a session's message history within 500ms
- **SC-004**: System supports at least 100 concurrent chat sessions without degradation
- **SC-005**: All authenticated users can access only their own sessions (100% access control accuracy)
- **SC-006**: Feedback submission succeeds within 200ms
- **SC-007**: Follow-up questions correctly reference context from previous messages in the session (verified through integration tests)

## Assumptions

- Indico's authentication system provides user_id for authenticated requests via standard RH (Request Handler) mechanisms
- The NL2SQL pipeline from feature 003 is available and functional
- PostgreSQL is available with the `plugin_assistant` schema already created
- Redis is available for rate limiting state (or rate limiting can use in-memory fallback)
- Frontend clients will handle session_id storage and pass it on subsequent requests
- Message content is plain text (no rich formatting or file attachments in this version)

## Dependencies

- **Feature 003 (NL2SQL Pipeline)**: Required for processing natural language queries into SQL and generating responses
- **Indico Core**: Authentication, user context, event access validation
- **PostgreSQL**: Data persistence for sessions, messages, and feedback
- **Redis** (optional): Rate limiting state management

## Clarifications

### Session 2026-01-14

- Q: How long should chat sessions and messages be retained before automatic cleanup? → A: 90 days - Sessions deleted after 90 days of inactivity
- Q: How many previous messages should be included as context for follow-up questions? → A: Last 10 message pairs (20 messages total)
- Q: What happens to a user's sessions when they lose access to the associated event? → A: Sessions remain visible but new queries are blocked with "access denied"
- Q: What format should error responses follow? → A: Simple JSON with `{"error": "code", "message": "human readable", "details": {...}}`
- Q: Should users be able to manually delete their chat sessions? → A: Yes, individual deletion via DELETE `/api/assistant/sessions/{id}`
