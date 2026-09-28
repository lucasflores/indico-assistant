# REST API contract: Persistent assistant with past chats

**Feature**: 020-chat-persistence | **Base**: `/api/assistant` | **Auth**: Indico session or the Chainlit JWT (as today)

Every response is `Cache-Control: private, no-store`. Errors use the existing `{"error": CODE, "message": …,
"details": …}` shape. Every session endpoint acts only on the caller's own sessions: someone else's gives
`403 SESSION_ACCESS_DENIED`, and a missing one gives `404 SESSION_NOT_FOUND`, as today.

## `POST /chat` (changed)

- `session_id` may be an id that does not exist yet. Indico then creates the session with that id, owned by
  the caller (R5). If the id exists and is someone else's: `403`.
- `event_id` is now **the page the message is sent from**, stored on the user message (R8). It is no longer
  checked against the session's event: a message from another event's page is accepted, and access is
  checked for its own event (`403 EVENT_ACCESS_DENIED` if the user cannot access it).
- The queued `job_id` is stored on the user message (R9). The response is unchanged.

## `GET /sessions` (changed)

Query parameters:

| Param | Meaning |
|---|---|
| `limit` | 1-100, default 20 (unchanged) |
| `cursor` | **new**: opaque; the `next_cursor` of the previous page. It replaces `offset`, which is still accepted and ignored when `cursor` is given |
| `search` | **new**: words to match in the title or in the caller's own messages (case-insensitive) |

Each item gains `title` (the stored title, or the first user message cut to 60 characters) and `updated_at`.
The response gains `next_cursor` (null on the last page):

```json
{"sessions": [{"session_id": "…", "title": "Move the weekly sync", "created_at": "…", "updated_at": "…",
               "last_message_at": "…", "message_count": 6, "event_id": 351}],
 "total": 42, "limit": 20, "next_cursor": "MjAyNi0wOS0yOFQx…"}
```

The order is `updated_at` descending, then `id`.

## `GET /sessions/<id>` (changed)

Adds `title`, `updated_at`, and `pending_job_id`: the `job_id` of the last message when that message is the
user's and has no answer yet. Otherwise it is null. Each message gains `metadata.event_id` for user messages,
where it is known.

## `PATCH /sessions/<id>` (new)

Body `{"title": "…"}`, 1-200 characters after trimming. It responds `200` with the session item.

## `DELETE /sessions/<id>` (unchanged)

It deletes the session and its messages. Its action plans stay (spec 019).

## `POST /plans/<plan_id>/token` (new)

Owner only. The plan must be `shown`, unexpired and not superseded, otherwise `409 PLAN_NOT_CONFIRMABLE`. It
replaces the plan's confirm token and returns the plan as `PlanView`, with the new `token`, exactly as the chat
job does. Earlier tokens stop working. The limit is the `read` rate bucket.

## `DELETE /feedback/<feedback_id>` (new)

It removes the caller's own feedback entry: `204`. Someone else's: `403`. A missing one: `404`.
