# Tasks: Connect GitHub, and ask the assistant about it

**Input**: [spec.md](spec.md), [plan.md](plan.md) · **Branch**: `023-github-connector`

**Tests**: test-first (constitution VI). In each phase, the tests come before the code they cover, and must fail
before it is written. There is no CI: run `pytest tests/unit tests/contract` after each phase, and all of `pytest
tests` at the end. The baseline is T001.

**Live checks** happen in one window at the end (T040). The shared stack runs the main checkout, so the window
switches the web server and the worker to `PYTHONPATH=~/indico-assistant/plugin-d`, then switches them back. Paid
runs (T042, T043) happen only after Lucas says go.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an open task)
- **[Story]**: US1–US4 from the spec; no label = shared

---

## Phase 1: Setup

- [x] T001 The baseline on this branch at its rebase on `57b103b` (2026-09-30):
  - `pytest tests/unit tests/contract`: 1350 passed, 1 skipped;
  - `pytest tests`: 2008 passed, 27 skipped, 7 failed. All 7 failures are in `test_chat_citations.py`, the known
    baseline on main.
- [x] T002 [P] `pyproject.toml`: declare `cryptography` (the plugin imports it).
- [x] T003 [P] Settings (plan, Design 1).
  - `default_settings.py`: `github_enabled`, `github_client_id`, `github_client_secret`, `github_app_url`,
    `github_timeout_seconds`.
  - `forms.py`:
    - the fields;
    - `github_client_secret` added to `SECRETS`;
    - the callback URL in the client ID's description;
    - `validate_github_enabled`, which refuses while the ID, the stored or new secret, or
      `INDICO_ASSISTANT_CONNECTOR_KEY` is missing.

  Test first, in `tests/unit/test_forms.py` or the settings test that exists:
  - an empty secret keeps the stored one, and `-` removes it;
  - "on" is refused without each of the three.
- [x] T004 `models/connection.py` + `migrations/010_create_connections.py` (down revision
  `009_create_issue_reports`), with `UNIQUE (user_id, service)`. Export it from `models/__init__.py`.

  Test first, in `tests/integration/connectors/test_model.py`: the unique pair; a second row for the same user and
  service is refused. The migration runs up and down on the dev database in the live window (T040), not before.

## Phase 2: Foundational (blocks every story)

### Tests first

- [x] T005 [P] `tests/unit/services/connectors/test_fake_github.py`. The fake's seed loads, and every method the
  client has exists on the fake with the same signature (`inspect.signature`). Also:
  - `fail_next` raises `GitHubError` once;
  - `expire` and `refuse_refresh` behave as named;
  - state survives a reload from its JSON file.
- [x] T006 [P] `tests/unit/services/connectors/test_github_client.py`, with `httpx.MockTransport`:
  - the headers;
  - a 4xx or 5xx becomes `GitHubError(status, message)`, and the message doesn't contain the token;
  - `authorize_url` carries `client_id`, `redirect_uri`, `state`, `code_challenge` and `S256`;
  - `exchange` and `refresh` post the right fields and parse the expiries;
  - `revoke` uses basic auth with the client ID and secret.
- [x] T007 `tests/integration/connectors/test_store.py`, on the test database with `FakeGitHub`:
  - `save` then `token` returns the access token, and the database holds only ciphertext;
  - an access token with less than 5 minutes left is refreshed once, and the new pair is saved;
  - two concurrent `token` calls, in two sessions or threads, refresh once: the second sees the new expiry under
    the lock;
  - a refused refresh gives `Renew` and sets `needs_renewal`;
  - a different key gives `Renew`, not an exception;
  - no key gives `NotConnected`, and logs once;
  - `disconnect` deletes, even when the revoke fails;
  - `merged` moves a row, or deletes it when the target has one;
  - `forget` deletes.

### Code

- [x] T008 `services/connectors/github.py`: `GitHubClient` and `GitHubError`, with the OAuth class methods (plan,
  Design 4). No tools yet. This makes T006 pass.
- [x] T009 `services/connectors/fake_github.py`, with the seed (3 repositories, pull requests, issues, reviews,
  comments, events, and the 10 injection items). `client_for(token)` returns the fake when
  `INDICO_ASSISTANT_FAKE_GITHUB=1` and `config.DEBUG`. This makes T005 pass.
- [x] T010 `services/connectors/store.py` (plan, Design 3). This makes T007 pass.
- [x] T011 `plugin.py`: connect `users.merged`, `users.db_deleted` and `users.anonymized` to the store.

**Checkpoint:** `pytest tests/unit tests/contract` + `tests/integration/connectors` pass.

## Phase 3: User Story 1 — a user connects GitHub (P1)

### Tests first

- [x] T012 [US1] `tests/integration/connectors/test_pages.py`, run as `tests/integration/reports/test_pages.py`
  runs its handlers. The page:
  - an anonymous visitor goes to the login page, not a 500 or a 404;
  - a user sees Connect when unconnected. Connected, they see the login, the dates, the repositories (from the
    fake), the "add repositories" link and Disconnect. A GitHub error while loading the repositories shows
    "couldn't load", and the page still renders.
