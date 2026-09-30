---
description: "Task list for 021 issue reports from the chat"
---

# Tasks: Issue reports from the chat

**Input**: Design documents from `/specs/021-issue-reports/` (plan.md, spec.md, research.md, data-model.md,
contracts/, quickstart.md)

**Tests**: required. The constitution's Principle VI is test-first. SC-003 to SC-006 are test-defined; SC-001
and SC-002 are measured by the browser check. Each story's tests are written first and must fail before the
code that makes them pass.

**Organization**: grouped by user story. Paths are relative to the worktree `~/indico-assistant/plugin-c/`.
`R#` refers to research.md; `FR`/`SC`/`AS` to spec.md.

**Test commands** (run from the worktree, R13):

- plugin: `cd ~/indico-assistant/plugin-c && ~/indico-assistant/instance/env/bin/python -m pytest -q -p no:cacheprovider tests/unit tests/contract tests/integration`
- Chainlit side: `cd ~/indico-assistant/plugin-c/chainlit_app && ~/indico-assistant/plugin/chainlit_app/.venv/bin/python -m pytest -q -p no:cacheprovider`
- browser: `cd ~/indico-assistant/plugin-c/tests/browser && WALK_USER=6 node reports.mjs` (needs the live stack
  on this branch, T001)

**Baseline** (measured 2026-09-30 at 60950d3):

- plugin: 1688 passed, 16 skipped, 7 failed. The 7 failures are all in
  `tests/integration/test_chat_citations.py`, and they must stay the only failures;
- Chainlit: 22 passed.

The new real-row tests follow `tests/integration/chat/test_session_history.py`: the `db` and `create_user`
fixtures, and a `call()` helper that runs an RH's `_process` with `request` mocked.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: the user story (US1–US4) the task serves

---

## Phase 1: Setup

- [x] T001 **Gate for live checks only**: choose R13's option with Lucas. Either (a) run the shared stack from this
  branch for a short window, with the other sessions warned, or (b) run a second stack. Record the choice in
  quickstart.md. Nothing before T019 needs it; every "live" task needs it.
  **Decided 2026-09-30 (Lucas): one swap window at the end.** All code and tests for US1–US4 are written first. Then
  every live task (T019, T020, T028, T036, T041, T043, T044) runs in one window with the shared stack on this branch,
  after warning the other local sessions.

---

## Phase 2: Foundational (blocks every user story)

**Purpose**: the table, the limiter's two new calls, and the API base with CSRF.

### Tests first

- [x] T002 [P] In `tests/integration/reports/test_model.py` (new package: add `__init__.py`), with real rows:
  - a new report has `status == 'open'` and `created_at` set, and `note`, `updated_*`, `closed_at` and `copy`
    empty;
  - a `category` or `status` outside the allowed values is refused by the database (`IntegrityError`);
  - two rows with the same `(user_id, form_key)` are refused. The same `form_key` for two users is fine.
- [x] T003 [P] In `tests/unit/services/chat/test_rate_limiter.py`:
  - `allowed(user, 'report')` is true until the limit and never counts;
  - `count(user, 'report')` counts;
  - after 20 counts, `allowed` is false;
  - `'report'` has `('5 per minute', '20 per day')`, and the `'chat'` and `'read'` entries are unchanged.
- [x] T004 [P] In `tests/integration/reports/test_create.py`, CSRF (R10), on a small RH derived from
  `RHReportsAPI`:
  - with `session.user` set and no `X-CSRF-Token`, a POST is refused (`BadRequest`);
  - with `session.csrf_token` in `X-CSRF-Token`, it passes;
  - with no session user (token auth), it passes without a CSRF token;
  - a GET never needs one.

### Implementation

- [x] T005 Write `indico_assistant/models/report.py`, with `IssueReport` exactly as data-model.md:
  - in `__table_args__`: the `CheckConstraint`s, `UniqueConstraint('user_id', 'form_key')`, the
    `(status, created_at)` index, and `{'schema': 'plugin_assistant'}`;
  - the constants `CATEGORIES`, `STATUSES` and `TEXT_MAX = 5000` / `NOTE_MAX = 2000`.

  Export it from `indico_assistant/models/__init__.py`. This makes T002 pass.
