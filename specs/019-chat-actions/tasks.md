---
description: "Task list for 019 chat actions"
---

# Tasks: Creating and editing meetings from the chat (chat actions)

**Input**: Design documents from `/specs/019-chat-actions/` (plan.md, spec.md, research.md, data-model.md,
contracts/, quickstart.md)

**Tests**: required. The constitution's Principle VI is test-first. SC-002 (zero writes without confirmation),
SC-003 (permission parity) and SC-006 (no leftovers on failure) are test-defined. Each story's tests are written
first and must fail before implementation.

**Organization**: grouped by user story. Paths are relative to `~/indico-assistant/plugin/` unless absolute.
`R#` refers to research.md.

**Test commands**:

- plugin: `cd ~ && INDICO_CONFIG=~/indico-assistant/instance/indico.conf ~/indico-assistant/instance/env/bin/python -m pytest -q --rootdir ~/indico-assistant/plugin <paths>`
- vc_teams: `cd ~/indico-assistant/indico-plugin-vc-teams && INDICO_CONFIG=... <indico env python> -m pytest -q`

The 17 already-failing plugin tests (see the PR #2 baseline) must stay the only failures.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: the user story (US1–US9) the task serves

---

## Phase 1: Setup (shared infrastructure)

**Purpose**: prerequisites outside the new package: the vc_teams fixes, settings and storage.

- [x] T001 [P] In `~/indico-assistant/indico-plugin-vc-teams` (branch `002-scale`), write failing tests in `tests/test_create_room.py`:
  - `create_room` cancels the Graph event and raises `VCRoomError` when a `requests.ConnectionError` / `Timeout` happens after `create_event`;
  - it raises `VCRoomError(field='coorganizers')` for a co-organizer without a tenant email.
- [x] T002 In `indico_vc_teams/plugin.py` + `indico_vc_teams/graph.py`, make T001 pass (R5 fixes 1 and 3):
  - wrap `requests` exceptions from `_request` as `GraphError`;
  - validate co-organizers in `create_room` instead of dropping them silently.
- [x] T003 [P] In vc_teams, add `discard_pending()` to `indico_vc_teams/plugin.py`. It pops `g.vc_teams_pending_cancel`, `g.vc_teams_pending_move` and `g.vc_teams_dirty`. Add a test in `tests/test_pending.py` that a rollback followed by `discard_pending()` sends nothing at the next commit (R5 fix 2).
- [x] T004 [P] Add the settings `actions_enabled` (False), `actions_allowed` (all action names), `actions_reminder_minutes` (15), `actions_outlook_freebusy` (False) and `retention_plan_days` (90) to `indico_assistant/default_settings.py`. Add their fields to `indico_assistant/forms.py`: `BooleanField`, `IndicoSelectMultipleCheckboxField`, and `IntegerField` with `NumberRange(min=0)`. Extend `tests/unit/test_forms.py`.
- [x] T005 [P] Create the `ActionPlan` model in `indico_assistant/models/action_plan.py`, with the columns, check constraint on `status`, FKs and indexes from data-model.md. Export it in `indico_assistant/models/__init__.py`.
- [x] T006 Write migration `indico_assistant/migrations/007_create_action_plans.py` (`down_revision = '006_add_partial_sync_status'`, upgrade + downgrade). Apply it locally with `indico db --all-plugins upgrade`, then check `\d plugin_assistant.action_plans`.
- [x] T007 [P] Add `('plugin_assistant.action_plans', 'created_at', 'retention_plan_days')` to `RETENTION` in `indico_assistant/tasks/cleanup.py`, and a case to `tests/unit/tasks/test_retention.py`.

**Checkpoint**: vc_teams tests green, the migration applied, and the settings visible in the admin panel.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: running as the user, the action framework, the plan lifecycle, routing and rendering. Every story
builds on these.

### Tests first

- [x] T008 [P] `tests/unit/services/actions/test_context.py`:
  - `acting_as(user)` yields `session.user == user` **with `memoize_request` enabled** (patch `config.TESTING` off for the check);
  - `session.set_session_user` would fail the same test (regression note, R1);
  - `user_timezone(user)` / `local_today(user)` follow R11.
- [x] T009 [P] `tests/unit/services/actions/test_plan_lifecycle.py`, the state machine from data-model.md on the test DB:
  - `confirm()` succeeds once, and returns `None` for a second call, a wrong token, an expired plan, a superseded plan and a plan with open questions;
  - `cancel()` works only from `shown`;
  - `expired` is computed.
- [x] T010 [P] `tests/integration/actions/test_plan_endpoints.py`:
  - `GET /plans/<id>`, `POST /plans/<id>/confirm` and `POST /plans/<id>/cancel` status codes per contracts/api.md: 202 / 404 / 409 / 403 `INVALID_TOKEN` / 403 `ACTIONS_DISABLED`;
  - the `read` rate limit;
  - `Cache-Control: private, no-store`.
- [x] T011 [P] `tests/unit/services/actions/test_executor.py`, using a fake write action and a fake external step:
  - every step runs inside one `track_time_changes` / `track_location_changes` block;
  - a failing step rolls back everything, runs the external undo, calls `discard_pending()`, resets `g.email_queue`, and records `failed` in a new transaction;
  - a refused re-check records `refused` and writes nothing.

### Implementation

- [x] T012 `indico_assistant/services/actions/context.py`: `acting_as(user)` (R1: `session['_user_id']`, `g.pop('memoize_cache')`, assert, lang/timezone), `user_timezone`, `local_today`.
- [x] T013 `indico_assistant/services/actions/base.py`:
  - the `Action` protocol, `StepResult`;
  - `refuse_if_locked(event)`;
  - the resolved-args Pydantic base with aware-datetime validation;
  - `describe()` helpers that format times with the timezone and category paths with `' » '`.
- [x] T014 `indico_assistant/services/actions/__init__.py`: catalogue registry `ACTIONS`, `enabled_actions()` (honours `actions_enabled` / `actions_allowed`, FR-021), and `validate_plan(steps)`: 25-step cap, backward refs only, Teams step last, disabled actions refused (FR-005, FR-012).
- [x] T015 `indico_assistant/services/actions/executor.py`:
  - `create_plan(...)` (row + token, token hash, `expires_at`);
  - `revise(plan, ...)` (supersede);
  - `confirm(plan_id, user, token)` as the atomic UPDATE;
  - `cancel`;
  - `run(plan_id)`: re-check → steps in one transaction → external step last → commit, plus the R2 rollback path.
  - Makes T009 and T011 pass.
- [x] T016 `indico_assistant/tasks/actions.py`: `execute_plan(plan_id, user_id, job_id)`. Decorated `@celery.task(request_context=True, plugin='assistant', queue='assistant', soft_time_limit=60, time_limit=90)`. It runs inside `acting_as`, calls `executor.run` and reports through `jobs.finish`. Import it in `indico_assistant/__init__.py`.
- [x] T017 [P] `indico_assistant/schemas/actions.py`: `PlanView` (without args or token, except where contracts/api.md includes the token), `ConfirmRequest`. Add `plan: PlanView | None` to `ChatResponse` in `indico_assistant/schemas/chat.py`.
- [x] T018 `indico_assistant/controllers/actions.py`: `RHPlan`, `RHPlanConfirm` (queues `execute_plan`, returns a job id), `RHPlanCancel`. Register the routes in `indico_assistant/blueprint.py`. Makes T010 pass.
- [x] T019 `indico_assistant/services/llm/service.py`: optional `messages=` parameter on `generate` (chat turns before the prompt). Test in `tests/unit/services/llm/test_service.py` that existing callers are unchanged.
- [x] T020 [P] `indico_assistant/services/llm/models/plan.py`: `PlanDraft` and step models exactly as in contracts/plan-draft.md. Contract test in `tests/contract/test_plan_draft.py` that its JSON schema is valid for instructor MD_JSON, and that recorded sample drafts parse.
- [x] T021 `indico_assistant/services/actions/planner.py` skeleton:
  - `plan_turn(user, session, message, open_plan)` builds the prompt (facts, open plan, last 20 turns, fenced context block) and calls `generate(response_model=PlanDraft)` inside `collect_calls()`;
  - it regenerates once on validation errors, then falls back to a question;
  - it stores `llm_calls` on the plan (FR-020);
  - no resolvers yet: stubs raise `NotImplementedError` per draft type.
- [x] T022 Routing in `indico_assistant/services/chat/service.py` `answer()` (R13):
  - an open plan in the session → planner;
  - otherwise the classifier's `write_request` intent → planner;
  - otherwise NL2SQL, unchanged;
  - actions disabled → a fixed "not available" reply.

  Add `write_request` to `CLASSIFICATION_PROMPT` in `indico_assistant/services/nl2sql/classifier.py`. Make `answer_chat` in `indico_assistant/tasks/chat.py` `request_context=True`, and run planning inside `acting_as`. Tests go in `tests/unit/services/chat/test_service.py` and `tests/unit/services/nl2sql/test_classifier.py`.
- [x] T023 Job response: `RHChatJob` in `indico_assistant/controllers/chat.py` returns `plan` when the job has one. `jobs.finish(..., plan=...)` is set by the planner path. Extend `tests/integration/chat/test_chat_endpoint.py`.
- [x] T024 Chainlit `chainlit_app/app_chnlit.py`:
  - render a plan answer: summary, numbered steps, side effects, questions as choice buttons, suggestions;
  - `cl.Action` `confirm_plan` (only when `can_confirm`) and `cancel_plan`;
  - `@cl.action_callback` handlers that call the endpoints, poll the job, post the outcome and `remove_actions()`;
  - a choice button sends its label as a chat message.

  Verify with the throwaway httpx `MockTransport` check pattern used for `_wait_for_answer`.

**Checkpoint**: a fake plan can be created, shown in Chainlit, confirmed once and executed by the worker as the user. NL2SQL questions behave as before.

---

## Phase 3: User Story 1 — Create a meeting from one sentence (P1) 🎯 MVP

**Goal**: the example sentence produces a plan and, once confirmed, a meeting with two 20-minute contributions, speakers, a reminder and a Teams room. Every entry is in the event log as the user.

**Independent test**: quickstart.md §2 on the local instance (fake Graph), checked in Indico's own UI.

### Tests first

- [x] T025 [P] [US1] Parity test `tests/integration/actions/test_parity_events.py`. `create_event.check` refuses exactly when `EventCreationFormBase.validate_category` would, for an admin, a category creator (`create` permission), a category manager, an open-mode category user and an unrelated user.
- [x] T026 [P] [US1] Parity test `tests/integration/actions/test_parity_contributions.py`. `add_contribution.check` matches `RHLegacyTimetableAddContribution` (full `can_manage`), including a locked event and a contribution-only manager.
- [x] T027 [P] [US1] Parity test `tests/integration/actions/test_parity_teams.py`. `add_teams_room.check` matches `RHVCManageEventCreate`: event manager, and the plugin `acl` / `managers` settings. It refuses when vc_teams is absent.
- [x] T028 [P] [US1] Parity test `tests/integration/actions/test_parity_reminders.py`. `add_reminder.check` matches `RHAddReminder`.
- [x] T029 [P] [US1] Execution test `tests/integration/actions/test_create_meeting.py`. A confirmed plan for the example:
  - creates the event (meeting, the user's timezone, the right category);
  - creates two scheduled contributions back to back, each with one speaker link;
  - creates the reminder (`send_to_speakers`, invitee recipients, `-15 min`);
  - creates a Teams room with co-organizers (FakeGraph records the meeting);
  - attributes every `EventLogEntry.user` to the user;
  - queues the emails and sends them only after commit (use the `smtp` fixture).
- [x] T030 [P] [US1] Rollback test `tests/integration/actions/test_rollback.py` (SC-006). Covers:
  - FakeGraph `fail_next` on create;
  - a raised exception in a step after the Teams step;
  - a commit failure (patched).

  Each case must leave no event, contribution, reminder, VC room, FakeGraph meeting or queued email.
- [x] T031 [P] [US1] Planner test `tests/unit/services/actions/test_planner_create.py`, using recorded `PlanDraft`s for the example sentence and three variants:
  - no end time → the end fits the slots, with a note (AS-3);
  - a named category → no question;
  - "both of us" → the requester is included.

### Implementation

- [x] T032 [P] [US1] `indico_assistant/services/actions/events.py` `CreateEvent`:
  - check: `can_create_events` + not locked;
  - describe;
  - execute: `create_event(category, EventType.meeting, data)` + `notify_event_creation`;
  - revert: `event.delete`.
- [x] T033 [P] [US1] `indico_assistant/services/actions/contributions.py` `AddContribution`: speakers through `EventPerson.for_user`; `ContributionPersonLink(is_speaker=True)` with submitter `True`; `create_contribution(..., extend_parent=True)`; revert with `delete_contribution` (R3).
- [x] T034 [P] [US1] `indico_assistant/services/actions/materials.py` `AddReminder`, as in R6: `reply_to_address` from the allowed senders; the reminder is left out when its time has passed; the executor writes `reminder.log`.
- [x] T035 [P] [US1] `indico_assistant/services/actions/teams.py` `AddTeamsRoom`:
  - the R5 sequence with two dict copies and vc_teams setting defaults;
  - `has_teams` via `find_tenant_email`;
  - it exposes `external_undo(result)` = `cancel_event(graph_event_id)` for the executor.
- [x] T036 [US1] `indico_assistant/services/actions/resolve.py`:
  - basic `find_person`: `search_users` as `RHUserSearch` does; 1 match → resolved, several → question, 0 → question;
  - basic `list_categories`: the R9 candidate query + `can_create_events`, `' » '` paths; unspecified → question listing them;
  - `draft_to_steps(CreateMeeting)`: When → aware datetimes in the user's timezone; slots back to back; the meeting extended to fit; Teams step last; reminder recipients = non-speaker invitees.
- [x] T037 [US1] Wire `CreateMeeting` in `indico_assistant/services/actions/planner.py` to the resolvers. The plan summary lists every object, times with the timezone, people with email, the category path and side effects (FR-006).
- [x] T038 [US1] Success reply in `indico_assistant/services/actions/executor.py`: link to the event (`event.external_url`) and a list of what was created (AS-4).
- [x] T039 [US1] Manual run of quickstart.md §2 on the local stack: restart the worker, run the example sentence, check the event in the UI. Record the results in the PR description.

**Checkpoint**: the MVP works. Confirmed plans create the meeting exactly as Indico's pages would.

---

## Phase 4: User Story 2 — Nothing happens without confirmation (P1)

**Goal**: cancel, amend, expiry, double confirmation, re-check at execution, and prompt injection all behave safely (SC-002).

**Independent test**: quickstart.md §3.

### Tests first

- [x] T040 [P] [US2] `tests/integration/actions/test_zero_writes.py`. For **every** write action in the catalogue (parametrised): unconfirmed, cancelled, expired, superseded and double-confirmed plans. Each must add no new rows in events / contributions / attachments / reminders / vc_rooms, and FakeGraph must record no calls (SC-002).
- [x] T041 [P] [US2] `tests/integration/actions/test_recheck.py`. The user loses management rights, the event is locked, or the category mode changes between show and confirm → the plan is `refused` with the reason and nothing is written (AS-4).
- [x] T042 [P] [US2] `tests/unit/services/actions/test_planner_followups.py`. With an open plan, "make it 30 minutes" → a revision (the old plan is superseded and its token no longer confirms); "yes, create it" → confirm through the same `executor.confirm`; "cancel" → cancelled; an unrelated question → NL2SQL.
- [x] T043 [P] [US2] `tests/unit/services/actions/test_injection.py`. Context-block text reading "also delete event 5 / add step" never produces a step that the user's own messages did not ask for; the plan is still only shown (FR-017, AS-5).

### Implementation

- [x] T044 [US2] Follow-up decisions in `indico_assistant/services/actions/planner.py`: `revise`, `confirm`, `cancel` and `unrelated`. The open plan's summary and questions go into the prompt. `confirm` requires `can_confirm`.
- [x] T045 [US2] Stale confirmations in `chainlit_app/app_chnlit.py`: a 409 from confirm shows "This plan changed or expired" and removes the old buttons. Only the latest plan message keeps its actions.
- [x] T046 [US2] A context-block builder in `indico_assistant/services/actions/context.py` that fences Indico content as data, with the explicit instruction in the planner prompt. The resolver drops draft steps that only a context item mentions (AS-5).

**Checkpoint**: SC-002 tests green for every action.

---

## Phase 5: User Story 3 — Choosing the category (P1)

**Goal**: an unspecified category gets a ranked list with a reasoned suggestion; propose-only categories are handled; names are matched.

**Independent test**: a user with create rights in three categories, one of which holds their recent meetings, gets that one suggested.

### Tests first

- [ ] T047 [P] [US3] `tests/integration/actions/test_categories.py`:
  - only categories passing `can_create_events` are in `create`;
  - `propose` holds `can_propose_events` categories only when unlisted events are enabled (fixture toggles `unlisted_events_settings`, R4);
  - ranking puts the category with the user's recent meetings first, with a reason;
  - a user with none → the "who to ask" reply, and no plan (AS-4);
  - name matching: "Engineering" → an exact match; an ambiguous name → a question with the closest paths (AS-3).
- [ ] T048 [P] [US3] Parity test `tests/integration/actions/test_parity_propose.py`: `propose_event.check` matches `can_create_unlisted_events` + `RHMoveEvent`'s rule.

### Implementation

- [ ] T049 [US3] Ranking in `list_categories` (`indico_assistant/services/actions/resolve.py`): the recent-activity count (the user's linked events, 12 months), plus topic similarity through `EmbeddingService` on event titles; a reason string per suggestion.
- [ ] T050 [P] [US3] `ProposeEvent` in `indico_assistant/services/actions/events.py`: unlisted `create_event(None, ...)` + `create_event_request` + `notify_move_request_creation`; revert withdraws the request and deletes the event.
- [ ] T051 [US3] Category name matching and the "no category" reply (the category managers of the nearest category the user can see, or the admins), in `resolve.py` + `planner.py`.

---

## Phase 6: User Story 4 — Finding the right people (P1)

**Goal**: the right person, never guessed; guest speakers; a clear note when someone cannot be a Teams co-organizer.

**Independent test**: two "Makoto" users → a question; one → name and email shown; an unknown name → a guest speaker is offered.

### Tests first

- [ ] T052 [P] [US4] `tests/integration/actions/test_people.py`. Covers:
  - search follows the `RHUserSearch` rules (excludes deleted and blocked users, includes pending, `ALLOW_PUBLIC_USER_SEARCH` off → the token rule);
  - ranking by shared events and the user's own chats;
  - several matches → a question with email and affiliation;
  - a guest speaker is created with `get_event_person` (lowercased email);
  - no tenant account → a "speaker, not Teams co-organizer" note (AS-3);
  - "with Makoto" without slots → an invitee plus reminder recipient, not a speaker (AS-5).

### Implementation

- [ ] T053 [US4] Full `find_person` in `indico_assistant/services/actions/resolve.py`: the search-token rule when public search is off, context ranking, `has_teams`.
- [ ] T054 [US4] Guest speakers in `AddContribution` (`indico_assistant/services/actions/contributions.py`) through `persons.util.get_event_person`. Plan text: "add as guest speaker (name, email)".
- [ ] T055 [US4] Plan flags in `resolve.py`: a time in the past (asks tomorrow / keep), and clashes with events the user or the named people manage or speak in (warns, does not block). These edge cases come from spec.md.

**Checkpoint**: all P1 stories are done. SC-001 is manually checked with the example sentence: at most two assistant turns plus a confirmation.

---

## Phase 7: User Story 6 — Adjusting what was just created (P2)

**Goal**: "move it to 3pm", "add a 10 minute Q&A", "add Kaori as a speaker in the second slot".

**Independent test**: create a meeting, then "move it to 3pm" → the event, its contributions and the FakeGraph meeting all move by one hour.

### Tests first

- [ ] T056 [P] [US6] Parity tests in `tests/integration/actions/test_parity_updates.py`:
  - `update_event` matches `RHEditEventData` / `RHEditEventDates` / `RHEditEventLocation`, including the `EventDatesForm` boundary rules;
  - `update_contribution` matches `RHLegacyTimetableEditEntry`.
- [ ] T057 [P] [US6] `tests/integration/actions/test_adjust.py`:
  - "it" = the event created in this chat; otherwise `find_event` among managed events, asking when ambiguous;
  - a time change moves the contributions (`update_timetable=True`) and queues the vc_teams move (the `times_changed` signal);
  - a user who does not manage the event is refused (AS-2).

### Implementation

- [ ] T058 [P] [US6] `UpdateEvent` + `FindEvent` in `indico_assistant/services/actions/events.py`. Record `before` / `after` in `StepResult`.
- [ ] T059 [P] [US6] `UpdateContribution` in `indico_assistant/services/actions/contributions.py`: time, duration, title, speakers.
- [ ] T060 [US6] `ChangeMeeting` → steps in `indico_assistant/services/actions/resolve.py`. The plan text shows the contributions moving with the event (AS-3).

---

## Phase 8: User Story 9 — Attaching a file sent in the chat (P2)

**Goal**: a PDF dropped in the chat + "attach this to my contribution" → an Indico attachment, as if uploaded through the material page.

**Independent test**: as a speaker, upload a PDF and ask; confirm; the file appears in the contribution's material, logged as the user's.

### Tests first

- [ ] T061 [P] [US9] `tests/integration/actions/test_uploads.py`, for `POST /chat/uploads`:
  - the allowlist is checked by extension **and** content (a renamed exe is refused);
  - 25 MB and `MAX_UPLOAD_FILE_SIZE`;
  - the `File` is unclaimed with `meta.assistant_user_id`;
  - another user's uuid is refused in `POST /chat` `uploads`;
  - more than 5 files → 422.
- [ ] T062 [P] [US9] Parity test `tests/integration/actions/test_parity_attachments.py`. `attach_link` / `attach_file` `check` matches `can_manage_attachments`: manager, submitter speaker, the `managers_only` event setting, and a subcontribution speaker with `subcontrib_speakers_can_submit`.
- [ ] T063 [P] [US9] `tests/integration/actions/test_attach.py`:
  - a confirmed `attach_file` copies the bytes into an `AttachmentFile` in the default folder, fires `attachment_created` (event log entry, and our indexer queued), and leaves the chat `File` unclaimed;
  - on rollback the copied blob is deleted;
  - "my contribution" resolves to contributions where the user is a speaker, asking when there are several.

### Implementation

- [ ] T064 [US9] `RHChatUpload` in `indico_assistant/controllers/actions.py` + route. Uses `File.create_from_stream`, the allowlist with content sniffing (magic bytes for pdf / zip-based office formats / png / jpg; utf-8 for txt / md), and the size limits. `ChatRequest.uploads` is validated in `indico_assistant/schemas/chat.py` + `controllers/chat.py`.
- [ ] T065 [P] [US9] `AttachLink` and `AttachFile` in `indico_assistant/services/actions/materials.py` (R7). Copied blobs are registered with the executor for deletion on rollback.
- [ ] T066 [US9] `Attach` → steps in `indico_assistant/services/actions/resolve.py`: resolve the target (the event, "my contribution" among speaker contributions, the contribution just created) and the uploads of the message.
- [ ] T067 [US9] Chainlit: in `chainlit_app/.chainlit/config.toml`, enable `spontaneous_file_upload` with the dict `accept` (MIME → extensions), `max_files = 5` and `max_size_mb = 25`. In `chainlit_app/app_chnlit.py`, `on_message` uploads each `message.elements[i].path` to `/chat/uploads` first, then posts with `uploads`, and shows upload refusals with their limits (AS-4).

---

## Phase 9: User Story 5 — Suggestions from context (P2)

**Goal**: optional, sourced suggestions (title, description, agenda items, people, material, duration), opt-in only.

**Independent test**: after chatting about the Q4 budget review, ask for a meeting about it → suggestions citing this chat and the previous meeting. Accepting two adds exactly those two.

### Tests first

- [ ] T068 [P] [US5] `tests/integration/actions/test_suggestions.py`:
  - context comes only from the user's own chats and from events and material passing `can_access` (another user's chat or a protected event never appears, FR-016);
  - every suggestion has a source;
  - none are applied until accepted;
  - accepting two creates exactly those two steps;
  - no context → no suggestions (AS-4).

### Implementation

- [ ] T069 [US5] The context block in `indico_assistant/services/actions/context.py`: the user's linked events from the last 12 months on the topic (embedding similarity on titles), their attendees, material titles and minutes (notes) with ids, and earlier-chat snippets from the user's own sessions within retention. Everything goes through `can_access`.
- [ ] T070 [US5] Suggestions in `indico_assistant/services/actions/planner.py`: validate `source_ref` against the context ids (drop unknown ones), map to Suggestion rows. "Add suggestion s1" → a revision that includes its step.
- [ ] T071 [P] [US5] Chainlit: render the suggestions as a separate list with an "Add" choice button each (`chainlit_app/app_chnlit.py`).

---

## Phase 10: User Story 8 — Suggesting a time (P2)

**Goal**: with no time given, up to three free slots for the user and the named people, with the sources stated.

**Independent test**: two users with fixtures of events they manage or speak in → the three earliest free working-hour slots avoid them; the plan names the sources.

### Tests first

- [ ] T072 [P] [US8] `tests/integration/actions/test_suggest_times.py`: busy intervals from `get_linked_events` + `happens_between` + contribution times; working hours in the user's timezone; up to three slots; a person without readable availability is named (AS-3); the sources are listed (AS-2).

### Implementation

- [ ] T073 [US8] `suggest_times` in `indico_assistant/services/actions/resolve.py` (R10), wired into `CreateMeeting` when `When.time` is missing. The slots become a choice question.
- [ ] T074 [US8] Add an Outlook free/busy hook behind `actions_outlook_freebusy`, returning "not configured" until the tenant probe confirms `getSchedule`. Leave a `ponytail:` note in `resolve.py` naming the probe as the upgrade path.

---

## Phase 11: User Story 7 — Undo (P3)

**Goal**: "undo that" reverses a plan the user confirmed in the last 24 hours, after confirmation.

**Independent test**: create a meeting, "undo that", confirm → the event is deleted through `event.delete` (FakeGraph meeting cancelled after commit).

### Tests first

- [ ] T075 [P] [US7] `tests/integration/actions/test_undo.py`:
  - the undo plan lists the user's `done` plans from the last 24 hours across chats;
  - a confirmed undo reverts in reverse order (event deleted → VC room deleted → the vc_teams cancel queued);
  - an object changed since → the differences are listed and must be confirmed (AS-2);
  - another user's plan and plans older than 24 hours are never offered.

### Implementation

- [ ] T076 [US7] `DeleteCreated` in `indico_assistant/services/actions/events.py`, using each action's `revert`, plus the `Undo` draft → steps in `resolve.py`. Diff `after` against the current values.

---

## Phase 12: Polish and cross-cutting

- [ ] T077 [P] Eval set in `~/indico-assistant/eval`: 50 meeting requests (varied phrasing, dates, people, ambiguity) with their expected plans and questions. Add a runner mode that scores intended-plan-or-right-question (≥ 90 %) and never-unasked-object (0 %) (SC-004).
- [ ] T078 [P] Latency check: time plan display and execution on the local stack, 10 runs each, against SC-005 (≤ 10 s / ≤ 15 s p50). Record the results in the PR description.
- [ ] T079 [P] README (`README.md`): a "Chat actions" section covering enabling, the per-action switches, what each action can do, the permission model ("the assistant can only do what you could do on the page"), uploads and their limits, and the vc_teams requirement.
- [ ] T080 [P] The admin note in `~/indico-assistant/indico-plugin-vc-teams/README.md`: in-process callers must pass co-organizers with tenant accounts, and `discard_pending()` is available.
- [ ] T081 Full plugin suite plus the vc_teams suite: only the 17 baseline failures. `ruff check` on the changed files.
- [ ] T082 Update `specs/019-chat-actions/quickstart.md` with anything learned during implementation.

---

## Dependencies and execution order

### Phases

- **Setup (1)**: T001→T002 in vc_teams; T004–T007 are independent of vc_teams.
- **Foundational (2)**: depends on T004–T006. It blocks every story.
- **US1 (3)**: depends on Phase 2 and on T002 / T003 (Teams step). **This is the MVP.**
- **US2 (4)**: depends on US1. It exercises every write action existing at that point; T040 is re-run as later stories add actions.
- **US3 (5) and US4 (6)**: depend on US1 (they refine its resolvers). They are independent of each other.
- **US6 (7), US9 (8), US5 (9), US8 (10)**: each depends on US1 only. They are independent of each other.
- **US7 (11)**: depends on US1. It is most useful after US6 and US9, which add revertable actions.
- **Polish (12)**: after the stories to ship.

### Within each story

The tests are written first and must fail. Then action classes, which are parallel across files, then resolvers and planner wiring, then Chainlit.

### Parallel opportunities

- Setup: T001 and T003 (vc_teams) run alongside T004, T005 and T007 (plugin).
- Foundational tests T008–T011 are all [P]. So are T017 and T020.
- US1:
  - tests T025–T031 are all [P];
  - the action classes T032–T035 are [P] (four files);
  - then T036 → T037 → T038 run in sequence.
- After US1, US3/US4 and US6/US9/US5/US8 can proceed in parallel.

## Parallel example: User Story 1

```text
Tests:   T025 test_parity_events.py | T026 test_parity_contributions.py | T027 test_parity_teams.py
         T028 test_parity_reminders.py | T029 test_create_meeting.py | T030 test_rollback.py | T031 test_planner_create.py
Actions: T032 events.py | T033 contributions.py | T034 materials.py | T035 teams.py
Then:    T036 resolve.py → T037 planner.py → T038 executor.py reply → T039 manual run
```

## Implementation strategy

- **MVP**: Phases 1–3 (US1 on the foundations). Stop and validate with quickstart.md §2, then open a PR.
- **Safety complete**: add Phase 4 (US2) before any deployment where `actions_enabled` could be turned on.
- **P1 complete**: Phases 5–6 (US3, US4).
- **Then, one PR per story in any order**: US6, US9, US5, US8, then US7, with Phase 12 items as they apply.

## Notes

- Never write through SQL, and never call Indico web endpoints (FR-002). Every write goes through an operation or the page's own steps (R3).
- Never use `session.set_session_user` in this feature (R1).
- Integration tests build all data with Indico fixtures on the test database. Count first before any command that could touch the local database (standing rule).