- [x] T013 [US1] Same file. Connect and the callback:
  - Connect is POST only, with CSRF, and only on your own profile (an admin on another profile gets 403);
  - it stores `state` and the verifier in the session, and redirects to the authorise URL;
  - the callback with the right state stores the connection and redirects to the page with a flash;
  - a wrong, missing or reused state, a state made for another user, or `error=access_denied` stores nothing;
  - fake mode goes straight to the callback.
- [x] T014 [US1] Same file. Disconnect: your own; an admin's on another profile (FR-006, Lucas 2026-09-30); a
  non-admin on another profile gets 403. CSRF is required.
- [x] T015 [P] [US1] `tests/integration/connectors/test_api.py`:
  - `GET /api/assistant/connections` lists the user's connections, and no field holds a token;
  - `DELETE /api/assistant/connections/github` disconnects;
  - a cookie call without the CSRF token is refused, and a token call (`X-Assistant-Auth`) needs none;
  - another user's connection can't be reached.
- [x] T016 [P] [US1] The menu: "Connected accounts" is on your own profile while GitHub is on, and absent while it
  is off. An admin on another profile sees it while that user has a connection.

### Code

- [x] T017 [US1] `views.py`: `WPConnections`. `templates/connections.html` extends `users/base.html` (block
  `user_content`), and its forms carry ids and `csrf_token`.
- [x] T018 [US1] `controllers/connections.py`: `RHConnections`, `RHConnect`, `RHGitHubCallback`, `RHDisconnect`,
  `RHConnectionsAPI`, and `profile_menu_item`. Routes go in `blueprint.py`; the menu goes in `plugin.py`.
  Objects are looked up in `_check_access`, after `RHUserBase._check_access`. This makes T012–T016 pass.
- [x] T019 [US1] `docs/DEPLOYMENT.md`:
  - registering the GitHub App: read-only Metadata, Issues and Pull requests; user tokens that expire; the
    callback URL from the settings page;
  - making the Fernet key;
  - that both the web server and the worker need it;
  - the fake mode.

**Checkpoint:** in dev mode (T040), a user connects, sees the repositories and disconnects.

## Phase 4: User Story 2 — a connected user asks about GitHub (P1, the MVP ends here)

### Tests first

- [ ] T020 [P] [US2] `tests/unit/services/connectors/test_tools.py`, against `FakeGitHub`. For each of the 7 tools:
  - the query it sends (`is:pr author:@me is:open`, the `repo:` filter, `is:merged`, one kind per `search`);
  - its text: one line per item, with `html_url`, and the 300-character cut;
  - `item` on a pull request adds its reviews;
  - `repositories` is capped at 100.
- [ ] T021 [P] [US2] `tests/unit/services/connectors/test_loop.py`, with a scripted `LLMService` mock and a fake
  clock:
  - a call, then an answer, makes 2 model calls and runs 1 tool;
  - three calls, then a forced `Final` on the 4th;
  - a repeated identical call isn't run, and the next step is `Final`;
  - once past 60 s, the next step is `Final`;
  - a result over 4,000 characters is cut;
  - `</github_data>` inside a result is escaped;
  - a `GitHubError` becomes a result the next step sees;
  - a failed `generate` gives `failed=True`;
  - each tool's record is `{name, ms, ok}`, with no arguments;
  - `urls` collects the `html_url`s.
- [ ] T022 [P] [US2] `tests/unit/services/knowledge/test_links.py`, additions:
  - `urls=` keeps an exact GitHub URL, ignoring its fragment, and drops one that isn't in the list;
  - `strip_images` turns `![x](https://evil/?q=secret)` into `x`;
  - nothing else changes (the existing tests still pass).
- [ ] T023 [P] [US2] `tests/unit/services/knowledge/test_gate.py`, additions:
  - `questions(connector=True)` offers `connector`, and the default doesn't;
  - an answer of `connector` when it wasn't offered is `invalid`;
  - the `QUESTIONS` sent today stay byte-for-byte the same with `connector=False`.
- [ ] T024 [P] [US2] Classifier tests: the prompt has the `connector` bullet only with `connector=True`. A
  `connector` classification exits with `connector_request` and makes no SQL call.
