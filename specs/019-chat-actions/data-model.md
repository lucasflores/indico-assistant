# Data model: Chat actions (019)

## ActionPlan (table `plugin_assistant.action_plans`, migration `007_create_action_plans`)

A plan the assistant showed to a user. It is one row per version: a revision creates a new row and supersedes
the old one.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `server_default=uuid_generate_v4()` |
| `user_id` | int, not null, indexed | Indico user id. There is no FK, matching the other plugin tables. |
| `session_id` | UUID FK → `chat_sessions.id`, nullable, `ON DELETE SET NULL` | the chat it was made in (the plan stays for audit when the chat is deleted) |
| `message_id` | UUID FK → `chat_messages.id`, `ON DELETE SET NULL` | the assistant message that showed it |
| `supersedes_id` | UUID FK → `action_plans.id`, nullable | the previous version |
| `undoes_id` | UUID FK → `action_plans.id`, nullable | set on undo plans |
| `status` | varchar(16), not null, check in the states below | |
| `steps` | JSONB, not null | list of **PlanStep** |
| `questions` | JSONB, not null, default `[]` | list of **Question**; a plan with open questions cannot be confirmed |
| `suggestions` | JSONB, not null, default `[]` | list of **Suggestion** |
| `summary` | text, not null | the plain-language plan the user saw (FR-006) |
| `token_hash` | varchar(64), not null | sha256 of the confirm token |
| `created_at` | timestamptz, not null | |
| `expires_at` | timestamptz, not null | `created_at + 30 min` (FR-007) |
| `confirmed_at`, `started_at`, `finished_at` | timestamptz, nullable | |
| `result` | JSONB, nullable | list of **StepResult** (for undo, FR-011) |
| `error` | text, nullable | a user-facing reason on `refused` / `failed` |
| `llm_calls` | JSONB, not null, default `[]` | `completion_record` dicts from `collect_calls()` (FR-020) |

Indexes: `(user_id, status, finished_at)` for undo lookups, and `(session_id, created_at)` for "the open plan of
this chat".

### States

```
shown ──confirm──▶ confirmed ──worker──▶ running ──▶ done
  │                    │                     └────▶ failed    (rolled back, nothing left behind)
  │                    └──re-check fails──▶ refused (nothing written)
  ├──cancel──▶ cancelled
  ├──revise──▶ superseded   (a new row with supersedes_id is 'shown')
  └──time──▶  expired       (computed: shown AND expires_at < now; stored lazily on read)
```

- The only way out of `shown` towards execution is the atomic
  `UPDATE … SET status='confirmed', confirmed_at=now() WHERE id=:id AND user_id=:u AND status='shown' AND
  expires_at > now() AND token_hash=:h AND questions = '[]'`. Zero rows means refused (double click, expired,
  revised, wrong token).
- `running` → `done` / `failed` is written by the worker. A failure is written in a fresh transaction after the
  rollback.
- The terminal states are `done`, `failed`, `refused`, `cancelled`, `superseded` and `expired`.
- An undo is only possible for a `done` plan with `finished_at > now - 24 h` whose `user_id` matches.

## PlanStep (element of `steps`)

```json
{
  "n": 1,
  "action": "create_event",
  "args": {"category_id": 12, "title": "Sync with Makoto", "start_dt": "2026-09-28T14:00:00+02:00",
           "end_dt": "2026-09-28T14:40:00+02:00", "timezone": "Europe/Zurich"},
  "refs": {},
  "description": "Create the meeting “Sync with Makoto” in Thoth » Engineering » Meetings, Mon 28 Sep 14:00–14:40 (Europe/Zurich)",
  "side_effects": []
}
```

- `args` are the action's **resolved** argument model, as JSON: ids, not names; aware datetimes. They are
  validated again by the action's Pydantic model at execution.
- `refs` maps an argument name to an earlier step's result, e.g. `{"event_id": "$1"}` for step 1's `event_id`.
  They are resolved at execution, in order. A reference to a later step, or to one that does not exist, is a
  validation error.
