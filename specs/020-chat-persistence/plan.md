# Implementation Plan: Persistent assistant with past chats

**Branch**: `020-chat-persistence` | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/020-chat-persistence/spec.md`

## Summary

The assistant becomes a panel docked to the right of every Indico page. It runs Chainlit's full app, with its
Past Chats sidebar, in an iframe. It comes back open, on the same conversation, after every navigation, and
each message is answered for the page it was sent from.

Conversations stay in Indico's `chat_sessions` and `chat_messages`. A Chainlit **data layer** reads and writes
them through Indico's API as the requesting user. The Chainlit thread id *is* the Indico session id. The page
and the frame talk by `postMessage`: sign-in, the current thread, links, close.

The work starts with the Chainlit 2.9.5 → 2.12.0 upgrade.

- Research: [research.md](research.md) (R1-R13)
- Data model: [data-model.md](data-model.md)
- Contracts: [contracts/api.md](contracts/api.md), [contracts/panel.md](contracts/panel.md)
- Local walkthrough: [quickstart.md](quickstart.md)

## Technical Context

**Language/Version**: Python 3.12 (Indico env and Chainlit env, separate venvs); JavaScript (ES2020, no
build step) for the widget script and the frame's `custom_js`
**Primary Dependencies**:

- Indico 3.3.13 (plugin, Flask RH, SQLAlchemy);
- **Chainlit 2.12.0** (up from 2.9.5), with its FastAPI app, data-layer API and full frontend;
- httpx (already used by the Chainlit app).

**Storage**: PostgreSQL, the existing `plugin_assistant` schema. Migration 008 adds `chat_sessions.title`, and
the new message keys live in the existing `metadata_json`. Browser: one `localStorage` key per user.
**Testing**:

- pytest with Indico fixtures (plugin);
- pytest with `httpx.MockTransport` for the data layer, via a new `chainlit_app/requirements-dev.txt`, since the
  Chainlit venv has no pytest today;
- puppeteer for the panel walk (`tests/browser/`, dev only; downloads Chromium);
- the chat-actions eval for regressions.

**Target Platform**: The Indico web app in desktop and mobile browsers. The Chainlit server runs next to Indico
on the same site (R3).
**Project Type**: Indico plugin plus the Chainlit app it embeds.
**Performance Goals**:

- the conversation is visible within 2 s of the next page loading (SC-002);
- the sidebar lists 100 chats and opens any of them within 2 s (SC-006);
- one extra request per panel load (`POST /auth/jwt`).

**Constraints**:

- nothing stored twice (FR-016);
- Indico checks ownership on every request (FR-017);
- the token never goes in a URL (R3);
- no focus stealing (FR-003);
- the page never breaks when Chainlit is down (constitution IV).

**Scale/Scope**:

- one user's sessions, bounded by the 90-day retention;
- about 15 files touched, 6 new (data layer, login page, frame script, migration, tests).

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | Status |
|---|---|
| I. Official plugin architecture | ✅ New routes on the existing `IndicoPluginBlueprint`. The migration is in `plugin_assistant`. No Indico core changes |
| II. API-first | ✅ Everything the panel shows comes from REST endpoints first: sessions list/get/rename/delete, token reissue, feedback delete (contracts/api.md). The panel is UI over them |
| III. LLM abstraction | ✅ Untouched. Only the context given to the existing calls changes (the page line, R8) |
| IV. Graceful degradation | ✅ The panel reports `login_failed` or unreachable and the page keeps working. A missing `event_id` on old messages falls back to the session's. A stale `threadId` falls back to a new chat |
| V. Configuration hierarchy | ✅ No new settings. It reuses `chat_widget_enabled` and `retention_chat_days` |
| VI. Test-first | ✅ Each story's tests come before its code in tasks.md. The Chainlit side gets its first test suite |
| Security requirements | ✅ Rate limits on the new endpoints (the `read` bucket); ownership on every call; token by `postMessage` with origin checks; ILIKE through the ORM with bound parameters |
| Code quality gates | ⚠️ As in spec 019: `ruff` is clean on new code; `black` and `mypy --strict` aren't run in this repo today. Not a new deviation |

Post-design re-check: no violations. The iframe and the data layer are the smallest design that meets
"classic sidebar + one store" (R2, R4).

## Project Structure

### Documentation (this feature)

```text
specs/020-chat-persistence/
├── spec.md
├── plan.md              # this file
├── research.md          # R1-R13
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── api.md           # REST changes
│   └── panel.md         # page ⇄ frame postMessage protocol, panel behaviour
├── checklists/requirements.md
└── tasks.md             # /speckit.tasks
```

### Source Code

```text
indico_assistant/
├── plugin.py                        # html-head hook: + data-user and the inline margin snippet (R6)
├── static/js/chat_widget.js         # REWRITE: panel, iframe, resize, state, postMessage (contracts/panel.md)
├── static/css/chat_widget.css       # panel, handle, placeholder, narrow-screen cover
├── models/session.py                # + title
├── migrations/008_add_chat_session_title.py
├── controllers/chat.py              # session_id may be new; job_id onto the user message
├── controllers/sessions.py          # list: cursor/search/title; get: pending_job_id; PATCH rename
├── controllers/actions.py           # POST /plans/<id>/token
├── controllers/feedback.py          # DELETE /feedback/<id>
├── blueprint.py                     # the three new routes
├── schemas/session.py               # title, updated_at, next_cursor, pending_job_id
├── services/chat/service.py         # per-message event (R8): no cross-event refusal, create with a client id
├── services/chat/session_manager.py # create_session(id=…), list with cursor/search, rename
├── services/chat/context_builder.py # "the user is on the page of …" line
├── services/actions/planner.py      # page event passed through
├── services/actions/resolve.py      # meeting_in_view/chat_event take the page event (R8 ordering rule)
└── services/actions/executor.py     # reissue_token (R10)

