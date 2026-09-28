---
description: "Task list for 020 persistent assistant with past chats"
---

# Tasks: Persistent assistant with past chats

**Input**: Design documents from `/specs/020-chat-persistence/` (plan.md, spec.md, research.md, data-model.md,
contracts/, quickstart.md)

**Tests**: required. The constitution's Principle VI is test-first. SC-001, SC-002 and SC-004 are measured by
the browser walk. SC-005 (two users, one browser) is test-defined. Each story's tests are written first and
must fail before implementation.

**Organization**: grouped by user story. Paths are relative to `~/indico-assistant/plugin/` unless absolute.
`R#` refers to research.md.

**Test commands**:

- plugin: `cd ~ && INDICO_CONFIG=~/indico-assistant/instance/indico.conf ~/indico-assistant/instance/env/bin/python -m pytest -q --rootdir ~/indico-assistant/plugin <paths>`
- Chainlit side: `cd ~/indico-assistant/plugin/chainlit_app && .venv/bin/python -m pytest -q tests`
- browser: `cd ~/indico-assistant/plugin/tests/browser && node walk.mjs` (the local stack must be running)
- eval: `cd ~/indico-assistant/eval && VC_TEAMS_FAKE_GRAPH=1 INDICO_CONFIG=~/indico-assistant/instance/indico.conf ~/indico-assistant/instance/env/bin/python scripts/actions_eval/run.py`

The 17 already-failing plugin tests (the `main` baseline) must stay the only failures.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: the user story (US1–US4) the task serves

---

## Phase 1: Setup (shared infrastructure)

**Purpose**: the Chainlit upgrade (R1) and the test tooling the later phases need.

- [x] T001 Upgrade Chainlit (R1):
  - pin `chainlit==2.12.0` in `chainlit_app/requirements.txt` and install it into `chainlit_app/.venv`
    (`uv pip install --python .venv/bin/python -r requirements.txt`);
  - in `chainlit_app/.chainlit/config.toml`, delete the `[features.mcp.sse]`, `[features.mcp.streamable-http]`
    and `[features.mcp.stdio]` blocks and set `generated_by = "2.12.0"`;
  - restart Chainlit and check `curl -sf http://127.0.0.1:8001/health`.
- [x] T002 Regression check of today's Copilot widget on 2.12.0, on the local stack. Run spec 019's
  quickstart sections 2-3: a question, a plan confirmed, a cancelled plan, an upload. Record anything broken
  and fix it before Phase 2.
- [x] T003 [P] Add `chainlit_app/requirements-dev.txt` (`pytest`, `pytest-asyncio`) and install it. Add
  `chainlit_app/tests/conftest.py`, which sets `CHAINLIT_AUTH_SECRET` for the tests and puts `chainlit_app`
  on `sys.path`, and `chainlit_app/pytest.ini` (`asyncio_mode = auto`).
- [x] T004 [P] Add `tests/browser/package.json` (dev only: `puppeteer`), `tests/browser/README.md` (how to
  run, which stack) and a `tests/browser/node_modules` entry in `.gitignore`. Run `npm install` there once to
  fetch Chromium.

---

## Phase 2: Foundational (blocks every user story)

**Purpose**: one store read by Chainlit (R4, R5), sign-in to the full app (R3), and answers carrying their
Indico ids (R11).

### Tests first

- [x] T005 [P] In `tests/integration/chat/test_session_history.py` (real rows; the older session tests are mock-only):
  - `create_session(user_id, event_id, session_id=<uuid>)` keeps the given id;
  - the list item's `title` falls back to the first user message cut to 60 characters when `title` is null.
- [x] T006 [P] In `tests/integration/chat/test_session_history.py`:
  - `POST /chat` with a `session_id` that does not exist creates that session, owned by the caller;
  - with another user's existing id it responds `403`;
  - the queued `job_id` is stored in the user message's `metadata_json`.
- [x] T007 [P] In `tests/integration/chat/test_session_history.py`:
  - `GET /sessions` returns `title`, `updated_at` and `next_cursor`;
  - walking the pages with `cursor` visits every session once, newest `updated_at` first, even when a
    session is updated between pages;
  - `GET /sessions/<id>` returns `pending_job_id` only when the last message is an unanswered user message;
  - it returns each message's `metadata.event_id` and the caller's own `feedback`.
