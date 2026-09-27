# REST API contract: Chat actions

**Feature**: 019-chat-actions | **Base**: `/api/assistant` | **Auth**: Indico session or the Chainlit JWT (as today)

Every response is `Cache-Control: private, no-store` (as for all assistant endpoints). Errors use the existing
`{"error": CODE, "message": …, "details": …}` shape.

## Chat job response (changed)

`GET /chat/jobs/<job_id>`: when the answer is a plan, `status: "done"` also carries `plan`:

```json
{
  "status": "done",
  "session_id": "…", "message_id": "…",
  "response": "Here is the plan. Which category should it go in?",
  "plan": {
    "id": "5b0c…", "status": "shown", "expires_at": "2026-09-28T12:30:00Z",
    "token": "q0Vt…",                       // confirm token; returned only to the plan's owner, only here
    "summary": "Create a Teams meeting …",
    "steps": [{"n": 1, "description": "…", "side_effects": ["…"]}],
    "questions": [{"id": "category", "text": "…", "kind": "choice", "choices": [{"value": "12", "label": "…", "note": "…"}]}],
    "suggestions": [{"id": "s1", "kind": "description", "content": "…", "source": {"type": "chat", "label": "this chat"}}],
    "can_confirm": false                    // false while questions are open
  }
}
```

`plan` is added to `ChatResponse` as an optional field; it is omitted when `None`. The step `args` are not sent
to the client; the plain-language `description` is what the user confirms.

A job for an executed plan (below) finishes as `status: "done"`, with `response` listing what was created and
links to it, and `plan.status` set to `done` / `failed` / `refused`.

## `POST /chat` (changed)

The body gains `uploads: [uuid, …]`, at most 5, each returned by `/chat/uploads` for this user. It responds
`422 VALIDATION_ERROR` if a uuid is unknown, already claimed or belongs to someone else.

## `POST /chat/uploads` (new)

`multipart/form-data`: `file` (one per request) and `session_id` (optional; the chat the file belongs to).

| Status | Body |
|---|---|
| 201 | `{"uuid": "…", "filename": "slides.pdf", "size": 1048576, "content_type": "application/pdf"}` |
| 413 | `{"error": "FILE_TOO_LARGE", "message": "Files can be at most 25 MB"}` |
| 415 | `{"error": "UNSUPPORTED_FILE_TYPE", "message": "Allowed: pdf, docx, pptx, xlsx, txt, md, png, jpg"}` |
| 429 | rate limited (`read`) |

- The file type is checked by extension **and** by the content (not the client-supplied MIME type).
- The size is the smaller of 25 MB and `MAX_UPLOAD_FILE_SIZE` (when set).
- The file is stored as an unclaimed Indico `File` (data-model.md).

## `GET /plans/<plan_id>` (new)

`200` returns the `plan` object above, without `token`. `404` if the plan is unknown or belongs to someone else.

## `POST /plans/<plan_id>/confirm` (new)

Body: `{"token": "…"}`.

| Status | Meaning |
|---|---|
| 202 | `{"job_id": "…", "plan_id": "…", "status": "confirmed"}`: queued; poll `/chat/jobs/<job_id>` |
| 404 `NOT_FOUND` | unknown plan, or not the user's |
| 409 `PLAN_NOT_CONFIRMABLE` | already confirmed, cancelled, superseded or expired, or it has open questions. `details.status` gives the current status |
| 403 `INVALID_TOKEN` | the token does not match this version |
| 403 `ACTIONS_DISABLED` | writes are switched off (FR-021) |

- The confirm is one atomic state transition (data-model.md), so confirming twice returns 202 once and 409
  after that.
- Permissions are checked again in the worker (FR-008). A plan that fails there ends as `refused`, with the
  reason in the job's `response`.
- Rate limit: `read`.

## `POST /plans/<plan_id>/cancel` (new)

`200` returns `{"plan_id": "…", "status": "cancelled"}`. `409` if the plan is no longer `shown`. Rate limit:
`read`.

## Chainlit

- A plan answer renders `summary`, steps, questions (as choice buttons) and suggestions, plus
  `cl.Action(name="confirm_plan", payload={"plan_id", "token"})` and `cl.Action(name="cancel_plan",
  payload={"plan_id"})`. The confirm button appears only when `can_confirm` is true.
- The action callbacks call the endpoints above, poll the job, post the outcome, and `remove_actions()` on the
  plan message.
- A choice or suggestion button sends its value as a chat message ("Thoth » Engineering » Meetings", "add
  suggestion s1"), which makes the planner produce a revision.
- `on_message` uploads every attached element (`message.elements[i].path`) to `/chat/uploads` first, then posts
  the message with `uploads`.