- [x] T006 Write `indico_assistant/migrations/009_create_issue_reports.py` (`down_revision =
  '008_add_chat_session_title'`), creating the table, its constraints and indexes, with a downgrade that drops
  them. Apply it in T019, not before.
- [x] T007 In `indico_assistant/services/chat/rate_limiter.py`, add `'report': ('5 per minute', '20 per day')` to
  `RATE_LIMITS`. Add `RateLimiter.allowed(user_id, kind)`, which calls `RateLimit.test()` on each limit, and
  `count(user_id, kind)`, which calls `hit()` on each. This makes T003 pass.
- [x] T008 Create `indico_assistant/controllers/reports.py` with `RHReportsAPI(RHChatBase)`:
  - `CSRF_ENABLED = True`, and `_check_csrf` that calls `super()._check_csrf()` only when `session.user is not
    None` (R10);
  - `_not_found()`, which returns `404 NOT_FOUND` with one fixed message.

  This makes T004 pass.

**Checkpoint**: the table exists in tests, and the limiter and the API base are ready.

---

## Phase 3: User Story 1 — Send a report from the chat (P1) 🎯 MVP

**Goal**: a user sends a bug, idea or wrong-answer report from a form in the chat, with a copy of the
conversation they can untick.
**Independent test**: open the form from ⚑, send it, and read it back from the database through
`services/reports.py` (spec US1 "Independent Test").

### Tests first

- [x] T009 [P] [US1] In `tests/integration/reports/test_create.py`, `POST /reports` (`RHReportCreate`, with the
  limiter mocked to record calls):
  - **created**: returns `201` with `{report_id, url}`, and `count` was called once;
  - **resend**: the same `form_key` again returns `200` with the same id, and `count` was not called again
    (FR-005, FR-008). With the limiter's `allowed` false, a resend still returns `200`: a resend is never
    limited;
  - **double click**: a row with that `form_key` inserted between the lookup and the insert (patch the lookup
    to miss once) returns the existing row, counted once (R8);
  - **limited**: with `allowed` false, a new form returns `429`, and no row is added;
  - **validation**: an unknown category, blank text, text over 5,000 characters, a malformed `form_key`, or
    `attach: true` without `session_id` each return `422`, and no row;
  - **unticked**: `attach: false` stores `copy = NULL` even when a `session_id` and `answer_id` are sent (FR-004).
- [x] T010 [P] [US1] In `tests/integration/reports/test_create.py`, the copy (R6, FR-003, FR-003a), on seeded
  sessions:
  - **ownership**: another user's session returns `404`, the same body as a session id that doesn't exist. An
    `answer_id` from a different session returns `404`, and so does one that is a user message. No row is added
    in any of these cases;
  - **extent**: in a session of 60 messages, reporting the answer that is message 40 copies messages 1–40
    (`truncated: false`). Reporting the answer that is message 60 copies messages 11–60 (`truncated: true`).
    With no `answer_id`, the copy ends at the latest message, and `reported_answer_id` is null;
  - **allowlist**: a message whose metadata has `job_id`, `answer_id` and an unknown key keeps none of them. An
    answer keeps `sql_generated`, `data_sources`, `confidence`, `pipeline_error`, `problem` and `evidence`
    when present, and leaves out the ones that are missing, rather than nulling them;
  - **plan**: an answer whose metadata has `plan_id` gets `plan: {summary, steps}` from `action_plans`. Deleting
    the plan afterwards leaves the copy unchanged;
  - **frozen**: continuing the conversation, deleting it (`SessionManager.delete_session`) and purging it each
    leave the stored copy byte-identical (SC-004);
  - **no query log**: with a `query_audit_log` row for that session holding an email and an IP, neither
    string appears anywhere in the copy (SC-004).
- [x] T011 [P] [US1] In `tests/unit/test_answer_evidence.py` (R5):
  - `NL2SQLPipeline.process` fills `intent` and `intent_confidence` after classification, and
    `validation_rejection` after a rejected query. Check both a successful result and a result returned
    early (out of scope, classification failed). Mock the LLM steps, as the existing pipeline unit tests do;
  - `ChatService._process_with_nl2sql` stores `metadata['evidence']` with the seven keys of data-model.md;
  - add to `tests/integration/chat/test_session_history.py`: `GET /sessions/<id>` returns no `evidence` key in
    any message's `metadata`, while `sql_generated` is still there.
