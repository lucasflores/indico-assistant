# Feature Specification: Persistent assistant with past chats

**Feature Branch**: `020-chat-persistence`
**Created**: 2026-09-28
**Status**: Draft
**Input**: User description: "At present the chat has no conversation persistence or chat history. If I am in a chat and click a link to another event, the chat is wiped. This is very disruptive to any workflow: the assistant must persist as the user navigates Indico. Chat session history is not the same thing, but it needs similar work, so implement both at the same time. We need the classic previous-chats sidebar."

## Context

Every link in Indico loads a new page, and the assistant starts from nothing on each one. The user has to open
it again, and it shows an empty chat. The conversation itself is not lost: every message is stored in Indico.
Three things cause the loss:

1. the chat window never loads a stored conversation back;
2. each page opens a new, empty conversation;
3. a conversation is tied to the event it started on, and the assistant refuses to continue it from another
   event's page.

The decisions taken before this spec (2026-09-28):

- **Where the assistant appears**: a panel docked to the side of Indico pages, with the previous-chats sidebar
  inside it. This replaces the floating chat bubble, which has no room for a sidebar.
- **Where conversations live**: only in Indico, where they are stored today. The panel and its sidebar read and
  write that one store; nothing keeps a second copy.
- **Which conversation comes back**: the one last open in this browser.
- **After navigating**: the panel reopens on the next page if it was open.
- **"This event" in a message**: the page the user is on when they send it, not the page the conversation
  started on.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The conversation survives navigation (Priority: P1)

A user asks the assistant about an event, gets an answer with a link to another event, and follows it. On the
new page the assistant is still open, with the whole conversation, and they carry on typing.

**Why this priority**: This is the problem as reported. Without it, any task that spans more than one page
means starting the conversation over.

**Independent Test**: Open the assistant on an event page, exchange two messages, click a link to another
event. The panel is open on the new page with both exchanges, and a third message continues the same
conversation (the reply can refer to what was said before).

**Acceptance Scenarios**:

1. **Given** the panel is open with a conversation, **When** the user follows any link within Indico, **Then**
   the panel is open on the new page and shows the same conversation, scrolled to its latest message.
2. **Given** the panel was closed on the previous page, **When** the user navigates, **Then** it stays closed.
   When they open it, the conversation they last had open is there.
3. **Given** the user sent a question and navigated before the answer arrived, **When** the new page loads,
   **Then** the panel shows the question with the answer still to come. The answer appears when ready and is
   not lost.
4. **Given** a plan from chat actions (spec 019) was waiting for confirmation, **When** the user navigates,
   **Then** the plan is shown again and its Confirm and Cancel buttons still work, only once, as before.
5. **Given** the panel reopens after navigation, **Then** keyboard focus stays on the page. The panel does not
   take it until the user clicks or tabs into it.
6. **Given** the user reloads the page or comes back later in the same browser, **Then** the conversation they
   last had open is the one shown.

---

### User Story 2 - "This event" is the page you are on (Priority: P1)

The user starts a conversation on event A, moves to event B, and asks "who are the speakers of this event?"
or "move this meeting to 3pm". The assistant answers about, or changes, event B.

**Why this priority**: Once one conversation spans pages, a fixed event would give wrong answers or change the
wrong meeting. It ships together with story 1.

**Independent Test**: Start on event A and ask about "this event". Move to event B in the same conversation and
ask again. The second answer is about B. A chat action "move this meeting" plans a change to B.

**Acceptance Scenarios**:

1. **Given** a conversation started on event A, **When** the user sends a message from event B's page, **Then**
   the message is answered with event B as its context, under the user's access to B.
2. **Given** the user is on a page that is not an event (home, a category, their profile), **When** they send a
   message, **Then** it has no event context, as today on such pages.
3. **Given** the user can no longer access event A (it was protected since), **When** they reopen a
   conversation that mentioned A, **Then** they see their own earlier messages and answers. New questions get
   no new information about A.
4. **Given** earlier messages were about event A, **When** the user asks about "this event" on B, **Then** the
   assistant does not mix up A and B: it is told which page the user is on now.

---

### User Story 3 - Past chats sidebar (Priority: P2)

The user opens the sidebar in the panel and sees their earlier conversations: newest first, grouped as Today,
Yesterday, Previous 7 days and Previous 30 days, each under a short title. They open one and continue it. They
start a new chat. They search their conversations by a word they remember.

**Why this priority**: History comes after persistence (stories 1 and 2), but it uses the same restore
mechanism, and the user asked for both together.

**Independent Test**: Have three conversations from different days. Open the sidebar: all three are listed
under the right time groups. Open the oldest and continue it, start a new chat, and search for a word that
appears only in the second one.