- `side_effects` are plain-language strings shown in the plan, e.g. "Teams invitations will be sent to
  makoto@aithoth.com".
- There are at most 25 steps (FR-012).

## Question (element of `questions`)

```json
{"id": "category", "text": "Which category should the meeting go in?",
 "kind": "choice",
 "choices": [{"value": "12", "label": "Thoth » Engineering » Meetings", "note": "suggested: your last 5 team syncs are here"},
             {"value": "7", "label": "Thoth » Management", "note": null}]}
```

- `kind` is one of `choice` (category, person, time slot) or `text` (a missing value).
- The answer arrives as the user's next message, or as a Chainlit choice button. Either way it goes to the
  planner, which produces the revised plan with the question removed.

## Suggestion (element of `suggestions`)

```json
{"id": "s1", "kind": "description", "content": "Review of the Q4 budget draft…",
 "source": {"type": "chat", "label": "this chat"}, "accepted": false,
 "step": {"action": "update_event", "args": {"description": "…"}, "refs": {"event_id": "$1"}}}
```

- `kind` is one of `title`, `description`, `agenda_item`, `person`, `material`, `duration`.
- `source` has a `type` (`chat`, `past_chat`, `event`, `attachment`, `note`) with `label`, plus `event_id` /
  `attachment_id` when it applies. The resolver drops a suggestion whose source the user cannot access
  (FR-016).
- Accepting a suggestion is a revision: the planner turns its `step` into a real step (FR-015: opt-in).

## StepResult (element of `result`)

```json
{"n": 1, "action": "create_event", "created": {"event_id": 431}, "before": null, "after": null}
{"n": 5, "action": "update_event", "created": null,
 "before": {"start_dt": "…T14:00…"}, "after": {"start_dt": "…T15:00…"}}
```

- `created` holds the ids of what was created: `event_id`, `contribution_id`, `vc_room_id` with `graph_event_id`,
  `attachment_id`, `reminder_id`.
- `before` / `after` hold the changed fields of existing objects. Undo compares `after` with the current values
  (US7 AS-2).

## Chat uploads (Indico `indico.files`, no new table)

An unclaimed `File` created by `POST /api/assistant/chat/uploads`:

- `context=('assistant', '<user_id>')`;
- `meta = {"assistant_user_id": <int>, "chat_session_id": "<uuid>"}`.

It is usable only by that user (FR-025). An `attach_file` step references it by `uuid`. Indico's
`delete_unclaimed_files` removes it after a day.

## Chat request / response additions

- `ChatRequest.uploads: list[UUID]` holds up to 5 file uuids sent with the message. They are checked for owner
  and existence.
- `ChatResponse.plan: PlanView | None` is added to the job response when the answer is a plan (contracts/api.md).

## Settings (`default_settings.py`, `forms.py`)

| Key | Type | Default |
|---|---|---|
| `actions_enabled` | bool | `False` |
| `actions_allowed` | list[str] | every action name |
| `actions_reminder_minutes` | int | 15 |
| `actions_outlook_freebusy` | bool | `False` |
| `retention_plan_days` | int | 90 (0 = keep) |

## Action (code, `services/actions/`)

```python
class Action(Protocol):
    name: ClassVar[str]                  # 'create_event', ...
    Args: ClassVar[type[BaseModel]]      # resolved arguments (ids, aware datetimes)
    writes: ClassVar[bool]               # False for find_person / list_categories / suggest_times
    def check(self, user, args) -> str | None: ...        # refusal reason, or None; mirrors the page (R3)
    def describe(self, args) -> tuple[str, list[str]]: ...  # description, side effects
    def execute(self, user, args) -> StepResult: ...       # Indico operations only (FR-002)
    def revert(self, user, result: StepResult) -> None: ... # for undo; write actions only
```

- `check` and `execute` run inside `acting_as(user)` (research R1).
- `execute` never commits; the executor owns the transaction (R2).