- [x] T012 [P] [US1] In `chainlit_app/tests/test_reports.py` (new), against a fake Indico (`httpx.MockTransport`, as
  in `test_resume.py`):
  - **the button's message**: `on_window_message({"source": "indico-assistant", "type": "report"})` sends one
    message with an `IssueReport` custom element. Its props are a new `form_key`, `answer_id: None`, no
    `category`, and `can_attach` equal to `session.has_first_interaction`;
  - **other messages**: `{"type": "login", "token": …}`, a string, and a dict from another `source` send
    nothing;
  - **`report_open`**: draws the form with the payload's `answer_id`, `category` and `text`, and `can_attach:
    true`;
  - **`report_submit`**: POSTs `/api/assistant/reports` with `X-Assistant-Auth` and `{form_key, category,
    text, attach, session_id, answer_id}`. `session_id` is the thread id only when `attach` is true. A `201` or
    `200` returns `{ok: true, report_id, url}`. A `404`, `422`, `429` (with its wait), `5xx` or a
    `RequestError` returns `{ok: false, message}`, one plain sentence each;
  - **`report_cancel`**: removes the form's message.

### Implementation

- [x] T013 [US1] Write `indico_assistant/services/reports.py` with `create_report(user, data) -> (report,
  created)`:
  - it validates as data-model.md says, raising a `ReportError(status, code)`;
  - it follows R8 exactly: look up the form, then `RateLimiter.allowed`, then `insert(...).on_conflict_do_nothing(
    index_elements=['user_id', 'form_key']).returning(IssueReport.id)`, then `count` only when a row came back;
  - `build_copy(user, session_id, answer_id)` follows R6.

  Mark R8's known ceiling with a `ponytail:` comment. This makes T009 and T010 pass at the service level.
- [x] T014 [US1] Add `RHReportCreate(RHReportsAPI)` to `indico_assistant/controllers/reports.py`. It parses the
  JSON body, calls `create_report`, maps `ReportError` to the error shape, and returns `report_url(report_id)`.
  That is a helper in `services/reports.py` returning `url_for_plugin('assistant.user_report', report_id=…,
  _external=True)`, the page route T027 registers. The US1 tests patch `report_url`. Register `POST /reports`
  in `indico_assistant/blueprint.py`. This makes T009 and T010 pass.
- [x] T015 [US1] Evidence (R5):
  - add `intent`, `intent_confidence` and `validation_rejection` to `PipelineResult`
    (`services/nl2sql/models.py`);
  - in `services/nl2sql/pipeline.py`, `process` creates `trace = {}` and passes it into `_process`. `_process`
    fills it next to `log_classification` and `log_validation_rejection`, and `process` copies it onto the
    result;
  - in `services/chat/service.py`, `_process_with_nl2sql` adds `metadata['evidence']`;
  - in `controllers/sessions.py`, `RHSessionDetail` drops `evidence` from each message's metadata.

  This makes T011 pass.
- [x] T016 [P] [US1] Write `chainlit_app/public/elements/IssueReport.jsx` as contracts/panel.md says: the props, the
  four states, the test-hook ids, `role="radiogroup"` with a label, `aria-checked`, the `aria-live` result
  line, and the attach box shown only with `can_attach`. Send is disabled while sending. Start from the
  2026-09-29 prototype (scratchpad `proto/public/elements/IssueReport.jsx`, which is gone with the session:
  rewrite it).
- [x] T017 [US1] In `chainlit_app/app_chnlit.py`:
  - `_report_form(answer_id=None, category=None, text="", can_attach=True)` sends a message with the element;
  - `@cl.on_window_message` handles the `report` message (R2);
  - `@cl.action_callback("report_open")`, `("report_submit")` and `("report_cancel")`;
  - the submit calls Indico as `_plan_call` does (the session token, the shared client).

  None of these runs inside `on_message`, so no thumbs appear (FR-007a). This makes T012 pass.
- [x] T018 [P] [US1] In `indico_assistant/static/js/chat_widget.js`:
  - add `<button id="assistant-panel-report" type="button" aria-label="Report a problem" title="Report a problem"
    disabled>⚑</button>` before `#assistant-panel-close`;
  - enable it on `ready`, and disable it on `unavailable` or `login_failed`;
  - on click, post `{source: "indico-assistant", type: "report"}` to `frame.contentWindow` at the Chainlit
    origin, and move focus into the frame.

  Style it like `#assistant-panel-close` in `static/css/chat_widget.css`. Check that `_widget_version()` changes
  (the `?v=` hash covers both files).
