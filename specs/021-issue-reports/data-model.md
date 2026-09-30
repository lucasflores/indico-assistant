# Data model: Issue reports from the chat (021)

## Table `plugin_assistant.issue_reports` (migration `009_create_issue_reports`)

| Column | Type | Rules |
|---|---|---|
| `id` | `integer` PK, serial | shown as "Report #id" |
| `user_id` | `integer`, not null, index | the reporter; a plain id, like `chat_sessions.user_id` |
| `form_key` | `uuid`, not null | made when the form is drawn; `UNIQUE (user_id, form_key)` (R8) |
| `category` | `varchar(20)`, not null | `CHECK IN ('bug', 'feature', 'wrong_answer')` |
| `text` | `text`, not null | 1-5,000 characters after trimming |
| `copy` | `jsonb`, null | the conversation copy (below); null when not attached |
| `status` | `varchar(20)`, not null, default `'open'` | `CHECK IN ('open', 'under_review', 'closed')` |
| `note` | `text`, null | the team's note, at most 2,000 characters |
| `updated_by_id` | `integer`, null | the admin who last saved the status or note |
| `updated_at` | `timestamptz`, null | when the team last saved; null until then. The stale-save check compares it (R11) |
| `closed_at` | `timestamptz`, null, index | set when the status moves to closed; cleared when it moves away. Retention's key (R7) |
| `created_at` | `timestamptz`, not null, default `now()` | when the report was sent |

Index `(status, created_at DESC)` serves the admin list. Retention deletes rows where
`closed_at < now() - retention_report_days` (0 = never). Deleting a report is a plain `DELETE`: the copy is in
the row.

### Status transitions (admins only)

Any status can follow any other (spec FR-017). The only side effect is `closed_at`:

| From → to | `closed_at` |
|---|---|
| anything → `closed` (it was not closed) | `now()` |
| `closed` → `closed` (note-only save) | unchanged |
| `closed` → `open` / `under_review` | `NULL` |
| otherwise | unchanged (`NULL`) |

## The conversation copy (`issue_reports.copy`)

```json
{
  "taken_at": "2026-10-02T14:03:11+00:00",
  "reported_answer_id": "9f2e…",          // null for a report without an answer
  "truncated": false,                     // true when earlier messages were left out (more than 50)
  "messages": [
    {"id": "…", "role": "user", "content": "…", "created_at": "…", "event_id": 351,
     "uploads": [{"filename": "agenda.pdf"}]},
    {"id": "9f2e…", "role": "assistant", "content": "…", "created_at": "…",
     "data_sources": [...], "sql_generated": "SELECT …", "confidence": 0.82,
     "pipeline_success": true, "pipeline_error": null, "problem": null,
     "evidence": {"intent": "event_lookup", "intent_confidence": 0.91, "row_count": 3,
                  "validation_rejection": null, "correction_attempts": 0, "corrected": false,
                  "cached": false},
     "plan": {"summary": "…", "steps": ["…", "…"]}}
  ]
}
```

- **Messages are copied from an allowlist** (R6). The message keys are `id`, `role`, `content`,
  `created_at`, `event_id` and `uploads`. Answers add `data_sources`, `sql_generated`, `confidence`,
  `pipeline_success`, `pipeline_error`, `problem`, `evidence` and `plan`. A key missing from an old answer is
  left out, not nulled.
- **`plan`** is frozen from `action_plans` when the copy is taken. It holds the summary and each step's
  description, as the chat showed them.

**The user's view** of their own report (page and `GET /reports/<id>`) gives `messages` with only `id`, `role`,
`content`, `created_at`, `uploads` and `plan`. The evidence and query keys are for admins (spec FR-013).

## Additions to `chat_messages.metadata_json` (assistant messages)

| Key | Type | Written by | Exposed |
|---|---|---|---|
| `problem` | `"failed" \| "out_of_scope" \| "not_understood" \| "cannot_do"`, absent when fine | `ChatService` (R4) | job result (`RESPONSE_METADATA`), session API, copy |
| `evidence` | object, as in the copy | `ChatService._process_with_nl2sql` (R5) | **copy only**. Left out of `GET /sessions/<id>`, and never in the job result |

Planner answers get `problem` but no `evidence`: they run no query.

## `PipelineResult` additions (`services/nl2sql/models.py`)

`intent: str | None`, `intent_confidence: float | None`, `validation_rejection: str | None`. They are filled
through the `trace` dict that `process` passes to `_process` (R5).

## `PlanTurn` addition (`services/actions/planner.py`)

`problem: str | None = None`: `not_understood` or `cannot_do`, at the return points listed in R4.

## Settings and limits

| Name | Where | Default |
|---|---|---|
| `retention_report_days` | `default_settings.py`, `forms.py` (next to `retention_chat_days`) | `365`; `0` = keep forever |
| `RATE_LIMITS["report"]` | `services/chat/rate_limiter.py` | `("5 per minute", "20 per day")` |

## Validation

| Field | Rule | Error |
|---|---|---|
| `category` | one of the three | `422 VALIDATION_ERROR` |
| `text` | 1-5,000 characters, trimmed | `422` |
| `form_key` | a UUID | `422` |
| `attach` | boolean; `true` needs `session_id` | `422` |
| `session_id`, `answer_id` | the caller's session; the answer is an assistant message in it | `404 NOT_FOUND`, the same whether or not it exists |
| `status` | one of the three | `422` |
| `note` | at most 2,000 characters | `422` |
| `seen` | equals the row's `updated_at` (ISO), or empty when null | `409 STALE` |
