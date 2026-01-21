# Feature Specification: Chat Source Citations

**Feature Branch**: `015-chat-source-citations`  
**Created**: January 20, 2026  
**Status**: Draft  
**Input**: User description: "Add in auto referencing for information pertaining to events/attachments in the chat response. Preference toward clean inline references but bottom-of-the-messages also fine if inline is not feasible/too complicated. If the information is drawn from any nominal component of the event (not from attached documents), just return the reference as a link to the event page (e.g. `http://127.0.0.1:8000/event/7/`), if the info is from document (attachment) (chunked and vectorized by us) then return a link the the attachment (e.g. http://127.0.0.1:8000/event/7/contributions/3/attachments/4/6/1706.03762v7.pdf)"

## Clarifications

### Session 2026-01-20

- Q: When the same document is cited multiple times in different parts of the response (e.g., "According to the paper... [later]... The paper also states..."), how should citations be handled? → A: Each mention gets its own inline citation - e.g., "The paper ([source](url)) shows X. Later, the paper ([source](url)) also states Y."
- Q: When information comes from NL2SQL queries (database event metadata like titles, dates, speakers) versus vector search (document content), how should citations be formatted? → A: Both cite the same way - NL2SQL results cite event pages, vector results cite documents (already specified)
- Q: What should happen when a citation link fails to open (e.g., user lacks permissions, document deleted, or network error)? → A: Standard HTTP error
- Q: Why is "5 sources" the threshold for switching from inline to bottom-of-message references? → A: We should always use inline if we can
- Q: When a citation is placed in a streamed response, should it appear as soon as the relevant content is generated, or should all citations be added after the full response completes? → A: Incremental - Citations appear inline as soon as the relevant content streams

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Inline Event Citations (Priority: P1)

When a user asks a question about an event and receives a response, they need to see exactly where the information came from so they can verify the source and explore further context.

**Why this priority**: This is the core value proposition - users must be able to trust and verify AI responses by seeing the source. Without this, the chat system lacks transparency and credibility.

**Independent Test**: Can be fully tested by asking "When is the workshop?" and verifying that the response includes a clickable link to the event page, e.g., "The workshop is on January 25th ([source](http://127.0.0.1:8000/event/7/))"

**Acceptance Scenarios**:

1. **Given** a user asks about event details (date, time, location), **When** the assistant retrieves information from event metadata, **Then** the response includes an inline link to the event page in the format `http://127.0.0.1:8000/event/{event_id}/`
2. **Given** a single response draws from multiple events, **When** the assistant generates the response, **Then** each piece of information has its own inline citation linking to the respective event
3. **Given** the assistant cannot determine the event source, **When** generating the response, **Then** no citation is included rather than an incorrect one

---

### User Story 2 - Inline Document/Attachment Citations (Priority: P1)

When a user asks a question that requires information from a document attachment (PDF, presentation, etc.), they need to see a link directly to that specific document so they can read the full context or verify the extracted information.

**Why this priority**: Document-sourced answers are the primary use case for RAG. Users must be able to access the original documents to verify claims and read more detail.

**Independent Test**: Can be fully tested by asking "What does the research paper say about X?" and verifying the response includes a direct link to the PDF attachment, e.g., "According to the study ([source](http://127.0.0.1:8000/event/7/contributions/3/attachments/4/6/paper.pdf)), the results show..."

**Acceptance Scenarios**:

1. **Given** a user asks a question answered by document content, **When** the assistant retrieves information from vectorized chunks, **Then** the response includes an inline link to the specific attachment in the format `http://127.0.0.1:8000/event/{event_id}/contributions/{contrib_id}/attachments/{attach_id}/{file_id}/{filename}`
2. **Given** multiple chunks from the same document are used in different parts of the response, **When** the assistant generates the response, **Then** each mention of that document includes its own inline citation link
3. **Given** information comes from multiple documents, **When** the assistant generates the response, **Then** each document has its own inline citation at each point where it's referenced
4. **Given** the chunk metadata is incomplete or malformed, **When** the assistant attempts to generate a citation, **Then** the system gracefully handles the error and either provides a partial link or omits the citation

