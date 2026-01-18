# Feature Specification: Chat Widget for Indico Assistant

**Feature Branch**: `008-chat-widget`  
**Created**: January 17, 2026  
**Status**: Draft  
**Input**: User description: "Create a dedicated chat widget that is embedded on the Indico sticky header or fixed navigation bar via template hooks"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Basic Chat Interaction (Priority: P1)

As an Indico user, I want to open a chat widget from the navigation bar and ask questions about events I have access to, so that I can quickly get information without leaving my current page.

**Why this priority**: This is the core value proposition - enabling users to interact with the assistant directly within Indico. Without this, the feature has no purpose.

**Independent Test**: Can be fully tested by clicking the chat button, typing a question, and receiving a response. Delivers immediate value by providing assistant access within Indico.

**Acceptance Scenarios**:

1. **Given** I am logged into Indico and viewing any page, **When** I click the chat widget button in the navigation bar, **Then** a chat panel expands showing the message input area and any previous messages from my session
2. **Given** the chat panel is open, **When** I type a question and press Enter or click Send, **Then** my message appears in the chat history and I see a loading indicator while waiting for a response
3. **Given** I have sent a message, **When** the assistant responds, **Then** the response appears in the chat history with visual distinction from my messages and the panel auto-scrolls to show the new message
4. **Given** I am using the chat widget, **When** I press Escape or click outside the panel, **Then** the chat panel closes but my session is preserved

---

### User Story 2 - Session Persistence (Priority: P2)

As an Indico user, I want my chat session to persist while I navigate between pages, so that I can continue conversations without losing context.

**Why this priority**: Session persistence significantly improves user experience but the widget is functional without it (users would just start fresh conversations).

**Independent Test**: Can be tested by having a conversation, navigating to another Indico page, opening the widget again, and verifying the previous conversation is still visible.

**Acceptance Scenarios**:

1. **Given** I have an active chat session with messages, **When** I navigate to a different Indico page, **Then** opening the chat widget shows my previous messages from this browser session
2. **Given** I have a chat session in one browser tab, **When** I open Indico in a new tab, **Then** the new tab shares the same session and can see/continue the conversation
3. **Given** I close my browser completely, **When** I return to Indico later, **Then** my previous thread may be resumed if Chainlit's localStorage thread ID is preserved (browser-dependent behavior)

---

### User Story 3 - Feedback on Assistant Responses (Priority: P2)

As an Indico user, I want to provide feedback on assistant responses, so that the system can improve over time.

**Why this priority**: Feedback is important for system improvement but does not block core functionality. Users can benefit from the widget without providing feedback.

**Independent Test**: Can be tested by receiving a response, clicking thumbs up/down, and verifying visual confirmation appears.

**Acceptance Scenarios**:

1. **Given** the assistant has responded to my question, **When** I look at the response, **Then** I see thumbs up and thumbs down buttons
2. **Given** I see feedback buttons on a response, **When** I click thumbs up, **Then** the button shows as selected and I see visual confirmation that feedback was recorded
3. **Given** I have already provided feedback on a response, **When** I click the opposite feedback button, **Then** my feedback is updated and the visual state reflects the change

---

### User Story 4 - Markdown Response Rendering (Priority: P3)

As an Indico user, I want assistant responses with formatting (code, lists, links) to display properly, so that I can easily read structured information.

**Why this priority**: Improves readability of complex responses but plain text responses are still functional.

**Independent Test**: Can be tested by asking a question that produces a markdown response (e.g., "list the sessions") and verifying proper formatting.

**Acceptance Scenarios**:

1. **Given** the assistant responds with markdown-formatted text, **When** I view the response, **Then** headings, bold, italic, and lists render as formatted HTML
2. **Given** the assistant responds with code snippets, **When** I view the response, **Then** code is displayed in a monospace font with syntax distinction
3. **Given** the assistant responds with links, **When** I click a link, **Then** the link opens in a new tab

---

### User Story 5 - Accessible Chat Experience (Priority: P3)

As an Indico user who relies on keyboard navigation or screen readers, I want the chat widget to be fully accessible, so that I can use it effectively.

**Why this priority**: Accessibility is important for inclusive design but does not block initial release for most users.

**Independent Test**: Can be tested using only keyboard navigation to open widget, send message, and close widget.

**Acceptance Scenarios**:

1. **Given** I am using keyboard navigation, **When** I tab through the navigation bar, **Then** I can focus on and activate the chat widget button
2. **Given** the chat panel is open, **When** I use Tab and Shift+Tab, **Then** I can navigate between the message input, send button, and close button
3. **Given** I am using a screen reader, **When** the assistant responds, **Then** the new message is announced appropriately

---

### User Story 6 - Graceful Degradation Without JavaScript (Priority: P3)

As an Indico user with JavaScript disabled, I want the page to not break, so that I can still use Indico normally.

**Why this priority**: Edge case for users with JS disabled. Most functionality requires JS but page should not break.

**Independent Test**: Can be tested by disabling JavaScript and verifying the chat button is hidden and page functions normally.

**Acceptance Scenarios**:

1. **Given** JavaScript is disabled in my browser, **When** I view any Indico page, **Then** the chat widget button is not visible and the page functions normally
2. **Given** JavaScript becomes available after page load, **When** the page detects JS support, **Then** the chat widget button becomes visible and functional

---

### Edge Cases

- What happens when the chat API returns an error? Display user-friendly error message in chat panel, allow retry
- What happens when the user sends an empty message? Send button is disabled when input is empty
- What happens during network connectivity issues? Show offline indicator, queue messages for retry when connection restored
- What happens if the session expires on the server? Automatically create new session, inform user that previous context may be lost
- What happens when very long responses are received? Scrollable message area handles long content, consider "show more" for extremely long responses
- What happens on mobile devices with limited screen space? Widget adapts to full-width panel on small screens

