# REST API contract: Issue reports from the chat

**Feature**: 021-issue-reports | **Base**: `/api/assistant` | **Auth**: Indico session or the Chainlit JWT
(`X-Assistant-Auth`), as today

- **Caching**: every response is `Cache-Control: private, no-store`.
- **Errors** use the existing `{"error": CODE, "message": …, "details": …}` shape.
- **CSRF**: a request that changes data and comes with the Indico session cookie must carry Indico's CSRF token
  (`X-CSRF-Token`). One authenticated only by `X-Assistant-Auth` skips that check (R10, spec FR-022).
- **Someone else's report, or one that doesn't exist**, gives the same `404 NOT_FOUND` (spec FR-014).

## User endpoints

### `POST /reports` (new): send a report

```json
{"form_key": "uuid", "category": "bug|feature|wrong_answer", "text": "…",
 "attach": true, "session_id": "uuid|null", "answer_id": "uuid|null"}
```

| Result | Status | Body |
|---|---|---|
| created | `201` | `{"report_id": 12, "url": "<absolute URL of the user's report page>"}` |
| this form was already sent | `200` | the same body, for the existing report (R8) |
| session or answer not the caller's, or missing | `404 NOT_FOUND` | |
| bad field | `422 VALIDATION_ERROR` | |
| limit used up | `429 RATE_LIMITED` | with `Retry-After` |

With `attach: false`, `session_id` and `answer_id` are ignored and nothing from the conversation is stored
(spec FR-004).

**Limits**: this counts only when a report is created, and only against `report` (5 a minute, 20 a day). It never
counts against `chat` (R8).

### `GET /reports` (new): the caller's reports

Returns `{"reports": [{"report_id", "category", "text_start", "status", "note", "created_at", "updated_at"}]}`,
newest first. `text_start` is the first 120 characters. The `read` limit applies.

(ponytail: unpaged, since a user's own list is small, and closed reports are purged after a year. Add a cursor
if someone passes a few hundred.)

### `GET /reports/<report_id>` (new): one of the caller's reports

Returns `{"report_id", "category", "text", "status", "note", "created_at", "updated_at", "copy"}`. `copy` is
the user's view (data-model.md): messages without the evidence or query keys, or `null`.

### `DELETE /reports/<report_id>` (new): delete one of the caller's reports

`204`. The report and its copy are gone (spec FR-013a). Only the reporter can do this, not an admin.

## Admin endpoints (`session.user.is_admin`, otherwise `403 FORBIDDEN`)

### `GET /admin/reports` (new)

Query: `status`, `category` (optional filters), `page` (1-based, 50 per page).

Returns `{"reports": [{…as the user list, plus "user": {"id", "name"}}], "page": 1, "pages": 3, "open": 7}`,
newest first.

### `GET /admin/reports/<report_id>` (new)

Returns the full report:

- `user: {id, name, email}`, the reporter as Indico knows them (not taken from the copy);
- `updated_by: {id, name} | null`;
- `closed_at`;
- `copy` with every key, the evidence included.

### `PATCH /admin/reports/<report_id>` (new)

```json
{"status": "open|under_review|closed", "note": "…", "seen": "<updated_at as last read, or empty>"}
```

| Result | Status |
|---|---|
| saved: sets `updated_by_id` and `updated_at`, and `closed_at` as in data-model.md | `200`, with the report as `GET` returns it |
| `seen` doesn't match | `409 STALE`, with the current report in `details` |
| bad field | `422` |

## Changed

- **`GET /sessions/<session_id>`** leaves `evidence` out of each message's `metadata` (R5).
- **`GET /chat/jobs/<job_id>`**: `RESPONSE_METADATA` gains `problem` (R4).

## Pages (HTML, Indico RHs; not part of the JSON API)

They call the same `services/reports.py` functions as the endpoints above, so the UI does nothing the API can't
(constitution II). Their forms POST with Indico's `csrf_token`.

| Route | What |
|---|---|
| `GET /user/assistant-reports/`, `/user/<user_id>/assistant-reports/` | the list (spec FR-012) |
| `GET /user/…/assistant-reports/<report_id>/` | one report, as the user sees it (spec FR-013) |
| `GET`, `POST /user/assistant-reports/<report_id>/delete` | the confirmation, then the delete (spec FR-013a; the reporter only) |
| `GET /admin/assistant-reports/` | the triage list: filters and pages (spec FR-015) |
| `GET`, `POST /admin/assistant-reports/<report_id>/` | one report with its evidence; the status and note form (spec FR-016, FR-017) |