---

### User Story 3 - Fallback to Bottom-of-Message References (Priority: P3)

When inline citations are technically infeasible or would break response formatting (rare edge case), users should see numbered references in the text with corresponding links at the bottom of the message.

**Why this priority**: This is a fallback mechanism for exceptional cases where inline citations cannot be generated. The system should always prefer inline citations when possible.

**Independent Test**: Can be fully tested by creating a scenario where inline citation generation fails (implementation-dependent edge case) and verifying the response falls back to numbered references like [1], [2], etc. with a "References:" section at the bottom.

**Acceptance Scenarios**:

1. **Given** inline citation generation encounters a technical limitation, **When** the assistant generates the response, **Then** numbered references [1], [2], etc. are used as a fallback with a "References:" section at the end
2. **Given** a response uses bottom-of-message references, **When** displaying the references section, **Then** each reference includes both the link and a brief descriptor (e.g., "Event: Conference 2026" or "Document: Research Paper")
3. **Given** the system can generate inline citations successfully, **When** the assistant generates any response, **Then** inline citations are always used regardless of the number of sources

---

### User Story 4 - Mixed Event and Document Citations (Priority: P2)

When a user asks a question that requires both event metadata and document content, they need to see citations that clearly distinguish between the two types of sources.

**Why this priority**: Real-world queries often combine metadata (who, when, where) with document content (what was discussed, what conclusions were reached). Clear distinction prevents confusion.

**Independent Test**: Can be fully tested by asking "Who presented the research on X at the January conference?" and verifying the response cites both the event page (for presenter/date) and the document (for research content).

**Acceptance Scenarios**:

1. **Given** a response combines event metadata and document content, **When** the assistant generates citations, **Then** event citations link to event pages and document citations link to attachments
2. **Given** the same event contains multiple cited documents, **When** the assistant generates citations, **Then** the event is cited once and each document is cited separately
3. **Given** a response mentions an event that also has cited documents, **When** displaying references, **Then** users can distinguish event-level information from document-level information

---

### User Story 5 - No Citation When Using General Knowledge (Priority: P3)

When a user asks a general knowledge question not specific to any event or document in the system, they receive an answer without citations since the information doesn't come from the indexed sources.

**Why this priority**: This prevents citation confusion and makes it clear when the assistant is using general knowledge vs. system-specific information.

**Independent Test**: Can be fully tested by asking "What is machine learning?" and verifying the response has no citations since it's answering from general knowledge.

**Acceptance Scenarios**:

1. **Given** a user asks a general knowledge question, **When** the assistant responds using its base knowledge, **Then** no citations are included in the response
2. **Given** a response mixes general knowledge with system-specific information, **When** the assistant generates the response, **Then** only the system-specific portions have citations
3. **Given** a user asks about content not found in the system, **When** the assistant responds, **Then** it clearly states the information is not available in the indexed sources

---

### Edge Cases

