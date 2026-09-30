# Research: Issue reports from the chat (021)

**Date**: 2026-09-30 | **Indico**: 3.3.13 | **Chainlit**: 2.12.0

The findings come from the Chainlit 2.12.0 wheel (paths relative to `site-packages/chainlit/`), from Indico
3.3.13 (paths relative to `site-packages/indico/`), and from this repo. The Chainlit ones were checked in a
throwaway app, run headless in Chrome at 480 px wide, on 2026-09-29 and 2026-09-30. Each section gives the
decision, the rationale and the alternatives considered.

---

## R1. The form is a custom element, sent with `callAction`

**Decision**: The form is `chainlit_app/public/elements/IssueReport.jsx`, a `cl.CustomElement` drawn inline in
a message. It is built from Chainlit's own components (`@/components/ui/button`, `textarea`, `checkbox` and
`label`). The three categories are toggle buttons in a `role="radiogroup"`, with an `aria-live` line for the
result. Send calls `callAction({name: "report_submit", payload})`, and Cancel calls `report_cancel`. The
element's props carry what the server decided when it drew the form: `form_key` (a new UUID), `answer_id` (or
null), the preselected `category`, a prefilled `text`, and `can_attach`.

**Rationale**:

- It is one card inside the conversation, in the panel's theme, with nothing loaded from Chainlit by the page
  (spec FR-002, FR-007).
- `callAction` is its own `POST /project/action`, and it reaches an `@cl.action_callback` in the session's
  context. The callback's return value comes back to the card, which then shows "Report sent" or the error, and
  keeps the text on an error (spec edge case).
- Toggle buttons work in a narrow frame. A select opens a pop-up.

**Alternatives considered**:

- **`AskElementMessage`** has a timeout (90 s by default). Worse, its answer calls `init_thread` on a chat's
  first interaction (`emitter.py:377`), which would create and name a conversation (spec FR-001).
- **An `AskActionMessage` then `AskUserMessage` sequence** takes three turns, and each has a timeout. Its text is
  typed in the chat's own input, where it shows as a message that Indico never stores.

## R2. The Report button sits in the panel's title bar and opens the form through `on_window_message`

**Decision**: `static/js/chat_widget.js` adds `#assistant-panel-report` to `#assistant-panel-bar`, before ». It
is disabled until the frame reports `ready`. A click posts `{source: "indico-assistant", type: "report"}` to the
frame, at the Chainlit origin. Chainlit's front end forwards every `window.postMessage` it receives to the server
as `window_message`. So `@cl.on_window_message` in `app_chnlit.py` sends the form, with no answer, and with
`can_attach` set to `cl.context.session.has_first_interaction`.

**Rationale**:

- **It works while an answer is being prepared.** Checked 2026-09-30: the form appeared 25 ms after the message,
  while an `on_message` run was sleeping. Socket.IO runs each event handler as its own task.
- **It creates no conversation.** The form is a message the app sends, and `IndicoDataLayer.create_step` does
  nothing. Only a user's first message starts an Indico session (`update_thread`, from `init_thread`).
- **The message is harmless from any sender.** Chainlit forwards window messages without checking their origin.
  This one carries only "open an empty form", so anything that could post it can only show the user a form they
  can cancel. The handler ignores every other message: the page's `login` message goes to `indico-login.html`,
  not to the app, but the handler is written as if it didn't.

**Alternatives considered**:

- **A composer command** (`emitter.set_commands`, `button: True`) was the spec's first draft.
  - The composer is disabled during a run, for up to `ANSWER_TIMEOUT` (180 s).
  - A new chat's first message runs `init_thread(message.content)` whether or not `message.command` is set
    (`emitter.py:281`). The data layer's `update_thread` then PUTs `/sessions/<id>`, which titles the chat with
    the report text.
  - Removing the command's user message also removes the form sent after it.
- **A report button under every answer**: noise on every answer, and actions are not redrawn after navigation.

## R3. The thumbs-down offer comes from `@cl.on_feedback`

**Decision**: `@cl.on_feedback` in `app_chnlit.py`. On `feedback.value == 0` (thumbs down), it sends one message
("Sorry that answer missed. Tell the team about it?") with a `report_open` action. The action's payload is
`{answer_id: feedback.forId, category: "wrong_answer", text: feedback.comment}`. The answers already offered in
this session are kept in `cl.user_session["offered"]`, so an answer gets one offer.

**Rationale**: `PUT /feedback` (`server.py:914`) runs `on_feedback` after `data_layer.upsert_feedback` has
succeeded, with `init_ws_context` for the request's session, so the hook can send into the chat. By then Indico
has accepted the vote, which means the answer exists and is the user's.