**Acceptance Scenarios**:

1. **Given** the user has earlier conversations, **When** they open the sidebar, **Then** they see only their
   own, newest first and grouped by when they were last active, each with a title.
2. **Given** the sidebar is open, **When** the user picks a conversation, **Then** it opens with all its messages
   and can be continued. It is also the one restored on the next page (story 1).
3. **Given** a conversation is open, **When** the user starts a new chat, **Then** an empty conversation starts.
   The previous one stays in the sidebar.
4. **Given** the user types in the sidebar's search, **Then** only their own conversations whose title or
   messages contain the words are listed.
5. **Given** a conversation is older than the chat retention period (an admin setting, 90 days by default),
   **Then** it is no longer listed, as it has been deleted.

---

### User Story 4 - Rename and delete conversations (Priority: P3)

From the sidebar the user renames a conversation, or deletes it after confirming.

**Why this priority**: This is housekeeping for the sidebar. It is useful but not needed for stories 1-3.

**Independent Test**: Rename a conversation and reload: the new title stays. Delete another: it is gone from
the sidebar and cannot be opened any more, including from a second tab that had it open.

**Acceptance Scenarios**:

1. **Given** a conversation in the sidebar, **When** the user renames it, **Then** the new title is shown there
   from then on, in every tab and after a reload.
2. **Given** a conversation in the sidebar, **When** the user deletes it and confirms, **Then** it and its
   messages are deleted. The records of chat actions it confirmed stay, for audit (spec 019).
3. **Given** the deleted conversation was the one open, **Then** the panel shows a new, empty chat.

---

### Edge Cases

- **Two tabs, one browser**: both tabs restore the conversation last open in the browser. A message sent in
  one tab shows in the other after its next load, not live.
- **Shared browser, another user logs in**: they never see the previous user's conversations. The one
  "last open in this browser" is remembered per user.
- **Logged out, or the assistant disabled by an admin**: no panel, as today. Nothing is shown from before.
- **A conversation deleted elsewhere** (another tab, retention): restoring it shows a new, empty chat, without
  an error.
- **The chat service is unreachable**: the page works as usual and the panel says the assistant is unavailable,
  as the widget does today.
- **Narrow screens**: the panel covers the page instead of sitting beside it, and the sidebar starts collapsed.
- **Very long conversations**: the panel opens at the latest messages. Earlier ones are still reachable.
- **Uploads** (spec 019): a file sent in the chat shows as sent after navigation. Whether it is still
  attachable follows spec 019's rules.
- **Messages from before this feature**: existing conversations appear in the sidebar with a title taken from
  their first message.
- **Sharing a conversation by link**: not offered. Conversations are private to their user.

## Requirements *(mandatory)*

### Functional Requirements

**Persistence across pages (US1)**

- **FR-001**: The assistant MUST keep one current conversation per user per browser, and show it again
  whenever the panel is opened, on any Indico page, after a reload or a later visit, until the user opens
  another conversation or starts a new one.
- **FR-002**: If the panel was open when the user left a page, it MUST open again on the next page without a
  click. If it was closed, it MUST stay closed.
- **FR-003**: Reopening after navigation MUST NOT move keyboard focus or scroll the page.
- **FR-004**: An answer still being prepared when the user navigates MUST NOT be lost. It MUST appear in the
  conversation once ready, on whichever page the panel is open.
- **FR-005**: A chat-action plan (spec 019) that was waiting for confirmation MUST be shown again with working
  Confirm and Cancel. All of spec 019's guarantees still apply: single use, expiry, re-checks.
- **FR-006**: Everything the chat does today MUST work in the panel: questions, answers with sources, chat
  actions with their buttons and choices, file uploads, suggested starters, the theme following Indico's
  light or dark mode, and keyboard and screen-reader use.

**Feeling native (US1-US3)**

- **FR-006a**: When the panel reopens on a new page, its frame MUST appear at once, at its remembered width,
  so the page does not shift. A light placeholder shows until the conversation is drawn.
- **FR-006b**: Links in answers (events, material, Indico pages) MUST open in the Indico page itself, never
  inside the panel.
- **FR-006c**: The user MUST NOT be asked to log in to the panel. Being logged in to Indico is enough, and
  it keeps working while the panel stays open for hours.
- **FR-006d**: The panel MUST be resizable by dragging its edge. It MUST remember its width, and whether it
  was open, per browser. Esc closes it.
- **FR-006e**: The panel's look MUST follow Indico: light or dark mode, with the assistant's own header and
  colours toned to Indico's. The sidebar and chat keep Chainlit's own layout and behaviour: on a narrow
  panel the sidebar becomes a drawer behind its menu button.

