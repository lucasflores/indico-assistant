# Implementation Plan: Assistant analytics and traces

**Branch**: `024-assistant-analytics` · **Date**: 2026-10-02 · **Spec**: [spec.md](spec.md) · **Reference**:
ibis-chat's Router Analytics (`~/thoth/ibis-chat`: `ibis_chat/stats.py`, `public/charts.js`, `public/stats.js`,
`db/views.sql`, `db/deltas.sql`)

## Summary

- **Recording:** a recorder lives in a context variable for the length of one `answer_chat` task.
  - It inserts the turn when the worker starts it, collects a step for each model call, query, Jev call and tool
    call, and writes everything when the task ends, whatever the outcome.
  - It writes on its own database connection, so it never touches the answer's transaction.
- **Storage:** three new tables. `turns` has one row per answer, `turn_steps` one row per step, and `turn_texts` the
  prompts, responses, SQL and row previews, kept 30 days. The same migration drops Langfuse's three tables.
- **Reading:**
  - Admin-only JSON endpoints serve the stats, the turn list, one trace and the export.
  - Each number is one named SQL query in `services/analytics/stats.py`, cached for 45 s in Redis.
  - Two admin pages draw them with a small chart script ported from ibis-chat.
- **Removing:** the Langfuse code, its settings, endpoints, tests, docs and dependency.

## Technical Context

- **Language/runtime:** Python 3.12 inside Indico 3.3.13.
  - Answers run in the Celery task `answer_chat` (queue `assistant`, request context, 120 s soft limit and 150 s
    hard limit).
  - The pages and API run in the web server.
- **New dependencies:** none. `langfuse` is removed.
- **Storage:**
  - migration `011_analytics` (down revision `010_create_connections`): creates 3 tables and drops 3;
  - settings: 3 new, 6 removed.
- **Scale:** small for a long time (Lucas, 2026-10-02). Live SQL over indexed time ranges is enough, with no rollups.
  SC-003 checks 50,000 turns.
- **Testing:** pytest, test-first.
  - Turns run through the real services with the model mocked, and the stats are checked against a fixed seed.
  - Page and API access follow `tests/integration/reports/test_pages.py`.
  - The baseline is T001.

## Constitution Check (1.1.0)

| Principle | How this plan meets it |
|---|---|
| I. Indico plugin architecture | The tables live in `plugin_assistant`, created and dropped by an Alembic migration. The pages use `RHAdminBase`, `WPAdmin` and the `admin-sidemenu` signal. Settings go in `default_settings` and the settings form. The plugin keeps listening to Indico's user signals. |
| II. API first | The pages only draw what the JSON endpoints return: stats, turns, trace and export. |
| III. LLM abstraction | Unchanged. Recording sits inside `LLMService.generate()`, and the tracer hook goes. |
| IV. Graceful degradation | A failure to record is logged and never changes the answer. There are no locks while the answer runs, and at most two short transactions per turn, on their own connection. |
| V. Configuration | Three global settings. None per event. |
| VI. Test-first | Every task lands with its tests first. |
| Security | The pages and API are admin-only and rate-limited. GitHub turns store no text, which a leak test checks. Text is deleted with its chat or user. Queries use bound parameters. |

## Design

### 1. Settings (`default_settings.py`, `forms.py`)

- **New:**
  - `analytics_trace_text`: True. Whether to keep the text.
  - `retention_trace_text_days`: 30.
  - `retention_turn_days`: 0, meaning forever.

  The form adds them next to the other retention fields, with descriptions that say what each one keeps.
- **Removed:** `langfuse_enabled`, `langfuse_host`, `langfuse_public_key`, `langfuse_secret_key`,
  `langfuse_privacy_level` and `retention_error_days`, along with its form field. Stored values are harmless:
  strict `get_all` drops unknown keys.

### 2. Tables (`models/analytics.py`, `migrations/011_analytics.py`)

There are no foreign keys to chats, messages, users or events (spec, "Outlives the chat"). Unknown values stay NULL.

**`turns`** (one per answer attempt):

