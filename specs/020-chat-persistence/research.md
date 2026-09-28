# Research: Persistent assistant with past chats (020)

**Date**: 2026-09-28 | **Indico**: 3.3.13 | **Chainlit**: 2.9.5 installed, 2.12.0 target

The findings come from the Chainlit 2.12.0 wheel (paths relative to `site-packages/chainlit/`) and from this
repo (paths relative to the plugin root). Each section gives the decision, the rationale and the
alternatives considered.

---

## R1. Upgrade Chainlit to 2.12.0 first

**Decision**: Move `chainlit_app/requirements.txt` from `chainlit==2.9.5` to `chainlit==2.12.0` as the first
task. Delete the legacy `[features.mcp.sse]`, `[features.mcp.streamable-http]` and `[features.mcp.stdio]`
blocks from `.chainlit/config.toml`, and set `generated_by = "2.12.0"`. Check that today's widget still works
(questions, chat actions, uploads) before building on it.

**Rationale**:

- **Security fixes this feature relies on.**
  - 2.10.1: the server checks session ownership when it restores a websocket session.
  - 2.12.0: about thirty vulnerable JS dependencies are patched, including an open redirect to XSS in
    `react-router-dom`.
- **Sidebar and resume fixes.**
  - The sidebar reorders after a message in an older chat (2.10.0), and sorts its date groups properly
    (2.11.0).
  - `update_thread` no longer drops metadata (2.10.0).
  - `on_chat_start` no longer runs twice on a reconnect (2.11.1).
- **New options.** `default_sidebar_state = "hidden"` (2.10.0), no confirmation for a new chat (2.9.6), and
  `/health` (2.10.0).
- **The breaking changes do not reach us.** They are MCP (off here: `features.mcp.enabled = false`) and
  `@chainlit/react-client`, which we do not import.
- **No effect on Indico's environment.** Chainlit has its own venv, so its `pydantic>=2.11` stays out of
  Indico's.

**Alternatives**: staying on 2.9.5 and building on a release with a known session-restore flaw (rejected).

## R2. Why the full app in a panel, not the Copilot

**Decision**: Replace the floating Copilot with the full Chainlit app, loaded in an `<iframe>` inside a
panel that our widget script docks to the right edge of every Indico page.

**Rationale**:

- The Past Chats sidebar exists only in the full app's bundle. Its strings (`threadHistory.sidebar.*`) and
  the `ThreadList` component are absent from `copilot/dist/index.js` in both 2.9.5 and 2.12.0. The Copilot's
  API client has `listThreads` but nothing renders it.
- The full app brings, unchanged:
  - the sidebar, with search, date groups, rename and delete;
  - resuming a thread;
  - the new-chat button;
  - feedback thumbs (once a data layer exists);
  - its own narrow-width behaviour, where the sidebar becomes a drawer below 768 px.
- The full app sends no `X-Frame-Options` or CSP `frame-ancestors`, so it can be framed. `custom_css` and
  `custom_js` (`[UI]` in `config.toml`) let us style it and add the page-side hooks of R6.

**Alternatives**:

- The Copilot in its 2.11 docked "sidebar mode": native docking, but no Past Chats list (rejected on
  2026-09-28).
- The Copilot plus our own history list: not the classic sidebar (rejected).
- A pop-out window: it would survive navigation, but it sits outside the page (rejected).

## R3. Signing in to the panel

**Decision**: Sign in on every panel load, silently:

1. Our widget script fetches `/api/assistant/widget/config?event_id=<page event>` as today. That returns a
   token minted by `jwt_service.create_chainlit_token`: `{identifier, metadata: {name, email, event_id},
   exp}`, signed with `CHAINLIT_AUTH_SECRET`.
2. The panel's iframe opens `chainlit_url/public/indico-login.html`, a static page we add to
   `chainlit_app/public/`.
3. The parent sends that page the token with `postMessage`, targeted at the Chainlit origin.
4. The page calls `POST /auth/jwt` with `Authorization: Bearer <token>` and `credentials: "include"`.
   Chainlit checks the token (`auth/jwt.py: decode_jwt` gives a `User(identifier, metadata)`), mints its own
   session JWT and sets it as the `access_token` cookie (`server.py: _authenticate_user`,
   `auth/cookie.py: set_auth_cookie`).
