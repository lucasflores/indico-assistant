# Feature Specification: Creating and editing meetings from the chat (chat actions)

**Feature Branch**: `025-chat-actions`
**Created**: 2026-09-27
**Status**: Draft
**Input**: User description: "Allow the user to create a meeting from the chat, e.g. 'Create a Teams meeting for today at 2pm with Makoto, add both of us as contributors with 20 min slots.' Take advantage of what Indico already does and be as native to it as possible."

## Context

Today the assistant answers questions by having an LLM write SQL (NL2SQL), run through a read-only
database role with row security. That design cannot write: writing rows directly would bypass everything
Indico does around a change (permission checks, validation, signals such as the one that makes `vc_teams`
create the Teams meeting, the event log, notifications).

This feature adds **actions**: a small catalogue of typed operations the LLM can plan, which the plugin
carries out with Indico's own functions (`create_event`, `create_contribution`, `schedule_contribution`,
the VC room creation sequence) after the same permission checks Indico's pages perform. Nothing is written
until the user has seen the complete plan and confirmed it.

Decided 2026-09-27 (approach "B + E" of the design review):

- **B** — typed actions in-process on Indico operations, with each action's permission check mirroring the
  page that does the same thing by hand. Not NL2SQL writes; not Indico's web endpoints (form-coupled, need
  an `full:everything` token); not an external MCP server.
- **E** — every write goes through a plan the user confirms.

The NL2SQL read path is unchanged by this feature. Moving common reads to typed actions is planned for
later (see Out of Scope).

## Clarifications

### Session 2026-09-27

- Q: Which category does a meeting go into when the user does not say? → A: **Always ask** when not
  specified: list the categories the user can create events in, and suggest one based on context (e.g.
  where their similar meetings live), with the reason.
- Q: How much should the assistant add beyond what was asked? → A: As frictionless as possible **but with
  rich data**: the assistant offers suggestions drawn from context (the current chat, the user's earlier
  chats, their past events) — a description, agenda items, material to attach, people who usually attend.
  Suggestions are offered, never applied without the user's acceptance.
- Q: Move common reads off NL2SQL now? → A: **Later**; not in this feature.
- Q: Expose actions through MCP? → A: **Later**; not in this feature.
- Q: What does "with Makoto" make him? → A: Always a **Teams invitee** and an **Indico reminder recipient**;
  a **speaker** only when slots/contributions are mentioned (OQ-1).
- Q: How are categories ranked? → A: **Both** the user's recent activity and the chat's topic (OQ-2).
- Q: Suggest a time when none is given? → A: **Yes** (OQ-3), see US8.
- Q: Admin control over actions? → A: **Yes**: an admin can enable or disable each action (OQ-4), FR-021.
- Q: Can a file sent in the chat be attached ("attach this to my contribution")? → A: **Yes**, see US9.
- Q: How far back can undo reach? → A: Any plan confirmed in the **last 24 hours**, from any chat.
- Q: Upload limits? → A: pdf, docx, pptx, xlsx, txt, md, png, jpg; 25 MB per file; 5 files per message.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create a meeting from one sentence (Priority: P1)

Lucas types "Create a Teams meeting for today at 2pm with Makoto, add both of us as contributors with 20 min
slots." The assistant replies with a plan card: *meeting "Sync with Makoto", today 14:00–14:40
(Europe/Zurich), category — which one?* with his categories listed and one suggested. He picks the
suggested one and confirms. The meeting exists in Indico with a Teams room (Makoto co-organizer, invites
sent) and two 20-minute contributions with Lucas and Makoto as speakers. The reply links to the event.

**Why this priority**: this is the capability.

**Independent Test**: on the local instance with vc_teams in fake-Graph mode, send the sentence above as a
user who manages a category, confirm the plan, and check the event, its timetable, speakers and Teams room
in Indico's own UI; the event log shows each change attributed to the user.

**Acceptance Scenarios**:

1. **Given** a user who can create events in at least one category, **When** they ask for a meeting with a
   date, time and people, **Then** the assistant shows a plan with every object to be created, resolved
   people, times in the user's timezone, and any question it needs answered (e.g. the category).
