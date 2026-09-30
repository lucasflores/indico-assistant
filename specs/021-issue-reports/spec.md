# Feature Specification: Issue reports from the chat

**Feature Branch**: `021-issue-reports`
**Created**: 2026-09-29
**Status**: Draft
**Input**: User description: "In chat bug report, feature suggestion, hallucination/performance report. I want the user to be
able to submit an "issue report" form in the chat from a few different categories (allowing us to use that chat thread
as context). The chat can also suggest submitting an issue report when things are seeming to not go well. The issues
should appear in the user's profile with a "status" indicator that can be updated by the team (i.e. open, under
review, closed) with a note field about the status."

## Context

Today a user who gets a wrong answer can only give it a thumbs down, with an optional comment. Nobody sees that as a
task, and the user never hears back. This feature adds a report: the user sends it from the chat, and the team reads
it with the conversation that led to it. The team sets a status and a note, and the user sees both in their Indico
profile.

The decisions taken before this spec (2026-09-29):

- **The team** is Indico's own administrators (Indico core admins). The plugin has no group of its own, and its
  settings are already admin-only. A configurable triage group can come later.
- **The categories**: bug; feature suggestion; wrong or poor answer (this covers made-up facts and slow or weak
  answers).
- **The statuses**: open, under review, closed, plus one note from the team, which the user can read.
- **The conversation is attached as a copy.** Spec 020's rule stays: Indico shows a user's conversation to no one
  else. A report carries a copy, taken when it is sent, and the team reads only that copy. The form says so, and the
  user can untick it.
- **Retention**: a report is kept until one year after it is closed. Retention never deletes open reports or
  reports under review.
- **No email.** The user sees the status in their profile. The admins see new reports on their own page, with a
  count of open ones in the admin menu.
- **Indico only.** Reports are not copied to GitHub or any other tracker. A "copy to GitHub" button can come later,
  once the GitHub connection (thread D) exists.
- **The Report button sits in the panel's title bar**, next to », not in the chat's input bar. The input bar is
  locked while an answer is being prepared, and a message sent from it starts and names a conversation (decided
  after review, 2026-09-29).
- **The user can delete their own report** at any time, with its copy (decided after review, 2026-09-29).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Send a report from the chat (Priority: P1)

A user gets a wrong answer about an event and wants the team to know. In the chat they choose "Report a problem".
A short form appears in the conversation. They pick "Wrong or poor answer", write what was wrong, leave "Attach this
conversation" ticked, and send it. The chat confirms it was sent, with a link to their reports.

A user with an idea ("could it list my own talks?") opens the same form from the Report button in the panel's title
bar, without any answer to point at.

**Why this priority**: This is the feature. Without it there is nothing to triage or to show.

**Independent Test**: In the panel, ask a question, then open the form from the title bar's Report button, fill it
in and send it. The report is stored with its category, text and a copy of the conversation. It can be read back
through the assistant's API as that user.

**Acceptance Scenarios**:

1. **Given** the panel is open, **When** the user chooses the Report button in the panel's title bar, **Then** a
   form appears in the conversation. It has the three categories, an empty text box, an "Attach this conversation"
   box that is ticked, a Send button and a Cancel button.
2. **Given** the assistant offered "Report a problem" under an answer (story 4), **When** the user chooses it,
   **Then** the same form appears. "Wrong or poor answer" is selected, and the user can change it.
3. **Given** a filled form with the box ticked, **When** the user sends it, **Then** the report is stored with the
   category, the text and a copy of the conversation up to that moment. The copy ends at the reported answer when
   there is one. It includes what the assistant recorded about each answer (story 3, scenario 2). The chat shows
   "Report sent" with a link to the user's reports, and the link opens in the Indico page.
4. **Given** the user unticks "Attach this conversation", **When** they send, **Then** the report has only the
   category and the text. Nothing from the conversation is stored with it.
5. **Given** no category is picked or the text is empty, **Then** Send is disabled.
6. **Given** the user presses Send twice, or reloads after sending, **Then** exactly one report exists.
7. **Given** the user chooses Cancel, **Then** the form closes and nothing is sent.
8. **Given** a new, empty chat, **When** the user opens the form, **Then** the attach box is not shown, because there
   is nothing to attach. Sending the report creates no conversation: Past Chats lists nothing new.