- [x] T019 [US1] **Live** (needs T001):
  - apply migration 009 (`indico db --plugin assistant upgrade`) and check `\d plugin_assistant.issue_reports`;
  - check the downgrade, then upgrade again;
  - restart the worker and Chainlit.
- [x] T020 [US1] **Live**: quickstart §2 as user 6 (Makoto):
  - the form from ⚑ in a new chat: no attach box, and no new Past Chats entry after sending (AS8);
  - during a slow answer: the form opens at once, with the box ticked (AS9);
  - a double-clicked Send makes one row;
  - Cancel sends nothing;
  - unticked stores `copy IS NULL`.

  "Report sent" shows, but its link works only after T027. It is checked in T028.

  Record anything broken and fix it before US2.

**Checkpoint**: reports can be sent. Nothing shows them yet except the database.

---

## Phase 4: User Story 2 — The user sees their reports (P1)

**Goal**: a profile page lists the user's reports with status and note. A report opens to its text and the
messages as the chat showed them, and the user can delete it.
**Independent test**: spec US2 "Independent Test".

### Tests first

- [x] T021 [P] [US2] In `tests/integration/reports/test_own.py`, the JSON endpoints:
  - `GET /reports` lists only the caller's reports, newest first, with `text_start` at most 120 characters;
  - `GET /reports/<id>` on the caller's own report returns the user view: each message has only `id`, `role`,
    `content`, `created_at`, `uploads` and `plan`, with no `evidence`, `sql_generated` or `pipeline_error`
    (FR-013);
  - someone else's report, and one that doesn't exist, give the same `404` body (SC-003);
  - `DELETE /reports/<id>` on the caller's own report returns `204`, and the row is gone;
  - on someone else's report it returns `404`, and the row stays. That holds for an admin too: only the
    reporter deletes (contracts/api.md);
  - `has_reports(user)` follows the rows.
- [x] T022 [P] [US2] In `tests/integration/reports/test_pages.py`, the profile pages, with RHs called directly
  and the template rendering mocked to capture its parameters:
  - **own**: the list page for your own profile passes your reports;
  - **someone else's profile**: another non-admin's is refused by `RHUserBase`'s `can_be_modified`. An admin
    viewing someone else's profile gets that user's reports;
  - **a report**: the report page passes the user view, as T021 describes;
  - **delete**: the GET shows the confirmation. The POST deletes it and redirects to the list. The delete page
    refuses anyone but the reporter, an admin included;
  - **menu**: the `user-profile-sidemenu` handler yields the item only when the profile's user has a report and
    `can_be_modified(session.user)`.

### Implementation

- [x] T023 [US2] In `services/reports.py`, add `own_reports(user)`, `own_report(user, report_id)`, which returns
  `None` when it isn't the user's, `delete_own(user, report_id)`, `has_reports(user)` and `user_view(copy)`
  (the allowlist of T021).
- [x] T024 [US2] Add `RHReportList`, `RHReportDetail` and `RHReportDelete` (all `RATE_LIMIT = "read"`) to
  `controllers/reports.py`. Register the routes in `blueprint.py`. This makes T021 pass.
- [x] T025 [US2] Create `indico_assistant/views.py` with `WPReports(WPJinjaMixinPlugin, WPUser)`. Create
  `indico_assistant/controllers/report_pages.py`:
  - `RHUserReports(RHUserBase)`, `RHUserReport(RHUserBase)` and `RHUserReportDelete(RHUserBase)`;
  - the delete refuses unless `self.user == session.user`;
  - its POST is protected by Indico's CSRF check by default.