- [x] T008 [P] In `chainlit_app/tests/test_data_layer.py`, against a fake Indico (`httpx.MockTransport`):
  - `get_thread` maps a session to `ThreadDict`/`StepDict` as data-model.md says (ids, types, `createdAt =
    updated_at`, name fallback, upload lines, feedback);
  - `list_threads` maps the page and `next_cursor` into `PaginatedResponse`/`PageInfo`;
  - `get_thread_author` returns the requester's identifier on `200`, and `""` on `403`/`404`;
  - `create_step`, `update_step`, `delete_step` and the element methods make no HTTP call;
  - `update_thread(name=…)` sends `PATCH` and ignores a `404`; `update_thread(metadata=…)` makes no call;
  - the token comes from the contextvar (HTTP path) or from `context.session.token` (websocket path);
  - with no token, reads return nothing and no call is made.

### Implementation

- [x] T009 Add `title = Column(String(200), nullable=True)` to `indico_assistant/models/session.py`. Write
  `indico_assistant/migrations/008_add_chat_session_title.py` (`down_revision = '007_create_action_plans'`,
  upgrade and downgrade). Apply it locally and check `\d plugin_assistant.chat_sessions`.
- [x] T010 In `indico_assistant/services/chat/session_manager.py`:
  - `create_session(..., session_id=None)`;
  - `list_sessions(user_id, limit, cursor, search=None)`, keyset on (`updated_at`, `id`), returning the next
    cursor;
  - the `title` fallback;
  - `set_message_metadata(message_id, **keys)`, which merges into `metadata_json`.

  Make T005 pass.
- [x] T011 Make T006 pass:
  - in `indico_assistant/services/chat/service.py`, `_get_or_create_session` creates the session with the
    client's id when none exists; the ownership check stays for existing ones;
  - in `indico_assistant/controllers/chat.py`, after `jobs.create`, write `job_id` onto the user message
    with `set_message_metadata` and commit.
- [x] T012 Make T007 pass:
  - in `indico_assistant/schemas/session.py`, add `title`, `updated_at` and `next_cursor` to the list;
    `title`, `updated_at` and `pending_job_id` to the detail; and `feedback` per message;
  - in `indico_assistant/controllers/sessions.py`, accept `cursor`. `offset` is ignored when `cursor` is
    given.
- [x] T013 Create `chainlit_app/indico_data_layer.py`, making T008 pass. It holds:
  - `IndicoDataLayer(BaseDataLayer)`, with the method mapping of R4;
  - `CURRENT_TOKEN: ContextVar[str | None]`;
  - `install_token_middleware(app)`, an ASGI middleware that sets `CURRENT_TOKEN` from
    `chainlit.auth.cookie.get_token_from_cookies(request.cookies)`;
  - `_token()`, which prefers `CURRENT_TOKEN`, then `chainlit.context.context.session.token`.

  Indico calls use one `httpx.AsyncClient` against `INDICO_API_URL`, with a timeout (constitution IV).
- [x] T014 Wire it into `chainlit_app/app_chnlit.py`:
  - register `@cl.data_layer` returning `IndicoDataLayer()`, and call
    `install_token_middleware(chainlit.server.app)` at import;
  - `_ask` sends `session_id = cl.context.session.thread_id` (R5) instead of `indico_session_id`;
  - Indico calls authenticate with the session's Chainlit JWT (`cl.context.session.token`, R3). The header
    callback's `auth_token` stays only as a fallback until T047;
  - the answer is sent as `cl.Message(id=<job's message_id>, …)`, replacing the loading message, so a step's
    id is its Indico message id (R11).
- [x] T015 [P] In `chainlit_app/.chainlit/config.toml`:
  - `user_session_timeout = 86400`;
  - `allow_thread_sharing = false` (check);
  - `[UI] custom_js = "/public/indico_panel.js"`;
  - `custom_css = "/public/widget.css"` (check);
  - `default_sidebar_state = "closed"`.