## Requirements *(mandatory)*

### Functional Requirements

#### Widget Injection
- **FR-001**: System MUST use `inject_bundle()` to load the Chainlit Copilot widget script on all pages; the widget self-mounts to `document.body` in a fixed bottom-right position
- **FR-002**: Chat widget button MUST be visible on all Indico pages where the navigation bar appears
- **FR-003**: System MUST inject required JavaScript and CSS assets via Indico asset injection system

#### Chat Widget UI
- **FR-004**: System MUST display a floating button that indicates chat functionality (icon + optional label)
- **FR-005**: Clicking the chat button MUST expand a chat panel with message input and history
- **FR-006**: Chat panel MUST display scrollable message history with clear visual distinction between user and assistant messages
- **FR-007**: System MUST show a loading indicator while waiting for LLM response
- **FR-008**: System MUST display user-friendly error messages when API calls fail
- **FR-009**: Chat panel MUST include a close button to collapse the panel

#### API Integration
- **FR-010**: Widget MUST call /api/assistant/chat endpoint to send messages
- **FR-011**: Widget MUST call /api/assistant/feedback endpoint to submit feedback
- **FR-012**: Widget MUST include appropriate authentication headers with all API requests
- **FR-013**: Widget MUST handle API error responses gracefully and display appropriate messages to users

#### Session Management
- **FR-014**: Widget MUST maintain session_id in browser sessionStorage
- **FR-015**: Widget MUST create a new session if no existing session_id is found
- **FR-016**: Widget MUST send session_id with all chat requests to maintain conversation context
- **FR-017**: Message history MUST persist via Chainlit's localStorage thread mechanism; thread ID survives browser close but can be cleared by user

#### User Interaction
- **FR-018**: Pressing Enter in the message input MUST send the message (unless Shift+Enter for newline)
- **FR-019**: Pressing Escape MUST close the chat panel
- **FR-020**: Chat panel MUST auto-scroll to show new messages
- **FR-021**: Message input MUST support multi-line text entry

#### Feedback Integration
- **FR-022**: Each assistant response MUST display thumbs up and thumbs down feedback buttons
- **FR-023**: Clicking a feedback button MUST send feedback to the API and show visual confirmation
- **FR-024**: Feedback buttons MUST show selected state after feedback is submitted

#### Styling and Design
- **FR-025**: Widget styling MUST match Indico design system (colors, fonts, spacing)
- **FR-026**: Widget MUST be responsive and usable on mobile devices
- **FR-027**: Chat panel MUST appear in a fixed position at bottom-right corner, overlaying page content without blocking critical navigation elements
- **FR-028**: Widget MUST support Indico theme variations if applicable

#### Accessibility
- **FR-029**: All interactive elements MUST be keyboard accessible
- **FR-030**: Widget MUST include appropriate ARIA attributes for screen reader support
- **FR-031**: Focus MUST be managed appropriately when opening/closing the panel

#### Graceful Degradation
- **FR-032**: Chat widget button MUST be hidden when JavaScript is disabled
- **FR-033**: Widget MUST NOT cause errors or break page functionality when JavaScript is unavailable

### Key Entities

- **ChatMessage**: Represents a single message in the conversation (role: user/assistant, content, timestamp, messageId)
- **ChatSession**: Represents the conversation session (sessionId, messages array, createdAt)
- **FeedbackRecord**: Represents user feedback on a response (messageId, feedbackType: positive/negative, timestamp)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can send a message and receive a response within 30 seconds of clicking send (excluding LLM processing time)
- **SC-002**: Chat widget loads and becomes interactive within 2 seconds of page load
- **SC-003**: Widget functions correctly on screens as small as 320px width (mobile support)
- **SC-004**: 100% of interactive elements are accessible via keyboard navigation
- **SC-005**: Chat session persists across page navigation within the same browser session with 100% reliability
- **SC-006**: Users can submit feedback on any assistant response with visual confirmation appearing within 1 second
- **SC-007**: Widget JavaScript bundle size is under 50KB (minified, before gzip)
- **SC-008**: Widget CSS bundle size is under 20KB (minified, before gzip)
- **SC-009**: Widget displays appropriate error message within 5 seconds when API is unavailable
- **SC-010**: Widget renders correctly in latest versions of Chrome, Firefox, Safari, and Edge

## Assumptions

- Indico provides template hooks for the sticky header/navigation bar that plugins can use
- The existing /api/assistant/chat and /api/assistant/feedback endpoints are available and functional
- Indico asset injection system supports loading plugin JavaScript and CSS
- Users are authenticated via Indico standard authentication mechanism before using the chat widget
- Browser sessionStorage is available (supported in all modern browsers)
- The LLM response times are outside the scope of this widget (handled by backend)
- Markdown rendering will use a lightweight library (e.g., marked-min or snarkdown) to stay within bundle size constraints while supporting basic formatting (bold, italic, links, lists, code blocks)

## Out of Scope

- Rich media support (images, file uploads) in chat messages
- Voice input/output capabilities
- Chat history persistence across browser sessions (intentionally ephemeral)
- Admin interface for widget configuration
- Real-time collaborative chat features
- Offline mode with full functionality (graceful degradation only)

## Clarifications

### Session 2026-01-17

- Q: Which Indico template hook location should the chat widget button use? → A: `global-header` - Global header area, appears on all pages above nav
- Q: Where should the expanded chat panel appear on screen? → A: Bottom-right corner - Fixed position, overlays page content
- Q: How should markdown in assistant responses be rendered? → A: Lightweight library (marked-min/snarkdown) - Basic markdown support, ~5-15KB