- [x] T026 [P] [US2] Write the templates under `indico_assistant/templates/`: `reports.html` and `report.html`, each
  extending `users/base.html` in `block user_content`. (Built without `report_delete.html`: Delete is Indico's own
  `data-href` + `data-method="POST"` + `data-confirm` button, as `oauth/user_apps.html` does, so the delete route
  is POST only.)
  - Messages show as escaped text with `white-space: pre-wrap`; answers are labelled "Assistant".
  - The status is a label (open / under review / closed), with the note and "updated <date>" under it.
  - An empty list says so.
- [x] T027 [US2] Register the page routes in `blueprint.py`, with `!`, in both forms Indico uses:
  `!/user/assistant-reports/` and `!/user/<int:user_id>/assistant-reports/`, plus `<int:report_id>/` and
  `<int:report_id>/delete`. Name the endpoints so `url_for_plugin('assistant.user_report', report_id=…)` works
  for T014. Connect the `user-profile-sidemenu` item in `plugin.py`. This makes T022 pass.
- [x] T028 [US2] **Live**: quickstart §4 as user 6:
  - the menu item appears after the first report;
  - the list and one report, with no SQL or intent;
  - delete with the confirmation;
  - user 1 viewing `/user/6/assistant-reports/` sees Makoto's reports, and no Delete;
  - in the chat, "Report sent"'s link now opens the report page in the Indico page, not in the panel.

**Checkpoint**: users see their reports and can delete them.

---

## Phase 5: User Story 3 — Admins triage reports (P1)

**Goal**: an admin page lists, filters and opens every report with its evidence, and saves a status and note
without overwriting anyone.
**Independent test**: spec US3 "Independent Test".

### Tests first

- [x] T029 [P] [US3] In `tests/integration/reports/test_admin.py`, the admin endpoints:
  - **list**: newest first, 50 a page, `page` and `pages` right for 120 rows, filters by `status` and by
    `category` (and both), and `open` counts the open reports;
  - **one report**: returns the full copy, evidence included, plus `user: {id, name, email}` from Indico and
    `updated_by`;
  - **a save**: `PATCH` sets `updated_by_id` and `updated_at`, and follows data-model.md's transition table.
    Moving to `closed` sets `closed_at`; a note-only save on a closed report keeps it; reopening clears it
    (FR-020);
  - **stale**: with `seen` set to an older `updated_at`, the save returns `409 STALE` with the current report,
    and the row is unchanged. `seen` empty on a report never updated passes;
  - **validation**: a bad status, or a note over 2,000 characters, returns `422`;
  - **access**: every admin endpoint refuses user 6's equivalent (a non-admin), with `403` (SC-003).
- [x] T030 [P] [US3] In `tests/unit/tasks/test_retention.py`:
  - the reports row is in `RETENTION`;
  - with `retention_report_days = 30`, a report closed 31 days ago is deleted;
  - an open and an under-review report created 400 days ago stay;
  - a report closed 400 days ago and then reopened stays, because `closed_at` was cleared (SC-005);
  - `0` keeps everything.
- [x] T031 [P] [US3] In `tests/integration/reports/test_pages.py`, the admin pages:
  - a non-admin is refused by `RHAdminBase`;
  - the detail POST with a stale `seen` re-renders with the current status and note and a message, and
    changes nothing;
  - a good POST saves and redirects;
  - the `admin-sidemenu` handler yields the item only for admins, in section `integration`, with
    `badge` = the open count, or `None` at 0.

### Implementation

- [x] T032 [US3] In `services/reports.py`, add `admin_list(status, category, page)`, `admin_report(report_id)`,
  `admin_update(admin, report_id, status, note, seen)` (the R11 check, the `closed_at` rules; it raises
  `ReportError(409, 'STALE')`), and `open_count()`.
- [x] T033 [US3] Add `RHAdminReportList`, `RHAdminReportDetail` and `RHAdminReportUpdate` to
  `controllers/reports.py`, on `RHReportsAPI` with `ADMIN_ONLY = True`. Register them in `blueprint.py`. This
  makes T029 pass.
- [x] T034 [US3] In `views.py`, add `WPReportsAdmin(WPJinjaMixinPlugin, WPAdmin)`. In `report_pages.py`, add
  `RHAdminReports(RHAdminBase)` and `RHAdminReport(RHAdminBase)`, whose GET shows the report and whose POST
  saves it. Add `admin_reports.html` and `admin_report.html` (extending `layout/admin_page.html`):
  - the filters are a GET form;
  - the pager;
  - the copy with the reported answer highlighted, and each answer's evidence as a definition list;
  - the status select, the note textarea, and the hidden `seen` field.

  Register `!/admin/assistant-reports/` and `<int:report_id>/`. Connect the `admin-sidemenu` item in
  `plugin.py`. This makes T031 pass.