- [x] T016 [P] Create `chainlit_app/public/indico-login.html`, as in contracts/panel.md and R3:
  - on load, post `hello` to `?parent=<origin>`;
  - accept `login` only from that origin, and only when the origin is in `allow_origins`;
  - `fetch('/auth/jwt', {method: 'POST', headers: {Authorization: 'Bearer ' + token}, credentials: 'include'})`;
  - then `location.replace(threadId ? '/thread/' + threadId : '/')`;
  - on failure, post `login_failed {status}`.

  The token is never written to the URL, storage or the console.
- [x] T017 Checkpoint:
  - T005–T008 pass;
  - the full plugin suite shows only the 17 baseline failures;
  - in a browser, `http://127.0.0.1:8001/public/indico-login.html?parent=http://127.0.0.1:8000`, driven by
    hand from the Indico page's console, signs in and shows the full app with the sidebar;
  - an existing conversation opened from the sidebar shows its messages, read from Indico.

---

## Phase 3: User Story 1 — The conversation survives navigation (P1) 🎯 MVP

**Goal**: the panel reopens on the next page, if it was open, with the same conversation. Pending answers
and waiting plans come back. Focus is not stolen.

**Independent test**: spec US1's test, plus the browser walk (SC-001, SC-002, SC-004, FR-003, FR-006a/b/d).

### Tests first

- [x] T018 [P] [US1] In `tests/integration/actions/test_plan_token.py`, for `POST /plans/<id>/token`:
  - owner only (`403`/`404` otherwise);
  - only for a `shown`, unexpired plan (`409` for confirmed, superseded or expired);
  - after the reissue, the old token no longer confirms, and the new one confirms exactly once.
- [x] T019 [P] [US1] In `chainlit_app/tests/test_resume.py`, the resume logic (`chainlit_app/resume.py: restore`, which `on_chat_resume` draws) against a fake Indico:
  - it sets the Indico session to the thread id;
  - with an open plan, it calls the token reissue and sends a card with Confirm/Cancel actions carrying the
    new token;
  - with `pending_job_id`, it polls the job and sends the answer with its message id;
  - an expired job gives the "went unanswered" note (R9).
- [x] T020 [P] [US1] In `tests/unit/test_widget_config.py`, the `html-head` hook:
  - for a logged-in user with the widget enabled, it renders the script tag with `data-user` and the inline
    margin snippet;
  - for anonymous users or a disabled widget, it renders nothing;
  - the snippet reads only `open` and `width`, and survives a `localStorage` that throws.
- [x] T021 [US1] Write `tests/browser/walk.mjs`, which logs in as the local admin. It asserts:
  - **SC-001.** It opens the panel and asks a question, then follows 10 links, each from the page or an
    answer. The same conversation is shown on every page, with every earlier message.
  - **SC-002.** The time from `load` to the frame's `ready`; the median of 10 is under 2 s.
  - **FR-006a.** The page's content box does not move between first paint and `ready`.
  - **FR-003.** `document.activeElement` is not inside the panel after reopening.
  - **FR-006b.** A link in an answer navigates the top page.
  - **FR-006d.** Esc closes the panel; the width survives a reload.
  - **SC-004.** A question sent just before navigating is answered on the next page.
  - **US1 AS-2.** A closed panel stays closed.

### Implementation

- [x] T022 [US1] Make T018 pass:
  - add `reissue_token(plan_id, user)` to `indico_assistant/services/actions/executor.py`. It is an atomic
    UPDATE of `token_hash` `WHERE status='shown' AND expires_at > now()` and returns the new token;
  - add `RHPlanToken` to `indico_assistant/controllers/actions.py` (the `read` rate bucket) and the route to
    `indico_assistant/blueprint.py`.
- [x] T023 [US1] Add `@cl.on_chat_resume` to `chainlit_app/app_chnlit.py` per R7, making T019 pass. It sets
  the session, redraws the waiting plan card with a reissued token, and polls a pending job. Reuse
  `render_plan` and `_wait_for_answer`.