- What happens when a chunk's source metadata is missing or incomplete (e.g., no event_id, malformed URLs)? → System gracefully omits the citation or provides a partial link per FR-010
- How does the system handle documents that have been deleted after being indexed? → Citation link will result in standard HTTP 404 error from Indico platform
- What happens when the same information appears in multiple documents - which one gets cited? → All documents contributing to the response are cited at their respective mention points
- How are citations handled when the event or attachment URL structure changes? → This is an out-of-scope infrastructure concern; URL structure assumed stable per Assumption #1
- What happens when citations are included in a streamed response - are they added incrementally or all at once? → Citations are added incrementally as content streams, appearing inline as soon as the relevant source-based content is generated (per FR-011)
- How does the system handle very long document filenames in citation links? → Filenames are included as-is in the URL; display truncation is a client-side concern
- What happens when a user doesn't have permission to access a cited event or document? → Citation link results in standard HTTP 403/401 error from Indico platform's access control

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST automatically identify when response content is derived from indexed event metadata (via NL2SQL or direct database queries) and include a citation link to the event page
- **FR-002**: System MUST automatically identify when response content is derived from vectorized document chunks (via vector search) and include a citation link to the specific attachment
- **FR-003**: System MUST format event citations as full URLs in the format `{base_url}/event/{event_id}/` where base_url is configured per environment (e.g., http://localhost:8000 for dev)
- **FR-004**: System MUST format document citations as full URLs in the format `{base_url}/event/{event_id}/contributions/{contrib_id}/attachments/{attach_id}/{file_id}/{filename}` where base_url is configured per environment
- **FR-005**: System MUST always use inline citations (embedded in the response text) as the default and preferred citation format
- **FR-006**: System MAY use numbered references with a bottom-of-message "References:" section only when inline citation generation is technically infeasible
- **FR-007**: System MUST include a citation link each time a source is referenced in the response text, even if the same source is mentioned multiple times
- **FR-008**: System MUST distinguish between event-level citations and document-level citations in the response
- **FR-009**: System MUST NOT include citations when answering from general knowledge rather than indexed sources
- **FR-010**: System MUST gracefully handle missing or incomplete source metadata by either omitting the citation or providing a partial link
- **FR-011**: System MUST include citation links inline as the response text is generated, ensuring citations appear with their corresponding content whether using streaming or synchronous response generation
- **FR-012**: Citations MUST be clickable hyperlinks that open the target resource
- **FR-013**: System MUST extract source metadata (event_id, contribution_id, attachment_id, file_id, filename) from chunk metadata during retrieval
- **FR-014**: System MUST maintain source tracking throughout the response generation pipeline
- **FR-015**: Bottom-of-message references MUST include both the link and a brief descriptor of the source type

### Key Entities

- **Source Metadata**: Information about where a piece of content originated, including:
  - Source type (event metadata vs. document chunk)
  - Event ID
  - Contribution ID (for documents)
  - Attachment ID (for documents)
  - File ID (for documents)
  - Filename (for documents)
  - Original URL components
  
- **Citation**: A formatted reference in a response that links back to a source, including:
  - Display format (inline vs. numbered reference)
  - URL (fully constructed link)
  - Position in response (inline location or reference list)
  - Source descriptor (for reference lists)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 95% of responses sourced from indexed content include at least one valid citation link
- **SC-002**: Users successfully navigate to source events or documents from citations in 90% of attempts
- **SC-003**: Citation generation adds less than 200ms to average response time
- **SC-004**: Zero broken or malformed citation links in responses
- **SC-005**: Users report improved trust and confidence in responses due to source transparency (target: 80% positive feedback)
- **SC-006**: 100% of citations correctly distinguish between event-level and document-level sources

## Assumptions

1. **URL Structure Stability**: We assume the Indico event/attachment URL structure (`/event/{id}/contributions/{id}/attachments/{id}/{file_id}/{filename}`) is stable and won't change during this feature's implementation
2. **Chunk Metadata Availability**: We assume vector search chunks already contain sufficient metadata (event_id, contribution_id, etc.) to construct full URLs
3. **Base URL Configuration**: The base URL (`http://127.0.0.1:8000`) will be configurable for different environments (dev, staging, production)
4. **Citation Rendering**: We assume the chat client can render markdown links or HTML hyperlinks in messages with no practical limit on the number of inline citations per response
5. **Streaming Compatibility**: Citation insertion is compatible with streamed response generation
6. **Source Attribution**: The LLM response generation process can track which sources contributed to which parts of the response

## Dependencies

- Vector search chunks must include complete source metadata in their stored format
- Chat response generation pipeline must expose source tracking information
- Frontend chat widget must support rendering clickable links in messages

## Out of Scope

- Citing specific page numbers or sections within documents
- Providing preview text or snippets in citation tooltips
- Tracking which citations users click (analytics)
- Suggesting related sources not used in the response
- Deep linking to specific locations within PDFs
- Citation export functionality (e.g., "Copy all sources")
- Customizable citation formats or styles
- Citation validation (checking if links are still valid)
- Access control warnings when citing restricted content