| Group | Columns |
|---|---|
| Key | `id` BIGSERIAL; `job_id` VARCHAR(32) UNIQUE |
| Who and where | `user_id` INT NULL; `is_admin` BOOL; `session_id` UUID; `message_id` UUID (the question); `answer_id` UUID NULL (the answer message); `event_id` INT NULL; `category_id` INT NULL; `private` BOOL (no text kept; FR-009). All but `answer_id` and `private` are stamped by the start row |
| When | `queued_at` (the question's `created_at`); `started_at`; `finished_at` NULL (NULL means running, or "no end record" once past the hard limit: the worker died or the end write failed) |
| Outcome | `outcome` VARCHAR(24) NULL: answered, failed, timeout, access_denied, refusal, cannot_plan. `error_code` VARCHAR(48) |
| Routing | `route` VARCHAR(16); `decided_by` VARCHAR(16): jev, classifier, shortcut or planner; `jev_confidence` FLOAT; `fallback` VARCHAR(48) |
| Totals | sums over the turn's steps: `llm_calls` SMALLINT (steps of kind llm or jev); `prompt_tokens` INT; `completion_tokens` INT; `cost_usd` NUMERIC(12,6), the known sum; `unpriced_calls` SMALLINT (llm/jev steps without a cost report) |
| Data route | `intent` VARCHAR(48); `corrections` SMALLINT; `row_count` INT; `truncated` BOOL; `sql_ms` INT |
| Others | `plan_id` UUID; `tool_calls` SMALLINT; `rating` SMALLINT (1, -1 or NULL) |
| The rest | `record` JSONB: the route record (`_route_record`), plus Jev's cost and probabilities, the knowledge pages, the tool-loop stop reason |

Indexes: `started_at`; `(user_id, started_at)`; `answer_id`; `session_id`; and a partial index on `started_at WHERE
finished_at IS NULL`.

**`turn_steps`**:

| Column | Notes |
|---|---|
| `id` BIGSERIAL | |
| `turn_id` | BIGINT FK → `turns` ON DELETE CASCADE |
| `seq` SMALLINT, `parent_seq` SMALLINT NULL | UNIQUE `(turn_id, seq)` |
| `kind` VARCHAR(8) | llm, sql, jev or tool |
| `stage` VARCHAR(48) | for model calls, the response model's name (`QueryClassification`, `SQLGeneration`, …); the page shows a friendly label |
| `name` VARCHAR(64) | the tool name, or the SQL intent |
| `offset_ms`, `duration_ms` INT | |
| `ok` BOOL, `error_code` VARCHAR(48) | |
| `requested_model`, `served_model`, `ibis_chosen` VARCHAR(128), `ibis_dial` VARCHAR(32) | model calls |
| `prompt_tokens`, `completion_tokens` INT, `cost_usd` NUMERIC(12,6), `attempts` SMALLINT | model calls |
| `row_count` INT | queries |

**`turn_texts`**:

| Column | Notes |
|---|---|
| `id` BIGSERIAL | `tasks/cleanup.purge` deletes by `id` |
| `turn_id` | BIGINT FK → `turns` ON DELETE CASCADE |
| `seq`, `kind` | kind is prompt, response, sql or rows; UNIQUE `(turn_id, seq, kind)` |
| `text` TEXT, `cut` BOOL | |
| `created_at` | indexed, for retention |

The turn's own question and answer are the steps' texts too. The trace reads them from the chat while it exists.

**Growth:** at 5,000 turns a month, about 8 steps each, that's 40,000 step rows a month. Text runs about 50 KB a
turn over the 30 days, so about 250 MB.

**Dropped:** `observability_sync_log`, `observability_error_records` and `observability_usage_stats`, in 003's
order. The downgrade recreates them from 003's body, and leaves `uuid-ossp` alone.

### 3. The recorder (`services/analytics/recorder.py`)

**The turn:**
- `turn(job_id, user_id, session_id, message_id)` is a context manager around the whole body of `answer_chat`.
  - **On entry**, it inserts the turn row in its own transaction, through `db.engine.begin()`, and sets the context
    variable.
    - The row is one `INSERT … SELECT` that stamps who and where (FR-002) from the question's row and the user's
      row: `queued_at`, `event_id` and its `category_id`, and `is_admin`.
    - So a turn that fails before routing still has them, and the admin filter (`is_admin IS NOT TRUE`) never drops
      it.
  - **On exit**, it always writes, in one more transaction on its own connection:
    1. an UPDATE of the turn: outcome, the totals (summed over its steps), and fields. It also sets `rating` from
       `feedback_entries` for `answer_id`, so a vote cast before this write isn't lost (FR-007);
    2. the steps (executemany);
    3. the texts, unless the turn is private.
  - **Errors:** the recorder catches and logs its own errors. It never raises into the task.
- `finish(outcome, error_code=None)` and `update(**fields)` are called by the task and the chat service.

**The steps:**
- `step(kind, stage, name=None)` is a context manager.
  - It gives the step the next `seq`, and its parent from a context-variable stack.
  - It times the step, and on an exception sets `ok=False` and `error_code` (the exception's class name), then
    re-raises.
  - It yields a mutable `Step` that the caller fills in: models, tokens, cost, attempts, rows, and `ok` and
    `error_code` when the call fails without raising. `generate()` returns errors as `LLMResponse`, so it sets them
    from `response.error`.
- `text(step, kind, value)` adds a text, cut at 100,000 characters. It does nothing while text is off: setting off,
  or the turn is private.
- `private()` marks the turn private, drops the texts collected so far, and keeps any more (FR-009). The chat
  service calls it in two cases:
  - **at the start of `answer()`**, when an earlier answer in this chat has `route = 'connector'` (one EXISTS on
    `chat_messages.metadata_json`);
  - **as soon as the route is `connector`**, which drops Jev's and the classifier's texts.
- **The attempt counter:** `factory.py` gives every OpenAI-SDK client an `httpx.Client` whose `response` event hook
  adds each HTTP attempt and its status to the current step. So retries the SDK makes on its own count: the non-ibis
  providers keep the SDK's default `max_retries=2` (`factory.py:133,171,212`), and the hooks of instructor never
  see those retries.

**Outside a turn** (tests, CLI, the admin health call, `execute_plan`), every call is a no-op. So
`LLMService.generate()` works unchanged everywhere.

**Turns with no end record** are computed by the queries: `finished_at IS NULL AND started_at < now() - interval
'160 seconds'`, the hard limit plus 10 s. They count lost answers and failed end writes together; the log tells
them apart. No sweep is needed.

### 4. Hooks (each one small; the recorder carries the logic)

- **`tasks/chat.py` `answer_chat`:**
  - The body runs inside `recorder.turn(...)`.
  - Each `except` branch calls `finish(...)` with its outcome: timeout, access_denied, failed (query processing),
    failed (internal).
  - Success: `finish('answered')`, unless the service already set an outcome: refusal, cannot_plan, or failed for an
    answer saved as a failure (see `answer()` below).
- **`services/llm/service.py`:**
  - **Steps:** `generate()` wraps `create()` in `recorder.step('llm', response_model.__name__)`. It fills the step
    from this call's own `calls`: tokens and cost summed over attempts (each was billed), `unpriced` if any attempt
    has no cost, the served model and ibis pick from the last attempt, and `attempts = len(calls)`.
  - **Texts:** the prompt as the JSON of `messages` (system, history, prompt), and the response as
    `result.model_dump_json()` or the error.
  - **Timeout (audit finding #1):** `SoftTimeLimitExceeded` is re-raised before the broad `except`, so the task's
    timeout branch runs. The same `except SoftTimeLimitExceeded: raise` goes before the other broad handlers on the
    answer's path: `executor.py:118` and `gate.py:186`. Without this, a timeout is never recorded as one.
  - **Failed attempts:** `_record_failed_attempt` widens from `APIConnectionError` to `openai.APIError`, so 429 and
    5xx attempts that reach instructor are recorded, with the status code as `error`. Attempts inside the SDK are
    counted by the HTTP hook (Design 3).
  - **Step outcome:** `ok` and `error_code` are set from the `LLMResponse` (FR-003).
  - **Cost:** `completion_record` also reads OpenRouter's `usage.cost` when ibis's `cost_usd` is missing (FR-005).
  - **Removed:** the tracer, `set_tracer` and the error-trace block (inventory 1).
- **`services/knowledge/gate.py` `decide()`:** `recorder.step('jev', 'route')`, with Jev's model, cost
  (`usage.cost`), skip reason and the request and decision as texts.
- **`services/nl2sql/executor.py` `execute()`:**
  - `recorder.step('sql', intent)`, with the rows returned and whether the result was cut off.
  - A timeout's message ("timed out after") becomes `error_code='timeout'`.
  - The texts are the SQL and a preview of up to 20 rows, as JSON with each value cut at 500 characters. The
    document template's preview is its passages.
- **`services/nl2sql/pipeline.py`:**
  - `PipelineResult.truncated`, copied from `ExecutionResult.truncated`, which was never passed on before.
  - `sql_ms` sums every execution, corrections included.
  - The tracer `_span` blocks go (inventory 1).
- **`services/connectors/loop.py`:**
  - The turn is already private by the time the loop runs (Design 3).
  - Each tool call is `recorder.step('tool', 'github', name)`.
  - The stop reason (answered, steps, budget, repeated, failed) and the access state go into `record`.
- **`services/chat/service.py` `answer()`:**
  - At the start, `recorder.private()` if the chat holds a GitHub answer. Again as soon as the route is
    `connector`.
  - One `recorder.update(...)` near the end: `answer_id`, `route`, `decided_by`, `jev_confidence`, `fallback`, and
    `record` (the route record plus extras).
  - From `PipelineResult`: intent, corrections, rows and truncated.
  - Also `plan_id` and `tool_calls`.
  - **The outcome:**
    - refusal and cannot-plan set it;
    - so does an answer saved as a failure, as `failed`. That's metadata `problem == 'failed'`, or a knowledge or
      chat answer with `failed=True`. Its `error_code` comes from `pipeline_error.error_type`, or is `model_error`.
- **`services/feedback/service.py`:** `submit_feedback` and `withdraw_feedback` set or clear `turns.rating` by
  `answer_id`. Only thumbs count: thumbs up is 1, thumbs down is -1.
- **Privacy (`plugin.py`, `services/chat/session_manager.py`, `tasks/cleanup.py`):**
  - `delete_session` deletes the texts of that chat's turns.
  - On `users.merged`, the turns' `user_id` moves to the account that remains.
  - On `users.db_deleted` and `users.anonymized`, `user_id` is set to NULL and the texts are deleted. This rides
    the existing `_forget_connections` path, after the flush.
  - The nightly task deletes the texts of turns whose chat no longer exists.

### 5. Stats (`services/analytics/stats.py`)

- **Shape:** one function per number, each one SQL statement with bound parameters `(since, until, tz, filters)`.
  Each returns plain lists and dicts.
- **Assembly:** `collect(params)` builds the page's payload. It's cached in `make_scoped_cache('assistant-analytics')`
  under a hash of the params, for 45 s (FR-020).
- **Days** are bucketed with `date_trunc('day', started_at AT TIME ZONE :tz)`, using the admin's Indico timezone.
- **Rates:** Wilson 95% intervals and the minimum-count rule (FR-016) are applied in Python.

| Section | Queries |
|---|---|
| Tiles | `tiles` |
| Adoption (US1) | `turns_per_day_by_route`, `active_users` (per day, per week), `chats` (turns per chat), `returning_users`, `top_events`, `top_categories` |
| Cost (US1) | `spend_per_day` (by route, stage, model), `cost_per_turn` (p50/p90 per route), `tokens_by_stage`, `top_spenders`, `costliest_turns`, `unpriced_share`, `cost_per_helpful` |
| Speed (US1) | `latency_by_route` (p50/p90), `queue_wait`, `step_time` (by stage), `model_time` (by model), `sql_time`, `jev_time`, `time_limit_hits` |
| Quality (US3) | `satisfaction` (by route, intent, model), `unrated_share`, `thumbs_down_queue` (50 newest, joined to the comment while the chat exists), `data_health` (success, corrections, timeouts, empty, truncated), `refusals`, `reports_by_kind` |
| Routing (US4) | `route_mix`, `jev_confidence` (histogram), `jev_skips`, `fallbacks`, `negative_by_route` |
| Depth (US4) | `calls_per_turn` (by route), `correction_loops`, `tool_calls` (per tool, with failure rate), `loop_steps` |
| Plans (US4) | `plan_funnel` (shown, confirmed, carried out, undone), `plan_failures` (by action), `time_to_confirm`, read from `action_plans` |
| Errors (US5) | `errors_by_type` (per day), `no_end_record` |

Percentiles use `percentile_cont`. Admin traffic is excluded unless the filter includes it.

### 6. API and pages (`controllers/analytics.py`, `blueprint.py`, `views.py`, `templates/`, `static/`)

**API:** `RHChatBase` subclasses with `ADMIN_ONLY = True` and `RATE_LIMIT = 'read'`:
- `GET /api/assistant/admin/analytics?range=…&since=…&until=…&route=…&model=…&user=…&event=…&category=…&admins=0|1`
  returns the payload.
- `GET /api/assistant/admin/turns?…&before=<id>&limit=50` returns the keyset-paged list.
- `GET /api/assistant/admin/turns/<id>` returns the turn, its steps in order, its texts (or `expired`), its rating
  and comment, its plan, and any reports that cite its answer.
  - The question and the answer are read from the chat and included only while the turn still has texts and isn't
    private (FR-010).
  - The thumbs-down queue and the export follow the same rule.
- `GET /api/assistant/admin/turns/export.csv|json?…&text=0|1` returns the export, and logs `assistant analytics
  export` with the user, the filters and the text flag (FR-021).

**Pages:** `RHAdminBase` with `WPAnalyticsAdmin`, built like `WPReportsAdmin`:
- `!/admin/assistant-analytics/` (`admin_analytics.html`);
- `!/admin/assistant-analytics/turns/<int:turn_id>/` (`admin_turn.html`).

The menu: `_admin_menu` yields both items, reports and analytics.

**Links:**
- the thumbs-down queue and the turn list link to the trace;
- an issue report's admin page links the turn whose `answer_id` matches `copy.reported_answer_id`;
- `?answer=<message id>` on the turn route resolves a turn from a chat message.

**Script:** `static/js/analytics/charts.js` is ported from ibis-chat's `charts.js` (304 lines: `el`, `sv`, `tabs`,
`tileInto`, `lineChart`, `niceTicks`, the tooltip, PNG/SVG download). `analytics.js` draws the sections from the
payload, keeps its state in `location.hash`, and lazy-loads the turn list. It's served with the CSP nonce, as the
panel snippet is.

### 7. Removing Langfuse (inventory from 2026-10-02)

- **Delete:**
  - `services/observability/` (all 6 files) and `models/observability.py`;
  - `controllers/admin.py` and `schemas/admin.py`;
  - `migrations/versions/`, dead copies that alembic never reads;
  - `tests/unit/services/test_observability_tracing.py` and `tests/integration/admin/`;
  - `docs/LANGFUSE_SETUP.md`.
- **Edit:**
  - `services/__init__.py`: the imports and `__all__`;
  - `services/llm/service.py`;
  - `services/nl2sql/pipeline.py`: the six `_span` blocks, dedented;
  - `blueprint.py`: the after-request flush hook, and the `admin_stats`, `admin_errors` and `admin_health` routes;
  - `models/__init__.py` and `schemas/__init__.py`;
  - `tasks/cleanup.py`: the two observability rows;
  - `default_settings.py` and `forms.py`;
  - `tests/unit/tasks/test_retention.py:65`;
  - `README.md`: the observability bullet and settings section, the tree, the docs link, and the wrong "Langfuse
    sync worker" line;
  - `docs/VECTOR_SEARCH_SETUP.md:220-240`: `/admin/health` becomes `/search/status`;
  - `pyproject.toml:33`;
  - `.github/agents/copilot-instructions.md`.
- **The live window:** `pip uninstall langfuse` from `instance/env`.

### 8. Retention (`tasks/cleanup.py`)

- **New rows in `RETENTION`:**
  - `('plugin_assistant.turn_texts', 'created_at', 'retention_trace_text_days')`;
  - `('plugin_assistant.turns', 'started_at', 'retention_turn_days')`. Its steps and texts cascade.
- **One more statement:** delete the texts of turns whose `session_id` no longer exists in `chat_sessions`, so text
  never outlives its chat (FR-011).
- **Removed:** the two observability rows.

## Project Structure

```text
indico_assistant/
├── models/analytics.py                     # new: Turn, TurnStep, TurnText
├── migrations/011_analytics.py             # new: 3 tables up, 3 Langfuse tables down
├── services/analytics/                     # new
│   ├── __init__.py
│   ├── recorder.py                         # context var, turn(), step(), text(), private()
│   └── stats.py                            # one query per number, collect(), cache
├── controllers/analytics.py                # new: API + pages
├── templates/admin_analytics.html, admin_turn.html   # new
├── static/js/analytics/charts.js, analytics.js       # new (charts.js ported from ibis-chat)
├── tasks/chat.py, tasks/cleanup.py         # changed
├── services/llm/{service,factory}.py       # changed: steps, timeout re-raise, failed attempts, HTTP attempt hook, OpenRouter cost, no tracer
├── services/knowledge/gate.py, services/nl2sql/{executor,pipeline,models}.py, services/connectors/loop.py
├── services/chat/{service,session_manager}.py, services/feedback/service.py
├── plugin.py, blueprint.py, views.py, default_settings.py, forms.py, models/__init__.py
├── (deleted) services/observability/, models/observability.py, controllers/admin.py, schemas/admin.py,
│             migrations/versions/
docs/ (LANGFUSE_SETUP.md deleted; VECTOR_SEARCH_SETUP.md, README.md edited)
tests/integration/analytics/                # recorder, hooks per route, stats golden, API, pages, privacy, retention
```

## Complexity Tracking

| Departure | Why | The simpler option, and why not |
|---|---|---|
| Writes on their own connection, outside the ORM session | The answer's session is rolled back on failure, and the failed turn must still be recorded (FR-001, FR-006) | Writing through `db.session` after the task's rollback works only on the failure paths, and would mix the record's commit into the answer's on success |
| A turn row at the start as well as the end | A hard kill runs no code, so a start row is the only way to count lost turns (edge case), and it stamps who and where for turns that fail early | One write at the end loses exactly the failures we most want to see |
| A chart script copied from another repo | FR-017 keeps the page to its own script, with no library to load or update, and Indico ships none | Writing charts from scratch repeats ibis-chat's 304 working lines; a shared package is premature for two users |
