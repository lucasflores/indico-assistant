# Tasks: Assistant analytics and traces

**Input**: [spec.md](spec.md), [plan.md](plan.md) · **Branch**: `024-assistant-analytics` (worktree
`~/indico-assistant/plugin-024`)

**Tests**: test-first (constitution VI).
- In each phase, the tests come before the code they cover, and must fail before it is written.
- There is no CI. Run `pytest tests/unit tests/contract` after each phase, and all of `pytest tests` at the end,
  from the worktree. The baseline is T001.

**Live checks** happen in one window at the end (T040):
- The shared stack runs the main checkout, so the window switches the web server and the worker to
  `PYTHONPATH=~/indico-assistant/plugin-024`, then back.
- A `pg_dump` comes first, because migration 011 drops tables.
- Paid questions (about $0.05 on the ibis testbed key) need Lucas's go.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an open task)
- **[Story]**: US1–US5 from the spec; no label = shared

---

## Phase 1: Setup

- [x] T001 The baseline on this branch, at `main` = `9d5e9f4` (2026-10-02). `pytest tests`: 2185 passed, 27 skipped,
  7 failed. All 7 failures are in `test_chat_citations.py`, the known baseline on main.
- [x] T002 [P] Settings (plan, Design 1).
  - `default_settings.py` and `forms.py`: add `analytics_trace_text`, `retention_trace_text_days` and
    `retention_turn_days`.
  - Remove the five `langfuse_*` settings and `retention_error_days`.

  Test first, in the settings form test that exists:
  - the defaults are True, 30 and 0;
  - a negative number of days is refused.
- [x] T003 `models/analytics.py` and `migrations/011_analytics.py` (down revision `010_create_connections`): the
  three tables of Design 2, with their indexes, and the drop of the three observability tables. The downgrade
  recreates them from 003's body. Export the models from `models/__init__.py`.

  Test first, in `tests/integration/analytics/test_models.py`:
  - deleting a turn removes its steps and texts;
  - `(turn_id, seq)` is unique;
  - `job_id` is unique.

  The migration runs up and down on the dev database in the live window (T040), not before.

## Phase 2: Foundational (blocks every story)

### Removing Langfuse (FR-022; plan, Design 7)

- [x] T004 Delete:
  - `services/observability/` and `models/observability.py`;
  - `controllers/admin.py` and `schemas/admin.py`;
  - `migrations/versions/`;
  - `tests/unit/services/test_observability_tracing.py` and `tests/integration/admin/`;
  - `docs/LANGFUSE_SETUP.md`.
- [x] T005 Edit:
  - `services/__init__.py`, `models/__init__.py` and `schemas/__init__.py`;
  - `blueprint.py`: the flush hook and the three admin routes;
  - `services/nl2sql/pipeline.py`: the `_span` blocks, dedented, with `set_tracer` gone;
  - `tasks/cleanup.py`: the two observability rows;
  - `tests/unit/tasks/test_retention.py:65`;
  - `pyproject.toml`: drop `langfuse`.
- [x] T006 `services/llm/service.py`: remove the tracer, `set_tracer` and the error-trace block.

  Test first: `pytest tests/unit tests/contract` passes with no import of `langfuse` or `observability` anywhere. A
  grep test in `tests/unit/test_no_langfuse.py` fails on any import of either name.

### Recording (FR-001 to FR-007, FR-023; plan, Designs 3–4)

#### Tests first

- [x] T007 [P] `tests/integration/analytics/test_recorder.py`:
  - **Rows:** `turn()` inserts a running row at entry, and writes the outcome, steps and texts at exit.
  - **Nesting:** nested `step()` calls set `parent_seq`; an exception in a step sets `ok=False` and `error_code`,
    then re-raises.
  - **Text:** a private turn, or the setting being off, stores no text. `private()` also drops the texts already
    collected. Text over 100,000 characters is cut and marked.
  - **Failing without raising:** a step whose caller sets `ok=False` and an `error_code` is stored that way.
  - **The start row:** it stamps `queued_at`, `is_admin`, `event_id` and `category_id` from the question and the
    user.
  - **Own connection:** the writes don't change `db.session`'s state. A pending row on the session is neither
    committed nor lost.
  - **Failures:** a failing write (monkeypatched) is logged and doesn't raise.
  - **No turn:** outside a turn, every call is a no-op.
