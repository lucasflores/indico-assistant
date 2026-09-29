# Data model: Persistent assistant with past chats (020)

Everything stays in the existing `plugin_assistant` tables. One migration (008) adds a column. Nothing is
stored on the Chainlit side, and the browser keeps only a pointer.

## ChatSession (`plugin_assistant.chat_sessions`), changed

| Column | Change | Meaning |
|---|---|---|
| `id` | none; may now be chosen by the client | The Chainlit thread id (R5). A v4 UUID. If it exists and is someone else's: 403 |
| `user_id` | none | Owner. Every read and write checks it |
| `event_id` | meaning changes | The page the conversation **started** on, for information only. No longer used to scope answers or to refuse messages (R8) |
| `title` | **new**: `String(200)`, nullable | Set by rename. When null, the listing shows the first user message cut to 60 characters (R12) |
| `created_at` | none | |
| `updated_at` | none | "Last active": what the sidebar sorts and groups by |

**Migration 008** (`indico_assistant/migrations/008_add_chat_session_title.py`): add `title`; the downgrade
drops it. No backfill: a null title falls back to the first message.

**Retention and deletion**: unchanged. `retention_chat_days` deletes old sessions and their messages
(CASCADE). Their `action_plans` keep their audit trail (`session_id` SET NULL, spec 019).

## ChatMessage (`plugin_assistant.chat_messages`), JSONB keys added

No schema change: `metadata_json` gains keys.

| Key | On | Meaning |
|---|---|---|
| `event_id` | user messages | The page the message was sent from (R8). Missing on old rows: fall back to the session's `event_id` |
| `job_id` | user messages | The answer job queued for it (R9). It is used only while the answer is pending |
| `uploads` | user messages | Spec 019, unchanged |
| `plan_id`, sources, … | assistant messages | Unchanged |

`id` is also the Chainlit step id (R11): assistant answers are sent to the UI with their Indico id.

## FeedbackEntry, unchanged

Thumbs from the panel land here (`thumbs_up` / `thumbs_down`, or `comment`), keyed by the message id. The new
`DELETE /feedback/<id>` removes the caller's own entry.

## ActionPlan, unchanged

There are no new columns, and `POST /plans/<id>/token` leaves the row as it is (R10). The confirm token is
derived from the plan id (an HMAC with `SECRET_KEY`), and `confirm` checks it directly. `token_hash` still
matches the random tokens of plans saved before this change, until those expire. (As amended after review,
PR #5.)

## Browser state (not in the database)

`localStorage["indico-assistant:<user id>"]` on the Indico origin, shared by the user's tabs:

```json
{"open": true, "width": 440, "threadId": "3f2c…"}
```

- `open`: whether the panel reopens on the next page (FR-002).
- `width`: the panel width in px, clamped to 320 px…50% of the viewport (FR-006d).
- `threadId`: the last conversation used, which is where a brand-new tab starts.

`sessionStorage["indico-assistant-thread:<user id>"]`, per tab: the conversation this tab resumes (FR-001).
It's an empty string for a new chat. Two tabs keep their own conversation (review, PR #5). A stale id
(deleted, expired, someone else's) resumes nothing, and the panel starts a new chat.

Chainlit's own auth cookie (`access_token`, on the Chainlit origin) holds the session JWT (R3).

## Mapping to Chainlit (R4)

| Chainlit `ThreadDict` | From |
|---|---|
| `id` | `ChatSession.id` |
| `name` | `title`, or the first user message cut to 60 characters |
| `createdAt` | `updated_at` (so the sidebar groups by last activity) |
| `userId`, `userIdentifier` | `str(user_id)` |
| `metadata` | `{"started_on_event_id": event_id}` |
| `tags` | `[]` |
| `steps` | the messages, oldest first (below); only for `get_thread` |
| `elements` | `[]` (uploads are shown as the file names inside the user message) |

| Chainlit `StepDict` | From `ChatMessage` |
|---|---|
| `id` | `id` |
| `threadId` | `session_id` |
| `type` | `user_message` / `assistant_message` from `role` |
| `name` | the user's name / `"Assistant"` |
| `output` | `content`, plus "📎 name" lines for `uploads` |
| `createdAt`, `start`, `end` | `created_at` |
| `feedback` | the caller's entry for this message, if any |
| `metadata` | `{}` |