5. The page then goes to `/thread/<current id>`, or to `/` for a new chat.

**Rationale**:

- **Nothing new on the server.** `POST /auth/jwt` exists and already accepts our token's shape. We add a
  static page, not a FastAPI route.
- **The token never enters a URL.** It travels by `postMessage` to a fixed origin, and the login page checks
  `event.origin` against the Indico origin it was built with. So nothing lands in server logs, history or
  `Referer`.
- **The page's event rides in the session.** Each Indico page load mints a token for that page, so the
  Chainlit session's `user.metadata.event_id` is the page's event. This is where "the page it was sent from"
  (R8) comes from.
- **No re-login for hours.** Set `project.user_session_timeout = 86400` (24 h, equal to the Indico token's
  `expiry_hours`; the default is 15 days). Every navigation signs in again anyway, which renews it.
- **Cookies inside the frame.** The cookie is `SameSite=Lax` by default (`CHAINLIT_COOKIE_SAMESITE`). That
  works in an iframe while Indico and Chainlit are the same site: 127.0.0.1 on two ports locally, and two
  subdomains of the labs domain in production. For a deployment on two different sites, the requirement for
  Makoto is `CHAINLIT_COOKIE_SAMESITE=none` over HTTPS.
- **Calling Indico.** The Chainlit app calls Indico with the session's Chainlit JWT. It is signed with the
  same secret and has the same `identifier` and `metadata` claims, so Indico's `validate_chainlit_token`
  accepts it; it only ever carries what Indico signed a moment before. The app no longer needs the
  `auth_token` it copied out of the header callback.

- **Login must stay required.** `auth/__init__.py: require_login()` is true only while an auth callback
  exists, or `CHAINLIT_CUSTOM_AUTH` is set. When the Copilot's `header_auth_callback` is retired, set
  `CHAINLIT_CUSTOM_AUTH=true` for the Chainlit server. Otherwise websocket connections would be accepted
  without a user.

**Alternatives**:

- The token in the iframe URL (rejected: it leaks through logs and `Referer`).
- A custom login route in the Chainlit app (not needed).
- Keeping `header_auth_callback` (rejected: an iframe cannot set headers). It stays for the old Copilot until
  it is removed.

## R4. The data layer: Chainlit reads and writes through Indico

**Decision**: A `BaseDataLayer` subclass, `IndicoDataLayer` in `chainlit_app/indico_data_layer.py`,
registered with `@cl.data_layer`. It calls Indico's `/api/assistant/*` as the requesting user. Mapping:

| Chainlit | Indico |
|---|---|
| thread | `ChatSession` (same UUID) |
| thread `name` | `ChatSession.title`, falling back to the first message |
| `user_message` / `assistant_message` step | `ChatMessage` (same UUID) |
| feedback | `FeedbackEntry` via `POST /api/assistant/feedback` |
| user | `PersistedUser(id=identifier, identifier=identifier)`, built each time and never stored |

The methods (`data/base.py`):

- **Reads.**
  - `get_thread(id)` → `GET /sessions/<id>` → `ThreadDict`, with steps built from the messages.
  - `list_threads(pagination, filter)` → `GET /sessions?limit=&cursor=&search=` →
    `PaginatedResponse[ThreadDict]`, without steps.
  - `get_thread_author(id)` → the requester's identifier if `GET /sessions/<id>` returns 200. Otherwise `""`,
    which Chainlit's `data/acl.py: is_thread_author` turns into a 404.
- **Writes Chainlit makes.**
  - `update_thread(id, name=…)` → `PATCH /sessions/<id> {title}`. A 404 is ignored: Chainlit calls this on
    the first message, before Indico has the session (`emitter.py: flush_thread_queues`).
  - `delete_thread(id)` → `DELETE /sessions/<id>`.
  - `upsert_feedback` → `POST /feedback`. `delete_feedback` → the same, with the rating removed (R11).