chainlit_app/
├── requirements.txt                 # chainlit==2.12.0
├── requirements-dev.txt             # NEW: pytest, pytest-asyncio
├── .chainlit/config.toml            # MCP legacy blocks out; user_session_timeout=86400; custom_js;
│                                    #   custom_css; default_sidebar_state; thread sharing off
├── app_chnlit.py                    # @cl.data_layer, @cl.on_chat_resume, thread id → session_id,
│                                    #   answers sent with their Indico id, page event from user metadata
├── indico_data_layer.py             # NEW: IndicoDataLayer + the token middleware/contextvar (R4)
├── public/indico-login.html         # NEW: postMessage → POST /auth/jwt → /thread/<id> (R3)
├── public/indico_panel.js           # NEW: custom_js: thread/navigate/close/ready reporting (R6)
├── public/widget.css                # becomes the full app's custom_css, toned to Indico
└── tests/test_data_layer.py         # NEW

tests/
├── unit/…, integration/chat/…       # sessions API, per-message event, token reissue, feedback delete
└── browser/                         # NEW: package.json (puppeteer), walk.mjs (SC-001/002/004, FR-003/006b)
```

**Structure Decision**: The existing plugin layout. The Chainlit-side code sits next to `app_chnlit.py` in
`chainlit_app/`, which has its own venv and dependencies. Browser tests get their own folder with a
dev-only `package.json`, so Node never becomes a plugin dependency.

## Delivery order (input for /speckit.tasks)

1. **Setup: the Chainlit upgrade (R1).**
   - Bump to 2.12.0 and clean up `config.toml`.
   - Run today's widget and chat actions on it: the quickstart for spec 019, sections 2-3.
   - Add `requirements-dev.txt` and the browser test scaffold.
2. **Foundation (blocks every story).**
   - Migration 008 and `title`.
   - `POST /chat` creating a session with a client id.
   - `job_id` on the user message.
   - The session-list cursor.
   - `IndicoDataLayer` with reads, no-op writes and the token context.
   - Login with `indico-login.html` and `/auth/jwt`.
   - Answers sent with their Indico ids.
3. **US1 (P1): survive navigation.**
   - The panel rewrite.
   - `on_chat_resume`.
   - Pending answers (R9).
   - The plan-token reissue (R10).
   - The `thread`, `navigate`, `close` and `ready` messages.
   - The inline margin snippet.
   - The browser walk.
4. **US2 (P1): the page's event.**
   - The per-message `event_id` through `answer`, NL2SQL and the planner.
   - The page line in the prompt.
   - `meeting_in_view` ordering.
   - SC-003 tests.
   - A rerun of the chat-actions eval.
5. **US3 (P2): Past Chats.**
   - `list_threads` with search.
   - Titles.
   - `default_sidebar_state` for narrow panels.
   - The two-user isolation tests (SC-005).
   - SC-006 timing.
6. **US4 (P3): rename and delete.** `PATCH`, `delete_thread`, and "deleted while open" → new chat.
7. **Feedback (FR-018).** `upsert_feedback` / `delete_feedback` and `DELETE /feedback/<id>`.
8. **Polish.**
   - Styling toned to Indico: `widget.css`, dark mode.
   - Retire the Copilot code paths: `header_auth_callback` and `getPersistedThreadId` go.
   - The README "Chat widget" section.
   - The full suite and ruff.
   - The latency check.

US1 and US2 ship together: a conversation that survives navigation but keeps the old event would change the
wrong meeting.

## Spec amendments made during planning

None. The spec's requirements hold as written. FR-006a-e were added before planning, on 2026-09-28.

## Complexity Tracking

| Addition | Why needed | Simpler alternative rejected because |
|---|---|---|
| An iframe and a `postMessage` protocol | The Past Chats sidebar exists only in Chainlit's full app (R2), and a cross-origin frame can only be reached by messages (R6) | The Copilot has no sidebar. Our own list isn't "the classic sidebar" |
| A data layer that calls Indico's API | Chainlit needs a data layer for the sidebar and resume. Conversations must stay in one store (FR-016) | Chainlit's SQL layer stores everything twice |
| A token contextvar and middleware in the Chainlit app | Chainlit calls the data layer without the user, and Indico must check ownership on every call (FR-017) | A service credential would move the ownership check into Chainlit |