- [x] T008 [P] `tests/integration/analytics/test_outcomes.py` (SC-001):
  - Drive `answer_chat` with the model mocked to each outcome:
    - answered on each of the six routes;
    - failed (query processing);
    - failed (internal);
    - a soft timeout (`SoftTimeLimitExceeded` raised inside `generate`);
    - access denied;
    - refusal;
    - couldn't plan.
  - Also these cases:
    - an answer saved as a failure (a failed query, or a model call that failed and was answered politely) →
      `failed`;
    - the soft limit fired inside a query (`executor.execute`) and inside Jev's call → `timeout`.
  - Each must leave exactly one turn with the right `outcome` and `error_code`.
  - A turn that fails before routing still has `is_admin` and `event_id`, and the default "users only" stats count
    it.
  - A turn left without an end past 160 s counts in `no_end_record`.
- [x] T009 [P] `tests/integration/analytics/test_steps.py` (SC-002, FR-004):
  - **Every route:** for one answer per route, run through the real services with the model mocked:
    - the steps hold every call record of the turn, in order;
    - the turn's tokens and known cost equal the sum of its steps;
    - `llm_calls` equals the number of `generate()` calls plus Jev's call.
  - **Failed calls:** a `generate()` that returns an error response is stored as `ok=False` with its error type.
  - **The data route** adds: classifier → generator → query (failing) → correction → query → formatter, with
    `parent_seq` and `corrections=1`.
  - **Jev:** with Jev on, its step comes first, with its cost.
  - **Failed attempts:** a 429 attempt that reaches instructor is recorded, with an unknown cost.
  - **SDK retries:** for an OpenAI-SDK provider other than ibis, an `httpx.MockTransport` answers 429 then 200. The
    step must show `attempts=2` and the 429.
  - **Cost:** OpenRouter's `usage.cost` is read when ibis's `cost_usd` is missing.
- [x] T010 [P] `tests/integration/analytics/test_privacy.py` (SC-005, FR-009, FR-011, FR-012):
  - **Leak test:** a GitHub answer over the fake GitHub, with a known marker string in an issue body and a known
    fake token, then a follow-up on another route in the same chat.
    - Neither the marker nor the token appears in any `turn_texts`, `turn_steps` or `turns.record` value, the trace
      response, the thumbs-down queue or the export.
    - Both turns are private, and the GitHub turn's Jev and classifier texts are gone too.
    - The tool steps exist with names, times and outcomes.
  - **Deleting a chat** deletes its texts and keeps its turns.
  - **Deleting a user** clears `user_id` and deletes the texts; anonymising them does the same.
  - **Merging users** moves the turns to the account that remains.
- [x] T011 [P] `tests/integration/analytics/test_rating.py` (FR-007):
  - a thumbs up sets `rating=1`; switching to down sets -1; withdrawing it sets NULL;
  - a comment alone doesn't change the rating;
  - a vote cast between the answer's commit and the recorder's end write is still on the turn after the end write.

#### Code