- **No-ops.**
  - `create_step`, `update_step` and `delete_step`. Indico already stores both sides of a message through
    the chat API, and storing them twice is what FR-016 forbids.
  - `create_element`, `get_element` and `delete_element`. Uploads go to Indico through spec 019's endpoint.
  - `update_thread(metadata=…)` (`socket.py: persist_user_session`).
  - `get_favorite_steps` returns `[]`. `set_step_favorite`, `build_debug_url` and `close` do nothing.
- `get_user` and `create_user` return the `PersistedUser` built from the identifier.

**As which user?** Chainlit calls the data layer without passing the user. So an ASGI middleware, added to
Chainlit's FastAPI `app` from our module, reads the request's `access_token` cookie
(`auth/cookie.py: get_token_from_cookies`) and puts that token in a `contextvars.ContextVar`. On the
websocket path the data layer reads `chainlit.context.context.session.token`. Every Indico call carries the
token as `Bearer`, so Indico checks ownership on every request (FR-017). With no token, nothing is returned.

**Rationale**:

- One store (FR-016). Retention, user deletion, the NL2SQL history and spec 019's planner keep reading the
  same rows.
- Indico stays the only place ownership is decided.

**Alternatives**:

- Chainlit's `SQLAlchemyDataLayer` on its own tables (rejected: two copies of every conversation).
- Letting Chainlit hold the conversations and Indico read from Chainlit (rejected: it inverts the source of
  truth).

## R5. Thread id = session id

**Decision**:

- A new chat's thread id comes from Chainlit: `session.py: self.thread_id = thread_id or str(uuid.uuid4())`.
- Our `on_message` sends it to Indico as `session_id`.
- `POST /chat` with a `session_id` that does not exist yet creates the `ChatSession` with that id, owned by
  the caller. One that exists but belongs to someone else gets 403, as today.

**Rationale**:

- No mapping table.
- The frontend's thread URL (`/thread/<id>`) and the Indico session are the same id.
- Taking over someone else's id stays impossible: ownership is checked on the existing row.
- Ids are v4 UUIDs, which Chainlit generates and asserts (`emitter.py: process_message`).

**Alternatives**: a `chainlit_thread_id` column (rejected: a second id for the same thing).

## R6. The panel, and how the page and the frame talk

**Decision**: Rewrite `indico_assistant/static/js/chat_widget.js`, keeping the lazy launcher:

- **The panel.** A right-docked panel (a `<div>` with the iframe and a drag handle).
- **Reserving the space.** On a page where the panel was open, space for it is reserved *before* the first
  paint. The `html-head` hook (`plugin.py: _render_widget_script`, rendered per request and only for logged-in
  users) also emits a few lines of inline script. It reads the stored state and sets
  `document.documentElement.style.marginRight` to the stored width. The deferred widget script builds the
  panel after that. The placeholder shows until the frame reports `ready`.
- **Indico's CSP.** When an instance sets `CSP_ENABLED`, Indico restricts only `script-src` (`'self'`,
  `'unsafe-eval'` and the page nonce, `web/flask/app.py: inject_csp`) and `base-uri`, with no `frame-src`. So
  the iframe to Chainlit's origin stays allowed, and the inline snippet carries `nonce="{get_csp_nonce()}"`.
  The old Copilot, which loads `copilot/index.js` from Chainlit's origin, would be blocked under that CSP;
  the panel is not.
- **Per-browser, per-user state in `localStorage`.** Key `indico-assistant:<user id>`, value
  `{open, width, threadId}`. The same hook puts the user id on the script tag (`data-user`).
- **Messages.** A small `postMessage` protocol (see `contracts/panel.md`), always checked against the other
  side's origin:
  - `login` (token, thread id): page → frame;
  - `ready`: frame → page, which removes the placeholder;
  - `thread` (id): the frame's route changed, so the page stores it;
  - `navigate` (url): a link in an answer, so the page sets `location.href`;
  - `close`: Esc inside the frame, so the page closes the panel.
- **`custom_js` inside the frame** (`chainlit_app/public/indico_panel.js`):
  - watches route changes (`pushState` and `popstate`) and reports `/thread/<id>`, or `/` for a new chat;
  - catches clicks on links whose origin is Indico's and sends `navigate` instead;
  - sends `close` on Esc.