- [x] T035 [P] [US3] Retention:
  - add `"retention_report_days": 365` to `default_settings.py`;
  - add an `IntegerField` in `forms.py` next to `retention_chat_days` (0 = keep forever, as its neighbours);
  - add the row to `tasks/cleanup.py`'s `RETENTION`.

  This makes T030 pass.
- [x] T036 [US3] **Live**: quickstart §5 and §6:
  - as user 1: the badge, the filters, the evidence on a wrong-answer report, and a save;
  - two tabs: the second save is refused;
  - user 6 is refused;
  - retention: **count what it would delete first**, then run `apply_retention` with a 1-day setting on one
    report closed by hand, and put the setting back to 365.

**Checkpoint (MVP)**: US1–US3 work end to end. Stop and show Lucas before US4.

---

## Phase 6: User Story 4 — The chat suggests a report (P2)

**Goal**: offers after a thumbs down, under failed or refused answers, and on messages that say no answer came.
**Independent test**: spec US4 "Independent Test".

### Tests first

- [x] T037 [P] [US4] In `tests/unit/test_answer_evidence.py`, the `problem` flag (R4):
  - **pipeline**: a failed result gives `problem: 'failed'`, an out-of-scope one gives `'out_of_scope'`, and a
    good one gives none;
  - **planner**: each `plan_turn` return point listed in R4 sets `PlanTurn.problem`. `planner.py:98` and `:143`
    give `not_understood`; `:76`, `:149`, `:151` and `:153` give `cannot_do`. A shown plan, a confirm and a
    cancel give none;
  - **carried through**: `ChatService._plan` puts it in the metadata. The job endpoint returns `problem` (add
    to the existing job test in `tests/integration/chat/test_chat_endpoint.py`).
- [x] T038 [P] [US4] In `chainlit_app/tests/test_reports.py`:
  - **thumbs**: `on_feedback` with `value=0` sends one offer message whose `report_open` payload is `{answer_id:
    forId, category: 'wrong_answer', text: comment}`. A second thumbs down on the same answer sends nothing, and
    `value=1` sends nothing;
  - **flagged answers**: `_show_answer` for a `200` whose metadata has `problem` attaches a `report_open` action
    with `answer_id` set to the job's `message_id`. With no `problem`, there is no action;
  - **no answer**: `202` after the timeout, a `5xx` and a `RequestError` each put the action on the error
    message, with no `answer_id`. A `429`, `401`, `403` or `422` gets none;
  - **resume**: `_after_resume`'s `UNANSWERED` and `UNREACHABLE` get the action.

### Implementation

- [x] T039 [US4] Add `problem` to `PlanTurn` in `services/actions/planner.py`, and set it at R4's return points.
  In `services/chat/service.py`, set `metadata['problem']` for NL2SQL results, and copy `turn.problem` in
  `_plan`. Add `"problem"` to `RESPONSE_METADATA` in `controllers/chat.py`. This makes T037 pass.
- [x] T040 [US4] In `chainlit_app/app_chnlit.py`:
  - `_offer(answer_id=None)` returns the `report_open` action (label "Report a problem", icon `flag`);
  - `@cl.on_feedback` handles thumbs down, with the `offered` set in `cl.user_session` (R3);
  - the offers go in `_show_answer`'s and `_after_resume`'s branches as T038 lists.

  This makes T038 pass.
- [x] T041 [US4] **Live**: quickstart §3:
  - a thumbs down with a comment gives one offer, and the comment is in its form;
  - an out-of-scope question gets the offer;
  - with the worker stopped, the timeout message gets the offer, and its report has no answer.

  Start the worker again.

---

## Phase 7: Polish and cross-cutting

- [x] T042 [P] Merged accounts (R12): in `plugin.py`, connect `signals.users.merged` to move `user_id` and
  `updated_by_id` from `source` to `target`. Test it in `tests/integration/reports/test_own.py`.