**Page context (US2)**

- **FR-007**: Each message MUST carry the page it was sent from, and "this event" MUST mean that page's event.
  This applies to questions (NL2SQL scoping) and to chat actions ("this meeting").
- **FR-008**: Access MUST be checked for each message against the event of the page it was sent from. A
  conversation MUST NOT be refused because it started on another event.
- **FR-009**: The assistant MUST be told, for each message, which page the user is on, so earlier messages
  about other events are not taken as "this event".

**Past chats (US3, US4)**

- **FR-010**: The panel MUST include a sidebar listing the user's own conversations, and nobody else's,
  newest first, grouped as Today, Yesterday, Previous 7 days and Previous 30 days.
- **FR-011**: Each conversation MUST have a title. By default it is the start of its first message; the user
  can rename it.
- **FR-012**: Users MUST be able to open any listed conversation and continue it, and to start a new, empty
  one.
- **FR-013**: Users MUST be able to search their conversations by words in the title or the messages.
- **FR-014**: Users MUST be able to delete a conversation after confirming. Its messages go; the records of
  chat actions go through their own retention (spec 019).
- **FR-015**: Sharing conversations by link MUST NOT be offered.

**One store**

- **FR-016**: Conversations MUST be kept only in Indico's existing chat store. The panel, the sidebar and the
  assistant's own use of the conversation all read the same data. Retention (`retention_chat_days`), deletion
  and the per-user limits apply unchanged.
- **FR-017**: A user MUST only ever be able to open, list, rename, delete or continue their own
  conversations. This is checked by Indico on every request, whatever the browser remembers or sends.
- **FR-018**: Thumbs up and down on an answer, where the panel offers them, MUST be recorded in the existing
  answer feedback (`/api/assistant/feedback`).

### Key Entities

- **Conversation** (the existing chat session): belongs to one user; has a title, when it was started and last
  active, and its messages. It is no longer tied to one event. It may record the event it started on, for
  information.
- **Message**: one user message or assistant answer in a conversation, in order. A user message records the
  page (event, if any) it was sent from. An answer records its sources and any chat-action plan, as today.
- **Current conversation (per browser)**: which conversation the panel shows for this user in this browser. It
  is only a pointer: the conversation itself stays in Indico.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a scripted walk through 10 pages, each followed from a link in the previous page or the
  answer, the same conversation is shown on every page, with every earlier message present (10/10 pages).
- **SC-002**: When the panel was open, the conversation is visible on the next page within 2 seconds of the page
  finishing loading (median of 10 navigations on the local stack).
- **SC-003**: Asking about "this event" after moving to another event is answered about the new event in 10 of
  10 tries. A "move this meeting" chat action targets the new page's meeting in 10 of 10.
- **SC-004**: An answer requested just before navigating appears in the conversation in 10 of 10 tries.
- **SC-005**: Across two users on one browser, neither ever sees the other's conversations, in the sidebar,
  after a restore, or by sending a remembered conversation id. This is covered by automated tests.
- **SC-006**: The sidebar lists 100 conversations and opens any of them within 2 seconds (local stack).
- **SC-007**: No regression. The chat's existing automated tests and the chat-actions eval (spec 019: at
  least 90% intended plan or right question, 0% unasked objects) pass unchanged.

## Assumptions

- **Logged-in users only**: the assistant is available only to logged-in users, and only where an admin
  enabled it, as today. Nothing changes for anonymous visitors.
- **Browser storage**: "this browser" means the browser's own storage. Clearing site data forgets which
  conversation was current. The conversations stay in the sidebar.
- **Multiple tabs**: tabs in one browser share the current conversation. Live syncing between open tabs is not
  needed.
- **Open by default**: new users see the panel closed until they open it once.
- **Width**: the panel's width suits a chat plus a collapsible sidebar. On narrow screens it covers the page.
  The exact sizes are a design detail for the plan.
- **Old conversations**: existing conversations keep their messages. Their stored event becomes "the page it
  started on"; nothing is migrated away.
- **Titles**: the first message's opening words make a good enough default title. No model-written titles.
- **Chat actions**: spec 019's behaviour and guarantees stay as they are. Only "the page it was sent from"
  replaces "the conversation's event".

## Out of Scope

- Syncing a conversation live between open tabs, or across devices ("the conversation last open" is per
  browser, by decision).
- Sharing conversations with other users.
- Folders, pinning or archiving of conversations.
- Model-generated titles or summaries.
- Changing how answers are produced (NL2SQL, planner, models). Only the page context they receive changes.