- **Focus (FR-003).** The panel never calls `focus()` on reopen; the iframe gets focus only when the user
  clicks or tabs into it.
- **Narrow screens.** Below 768 px the panel covers the page, without the margin.
- **Theme.** `data-chainlit-theme` handling moves over: the page tells the frame light or dark in `login`,
  and `widget.css` becomes the full app's `custom_css`, toned to Indico.

**Rationale**:

- A cross-origin iframe cannot be read or scripted by the page, so `postMessage` is the only channel.
- Keeping the state in the page's origin (Indico's) makes it per user and per browser (FR-001).
- Sending links through the page keeps navigation in Indico (FR-006b). Setting `target=_top` on links is
  unreliable once Chainlit renders them.

**Alternatives**:

- Reading the frame's URL (impossible across origins).
- Keeping the current thread in Indico (rejected: the spec decided "per browser").

## R7. Resuming, and what `on_chat_resume` must redraw

**Decision**:

- Define `@cl.on_chat_resume`. That turns on `threadResumable` (`server.py: /project/settings`), and the
  frontend then resumes `/thread/<id>` automatically: its thread page calls `setIdToResume(id)` when
  `threadResumable`, with no button.
- `socket.py` loads the thread through `get_thread`, re-renders its steps and calls our hook with the
  `ThreadDict`.
- The hook:
  1. **Page context.** It sets `indico_session_id = thread["id"]` and takes the page event from
     `user.metadata["event_id"]`.
  2. **A waiting plan.** If Indico has one for the session, it asks Indico to reissue the plan's token
     (R10) and sends a fresh plan card with working buttons.
  3. **A pending answer.** If the last message is the user's and has a `job_id` in its metadata (R9), it
     polls `GET /chat/jobs/<job_id>` as `on_message` does now, and shows the answer when done.

**Rationale**:

- Chainlit's resume redraws text only, not actions (buttons). So spec 019's cards and anything still pending
  must be restored by us.
- Checking `socket.py: connect` against the thread's author prevents resuming another user's thread, and
  that check again ends in Indico (R4).