- [x] T024 [P] [US1] Create `chainlit_app/public/indico_panel.js` (`custom_js`, contracts/panel.md):
  - post `ready` once the chat is drawn;
  - post `thread {threadId}` on every route change (wrap `history.pushState` and `replaceState`, and listen
    for `popstate`);
  - intercept clicks on links whose origin is the parent's and post `navigate {url}`;
  - post `close` on Esc.

  It learns the parent origin from `sessionStorage`, which `indico-login.html` sets.
- [x] T025 [P] [US1] In `indico_assistant/plugin.py: _render_widget_script`, add `data-user="<id>"` and the
  inline snippet, as `<script nonce="{get_csp_nonce()}">` so it runs under Indico's CSP: read
  `localStorage['indico-assistant:<id>']`; if `open`, set `document.documentElement.style.marginRight` to its
  `width` (inside try/catch). Make T020 pass, including a check that the nonce is present.
- [x] T026 [US1] Rewrite `indico_assistant/static/js/chat_widget.js` as in contracts/panel.md:
  - the launcher, which is hidden while open;
  - the panel with the iframe (`indico-login.html?parent=…`) and a placeholder until `ready`;
  - the `hello` → `login` handshake with a fresh `/widget/config?event_id=` token;
  - `thread`, `navigate`, `close` and `login_failed` handling;
  - a drag handle (320 px…50%) that saves on release;
  - the state in `localStorage` per user;
  - below 768 px the panel covers the page, with no margin;
  - it never calls `focus()`.

  Drop the Copilot mount, the fetch/XHR patching and the shadow-DOM styling code.
- [x] T027 [P] [US1] Put the panel, handle, placeholder and narrow-screen styles in
  `indico_assistant/static/css/chat_widget.css`. It is served with the widget.
- [x] T028 [US1] Live check: spec 020 quickstart §2 on the local stack, then run `walk.mjs` (T021) until it
  passes. Restart the worker and Chainlit first.

**Checkpoint**: US1 works across navigation. It ships only together with US2 (plan.md, delivery order).

---

## Phase 4: User Story 2 — "This event" is the page you are on (P1)

**Goal**: every message is answered, and planned, for the page it was sent from (R8).

**Independent test**: spec US2's test, plus SC-003 (10/10 for questions and for "move this meeting").

### Tests first

- [x] T029 [P] [US2] In `tests/unit/services/chat/test_service.py`:
  - a message sent with another event than the session's is accepted;
  - access is checked against the message's event (`EventAccessDeniedError` when the user cannot access it);
  - `answer()` passes the message's event to NL2SQL;
  - an old message without `event_id` falls back to `session.event_id`.
- [x] T030 [P] [US2] In `tests/integration/chat/test_page_context.py`, the prompt gets "The user is on
  the page of event <id> “<title>”" for an event page, and "not on an event page" otherwise. The title is
  never taken from an event the user cannot access.
- [x] T031 [P] [US2] In `tests/integration/actions/test_page_context.py` (R8 ordering):
  - "move this meeting" sent from B's page plans a change to B;
  - just after the chat made meeting M, "add a talk to it" on the same page targets M;
  - after the user moves to B, "move it" targets B.

### Implementation

- [x] T032 [US2] In `indico_assistant/services/chat/service.py`:
  - `submit_message` stores `event_id` in the user message's metadata;
  - remove the "different event scope" refusal (line 231);
  - check access per message;
  - `answer()` reads the message's event (falling back to the session's) for access, NL2SQL and the planner.

  Make T029 pass.
- [x] T033 [US2] Add the page line to `indico_assistant/services/chat/context_builder.py`, under the user's
  access. Make T030 pass.
- [x] T034 [US2] Pass `page_event_id` through the chat-action code, making T031 pass:
  - `indico_assistant/services/chat/service.py: _plan` → `planner.plan_turn` → `resolve.draft_to_plan`;
  - `chat_event` and `meeting_in_view` in `indico_assistant/services/actions/resolve.py` take it;
  - `meeting_in_view` applies R8's rule: the page wins when the user navigated after the meeting was made.
- [x] T035 [US2] In `chainlit_app/app_chnlit.py`, always send `event_id` from the session user's metadata,
  which is the page that signed in (R3). After a resume, check that it is the new page's.