- [ ] T025 [US2] `tests/unit/services/chat/test_routing.py`, additions:
  - Jev's `connector` goes to `_connector`, and the classifier's `connector_request` goes there too;
  - `connector=` is passed only while GitHub is on;
  - the route record has `tools` and `offer: None`;
  - a failed loop has `problem: failed`;
  - a "yes" after a connector answer is routed afresh (there's no offer).

### Code

- [ ] T026 [US2] The 7 tools in `services/connectors/github.py` (plan, Design 4). This makes T020 pass.
- [ ] T027 [US2] `services/connectors/loop.py` (plan, Design 5). This makes T021 pass.
- [ ] T028 [US2] `links.py`: `urls=` and `strip_images`. This makes T022 pass.
- [ ] T029 [US2] `gate.py`: `questions()` and `decide(connector=)`. The classifier gets `{connector}`,
  `PipelineResult.connector_request` and `schema.py`. This makes T023 and T024 pass.
- [ ] T030 [US2] `chat/service.py`: `_connector`, `_route_of`, `_route_record.tools`, and passing `connector=` to Jev
  and the pipeline. This makes T025 pass.

**Checkpoint:** the MVP. In dev mode (T040), "which of my pull requests are still open?" lists the seed's open pull
requests, linked to GitHub.

## Phase 5: User Story 3 — not connected, or the connection broke (P2)

### Tests first

- [ ] T031 [US3] `tests/unit/services/chat/test_routing.py`, additions:
  - `NotConnected` gives the fixed reply with the profile link, and `Renew` gives the renew reply;
  - neither makes a model call;
  - both are recorded as route `connector` with `tools: []`.
- [ ] T032 [P] [US3] `tests/unit/services/knowledge/test_capabilities.py`, additions:
  - GitHub off: the "no access to GitHub" line stays;
  - on and not connected: "once they connect it", with the page;
  - on and connected: "connected as @login".

### Code

- [ ] T033 [US3] The fixed replies in `_connector` (FR-012), and `last_used_at` set on use. This makes T031 pass.
- [ ] T034 [US3] `capabilities.py`: the GitHub line (plan, Design 8). This makes T032 pass.

## Phase 6: User Story 4 — follow-ups (P2)

- [ ] T035 [US4] `tests/unit/services/connectors/test_loop.py`, an addition: the history reaches every step's
  `generate(messages=…)`, so "the second one" can be worked out.
- [ ] T036 [US4] Write the follow-up cases (6) for T043:
  - "which of those is oldest?" expects chat, with no tool;
  - "what did the reviewer say on the second one?" expects connector, with `item` on the seed's second pull
    request.

  Nothing else is built: Jev already reads the last two exchanges.

## Phase 7: Polish and checks

- [ ] T037 The leak test, `tests/integration/connectors/test_no_token_leak.py` (SC-004). With a known fake token,
  it runs connect, the page, the API, a chat answer through the loop (with a mocked model that records its
  prompts), a refresh and a disconnect. Then the token and the refresh token appear in none of these:
  - `caplog`;
  - any response body or redirect `Location`;
  - the route records;
  - the prompts;
  - the page HTML.
- [ ] T038 [P] `README.md`: one section on connectors (what GitHub can answer, connecting, read-only, the key).
  `.github/agents/copilot-instructions.md` if it lists the routes.
- [ ] T039 The full suite: `pytest tests` (the baseline from T001, plus the new tests), the Chainlit suite, and
  `ruff check` on the touched files. Revert ruff's churn in code we didn't touch.
- [ ] T040 The live window. Tell the other sessions first, and check `ps` for a `PYTHONPATH` override.
  1. Switch the web server and the worker to `PYTHONPATH=~/indico-assistant/plugin-d`, with
     `INDICO_ASSISTANT_FAKE_GITHUB=1` and a dev key.
  2. Migrate to 010.
  3. Then, as user 6 (Makoto) and user 1 (Lucas, admin):
     - connect, look at the page and disconnect (US1);
     - ask the story 2 questions (US2);
     - the unconnected and renew replies (US3);
     - an admin disconnecting Makoto;
     - the knowledge answer to "how do I connect GitHub?".
  4. Afterwards: roll back to 009 (main doesn't know 010), and switch the stack back to the main checkout.
- [ ] T041 Real GitHub, optional, with Lucas. He registers the test GitHub App (as Indico's top admin; AI-Thoth or
  his own account) and enters its settings; then connect, and one question. This is skipped if he doesn't want it
  before the merge.
- [ ] T042 Paid, only with Lucas's go: the router probe with `connector` (~$0.006), with the 30 GitHub questions
  and the existing sets (SC-001).
- [ ] T043 Paid, only with Lucas's go: the eval repo's `connector` set, run on the live window's fake mode, graded
  by code (~$0.15; SC-002, SC-003, SC-005). The set goes on a branch in `~/indico-assistant/eval`.
- [ ] T044 The ONE pull request, `023-github-connector` → main. Its description covers the routing note, the spec,
  the plan and the code. Add Copilot as reviewer once at open, by the API, login `Copilot`. If that doesn't
  register, Lucas requests it in the UI, or we use /fresh-review. Never merge.

## Dependencies

- **Phase 1** comes first; T001 before any code.
- **Phase 2** blocks every story.
- **US1 (phase 3) and US2 (phase 4)** can run side by side after phase 2. Both touch `plugin.py` and `blueprint.py`
  only in US1.
- **US3** needs US2's `_connector`. **US4** needs US2.
- **Phase 7** comes after the stories.
- T040 needs T001–T036. T042 and T043 need T040 and Lucas's go.

**The MVP** is phases 1–4: connect, then ask.
