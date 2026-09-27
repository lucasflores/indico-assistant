# Action catalogue contract (v1)

**Module**: `indico_assistant.services.actions` | See research.md R3–R10 for the operations and checks behind
each row.

Each action is a class with `name`, `Args` (Pydantic, **resolved** values), `writes`, and `check`, `describe`,
`execute`, `revert` (data-model.md). `check` returns a refusal reason, or `None`, and **mirrors the Indico page
named in the Parity column**. It runs at planning time and again in the worker.

Every write action also refuses when `event.is_locked`, as `check_event_locked` does.

## Read actions (run by the planner's resolvers; never shown as steps)

| Action | Input | Output | Rules |
|---|---|---|---|
| `find_person` | `name` or `email`; `event_id?` | ≤ 10 `{user_id, name, email, affiliation, has_teams}` ranked by context | `search_users(..., include_pending=True, external=False)`. The `ALLOW_PUBLIC_USER_SEARCH` / `RHUserSearchToken` rule applies. `has_teams` = `find_tenant_email(user) is not None`. |
| `list_categories` | `query?` (a name), `topic?` | `{create: [...], propose: [...]}`, each `{category_id, path, reason?}`, ranked; `suggested_id` | Candidate query + `can_create_events` / `can_propose_events` (R9). `propose` only when `can_create_unlisted_events(user)` (R4). |
| `suggest_times` | `people: [user_id]`, `duration`, `window` (date range, default the next 5 working days) | ≤ 3 `{start, end}` + `sources` + `unknown: [user_id]` | Indico involvement only (R10); Outlook only with `actions_outlook_freebusy`. Only people found through `find_person`. |
| `find_event` | `text?`, `created_in_session?` | events the user **manages**, ranked | `event.can_manage(user)`. For US6 ("move it to 3pm"). |

## Write actions (plan steps)

| Action | Args (resolved) | Parity (page) | Execute | Revert |
|---|---|---|---|---|
| `create_event` | `category_id`, `title`, `description?`, `start_dt`, `end_dt`, `timezone`, `location?: {venue_name, room_name, address}` | `RHCreateEvent` form: `category.can_create_events(user)` | `create_event(category, EventType.meeting, data)` + `notify_event_creation` → `{event_id}` | `event.delete(reason, user)` |
| `propose_event` | as `create_event` + `comment?` | `can_create_unlisted_events(user)` and `category.can_propose_events(user)` (`RHMoveEvent`) | unlisted `create_event(None, …)`, `create_event_request`, `notify_move_request_creation` → `{event_id, request_id}` | withdraw the request + delete the event |
| `update_event` | `event_id`, any of `title`, `description`, `start_dt`, `end_dt`, `timezone`, `location` | `RHEditEventData` / `RHEditEventDates` / `RHEditEventLocation`: full `can_manage` + the `EventDatesForm` rules | `update_event(event, update_timetable=True, **changes)` inside the executor's time/location tracking → `{before, after}` | `update_event` back to `before` |
| `add_contribution` | `event_id`, `title`, `start_dt`, `duration`, `speakers: [{user_id} \| {first_name, last_name, email}]` | `RHLegacyTimetableAddContribution`: full `event.can_manage(user)` | `create_contribution(event, data, extend_parent=True)` with `ContributionPersonLink(is_speaker=True)` → `{contribution_id}` | `delete_contribution` |
| `update_contribution` | `contribution_id`, any of `title`, `start_dt`, `duration`, `speakers` | `RHLegacyTimetableEditEntry`: full event manage | `update_contribution` → `{before, after}` | `update_contribution` back |
| `add_teams_room` | `event_id`, `name`, `coorganizers: [user_id]` (each `has_teams`), `description?` | `RHVCManageEventCreate`: `event.can_manage(user)` + `plugin.can_manage_vc_rooms(user, event)`. Refused if vc_teams is not installed. | the R5 sequence, **last** in the plan → `{vc_room_id, graph_event_id}` | nothing on its own (deleting the event cancels the meeting); standalone: `vc_room.delete(user)` |
| `add_reminder` | `event_id`, `minutes_before` (default `actions_reminder_minutes`), `recipients: [email]`, `send_to_speakers: true` | `RHAddReminder`: full manage | the R6 inline creation → `{reminder_id}` | delete the reminder if it has not been sent |
| `attach_link` | `target: {event_id} \| {contribution_id}`, `title`, `url` (http/https) | `can_manage_attachments(obj, user)` | R7 link → `{attachment_id}` | `attachment.is_deleted = True` + `attachment_deleted` |
| `attach_file` | `target`, `upload_uuid` | `can_manage_attachments(obj, user)` + the upload is the user's and unclaimed | R7 copy → `{attachment_id}` | as `attach_link` |
| `delete_created` (undo only) | `plan_id` | the plan is the user's, `done`, < 24 h; `can_manage` on each object | `revert` of each step, in reverse order | — |

Rules applied by the validator when a plan is built (FR-005):

- step order: `add_teams_room` is last among write steps; `refs` point backwards only;
- at most 25 steps;
- disabled actions (`actions_allowed`) are never planned;
- no two `add_teams_room` steps for one event.