- [x] T036 [US2] Regression and SC-003:
  - rerun the chat-actions eval (at least 90% intended, 0% unasked);
  - live, in one conversation across two events, ask "What is this event about?" and "move this meeting to
    4pm" 10 times each; they target the page's event 10/10.

  Record the numbers in the PR description.

---

## Phase 5: User Story 3 — Past chats sidebar (P2)

**Goal**: the sidebar lists, searches and opens the user's own conversations (FR-010 to FR-013).

**Independent test**: spec US3's test, plus SC-005 and SC-006.

### Tests first

- [ ] T037 [P] [US3] In `tests/integration/chat/test_sessions_endpoint.py`:
  - `search` matches the title or the caller's own messages, case-insensitively, and never another user's;
  - two users on one browser: user A's remembered session id sent by user B to `GET/PATCH/DELETE
    /sessions/<id>` and to `POST /chat` gets `403`/`404` (SC-005).
- [ ] T038 [P] [US3] In `chainlit_app/tests/test_data_layer.py`:
  - `list_threads` passes `filter.search` and `pagination.cursor` to Indico, and `filter.userId` is ignored
    (Indico decides);
  - a thread fetched with another user's token is not returned.

### Implementation

- [ ] T039 [US3] Search in `session_manager.list_sessions`: `ILIKE` on `title` OR an `EXISTS` on the
  caller's messages, bound parameters, with a ponytail note naming the trigram upgrade (R12). Wire the
  `search` parameter in `controllers/sessions.py`. Make T037 pass.
- [ ] T040 [US3] Pass `search` and `cursor` through `IndicoDataLayer.list_threads`. Make T038 pass.
- [ ] T041 [US3] SC-006: seed 100 conversations for the local admin with a scratchpad script. Extend
  `walk.mjs` to time opening the sidebar and opening the oldest conversation (each under 2 s). Remove the
  seeded rows afterwards, counting them first.

---

## Phase 6: User Story 4 — Rename and delete (P3)

**Goal**: rename and delete from the sidebar (FR-011, FR-014).

**Independent test**: spec US4's test.

### Tests first

- [ ] T042 [P] [US4] In `tests/integration/chat/test_sessions_endpoint.py`, `PATCH /sessions/<id>`:
  - a title of 1-200 characters after trimming, otherwise `422`;
  - owner only.

  Deleting keeps the session's action plans (`session_id` null).
- [ ] T043 [P] [US4] In `walk.mjs`:
  - delete the open conversation from the sidebar: the panel shows a new, empty chat;
  - a stale `threadId` in `localStorage` (a deleted session) opens a new chat without an error.

### Implementation

- [ ] T044 [US4] Add `rename(session, title)` to `session_manager`, an `RHSessionRename` in
  `controllers/sessions.py`, and the `PATCH` route in `blueprint.py`. Make T042 pass.
- [ ] T045 [US4] In `IndicoDataLayer`, map `update_thread(name)` to `PATCH` and `delete_thread` to `DELETE`.
  In `chat_widget.js`, treat `thread {threadId: null}` (Chainlit went to `/` after a delete) as a new chat.
  Make T043 pass.

---

## Phase 7: Feedback (FR-018)

- [ ] T046 [P] Tests:
  - `tests/integration/chat/test_feedback_endpoint.py`: `DELETE /feedback/<id>`: `204` for the caller's own
    entry, `403` for someone else's, `404` when missing;
  - `chainlit_app/tests/test_data_layer.py`: `upsert_feedback` maps value `1`/`0` to
    `thumbs_up`/`thumbs_down` and returns Indico's id; `delete_feedback` calls `DELETE`.
- [ ] T047 Add `RHFeedbackDelete` to `indico_assistant/controllers/feedback.py` and its route. Add
  `upsert_feedback` and `delete_feedback` to `IndicoDataLayer`. Make T046 pass.

---

## Phase 8: Polish and cross-cutting

- [ ] T048 [P] Rework `chainlit_app/public/widget.css` as the full app's `custom_css`, toned to Indico:
  - header, colours and fonts in light and dark (FR-006e);
  - the page's `theme` message switches the frame's theme.

  Check against an Indico event page in both modes.
- [ ] T049 Retire the Copilot paths:
  - set `CHAINLIT_CUSTOM_AUTH=true` next to `CHAINLIT_AUTH_SECRET` for the Chainlit server (R3), in the
    `indico-dev-server` skill and in `docs/DEPLOYMENT.md`;
  - then remove `header_auth_callback`, the `auth_token` fallback and `getPersistedThreadId`;
  - confirm that a request without the cookie is refused (a websocket connect without the cookie → refused).
- [ ] T050 [P] Documentation:
  - `README.md` "Chat widget" section: the panel, Past Chats, "this event" follows the page;
  - `docs/DEPLOYMENT.md`: same-site hosting, or `CHAINLIT_COOKIE_SAMESITE=none` with HTTPS (the requirement
    for Makoto); `allow_origins` set to the Indico origin; `CHAINLIT_CUSTOM_AUTH`; the 2.12.0 upgrade;
  - `specs/020-chat-persistence/quickstart.md`: anything learned.
- [ ] T051 Full checks:
  - the plugin suite shows only the 17 baseline failures;
  - the Chainlit tests pass;
  - `ruff check` is clean on the changed Python files;
  - `walk.mjs` passes;
  - the chat-actions eval stays at least 90% intended and 0% unasked.
- [ ] T052 Record SC-002 and SC-006 (medians of 10) and the eval numbers in the PR description.

---

## Dependencies and execution order

### Phases

- **Setup (1)**: T001 → T002, which must be clean before anything else. T003 and T004 are independent.
- **Foundational (2)**: depends on Setup. It blocks every story. T009 → T010 → T011/T012. T013 → T014.
  T015 and T016 are independent.
- **US1 (3) and US2 (4)**: both depend on Phase 2. They are **developed in either order but shipped
  together**: persistence without the page's event would change the wrong meeting.
- **US3 (5)**: depends on Phase 2; the sidebar needs T013. It is independent of US1 and US2 apart from
  T041, which uses `walk.mjs`.
- **US4 (6)**: depends on US3's sidebar.
- **Feedback (7)**: depends on Phase 2 (T014's message ids).
- **Polish (8)**: last. T049 only after T026 (the Copilot is gone from the page).

### Within each story

The tests are written first and must fail. Then the Indico side (models, services, controllers), then the
Chainlit side, then the browser.

### Parallel opportunities

- Setup: T003 and T004.
- Foundational tests T005–T008 are all [P]. So are T015 and T016.
- US1: tests T018–T020 are [P]; T024, T025 and T027 are [P] (different files) alongside T022 and T023.
- US2: tests T029–T031 are [P].
- Once Phase 2 is done, US1, US2 and US3 can proceed in parallel.

## Parallel example: User Story 1

```text
# tests first, together
T018 tests/integration/actions/test_plan_token.py
T019 chainlit_app/tests/test_resume.py
T020 tests/unit/test_plugin.py (html-head hook)

# then, side by side
T022 executor.reissue_token + RHPlanToken    |  T024 public/indico_panel.js
T023 on_chat_resume                          |  T025 plugin.py inline snippet
                                             |  T027 chat_widget.css
# then
T026 chat_widget.js rewrite → T028 live check + walk.mjs
```

## Implementation strategy

1. **Setup, then Foundational.** Stop at T017: the full app signs in and reads conversations from Indico.
2. **US1 and US2 together. This is the MVP**, what the reported problem needs. Run the walk and the eval,
   then stop and demo.
3. **US3 (Past Chats), then US4 (rename and delete).**
4. **Feedback, then Polish.** Retiring the Copilot comes last, so the old widget keeps working until the panel
   replaces it.

## Notes

- **Never merge PRs.** Open them, address review, hand the link over.
- **Count before deleting.** Count what a delete would remove before running it on the local database: T041's
  seeded rows, and any test cleanup.
- **Tokens stay out of logs.** A token never goes in a URL, a log line or `localStorage`: only in
  `postMessage` and in Chainlit's httpOnly cookie.
- **Restart the worker and Chainlit** after changing their code: planning and answers run in the worker.