**Alternatives**: replaying the messages ourselves from `on_chat_start` (rejected: the sidebar needs the data
layer anyway, and Chainlit's resume draws them natively).

## R8. "This event" = the page each message is sent from

**Decision**:

- **Per message.** Each user message stores the page it was sent from:
  `ChatMessage.metadata_json["event_id"]`, taken from the request's `event_id`. The Chainlit app always
  sends the session's current page event.
- **Every answer path reads that message's event, not `ChatSession.event_id`.** That covers
  `ChatService.answer` → `_validate_event_access`, NL2SQL `event_id`, and spec 019's planner.
- **No more cross-event refusal.** `_get_or_create_session` no longer refuses a different event
  (`service.py:231`). Access is checked per message against its page (FR-008).
- **`ChatSession.event_id`** stays, as "the page it started on", for information only.
- **Telling the model (FR-009).** The context builder adds one line to the prompt: "The user is on the page of
  event <id> “<title>”", or "not on an event page".
- **Chat actions** (`resolve.meeting_in_view`, `chat_event`) get the page event passed in instead of reading
  the chat's. "This meeting" then means the most recent of:
  - the meeting made in this chat;
  - the page the user moved to since.
  If the user navigated after the plan made the meeting, the page wins; otherwise the made meeting wins, as
  in spec 019. Named meetings are resolved as before.

**Rationale**:

- Pages change within one conversation, so only the message knows its page.
- Storing the event in the existing JSONB metadata needs no migration, and old rows without it fall back to
  the session's event.

**Alternatives**:

- A column on `chat_messages` (not needed).
- Letting the page always win (rejected: "add a talk to it", right after making a meeting from another event's
  page, would change the wrong meeting).

## R9. Answers still in progress

**Decision**:

- **Keep the job id.** When `POST /chat` queues a job, the controller writes `job_id` into the user message's
  `metadata_json` in the same commit.
- **Report it.** `GET /sessions/<id>` returns `pending_job_id` when the last message is the user's.
- **Wait for it.** `on_chat_resume` polls it (R7).
- **If the job has expired from the cache** (after 1 h), no answer is coming: the message says the question
  went unanswered, with a nudge to ask again.

**Rationale**: The worker saves the answer whether or not anyone is waiting. All that's lost on navigation is
the waiting, and the job id restores it.

**Alternatives**: polling the session until an answer shows up (rejected: it can't tell "still working" from
"failed").

## R10. Plan cards after a restore

**Decision**:

- **Reissue the token.** `POST /plans/<id>/token` (owner only, plan `shown` and not expired) sets a new
  `token_hash` and returns the new token. The old buttons stop working, which is what a new card should
  mean.
- **Redraw the card.** `on_chat_resume` calls it for the chat's open plan and sends the card again.

**Rationale**:

- Only a hash of the token is stored (spec 019, R14), so the old token can't be shown again.
- A new token keeps every spec 019 guarantee: single use, expiry and supersession.
- **Two tabs:** the tab restored last holds the working card, and the other tab's Confirm answers "no longer
  valid". Typing "yes" works in either.

**Alternatives**: several valid tokens per plan (rejected: more state for a rare case).

## R11. Feedback

**Decision**:

- **Step ids = message ids.** Assistant answers are sent as `cl.Message(id=<Indico message id>)`: the job
  returns `message_id`, and the loading placeholder is removed and replaced. So in live and resumed threads
  alike, a step's id is its Indico message id.
- **Thumbs.** `upsert_feedback(Feedback(forId, value))` → `POST /feedback {message_id: forId, feedback_type:
  thumbs_up|thumbs_down}`. A comment goes as `feedback_type: comment`.
- **Delete.** `upsert_feedback` returns the id Indico gives the feedback (`POST /feedback` answers `201` with
  it). `delete_feedback(feedback_id)` calls `DELETE /feedback/<feedback_id>`, a new, owner-only endpoint.

**Rationale**: It reuses the existing feedback store (FR-018), with no second id scheme.

**Alternatives**: hiding the thumbs (rejected: they are free with the data layer, and the feedback store
exists).

## R12. Titles, listing and search

**Decision**:

- **Titles.** Add `chat_sessions.title` (`String(200)`, nullable), in migration 008. A missing title shows as
  the first user message cut to 60 characters.
- **Listing.** `GET /sessions` gains:
  - `cursor`: the `updated_at` and id of the last row, for keyset pagination, since Chainlit's `Pagination`
    is cursor-based;
  - `search`: `ILIKE` on the title and on the user's own messages' content, joined only to the caller's
    sessions;
  - `title` and `updated_at` in each item.
- **Order.** Newest `updated_at` first.
- **Date groups.** Chainlit does the grouping (Today / Yesterday / 7 / 30 days) from `createdAt` in the
  `ThreadDict`. We send `updated_at` there, so a chat moves up when it's used, as the spec asks: "last
  active".

**Rationale**:

- It fits the existing endpoint and Chainlit's contract.
- Retention bounds a user's sessions to 90 days, so an unindexed `ILIKE` over one user's messages is cheap.
  **ponytail**: move search to a trigram index if users keep thousands of chats.

**Alternatives**: full-text search (not needed at this size).

## R13. Testing

- **Indico side (pytest, as today).**
  - Sessions API: create with a client id; the ownership refusals; title; cursor; search; `pending_job_id`.
  - The token reissue.
  - The feedback delete.
  - The per-message event in `answer`, NL2SQL and the planner (SC-003).
  - Two users on one "browser", replayed with remembered ids (SC-005).
- **Chainlit side.** The data layer runs against a fake Indico (`httpx.MockTransport`): mapping, the no-ops,
  the 404-on-first-rename rule, the token from the contextvar and from the websocket session, and "no token,
  nothing returned".
- **Panel.** The widget script's state and protocol are checked in the browser with puppeteer, as the ibis
  demos are:
  - a 10-page walk (SC-001);
  - timing (SC-002);
  - a pending answer across a navigation (SC-004);
  - focus not stolen (FR-003);
  - Esc;
  - links opening in the page.
- **Regression.** The full plugin suite (the 17 known failures), and the chat-actions eval (SC-007).