2. **Given** the plan is confirmed, **When** it is carried out, **Then** the event, its contributions,
   speakers and Teams room are created through Indico's operations, appear in Indico exactly as if made
   through its pages, and each change is in the event log attributed to the user.
3. **Given** the slots add up to more than the meeting length (or no end time was given), **When** the plan
   is built, **Then** the meeting's end is set to fit the slots and the plan says so.
4. **Given** a successful run, **Then** the reply links to the new event and lists what was created.

---

### User Story 2 - Nothing happens without confirmation (Priority: P1)

Every change the assistant would make is shown first. The user can confirm, cancel, or change the plan in
plain language ("make it 30 minutes", "not Makoto Tanaka, Makoto Sato") and see the updated plan.

**Why this priority**: actions send emails and Teams invites and change shared data; a misunderstood
sentence must cost nothing.

**Independent Test**: send a create request and cancel it — nothing is written and no Teams call is made;
send it again, amend it twice, confirm — only the final version is created.

**Acceptance Scenarios**:

1. **Given** a plan is shown, **When** the user cancels or ignores it, **Then** nothing is written in Indico
   or Teams; an unconfirmed plan expires after 30 minutes.
2. **Given** a plan is shown, **When** the user asks for a change, **Then** a revised plan replaces it and
   only the revised one can be confirmed.
3. **Given** a plan is confirmed twice (double click, two tabs), **Then** it is carried out once.
4. **Given** permissions or data changed between showing and confirming (e.g. the user lost management
   rights), **When** the user confirms, **Then** every check runs again and the plan is refused with the
   reason, writing nothing.
5. **Given** text inside an event, note or document the assistant read contains instructions, **Then** it can
   at most influence a plan the user still sees and must confirm; no action runs from content alone.

---

### User Story 3 - Choosing the category (Priority: P1)