**Alternatives considered**: watching the PUT from the frame script and relaying it with a window message. It
is longer and weaker: a window message can come from any sender, and it would carry the comment. (The first draft
missed `on_feedback`.)

**Known ceiling**: `offered` lives in the Chainlit session, which each page load starts anew, so after
navigating, a new thumbs down on an old answer offers again. That is harmless.

## R4. A `problem` flag on the answer drives the offers under failures

**Decision**: When it makes an answer, `ChatService` stores `metadata_json["problem"]` as one of:

| Value | When | Set in |
|---|---|---|
| `failed` | the NL2SQL pipeline returned `success=False`, other than out of scope | `ChatService._process_with_nl2sql` |
| `out_of_scope` | `pipeline_error.error_type == OUT_OF_SCOPE` | the same |
| `not_understood` | the planner made no steps (`planner.py:98`, `:143`) | a new `PlanTurn.problem`, copied in `ChatService._plan` |
| `cannot_do` | `NOT_AVAILABLE`, `NOT_SUPPORTED`, a refusal, or validation errors (`planner.py:76`, `:149`, `:151`, `:153`) | the same |

`problem` joins `RESPONSE_METADATA` (`controllers/chat.py:29`), so the job result carries it. `_show_answer`
adds the `report_open` action under an answer that has a `problem`, with `answer_id` set to the job's
`message_id`.

For a question that got no answer (spec FR-010a), `_show_answer` puts the same action on the error message,
with no `answer_id`. That covers these branches:

- still pending after `ANSWER_TIMEOUT` (202);
- `>= 500`, including a failed job;
- `UNREACHABLE`;
- `UNANSWERED` in `_after_resume`.

Rate limits (429), sign-in (401, 403) and validation (400, 422) get no offer: they are not problems with the
assistant.

**After spec 022** (merged 2026-09-30, rebased onto): answers now come by routes.
- The router's own out-of-scope refusal sets `problem: 'out_of_scope'`.
- A knowledge or chat answer with `failed` set gets `problem: 'failed'`.
- When the planner cannot plan and no plan is waiting (`cannot_plan`), the knowledge answer replaces the planner's
  reply, and its `problem` goes with it. The user gets an explanation, not a failure.
- With a plan waiting, the planner's reply and its `problem` stand.

**Rationale**: the Chainlit app does not import `indico_assistant`, and the planner's replies vary, so the app
cannot recognise a failure from the text (spec FR-010). A planner answer stores only `{"plan_id"}` today.

**Alternatives considered**: matching `NOT_UNDERSTOOD` in the app. It misses every reply the model writes
itself.

**Judgement call**: a planner answer with no steps but with its own reply (`planner.py:143`), such as a
clarifying question, counts as `not_understood`. The change did not go through, and the offer is only a button.
Narrow it to `not draft.reply` if the offers turn out to be noise.

## R5. The evidence is recorded with the answer, and only admins see it

**Decision**:

- `PipelineResult` gains `intent`, `intent_confidence` and `validation_rejection`. It already has `row_count`,
  `correction_attempts`, `corrected` and `from_cache`. The existing `process` wrapper, which already sets
  `llm_calls` on every result, passes a `trace` dict into `_process`. `_process` fills it where it calls
  `log_classification` and `log_validation_rejection`, and `process` copies it onto the result. That covers all
  9 return points of `_process` without touching them.
- `_process_with_nl2sql` stores them under `metadata_json["evidence"]`: `{intent, intent_confidence, row_count,
  validation_rejection, correction_attempts, corrected, cached}`.
- `sql_generated`, `confidence`, `data_sources` and `pipeline_error` stay where they are today.
- `RHSessionDetail` leaves out `evidence` when it returns messages. The job result never had it, because
  `RESPONSE_METADATA` is an allowlist.

**Rationale**:

- The query log can't be the source. `query_audit_log` has no message id, and its rows have `session_id =
  NULL`, because `_process_with_nl2sql` never passes one to `pipeline.process` (`service.py:457`).
- The log is off when `audit_enabled` is false: `AuditLogger.create_log_entry` returns `None`. It is also
  purged after `retention_audit_days`.
- Recording the evidence at answer time is the only exact link (spec FR-003b).
- Leaving `evidence` out of the session API keeps the validator's reasons away from a user probing it (spec
  FR-013). `sql_generated` and `pipeline_error` already reach the owner today, and that is unchanged.

**Alternatives considered**: passing the answer id into the audit row. It still breaks when auditing is off,
and after 90 days.

**Old answers**: they have no `evidence`. The copy shows what they have.

## R6. The copy is built by Indico when the report is sent

**Decision**: `POST /reports` with `attach: true` and a `session_id` (and optionally an `answer_id`) builds the
copy in `services/reports.py`.

1. **Check ownership.** The session must be the caller's, and the answer must be an assistant message in it.
   Otherwise the refusal is `404 NOT_FOUND`, the same whether or not the session exists (spec FR-003a).
2. **Take the messages** up to 50 of the session's messages, in order, ending at the answer. When there is no
   answer, they end at the latest message. Set `truncated` when more came before.
3. **Copy each message from an allowlist**:
   - `id`, `role`, `content` and `created_at`;
   - the page's `event_id`;
   - `uploads` (file names);
   - for answers: `data_sources`, `sql_generated`, `confidence`, `pipeline_success`, `pipeline_error`,
     `problem` and `evidence`.
4. **Freeze a plan the answer showed** as `{summary, steps: [description]}`, read from `action_plans`. That row
   is purged by `retention_plan_days`, and the copy must outlive it.

**Rationale**:

- The server reads Indico's own store, so the client can't forge the copy. The chat panel sends only ids.
- The allowlist keeps job ids and anything added to message metadata later out of the copy (spec FR-003).
- Nothing comes from `query_audit_log`, so its `user_email` and `ip_address` can't leak.
- The copy is JSON that is never updated. Deleting or purging the conversation leaves it unchanged (spec FR-019).

**Alternatives considered**:

- **Chainlit sends the messages it shows.** The copy could then be forged, and it would lack the evidence.
- **A live link to the session.** Removed in review: nothing needs it, and it breaks "unticked stores nothing".

## R7. Storage: one table, with the database doing the checking

**Decision**: `plugin_assistant.issue_reports`, created by migration `009_create_issue_reports`, with columns
as in data-model.md.

- The id is an integer, so a report reads as "Report #12".
- `CHECK` constraints cover `category` and `status`.
- `UNIQUE (user_id, form_key)` stops duplicates.
- Indexes: `(status, created_at)` for the admin list, `user_id`, and `closed_at` for retention.
- Retention adds one row to `tasks/cleanup.py`'s `RETENTION`: `('plugin_assistant.issue_reports',
  'closed_at', 'retention_report_days')`. `purge()` deletes where `closed_at < now() - N days`. A NULL
  `closed_at` (open or under review) never matches (spec FR-020).
- A new setting, `retention_report_days`, defaults to 365 in `default_settings.py`, with a field in
  `forms.py`.

**Rationale**:

- Database constraints are the smallest correct guard: the category, the status and duplicate forms are
  enforced where every writer goes through.
- Keying retention on `closed_at` needs no new purge code.

## R8. One report per form, and one count per report

**Decision**: in `services/reports.py`, `create_report`:

1. `(user_id, form_key)` exists → return that report (200). Nothing is counted.
2. `RateLimiter.allowed(user_id, "report")` → `429` if any limit is used up. This uses Indico's
   `RateLimit.test()`, which counts nothing.
3. `INSERT … ON CONFLICT (user_id, form_key) DO NOTHING RETURNING id`. No row back means a concurrent double
   click inserted it first: return that one, uncounted.
4. A row was created → `RateLimiter.count(user_id, "report")`, which calls `hit()`.

The new limits are `RATE_LIMITS["report"] = ("5 per minute", "20 per day")`. The report endpoints don't use
`RHChatBase.RATE_LIMIT`: that counts in `_check_access`, before the handler knows whether the request is a
resend. The read endpoints keep `RATE_LIMIT = "read"`.

**Rationale**:

- Each `callAction` is its own concurrent POST. A plain "look, then insert" lets a double click through twice,
  and counts it twice (spec FR-005, FR-008).

**Known ceiling**: two different forms sent at the same instant, at the 20th report, can make 21. Checking and
counting in one step would need a Redis script. Mark it `ponytail:`.

## R9. The pages are server-rendered Indico pages

**Decision**: plain Jinja templates, under `indico_assistant/templates/`, rendered by Indico RHs through
`WPJinjaMixinPlugin` (`core/plugins/__init__.py:310`). They use forms that POST with Indico's `csrf_token`, and
no JavaScript. The template bases and wiring:

| Page | RH base | WP | Template extends | Route |
|---|---|---|---|---|
| My reports (list, detail, delete) | `RHUserBase` | `WPReports(WPJinjaMixinPlugin, WPUser)` | `users/base.html`, `block user_content` | `!/user/assistant-reports/`, `!/user/<int:user_id>/assistant-reports/` (+ `<int:report_id>/`, `…/delete`) |
| Triage (list, detail, save) | `RHAdminBase` | `WPReportsAdmin(WPJinjaMixinPlugin, WPAdmin)` | `layout/admin_page.html` | `!/admin/assistant-reports/` (+ `<int:report_id>/`) |

- **The profile menu**: `signals.menu.items.connect_via('user-profile-sidemenu')`. It yields
  `SideMenuItem('assistant_reports', 'Assistant reports', url, …)` only when the profile's user has a report
  (one `EXISTS` query) and `user.can_be_modified(session.user)`. This follows `modules/oauth/__init__.py:23`.
- **The admin menu**: `connect_via('admin-sidemenu')`. It shows the item when `session.user.is_admin`, in
  section `'integration'`, with `badge` set to the count of open reports (one indexed `COUNT`) or `None`.
- **Routes outside the API**: a rule that starts with `!` skips the blueprint's `/api/assistant` prefix, as Indico
  does itself (`modules/core/blueprint.py:37`).
- **Delete** asks through a confirmation page. The profile page offers Delete only when the reporting user is
  viewing it.
- **Messages in a copy** show as preformatted text (Jinja escaping, `white-space: pre-wrap`), and a copy's
  evidence as a definition list per answer. No Markdown rendering.

**Rationale**:

- It is the most boring Indico-native choice. `RHUserBase` already handles "own profile, or admin" (spec FR-014).
- Indico's own RHs check CSRF on every non-GET, so the pages need no extra code for FR-022.
- These are the plugin's first pages, so they set the pattern thread D will follow. The pattern is a WP class
  per area, templates under `templates/`, and `!` routes.

**Alternatives considered**: a React page calling the JSON API. It needs a build step the plugin doesn't have,
and more code.

## R10. The JSON API keeps CSRF for calls made with the Indico session

**Decision**: the report API RHs share `RHReportsAPI(RHChatBase)`. It sets `CSRF_ENABLED = True` and
overrides `_check_csrf` to run Indico's check only when `session.user` is set, meaning the request came with
Indico's session cookie. The chat panel's server calls with `X-Assistant-Auth` and no cookie, so it skips the
check (spec FR-022).

**Rationale**:

- `RHAssistantBase` sets `CSRF_ENABLED = False` (`controllers/base.py:34`) but accepts the session cookie. A
  same-site page could then post with the user's session.
- Indico's `_check_csrf` (`web/rh.py:220`) already reads `X-CSRF-Token` or the form's `csrf_token`.

**Outside this feature**: the existing cookie-authenticated writes, such as plan confirm, chat and delete
session, share that setting. Worth a separate issue.

## R11. A stale admin save is refused

**Decision**: the triage form carries `seen` as a hidden field: the report's `updated_at` as the page showed
it, or empty if never updated. `PATCH` (API) and the page's POST refuse with `409` when it doesn't match the
row, and the page then shows the current status and note. A save changes `status` and `note` together from the
form. `closed_at` is set only when the status moves to closed, and cleared when it moves away from closed. A
note-only save keeps it (spec FR-017, FR-020).

**Rationale**: comparing one timestamp needs no version column, and nothing is ever overwritten silently.

**Alternatives considered**: saving only the changed fields. Two admins editing the note would still overwrite
each other without knowing.

## R12. Merged accounts

**Decision**: `signals.users.merged` moves `user_id` and `updated_by_id` from the source user to the target
(spec edge case). The feedback and chat tables don't handle merges today, and this feature doesn't change them.

## R13. Building and testing in the worktree

**Decision**: `python -m pytest tests/unit tests/contract`, run from `~/indico-assistant/plugin-c`, imports
the worktree's `indico_assistant`: the working directory comes first on `sys.path`, ahead of the editable
install's finder (checked 2026-09-30). Unit and contract tests need no running stack.

**Live checks** (browser walks, migration 009 on the dev database) are the catch. The running Indico, its
Celery worker and Chainlit load the plugin from the main checkout (`~/indico-assistant/plugin`, the editable
install's `MAPPING`), and other sessions use that stack. Choose when the build reaches them:

- **(a)** For a short window, with the other sessions warned, run the shared stack from this branch: `git -C
  ~/indico-assistant/plugin switch` is not possible while a worktree has the branch, so run `pip install -e
  ~/indico-assistant/plugin-c` and switch back after.
- **(b)** Run a second stack from `plugin-c`: `PYTHONPATH=~/indico-assistant/plugin-c indico run` on :8002, a
  Chainlit on :8011, and a worker on its own queue names. The worker needs separate queues, or the shared worker
  may take this stack's jobs.

Both options share the dev database, so migration 009 lands there either way. It only adds a table, and
`indico db downgrade` (with `printf 'YES\n' |`) removes it.