- [x] T043 Write `tests/browser/reports.mjs`, using `lib.mjs`'s `browserAs`:
  - **SC-001**: as user 6, send a report from an offer and one from ⚑. Each takes at most three choices besides
    typing, and each shows on `/user/assistant-reports/` right after. 10 runs;
  - **SC-002**: 10 thumbs down each give an offer, and 10 out-of-scope questions each carry one. A
    double-clicked Send makes one report;
  - at the end, count and then delete the reports and chats the run made as user 6.

  Add it to `tests/browser/README.md`.
- [x] T044 **Live**: run every existing browser check unchanged (SC-007): `walk` (as user 1), `sc003`, `us4`,
  `hover`, `feedback`, `tabs` and `sidebar`. Fix any regression.
- [x] T045 [P] Documentation:
  - `README.md`: a short "Issue reports" section: the ⚑ button, offers, the profile page, the admin page,
    retention;
  - `docs/DEPLOYMENT.md`: migration 009 and the `retention_report_days` setting;
  - `quickstart.md`: anything learned while building.
- [ ] T046 Full checks:
  - the plugin suite equals the baseline plus the new tests, with only the 7 citation failures;
  - the Chainlit tests pass;
  - `ruff check` is clean on every changed Python file;
  - `reports.mjs` passes.
- [ ] T047 Open the feature's one PR, `021-issue-reports-build` → `main`:
  - the description covers the spec, the plan, and the numbers from T043, T044 and T046;
  - add Copilot as reviewer once;
  - hand Lucas the link, and never merge.

---

## Dependencies and execution order

### Phases

- **Setup (1)**: T001 is a gate for live tasks only (T019, T020, T028, T036, T041, T043, T044). Ask it early;
  the code doesn't wait for it.
- **Foundational (2)**: T005 → T006. T007 and T008 are independent. It blocks every story.
- **US1 (3)**: T013 → T014. T015, T016, T017 and T018 can go side by side once the tests are written. Then
  T019 → T020.
- **US2 (4)** needs US1's service (T013). Its page route (T027) is the one `report_url` names, so the "Report
  sent" link works from T027 on.
- **US3 (5)** is independent of US2's pages, but shares `report_pages.py` and `views.py` with them: do it after
  US2.
- **US4 (6)** needs US1's `report_open` (T017) and form (T016).
- **Polish (7)**: last. T047 only after T046 is clean.

### Within each story

The tests are written first and must fail. Then the Indico side (service, controllers, pages), then the
Chainlit side, then the live check.

### Parallel opportunities

- Foundational tests T002, T003 and T004.
- US1 tests T009–T012. Then T015 (answers), T016 (JSX), T017 (Chainlit) and T018 (page script) touch
  different files.
- US2 tests T021 and T022, and template T026, alongside T023–T025.
- US3 tests T029–T031, and retention T035, alongside T032–T034.
- US4 tests T037 and T038.

## Parallel example: User Story 1

```text
# tests first, together
T009, T010 tests/integration/reports/test_create.py
T011 tests/unit/test_answer_evidence.py
T012 chainlit_app/tests/test_reports.py

# then
T013 services/reports.py → T014 controllers/reports.py + route
T015 pipeline + service + sessions (evidence)   |  T016 IssueReport.jsx
                                                |  T017 app_chnlit.py
                                                |  T018 chat_widget.js/.css
# then (needs T001)
T019 migration live → T020 live check
```

## Implementation strategy

1. **Foundational, then US1.** Stop at T020: a report can be sent from the chat, even though nothing shows it
   yet.
2. **US2, then US3. This is the MVP**: send, see, triage. Stop at T036 and show Lucas.
3. **US4** (the offers), then **Polish**, then the one PR (T047).

## Notes

- **One PR**, at T047. The spec, plan and tasks stay on this branch until then.
- **Never merge PRs.** Open them, address review, hand the link over.
- **Count before deleting**: retention runs, browser-test cleanup, anything on the dev database.
- **Tokens stay out of logs and URLs**: `report_submit` sends the session token only in `X-Assistant-Auth`.
- **Restart the worker and Chainlit** after changing their code: answers are made in the worker, so T015 and
  T039 need a restart to show live.
- **Commit before any break-and-restore test**: never run `git checkout <file>` on uncommitted work.
