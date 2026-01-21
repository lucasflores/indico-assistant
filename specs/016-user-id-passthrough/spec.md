# Feature Specification: User ID Passthrough Fix

**Feature Branch**: `016-user-id-passthrough`  
**Created**: 2026-01-21  
**Status**: Draft  
**Input**: User description: "Fix user_id pass through - the user_id should be available to the service for personalized queries like what meetings do I have. Currently returns null. Add fallback to prompt user for name/email if user_id unavailable."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Authenticated User Asks Personal Query (Priority: P1)

An authenticated user asks the chat assistant a personalized question like "What meetings do I have coming up this week?" and receives accurate results filtered to their identity.

**Why this priority**: This is the core functionality - personalized queries are a key feature that requires reliable user identification to work correctly.

**Independent Test**: Can be fully tested by logging in as a user, asking "What meetings do I have this week?", and verifying the results match only that user's meetings.

**Acceptance Scenarios**:

1. **Given** a user is authenticated via Indico session, **When** they ask "What meetings do I have coming up this week?", **Then** the system correctly identifies them and returns only their meetings.

2. **Given** a user is authenticated via JWT token (Chainlit widget), **When** they ask "Show me my contributions", **Then** the system extracts their user ID from the token and returns only their contributions.

3. **Given** a user asks a query using "I", "me", or "my", **When** the NL2SQL pipeline processes the query, **Then** the generated SQL correctly uses the `:user_id` parameter with their actual ID.

---

### User Story 2 - Graceful Identity Prompting (Priority: P2)

When the system cannot determine who the user is, the assistant gracefully prompts the user to provide identifying information (name, user ID, or email) to complete their personalized query.

**Why this priority**: Provides a fallback user experience when authentication context is unavailable, rather than failing silently or returning incorrect results.

**Independent Test**: Can be tested by simulating a scenario where user_id is null and verifying the assistant responds with a helpful identity prompt.

**Acceptance Scenarios**:

1. **Given** the user identity cannot be determined (user_id is null), **When** they ask "What meetings do I have?", **Then** the assistant responds with a helpful message asking for their name, email, or user ID.

2. **Given** the user has previously provided their name/ID in the conversation, **When** they ask a follow-up personal query, **Then** the system uses the provided identifier to complete the query.

3. **Given** the user provides their email address, **When** the system looks up their identity, **Then** it finds the matching user and uses their ID for the query.

---

### User Story 3 - Transparent Identity Status (Priority: P3)

Users have visibility into whether the system has successfully identified them, helping them understand why certain queries may require additional information.

**Why this priority**: Improves user trust and understanding of the system capabilities, but is not essential for core functionality.

**Independent Test**: Can be tested by checking that the chat response metadata includes identity status information.

**Acceptance Scenarios**:

1. **Given** a user is successfully identified, **When** they receive a response, **Then** the response metadata indicates their identified status.

2. **Given** a user identity was determined via fallback (manual input), **When** they receive a response, **Then** the response indicates the identity source was user-provided.

---

### Edge Cases

- What happens when the JWT token is valid but contains no user identifier?
- How does the system handle when the provided name/email matches multiple users?
- What happens when the user provides an invalid or non-existent user ID?
- How does the system behave when the database lookup for a user fails?
- What happens when the user provides partial information (e.g., first name only)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST extract user_id from Indico session when available
- **FR-002**: System MUST extract user_id from JWT token (identifier or id field) when session is unavailable
- **FR-003**: System MUST propagate user_id through the entire chat processing chain (controller to service to pipeline to generator)
- **FR-004**: System MUST detect when a query requires user identity (contains "I", "me", "my", or similar pronouns)
- **FR-005**: System MUST prompt user for identifying information on-demand (only when user_id is unavailable AND query requires it) - not proactively at session start
- **FR-006**: System MUST support user identification via full name lookup against the users table
- **FR-007**: System MUST support user identification via email lookup against the users table
- **FR-008**: System MUST support direct user ID input as an alternative to name/email
- **FR-009**: System MUST handle multiple user matches by reporting the count and asking for email or user ID (without listing user details to protect privacy)
- **FR-010**: System MUST NOT fallback to user_id=0 when identity is required - instead trigger the prompting flow
- **FR-011**: System MUST persist user-provided identity context within the conversation session for follow-up queries
- **FR-012**: System MUST restrict user-provided identity to read-only queries; sensitive operations (modifications, deletions) require authenticated identity
- **FR-013**: System MUST display a disclaimer when returning results based on user-provided (non-authenticated) identity

### Key Entities

- **User**: Represents an Indico user with id, first_name, last_name, email attributes
- **ChatSession**: Conversation session that may store resolved user identity for the conversation
- **JWT Payload**: Token payload containing identifier or id field for user identification

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Personal queries from authenticated users return correct results 100% of the time when user_id is available
- **SC-002**: When user_id is unavailable, the system prompts for identity within 2 seconds rather than returning empty/incorrect results
- **SC-003**: Users can successfully identify themselves via name, email, or user ID with 95% success rate on first attempt
- **SC-004**: Follow-up queries in the same conversation reuse the resolved identity without re-prompting
- **SC-005**: User satisfaction with personal query accuracy improves (measured via feedback mechanism)
- **SC-006**: Zero instances of queries returning another user data due to identity confusion

## Assumptions

- The existing authentication mechanisms (Indico session and JWT) are working correctly when properly configured
- The users table contains accurate first_name, last_name, and email data for lookups
- User-provided identity information should be treated with appropriate skepticism (cannot be fully trusted for security-sensitive operations)
- The identity prompting flow is acceptable UX when authentication context is missing

## Clarifications

### Session 2026-01-21

- Q: When user_id is unavailable and the user provides identifying information, what level of trust should the system give to user-provided identity for data access? → A: Read-only trust - User-provided identity enables read queries with disclaimer, no sensitive operations
- Q: When multiple users match the provided name, how should the system present disambiguation options? → A: Count only - Report number of matches, ask for email or user ID to disambiguate (protects user privacy)
- Q: Should the identity prompting flow be triggered only for personal queries, or proactively at session start? → A: On-demand - Only prompt when user asks a personal query and identity is needed