- [x] T012 `services/analytics/recorder.py` (Design 3). Makes T007 pass.
- [x] T013 `tasks/chat.py`: the body runs inside `recorder.turn(...)`, and each branch calls `finish` (Design 4).
- [x] T014 `services/llm/service.py` and `factory.py`:
  - each `generate()` is one step, with its texts, and `ok`/`error_code` from the response;
  - `SoftTimeLimitExceeded` is re-raised (audit finding #1);
  - `_record_failed_attempt` takes `openai.APIError`;
  - `completion_record` reads OpenRouter's `usage.cost`;
  - every OpenAI-SDK client gets the `httpx` response hook that counts attempts (plan, Design 3).
- [x] T015 [P] `services/knowledge/gate.py`: the Jev step, and `SoftTimeLimitExceeded` re-raised before the
  broad `except`.
- [x] T016 [P] `services/nl2sql/executor.py`: the query step, with the timeout code and the preview, and
  `SoftTimeLimitExceeded` re-raised before the broad `except`.
  `services/nl2sql/models.py` and `pipeline.py`: `PipelineResult.truncated` and `sql_ms`.
- [x] T017 [P] `services/connectors/loop.py`: the tool steps and the stop reason.
- [x] T018 `services/chat/service.py` (Design 4):
  - `recorder.private()`, at the start for a chat holding a GitHub answer and on the `connector` route;
  - the `recorder.update(...)` call with every field;
  - the `failed` outcome for answers saved as failures.

  Makes T008 and T009 pass.
- [x] T019 [P] `services/feedback/service.py`: the rating. Makes T011 pass.
- [x] T020 Privacy hooks:
  - `services/chat/session_manager.delete_session`;
  - `plugin.py`: merged, db_deleted and anonymized.

  Makes T010 pass.
- [x] T021 `tasks/cleanup.py`: the two retention rows and the orphan-text statement (Design 8).

  Test first, in `tests/unit/tasks/test_retention.py` and `tests/integration/analytics/test_retention.py` (SC-006):
  - texts older than the setting go, and turns stay;
  - with `retention_turn_days` set, old turns go with their steps and texts;
  - the texts of a deleted chat go.

## Phase 3: User Story 1 — usage, cost and speed (P1)

### Tests first

- [x] T022 [US1] `tests/integration/analytics/seed.py`: a fixed seed.
  - Contents:
    - 60 days of turns across all routes, outcomes, users and admins, two events in two categories, two models;
    - steps with tokens and cost, some unpriced;
    - ratings, plans in every status, reports of every kind.
  - A function per query computes the expected value with plain SQL over the seed, written independently of
    `stats.py`.
- [x] T023 [US1] `tests/integration/analytics/test_stats_usage.py` (SC-007, FR-014):
  - **Golden tests:** one for each query in Design 5's Tiles, Adoption, Cost and Speed rows.
  - **Ranges:** "7 days" covers exactly 7 days in the admin's timezone.
  - **Admins:** excluded by default, included with `admins=1`.
  - **Filters:** a route filter narrows every number.
  - **Unknown cost:** an unpriced call counts in `unpriced_share` and not in the spend.
- [x] T024 [US1] `tests/integration/analytics/test_api.py` (FR-019, FR-020, SC-008):
  - **Access:** a logged-in non-admin gets 403 on every new endpoint and page; an anonymous user gets the login
    response.
  - **Cache:** a second call within 45 s doesn't query, and a different filter does.
  - **Rate limit:** the read limit applies.

### Code

- [x] T025 [US1] `services/analytics/stats.py`: the US1 queries, `collect()` and the cache (Design 5).
- [x] T026 [US1] `controllers/analytics.py`, `blueprint.py` and `views.py`: `GET /api/assistant/admin/analytics`, the
  page route `!/admin/assistant-analytics/`, and the menu item (`_admin_menu` yields both).
- [ ] T027 [US1] `static/js/analytics/charts.js`, ported from ibis-chat's `public/charts.js`: keep `el`, `sv`,
  `tabs`, `tileInto`, `lineChart`, `niceTicks`, the tooltip and PNG/SVG download, and drop the rest.
  - `analytics.js`: the range tabs, the filters, the URL-hash state, the tiles, and the adoption, cost and speed
    sections, each with an empty state.
  - `templates/admin_analytics.html`, extending `layout/admin_page.html`.
- [ ] T028 [US1] Browser check, as `tests/browser/walk.mjs` does: the page renders with the seed, with no console
  errors and with the CSP nonce, and a hash link restores the filters.

## Phase 4: User Story 2 — one answer's trace (P1; the MVP ends here)

### Tests first

- [x] T029 [US2] `tests/integration/analytics/test_trace.py`:
  - **The trace:** `GET /admin/turns/<id>` returns the turn, its ordered steps and its texts. For texts past their
    retention it returns `expired`.
  - **GitHub turns:** the trace returns no texts.
  - **The list:** filters by route, outcome, user, event, model and date, newest first, with keyset paging.
  - **Lookups:** `?answer=<message id>` resolves the turn. A report's `copy.reported_answer_id` links to its turn.
  - **What's shown:** the question and the answer are included only while the turn's texts are kept and it isn't
    private. Past retention, or for a private turn, neither appears.
  - **Speed:** the trace answers in under 300 ms on the SC-003 seed.

### Code

- [x] T030 [US2] `controllers/analytics.py`: the turn list and trace endpoints.
- [ ] T031 [US2] `templates/admin_turn.html` plus the trace view in `analytics.js`:
  - the header (question, answer, outcome, route decision);
  - the timeline of steps with their durations, with expandable texts;
  - the plan and the rating.
- [x] T032 [US2] Links: the turn list on the analytics page, and "open the trace" on the admin report page
  (`templates/admin_report.html`).

## Phase 5: User Story 3 — how well it answers (P2)

- [x] T033 [US3] Tests first, in `test_stats_quality.py`:
  - golden tests for the Quality row;
  - the 9-rating case shows "not enough ratings (9 of 10)";
  - the Wilson interval matches a hand-computed value.
- [ ] T034 [US3] Code: the queries, plus the quality section, including the thumbs-down queue with trace links.

## Phase 6: User Story 4 — routing and the agent's work (P2)

- [x] T035 [US4] Tests first, in `test_stats_routing.py`: golden tests for the Routing, Depth and Plans rows.
- [ ] T036 [US4] Code: the queries and the sections.

## Phase 7: User Story 5 — errors and export (P3)

- [x] T037 [US5] Tests first, in `test_export.py`:
  - the CSV and JSON rows match the turn list for the same filters;
  - `text=1` adds the texts that are still kept. A private turn has neither texts nor its question and answer;
  - the export logs a line with the user, the filters and the text flag.
  - Also golden tests for `errors_by_type` and `no_end_record`.
- [ ] T038 [US5] Code: the export endpoint and the errors section.

## Phase 8: Polish and checks

- [x] T039 Speed (SC-003): `tests/integration/analytics/test_speed.py` seeds 50,000 turns and 400,000 steps in bulk.
  The stats endpoint must take under 2 s uncached and under 100 ms cached, and the trace under 300 ms. The test is
  marked `slow`, and fixes go in the indexes.
- [ ] T040 The live window (instructions at the top):
  1. `pg_dump`, then `PYTHONPATH=… indico db --plugin assistant upgrade`. Check that the three observability tables
     are gone and the three new ones exist.
  2. `pip uninstall langfuse` from `instance/env`.
  3. Restart the web server and the worker on the worktree.
  4. With Lucas's go, ask one question per route.
  5. Check:
     - each turn's trace;
     - the page's numbers against `psql`;
     - SC-004: the recording's added time, and two transactions.
  6. Run the downgrade and the upgrade again.
  7. Restore the stack to main (skill, "Restore").
- [x] T041 [P] Docs:
  - `README.md`: the Analytics section, the settings and the retention line, plus the removals in Design 7.
  - `docs/VECTOR_SEARCH_SETUP.md`: `/search/status`.
  - `docs/DEPLOYMENT.md`: the drop in migration 011, and uninstalling `langfuse`.
- [ ] T042 All of `pytest tests` from the worktree passes, apart from the T001 baseline.
- [ ] T043 The ONE pull request, `024-assistant-analytics` → main. Its description covers the spec, the plan and the
  code. Copilot credits are out, so run `/fresh-review` and record its findings in the fix commit. Never merge.

## Dependencies

- **Phase 1** comes first; T001 before any code.
- **Phase 2** blocks every story. T004–T006 (removing Langfuse) come before T014, which rewrites the same block of
  `generate()`.
- **US1 (phase 3)** comes before US2 (phase 4), because US2's page links from US1's.
- **US3, US4 and US5** can run in any order after US1.
- **T040** needs T002–T038. **T043** needs T040–T042.

**The MVP** is phases 1–4: every turn recorded, the usage, cost and speed page, and the trace.

**Overlap with the 2026-10-01 scale audit:** T014 includes audit finding #1, the timeout re-raise in `generate()`.
If the audit's fix batch lands first, T014 only adds the step.