9. **Given** an answer is still being prepared, **When** the user chooses Report, **Then** the form opens at once.
   Its copy holds the messages finished so far.

---

### User Story 2 - The user sees their reports and their status (Priority: P1)

The user opens their Indico profile, where a new "Assistant reports" item lists what they sent. Each report shows
its category, when it was sent, its status (open, under review or closed), the team's note, and when the team last
updated it. They can open a report and read what they sent, including the attached messages, and they can delete
it.

**Why this priority**: Lucas asked for the status to be visible to the user. It is also the only way the user hears
back, since there is no email.

**Independent Test**: As a user with two reports, one of them closed with a note, open the profile page. Both are
listed with the right status and note. Signed in as another user, neither report can be seen, from the page or the
API.

**Acceptance Scenarios**:

1. **Given** the user has sent reports, **When** they open their profile, **Then** "Assistant reports" is in the
   profile menu and lists their reports, newest first, each with its category, the start of the text, the date
   sent, the status, the team's note and when the team last updated it.
2. **Given** the user opens one of their reports, **Then** they see the full text and, if attached, the copied
   messages as the chat showed them. How the answers were made (FR-003) is shown only to admins.
3. **Given** an admin changed the status or the note, **When** the user next loads the page, **Then** they see the
   new status and note.
4. **Given** a user who is not an admin, **When** they try to open another user's report, by the page or the API,
   **Then** they are refused, and the refusal does not say whether the report exists.
5. **Given** the user has never sent a report, **Then** the profile menu does not show the item.
6. **Given** one of their reports, whatever its status, **When** the user deletes it and confirms, **Then** the report
   and its copy are gone at once, from their page and from the admins' page.

---

### User Story 3 - Admins triage reports (Priority: P1)

An Indico admin sees "Assistant reports" in the admin menu, with the number of open reports. The page lists every
report, and they can filter it by status and category. They open a wrong-answer report, read the copied conversation
with the reported answer marked, and see how the answer was made: the query that ran, how confident the assistant
was, how many rows came back, and any error or correction. They set the status to "under review", add a note, and
later close it.

**Why this priority**: Without triage, statuses never change and the reports go nowhere. Stories 1-3 ship together
as the first usable version.

**Independent Test**: As an admin, open the admin page, filter to open wrong-answer reports, open one, and set it to
"closed" with a note. As the reporting user, the profile shows it closed with that note. As a non-admin (user 6),
the admin page and its API are refused.

**Acceptance Scenarios**:

1. **Given** reports exist, **When** an admin opens "Assistant reports" in the admin menu, **Then** they see all
   reports, newest first, with the reporting user, category, start of the text, date and status. They can filter by
   status and by category. The menu item shows the number of open reports.
2. **Given** an admin opens a report with a copy, **Then** they see the copy's messages in order, with the reported
   answer marked. For each answer they see the evidence recorded with it (FR-003b): its sources, the generated
   query, its confidence, any error, the question's classified intent, the row count, whether a check rejected the
   query, the number of correction attempts and whether the answer was cached.
3. **Given** a report, **When** an admin changes its status or writes the note and saves, **Then** the change is
   stored with the admin and the time. Any status can follow any other, so a closed report can be reopened. If the
   report changed after the admin opened it, the save is refused and the page shows the current status and note.
4. **Given** a user who is not an Indico admin, **When** they open the admin page or call its API, **Then** they are
   refused.
5. **Given** the reporting user's conversation has since changed, been deleted or been purged, **Then** the admin
   still sees the copy as it was when the report was sent. Admins never see the live conversation.

---

### User Story 4 - The assistant suggests a report when things go badly (Priority: P2)

A user gives an answer a thumbs down and writes "the date is wrong". Right after, the chat says it's sorry that
missed and offers "Report a problem", with the comment already in the form. When the assistant fails to answer, or
says a question is outside what it can do, it offers the same button under that answer.

**Why this priority**: Most problems are noticed at the moment an answer goes wrong, and a thumbs down is not a
report. It depends on story 1's form.