When the user does not name a category, the plan asks for one: it lists the categories where the user may
create events (their names and paths, most relevant first) and marks a suggestion with its reason ("your
last 5 team syncs are in *Thoth » Engineering » Meetings*"). The user can pick from the list or name one in
chat.

**Why this priority**: Indico requires a category; guessing wrong puts a meeting where its audience cannot
see it.

**Independent Test**: as a user with create rights in three categories, one of which holds their recent
meetings, ask for a meeting without a category: the plan lists the three and suggests the right one.

**Acceptance Scenarios**:

1. **Given** no category in the request, **Then** the plan lists only categories where
   `category.can_create_events(user)` is true, and suggests one with a stated reason.
2. **Given** the user can only *propose* events in a category (`can_propose_events`), **Then** that category
   is listed as "propose (needs approval)" and choosing it creates the meeting unlisted and requests its
   publication in the category (Indico's own proposal path, which needs unlisted events enabled; when they are
   not, the category is not offered and the assistant says why).
3. **Given** the user names a category ("in Engineering"), **Then** it is matched against the allowed list; an
   ambiguous or unknown name is shown back with the closest matches.
4. **Given** the user has no category they can create or propose events in, **Then** the assistant says so
   and who to ask, and offers no plan.

---

### User Story 4 - Finding the right people (Priority: P1)

"Makoto" becomes a specific person. If one user matches, the plan shows their full name and email. If several
match, the assistant asks which one. If none match, the user can add the person by name and email as a
speaker who is not an Indico user.

**Why this priority**: the wrong Makoto gets the invite.

**Independent Test**: with two users named Makoto, the plan asks which; with one, it shows name and email;
with an unknown name, it offers "add as a guest speaker (name, email)".

**Acceptance Scenarios**:

1. **Given** a name, **When** it is looked up, **Then** the search follows the same rules as Indico's own user
   search (`ALLOW_PUBLIC_USER_SEARCH`, no deleted/blocked users) and uses the user's context to rank
   (people in their past events and chats first).
2. **Given** several matches, **Then** the assistant asks, showing enough to tell them apart (email,
   affiliation) — it never picks silently.
3. **Given** a person with no Microsoft 365 account in the tenant, **Then** the plan says they will be a
   speaker but not a Teams co-organizer (they can still join via the link).
4. **Given** "both of us", **Then** the requesting user is included as themselves.
5. **Given** "with Makoto" and no slots, **Then** Makoto is a Teams invitee and a recipient of the event
   reminder, not a speaker; **given** slots, he is also the speaker of his slot.

---

### User Story 5 - Suggestions from context (Priority: P2)

With the plan, the assistant offers optional additions based on what it knows: a title and short description
from the conversation, agenda items discussed earlier in the chat, people who attended the user's previous
meetings on the same topic, the previous meeting's minutes or documents as material, the usual duration of
this kind of meeting. Each suggestion says where it came from and is unchecked unless the user accepts it.

**Why this priority**: this is what makes a two-line request produce a well-filled event; it is also where
the assistant can overreach, so it follows the rules below.

**Independent Test**: after chatting about "the Q4 budget review", ask for a meeting about it: the plan
suggests a title and description drawing on the chat, the attendees and material of the user's last Q4
budget meeting, each with its source; accepting two suggestions creates exactly those two additions.

**Acceptance Scenarios**:

1. **Given** context is available, **Then** suggestions appear as a separate, optional part of the plan, each
   with its source ("from this chat", "from *Q3 budget review*, 12 Aug").
2. **Given** a suggestion, **Then** it only uses information the user can see (Indico's `can_access` for
   events and material; the user's own chat sessions only).
3. **Given** the user accepts some suggestions, **Then** only those are added; declining costs nothing.
4. **Given** no useful context, **Then** no suggestions are shown (no filler).

---

### User Story 6 - Adjusting what was just created (Priority: P2)

Right after creating it — or later, naming it — the user can say "move it to 3pm", "add a 10 minute Q&A
at the end", "add Kaori as a speaker in the second slot". Each is a plan to confirm, applied to an event the
user manages, and Teams follows (vc_teams moves the meeting when the event's times change).

**Why this priority**: real requests come in several turns.

**Independent Test**: create a meeting, then "move it to 3pm" and confirm: the event, its contributions and
the Teams meeting all move by one hour.

**Acceptance Scenarios**:

1. **Given** an event created in this chat, **Then** "it" refers to that event; otherwise the user names it
   and the assistant resolves it among events they manage (asking if ambiguous).
2. **Given** the user does not manage the event, **Then** the change is refused with the reason.
3. **Given** a time change, **Then** the plan shows the contributions moving with the event.

---

### User Story 7 - Undo (Priority: P3)

"Undo that" reverses a plan the user confirmed in the last 24 hours (from any chat; the assistant lists them
when there is more than one), after confirmation: objects it created are
deleted (the Teams meeting is cancelled); changes it made to existing objects are restored.

**Why this priority**: a safety net; less important once confirmation works.

**Acceptance Scenarios**:

1. **Given** the last plan created an event, **When** undo is confirmed, **Then** the event is deleted through
   Indico's own deletion (which cancels the Teams meeting and notifies as Indico does).
2. **Given** others have changed the objects since, **Then** undo lists what differs and asks before
   proceeding.

### User Story 8 - Suggesting a time (Priority: P2)

"Set up 30 minutes with Makoto this week" — the plan proposes two or three slots when both are free, with
the reason ("you both have nothing in Indico or Outlook on Thursday 10:00–11:00").

**Why this priority**: removes the back-and-forth of finding a time; the user asked for it.

**Acceptance Scenarios**:

1. **Given** no time in the request, **Then** the plan proposes up to three slots within working hours, and
   the user picks one (or names another).
2. **Given** availability sources, **Then** the plan uses Indico (events the people manage, chair, speak in
   or are registered for) and, where the tenant allows it, Outlook free/busy through Microsoft Graph; the
   plan says which sources were used.
3. **Given** a person whose availability cannot be read, **Then** the plan says so rather than assuming they
   are free.

---

### User Story 9 - Attaching a file sent in the chat (Priority: P2)

The user drops a PDF into the chat and says "attach this to my contribution to the meeting". The plan
shows the file, the contribution it will go to, and the folder; on confirmation the file is an Indico
attachment of that contribution, exactly as if uploaded through the contribution's material page (and the
document index picks it up).

**Why this priority**: a common follow-up to creating a meeting, and the same confirm-before-write path.

**Independent Test**: as the speaker of a contribution, upload a PDF in the chat and ask to attach it to
"my contribution": the plan names the right contribution; after confirming, the file is listed in the
contribution's material, logged as the user's upload.

**Acceptance Scenarios**:

1. **Given** a file sent in the chat, **Then** it is stored as an Indico unclaimed file (auto-deleted by
   Indico if never used) and the assistant can refer to it in the conversation.
2. **Given** "my contribution", **Then** it resolves to contributions where the user is a speaker (asking if
   several), and the plan is refused unless `can_manage_attachments(contribution, user)` holds.
3. **Given** the plan is confirmed, **Then** the file becomes an attachment through the same steps as
   Indico's upload page (attachment + file, `attachment_created` signal, event log).
4. **Given** a file type or size the instance does not allow, **Then** the upload is refused in the chat
   with the limits.
5. **Given** the assistant reads the file to make suggestions (e.g. a title), **Then** its content is data
   only (FR-017).

### Edge Cases

- **Time in the past** ("today at 2pm" at 3pm): the plan flags it and asks (tomorrow? keep?).
- **Timezones**: times are in the user's Indico timezone unless stated; the plan always shows the timezone.
  Relative dates ("next Tuesday") resolve against the user's local date, shown explicitly.
- **Clash**: the user (or a named person) already has an event they manage or speak in at that time — the plan
  warns, it does not block.
- **Teams unavailable** (plugin not installed, user not allowed to create Teams rooms, Graph failing): the
  plan says so before confirmation; at execution, a Teams failure rolls back the whole plan.
- **Partial failure** at execution: Indico objects are created in one transaction and the Teams meeting last;
  any failure leaves nothing behind (a created Teams meeting is cancelled).
- **Vague request** ("set up something with Makoto"): the assistant asks the one or two questions it needs
  (when? how long?) rather than inventing values; defaults it does use (duration 30 min) are shown.
- **The LLM produces an invalid plan** (unknown action, bad arguments): it is regenerated once with the
  errors, then the assistant asks the user a question instead of failing opaquely.
- **Large requests** (a 20-talk workshop): allowed, but plans above 25 steps are refused with a suggestion to
  use Indico's timetable directly.
- **Rate limits**: plans count against the chat limit; carrying out a plan does not count twice.

## Requirements *(mandatory)*

### Functional Requirements

**Actions**

- **FR-001**: The assistant MUST have a catalogue of typed actions, each with a JSON-schema argument model, a
  permission check, a human-readable description for the plan, and an executor built on Indico operations.
  v1 catalogue:

  | Action | Carried out with | Permission check (mirrors) |
  |---|---|---|
  | `find_person` | `search_users` (+ EventPerson for guests) | Indico user search rules |
  | `list_categories` | category tree | `can_create_events` / `can_propose_events` |
  | `create_event` | `create_event(category, EventType.meeting, …)` | `category.can_create_events(user)` |
  | `propose_event` | unlisted `create_event` + `create_event_request` (Indico has no propose-on-create path) | `can_create_unlisted_events(user)` and `category.can_propose_events(user)` |
  | `update_event` | `update_event` (title, description, times, location) | `event.can_manage(user)` |
  | `add_contribution` | `create_contribution` + `schedule_contribution`, `person_link_data` (speakers) | `event.can_manage(user)` |
  | `update_contribution` | `update_contribution` / `update_timetable_entry` | `contribution.can_manage(user)` |
  | `add_teams_room` | the VC creation sequence of `RHVCManageEventCreate` (vc_teams `create_room`, `vc_room_created` signal, notification) | `plugin.can_manage_vc_rooms(user, event)` and `event.can_manage(user)` |
  | `attach_link` | `add_attachment_link` (takes a form object: a small adapter supplies the same fields) | `can_manage_attachments(obj, user)` |
  | `attach_file` | the steps of Indico's upload page (`Attachment` + `AttachmentFile.save`, `attachment_created`), from a chat upload | `can_manage_attachments(obj, user)` |
  | `add_reminder` | an `EventReminder` as the reminders page creates it (`send_to_speakers` + explicit invitee emails) | `event.can_manage(user)` |
  | `suggest_times` (read) | Indico involvement queries; Graph `getSchedule` where permitted | people the user could find via user search |
  | `delete_created` (undo only) | Indico's deletion operations | object created by this plan, `can_manage` |

- **FR-002**: Actions MUST NOT write through SQL, and MUST NOT call Indico's web endpoints; they call the
  same operation functions Indico's pages call, so signals, the event log and notifications behave as for a
  manual change.
- **FR-003**: Each action's permission check MUST match the corresponding Indico page's check; a parity test
  per action asserts refusal exactly when the page refuses.

**Plans and confirmation**

- **FR-004**: The LLM MUST produce a **plan**: an ordered list of actions with arguments, questions for the
  user, and optional suggestions. Plans are produced as structured output (instructor, prompt-JSON), so any
  provider works, including the ibis router; native tool calling can replace this later without changing
  actions.
- **FR-005**: The plan MUST be validated (schema, references between steps, permission pre-checks) before it
  is shown. Invalid plans are regenerated once, then turned into a question for the user.
- **FR-006**: The user MUST see the complete plan in plain language — every object, time with timezone,
  person with email, category path, side effects ("Teams invites will be sent to …") — and confirm it with an
  explicit action (a button in the chat, or "yes, create it").
- **FR-007**: No action with side effects may run without confirmation of the exact plan shown; a revised
  plan invalidates the previous one. Plans expire 30 minutes after being shown.
- **FR-008**: Confirmation MUST be idempotent (a plan runs at most once) and MUST re-run every permission check
  at execution time.

**Execution**

- **FR-009**: A confirmed plan MUST run in the Celery worker (queue `assistant`), as the confirming user, inside
  a request context where `session.user` is that user (Indico operations read it).
- **FR-010**: Indico changes MUST be made in one transaction; external side effects (the Teams meeting) run
  last; on any failure everything is rolled back and a created Teams meeting is cancelled.
- **FR-011**: Every change MUST appear in Indico's event log as the user's; the plugin additionally records
  the plan (steps, confirmation time, outcome) for undo and audit.
- **FR-012**: Plans MUST NOT exceed 25 steps.

**Context and suggestions**

- **FR-013**: Category: when not specified, the plan MUST ask, listing allowed categories (create and propose
  separately), ranked by relevance to the user, with one suggestion and its reason.
- **FR-014**: People: resolution MUST follow Indico's user-search rules; ambiguity MUST be asked, never
  guessed; unknown people can be added as guest speakers with name and email.
- **FR-015**: Suggestions MAY draw on: the current chat; the user's own earlier chat sessions (within
  retention); events the user created, manages or speaks in (last 12 months); material and minutes of those
  events the user can access. Each suggestion MUST name its source and MUST be opt-in.
- **FR-016**: Context used for plans and suggestions MUST respect Indico access (`can_access` /
  `can_manage`); the user's chats are never mixed with anyone else's.
- **FR-017**: Content read from Indico (descriptions, notes, documents, transcripts) is data, not
  instructions: it may shape suggestions but MUST NOT add actions to a plan on its own, and every action still
  needs confirmation (FR-007).

**Reminders and invitees**

- **FR-022**: Invitees who are not speakers MUST receive the Teams invitation and be explicit recipients of an
  event reminder; speakers are covered by the reminder's `send_to_speakers`. The reminder's default timing
  (e.g. 15 minutes before) is an admin setting, shown in the plan and editable.

**Times**

- **FR-023**: When no time is given, the plan MUST propose up to three slots from the availability of the user
  and the named people, stating the sources used; Outlook free/busy (Graph `calendar/getSchedule`,
  permission `Calendars.ReadBasic`) is used only if the tenant probe confirms it works with the scoped
  service-account setup, otherwise Indico-only.

**Chat uploads**

- **FR-024**: Chainlit MUST accept file uploads again (disabled in Phase 1 because files were ignored), limited
  to pdf, docx, pptx, xlsx, txt, md, png, jpg and 25 MB per file (enforced by the plugin: Indico has no
  attachment type allowlist and no default size limit; `MAX_UPLOAD_FILE_SIZE` applies when set), and forward
  them immediately (Chainlit deletes its copies when the session ends) to a new Indico
  endpoint that stores them as unclaimed `File`s owned by the user and tied to the chat session.
- **FR-025**: An uploaded file MUST only be usable by its uploader, and is claimed (copied into an
  `AttachmentFile`) only by a confirmed `attach_file` step; unused uploads are removed by Indico's own
  unclaimed-file cleanup.

**Administration**

- **FR-021**: An admin setting MUST enable or disable each action individually (and all writes at once);
  a disabled action is never planned, and the assistant says it is not available.

**Integration**

- **FR-018**: Write intents MUST be recognised in the existing chat flow (classification), routed to planning;
  read questions keep going to NL2SQL unchanged.
- **FR-019**: Plans and their state are exposed to Chainlit through the chat job response (a `plan` object with
  a confirm token); Chainlit renders the plan and confirm/cancel buttons.
- **FR-020**: Each LLM call made for planning is recorded (model, tokens, cost) like the existing calls.

### Key Entities

- **ActionPlan**: user, chat session, steps, questions, suggestions, status (draft → shown → confirmed →
  running → done / failed / cancelled / expired), confirm token, shown/confirmed/finished times, result
  (created object ids), error.
- **PlanStep**: action name, validated arguments, references to earlier steps' results (e.g. the event id),
  human-readable description, side effects.
- **Suggestion**: kind (description, agenda item, person, material, duration), content, source (chat, event,
  document), accepted flag.
- **Action (code)**: argument schema, `check(user, args)`, `describe(args)`, `execute(user, args)`, and for
  undo `revert(result)`.

## Out of Scope (v1)

- Moving read questions from NL2SQL to typed actions (planned next).
- An MCP server exposing the actions (planned later).
- Registration forms, room booking, abstracts, paper reviewing, recurring event series.
- Deleting or bulk-editing pre-existing events (only undo of the assistant's own plans).
- Long-term assistant memory beyond chat history (FR-015 uses what Indico and the chat tables already hold).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The example request produces a correct confirmed meeting in at most two assistant turns plus one
  confirmation (one turn if the category is named).
- **SC-002**: Zero writes without confirmation, verified by tests that drive every action path with an
  unconfirmed, expired, revised and double-confirmed plan.
- **SC-003**: Permission parity: for every action, the assistant refuses exactly when the corresponding Indico
  page refuses (parity tests across admin, manager, submitter and unrelated users).
- **SC-004**: On a new eval set of 50 meeting requests (varied phrasing, dates, people, ambiguity), ≥ 90 %
  produce the intended plan or ask the right question; 0 % create something the user did not ask for.
- **SC-005**: Plan shown in ≤ 10 s (p50) and carried out in ≤ 15 s (p50) including the Teams meeting.
- **SC-006**: A failed execution leaves no Indico objects and no Teams meeting behind (fault-injection tests).

## Assumptions

- `vc_teams` is installed for Teams requests; without it the assistant can still create meetings without a
  Teams room.
- Users have a timezone set in Indico (else the instance default).
- Chainlit renders the plan (Chainlit supports action buttons); the Indico side exposes the plan as data.
- The LLM provider handles structured output via prompt-JSON (as today).

## Open Questions

- ~~OQ-1~~ resolved: invitee = Teams invite + reminder recipient; speaker only with slots (FR-022).
- ~~OQ-2~~ resolved: rank categories by both recent activity and chat topic.
- ~~OQ-3~~ resolved: suggest times (US8, FR-023); Outlook free/busy pending the tenant probe.
- ~~OQ-4~~ resolved: per-action admin switch (FR-021).
- ~~OQ-5~~ resolved: undo reaches any plan the user confirmed in the last 24 hours, from any chat; the
  assistant lists them and the user picks (US7).
- ~~OQ-6~~ resolved: chat uploads limited to pdf, docx, pptx, xlsx, txt, md, png, jpg; 25 MB per file; 5 files
  per message (FR-024).