**Independent Test**: Give an answer a thumbs down with a comment: the offer appears once, and its form has "Wrong
or poor answer" and the comment. Ask a question the assistant refuses as out of scope: the answer carries the offer.
No report exists until Send is pressed.

**Acceptance Scenarios**:

1. **Given** an answer, **When** the user gives it a thumbs down, **Then** the chat offers "Report a problem" for
   that answer, once. The form opens with "Wrong or poor answer" and the thumbs-down comment, if there was one.
2. **Given** a question the assistant could not answer (the query failed, the question was outside what it can do,
   or a requested change was not understood or can't be made), **Then** the answer carries the "Report a problem"
   offer.
3. **Given** a question that got no answer at all (the answer timed out, the worker failed, or the chat could not
   reach Indico), **Then** the chat's error message carries the offer. The report has no reported answer, and its
   copy ends at the question.
4. **Given** any offer, **Then** nothing is sent until the user presses Send in the form. The assistant never sends
   a report by itself.
5. **Given** the user changes the thumbs down to a thumbs up, or takes it back, **Then** no new offer appears. An
   offer already shown stays.

---

### Edge Cases

- **Navigation**: an offer, an open form or a "Report sent" note under an answer is not drawn again after the panel
  reloads on the next page. The Report button in the title bar is always there. A form not yet sent is lost with the
  page, and the user starts it again.
- **The conversation is deleted or purged** after a report: the report and its copy stay unchanged.
- **Very long conversations**: the copy holds the 50 messages that end at the reported answer (or at the latest
  message). The copy says when earlier messages were left out.
- **An answer is still being prepared**: an offer exists only under a finished answer or a failure. The title bar's
  Report works meanwhile, and copies the messages finished so far.
- **The user deletes a report an admin has open**: the admin's next save or reload says the report no longer
  exists.
- **The assistant is unavailable**: the form says the report could not be sent and keeps the text, so the user can
  try again. The chat and Indico keep working (constitution IV).
- **Too many reports**: a user can send at most 20 reports a day. Past that, the form says when they can send again.
- **The plugin is disabled**: no panel, no profile item and no admin page. Stored reports stay until it is enabled
  again.
- **Merged Indico accounts**: reports move to the account that remains.
- **Chat actions** (spec 019): a copy includes the plan an answer proposed, as the chat showed it. A report never
  confirms, cancels or changes a plan.
- **Text limits**: the user's text is at most 5,000 characters and the team's note at most 2,000.
- **Two admins at once**: a save from a page opened before the other admin's save is refused, and the page shows the
  current status and note. Nothing is overwritten silently.

## Requirements *(mandatory)*

### Functional Requirements

**Sending a report (US1)**

- **FR-001**: Users MUST be able to open a report form at any time, from a Report button in the panel's title bar,
  including while an answer is being prepared. Opening the form or sending a report MUST NOT send a message to the
  assistant, and MUST NOT create or name a conversation.
- **FR-002**: The form MUST appear inside the chat panel, as part of the conversation. It MUST ask for a category
  (bug, feature suggestion, or wrong or poor answer) and the user's text. It MUST offer "Attach this conversation",
  ticked by default and shown only when there is something to attach. It MUST have Send and Cancel buttons.
- **FR-003**: When "Attach this conversation" is ticked, the report MUST store a copy of the conversation, taken when
  it is sent: up to 50 messages ending at the reported answer, or at the latest message when the report has no
  answer. The copy MUST include, for each message, its text, time and the page it was sent from. For each answer it
  MUST also include what was recorded with the answer when it was made (FR-003b). The copy MUST NOT include email
  or IP addresses.
- **FR-003a**: A report MUST copy only a conversation of the user sending it, and a reported answer MUST belong to
  that conversation. Anything else is refused, with the same refusal whether the conversation exists or not
  (FR-014).
- **FR-003b**: Each answer MUST record, when it is made, the evidence triage needs: its sources, the generated
  query, confidence, success or error, any chat-action plan it showed, the question's classified intent and its
  confidence, the row count, a check's rejection, the number of correction attempts, and whether it was cached.
  Answers made before this feature carry only what they recorded then (sources, query, confidence, error, plan).
  The copy never reconstructs evidence from the query log.
- **FR-004**: When the box is unticked, the report MUST store only the category and the text, plus the user and the
  time.
- **FR-005**: A report MUST be stored at most once per form, however many times Send is pressed.
- **FR-006**: After sending, the chat MUST confirm it with a link to the user's reports. The link opens in the
  Indico page (spec 020 FR-006b).
- **FR-007**: The form MUST follow the panel's look (light or dark), and MUST work with the keyboard and a screen
  reader. The categories form one labelled choice, and the result of Send is announced.
- **FR-007a**: The messages this feature adds to the chat (offers, forms, "Report sent") MUST NOT carry thumbs.
- **FR-008**: Report sending MUST be limited to 20 reports per user per day. Sending the same form again (FR-005)
  MUST NOT count again. It MUST NOT count against the chat's question limit.

**Suggesting a report (US4)**

- **FR-009**: After the user gives an answer a thumbs down, the chat MUST offer "Report a problem" for that answer,
  once. The form opens with "Wrong or poor answer" selected and the thumbs-down comment as its text.
- **FR-010**: An answer that failed, was refused as outside what the assistant can do, or answers a chat-action
  request the assistant did not understand or cannot make MUST carry the "Report a problem" offer. Which of these
  an answer is MUST be recorded with it when it is made, not guessed from its text.
- **FR-010a**: A question that got no answer (a timeout, a failed worker, Indico unreachable) MUST get the offer
  on the chat's error message. That report has no reported answer, and its copy ends at the question.
- **FR-011**: The assistant MUST NOT send a report without the user pressing Send.

**Seeing reports (US2)**

- **FR-012**: A user's Indico profile MUST show an "Assistant reports" item once they have sent a report. It lists
  their reports, newest first, with category, date, status, the team's note and when the team last updated it.
- **FR-013**: A user MUST be able to read each of their reports in full: their text, and the copied messages as the
  chat showed them. The evidence of FR-003b is shown only to admins, on the page and in the API.
- **FR-013a**: A user MUST be able to delete their own report, whatever its status, after confirming. The report and
  its copy are deleted at once.
- **FR-014**: A user MUST only ever see their own reports. This is checked by Indico on every request, and a refusal
  does not reveal whether a report exists. Indico admins may also see another user's reports from that user's
  profile, as Indico's other profile pages allow.

**Triage (US3)**

- **FR-015**: Indico admins, and only they, MUST have an "Assistant reports" page in the admin menu. The menu item
  shows the number of open reports. The page lists all reports, newest first, a page at a time, and can be
  filtered by status and category.
- **FR-016**: An admin MUST be able to open any report and read its text and copy, with the reported answer marked
  and its evidence shown (FR-003b).
- **FR-017**: An admin MUST be able to set the status (open, under review, closed) and edit one note. Each save
  records the admin and the time. Any status can follow any other. A save made from an out-of-date view of the
  report MUST be refused, never applied over the newer state.
- **FR-018**: Admins MUST read reports only through their copies. Nothing on the triage page reads the reporting
  user's live conversation.

**Storage and retention**

- **FR-019**: Reports MUST be stored in the plugin's own schema. A report does not point at the live conversation. It
  keeps its copy, unchanged, when the conversation is deleted or purged.
- **FR-020**: A closed report MUST be deleted, with its copy, once it has been closed for the report retention
  period. This is a new admin setting, 365 days by default, where 0 means keep forever. Open reports and reports
  under review MUST NOT be deleted by retention. Reopening a report clears when it was closed, so its count starts
  again at its next closing. Saving only a note does not change when a report was closed.
- **FR-021**: Everything the form, the profile page and the admin page do MUST also be available through the
  assistant's authenticated API, with the same permission checks (constitution II).
- **FR-022**: A request that changes a report and is authenticated by the Indico session (the profile and admin
  pages) MUST pass Indico's CSRF check. Only calls with the assistant's own token may skip it.

### Key Entities

- **Issue report**: one report from one user. It has a category, the user's text, a status, the team's note, who
  last changed the status or note and when, when it was sent, and when it was closed (empty unless closed). It
  optionally has a conversation copy. It does not point at the live conversation. The copy marks the reported
  answer. It has a form key, unique per user, so a second Send of the same form finds the first report instead of
  making another.
- **Conversation copy**: a frozen snapshot, taken when the report is sent. It holds up to 50 messages with their
  times, pages and recorded evidence, and marks the reported answer. It notes whether earlier messages were left
  out. It is never updated afterwards.
- **Status**: open, under review or closed. New reports are open.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a scripted browser walk on the local stack, a user sends a report from an offer and one from the
  title bar's Report button. Each takes at most three choices besides typing, and each is listed on the user's profile page right
  after (10 of 10 runs).
- **SC-002**: After a thumbs down, the offer appears in 10 of 10 tries. It appears under 10 of 10 answers that failed
  or were refused, and on 10 of 10 questions that got no answer (a forced timeout or worker failure). In the same
  runs, zero reports exist that the user did not send, and a double-clicked Send makes one report.
- **SC-003**: Automated tests show that a non-admin can neither read another user's report nor reach the admin page
  or its API, by page or by API, and that the refusal is the same for a report that does not exist. They also
  show that a report naming another user's conversation, or an answer from a different conversation, is refused
  and stores nothing (FR-003a).
- **SC-004**: Automated tests show that the copy stays unchanged when the conversation is continued, deleted or
  purged. They also show that an unticked report stores nothing from the conversation, that no copy holds an email
  or IP address, that a user's view of a report holds no evidence, and that a deleted report leaves nothing behind.
- **SC-005**: Automated tests show that retention deletes a closed report past the period and keeps every open or
  under-review report, whatever its age, including one closed longer ago than the period and then reopened.
- **SC-006**: An admin's status or note change shows on the user's profile page at its next load, in every test.
- **SC-007**: No regression. Every existing automated test and browser check of the chat panel passes unchanged.

## Assumptions

- **Logged-in users of the panel only**: reports come from the chat panel (spec 020), which only logged-in users
  have. The API is there for other clients, but no other page offers a form.
- **Admins see everything anyway**: Indico core admins can already open every event and every piece of material, so
  a copy shows them nothing about Indico they could not see. What the user consents to is sharing their own words.
- **The profile page is the plugin's first HTML page**: the plugin has served only JSON and the chat panel so far.
  Whichever of this feature and the GitHub connection (thread D) is built first sets the pattern for templates and
  profile menu items. The other follows it.
- **The Indico menu names** are `user-profile-sidemenu` and `admin-sidemenu`, checked against Indico 3.3.13.
- **One note per report**: it is overwritten, not a thread. The status history beyond "last changed by and when" is
  not kept.
- **The user can't edit a report once it is sent.** They can delete it and send a new one.

## Out of Scope

- Email or any other notification, to users or admins (decided 2026-09-29).
- Copying reports to GitHub or another tracker (decided; can follow thread D).
- A configurable triage group beyond Indico admins.
- Editing a sent report, and replies or comment threads between the user and the team.
- Spotting a user rephrasing the same question as a sign that things are going badly.
- Screenshots or files attached to a report.
- Drawing offers and forms again after the panel reloads on the next page.

## Notes for the plan (prototype, 2026-09-29)

A throwaway Chainlit 2.12.0 app, run headless in Chrome at a panel's 480 px width, showed:

- **The form**: a `cl.CustomElement` (a JSX file in `public/elements/`) built from Chainlit's own Button, Textarea,
  Checkbox and Label renders as one card inside the conversation. Its Send calls `callAction`, which reaches an
  `@cl.action_callback` on the server with the form's values, and the callback's return value comes back to the
  card. There is no timeout, unlike `AskActionMessage` and `AskElementMessage`, and the page loads nothing from
  Chainlit. Three toggle buttons worked better than a select for the categories: nothing opens as a pop-up in a
  narrow frame.
- **The Report button in the title bar**: `#assistant-panel-bar` (`static/js/chat_widget.js`) is the page's own
  chrome, next to `#assistant-panel-close`. It can post `{source: "indico-assistant", type: "report"}` to the frame.
  Chainlit's front end forwards every `window.postMessage` it receives to the server as `window_message`, and
  `@cl.on_window_message` runs with the session's context, so it can send the form. Any sender can post that
  message, so it carries nothing but "open an empty form". To check in the plan: the handler runs while an
  `on_message` run is still going, and the form in a new, empty chat creates no Indico session.
- **Why not a composer command** (`emitter.set_commands`, `button: True`), which the first draft used. The composer
  is disabled while a run is in progress, for up to `ANSWER_TIMEOUT` (180 s). A new chat's first message goes
  through `init_thread(message.content)` whether or not `message.command` is set (`chainlit/emitter.py:281`), so
  the data layer's `update_thread` PUTs `/sessions/<id>` and titles the chat with the report text. Removing the
  user's message also removes the form sent after it.
- **The thumbs-down offer**: `@cl.on_feedback` (`chainlit/callbacks.py:495`). `PUT /feedback`
  (`chainlit/server.py:914`) runs it with `init_ws_context` for the request's session, after
  `IndicoDataLayer.upsert_feedback` has succeeded. It takes `forId` and `comment` from the saved `Feedback`, so no
  frame script or window message is needed. (The first draft's route through the frame was wrong: it missed this
  hook.)
- **No thumbs on report messages** (FR-007a): Chainlit draws thumbs on every run's messages while data persistence
  is on. `on_feedback` and `on_window_message` are not runs, but anything sent from an `on_message` run is.
- **The evidence gap** (FR-003b): the answer's `metadata_json` has only `sql_generated`, `confidence`,
  `data_sources`, `pipeline_success`, `pipeline_error`, `suggested_followups` and `write_request`
  (`services/chat/service.py:503`). Intent, row count, a rejection, corrections and cached are only in
  `query_audit_log`, which has no message id. `_process_with_nl2sql` doesn't pass `session_id` to
  `pipeline.process`, so its rows have none. The log can be turned off (`audit_enabled`), and it is purged after
  `retention_audit_days`. `PipelineResult` has no intent, cached or rejection field. So the pipeline must return
  them, and the answer must store them in its metadata.
- **Failure flags** (FR-010): a planner answer stores only `{"plan_id": ...}`. It replies with `draft.reply or
  NOT_UNDERSTOOD` when there are no steps (`services/actions/planner.py:143`), with `NOT_SUPPORTED`, or with a
  refusal. A model-written reply never equals the constant, and the Chainlit app doesn't import
  `indico_assistant`, so the planner must record a flag (for example `not_understood: true`).
- **Failures with no answer** (FR-010a): on a soft time limit, `QUERY_PROCESSING_ERROR` or `INTERNAL_ERROR`,
  `tasks/chat.py` rolls back and stores no assistant message. A thumbs down on the error message can't be stored
  either, because `POST /feedback` finds no message.
- **Retention**: `tasks/cleanup.py`'s `RETENTION` list takes the reports table keyed on `closed_at`. Rows with no
  `closed_at` never match, which is exactly FR-020.
- **No-regression baseline** (SC-007): `pytest tests/unit tests/contract` passes 1207 at `2e52051`. The browser
  checks in `tests/browser/` are `walk`, `sc003`, `us4`, `hover`, `feedback`, `tabs` and `sidebar`. `tabs` and `us4`
  cover new chats and Past Chats, which FR-001 touches.
- **One report per form, one count per report** (FR-005, FR-008): each `callAction` is its own
  `POST /project/action`, and these are handled concurrently, so "look for it, then insert" lets a double click
  through twice. Use a unique `(user_id, form_key)`, insert with `ON CONFLICT DO NOTHING`, and count against a new
  `report` entry in `RATE_LIMITS` (`services/chat/rate_limiter.py`) only when a row was created.
  `RHChatBase.RATE_LIMIT` can't do this, because it counts in `_check_access`, before the handler runs.
- **CSRF** (FR-022): `RHAssistantBase` sets `CSRF_ENABLED = False` (`controllers/base.py:34`) but also accepts the
  Indico session cookie. The profile and admin pages' saves must keep Indico's CSRF check. Outside this spec: the
  existing cookie-authenticated writes may share the gap, and are worth checking.
