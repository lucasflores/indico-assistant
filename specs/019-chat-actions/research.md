# Research: Chat actions (019)

**Date**: 2026-09-27 | **Indico**: 3.3.13 | **vc_teams**: branch `002-scale` | **Chainlit**: 2.9.5

All findings were read from the installed sources (paths relative to `site-packages/indico/` unless stated).
Each section gives the decision, the rationale and the alternatives considered.

---

## R1. Running Indico operations as the user, outside a web request

**Decision**: Every piece of code that checks permissions or calls an Indico operation runs inside
`acting_as(user)`, a context manager (in `services/actions/context.py`). It:

- needs a request context. Celery tasks get one with `@celery.task(request_context=True, plugin='assistant')`,
  which pushes `test_request_context(base_url=BASE_URL)` (`core/celery/core.py:120-140`);
- sets `session['_user_id'] = user.id`;
- clears `g.memoize_cache`;
- asserts `session.user == user`;
- sets `session.lang` and `session.timezone` from the user's settings.

**Rationale**:

- **Operations read `session.user`.** `create_event`, `update_event`, `create_event_request`,
  `update_contribution`, `delete_contribution` and `update_timetable_entry` read `session.user` without a
  guard. They use it for the creator and for every event-log entry.
- **Permission checks read it too.** `Contribution.can_manage(user)` checks
  `self.event.can_manage(session.user, 'contributions')` and ignores its argument
  (`modules/events/contributions/models/contributions.py:558-569`). So the checks are only right if
  `session.user` is the acting user. That applies at planning time as well, not only at execution.
- **`session.set_session_user(user)` does not work here.** It first calls `get_request_user()`, which is
  `@memoize_request`, so `(None, None)` is cached in `g`. The next `session.user` is then `None`.
  - This was confirmed empirically in an app context.
  - Tests do not show it, because `memoize_request` is off under `TESTING`
    (`util/caching.py:41-58`, `web/flask/session.py:65-80`).
  - The regression test for `acting_as` must therefore turn memoization back on.
- **Commits clear the cache.** `db.session.commit()` clears `g.memoize_cache` (`core/db/sqlalchemy/core.py:63-66`).
- **Push a fresh context per unit of work.** `g` belongs to the app context, and the Celery wrapper
  pushes a fresh one per task.

**Side effects of the test request context** (all harmless, and stricter rather than looser):

- `request.remote_addr` is `None`, so IP-network grants do not apply.
- `session['access_keys']` is empty.
- `g.rh` is unset.
- `url_for(_external=True)` uses `BASE_URL`.

**Alternatives considered**:

- `login_user()`: it fires `users.logged_in` and syncs identity data, and it hits the same memoize trap.
- Passing the user explicitly: most operations do not accept a user.
- Calling Indico's HTTP endpoints with a token: rejected in the spec (they are form-coupled and need
  `full:everything`).

## R2. Transaction, ordering and rollback

**Decision**: One Celery task per confirmed plan (`tasks/actions.py: execute_plan`, queue `assistant`). Inside
`acting_as(user)`, the task runs these steps:

1. Re-run every permission check against the current data (FR-008).
2. Run all Indico steps inside **one** `with track_time_changes(auto_extend=True, user=user),
   track_location_changes():` block, then `db.session.flush()`.
3. Run the external step last: `create_room` for Teams. Remember the Graph `event_id` it returns.
4. `db.session.commit()`.

If any step fails:

- `db.session.rollback()`;
- cancel the Teams meeting if one was created (`graph.get_client().cancel_event(event_id)`, which treats 404 as
  success);
- delete attachment blobs copied during the run;
- discard the queued emails (`init_email_queue()` resets `g.email_queue`);
- pop vc_teams' `g` keys (`vc_teams_pending_cancel`, `vc_teams_pending_move`, `vc_teams_dirty`);
- then record the failure on the plan in a new transaction.

**Rationale**:

- No Indico operation commits; they only flush. The RH normally commits (`web/rh.py:315`).
- Changes to start/end/duration and location on persistent objects **raise** outside
  `track_time_changes` / `track_location_changes` (`modules/events/util.py:445-557`). Those two are also the
  only way `event.times_changed` and `event.location_changed` fire, which vc_teams and reminders rely on.
  They cannot be nested, so the executor opens them once, around all steps.
- **Emails wait for the commit.** The Celery wrapper calls `init_email_queue()` before the task and
  `flush_email_queue()` after it. The flush commits, and it is skipped if the task raises
  (`core/celery/core.py:137-141`, `core/notifications.py:154-185`). So emails leave only after the commit,
  and a failed plan must not leave queued mail behind.
- **Some effects survive a rollback, so they are undone by hand:**
  - a Teams meeting that was already created;
  - `AttachmentFile.save()` bytes, which are written immediately;
  - vc_teams' request-scoped `g` state.

**Alternatives considered**:

- One commit per step: this leaves half-built meetings (FR-010).
- Teams first: its failure would then need Indico rollback plus a cancel anyway, and Teams is the slowest
  and least reliable step.

## R3. The operation behind each action, and the page check it mirrors

All pages below also run `check_event_locked`, which refuses non-GET requests when `event.is_locked`. The
actions mirror this as a plain "refuse if locked".

| Action | Operation (in-process) | Permission check mirrored (page) |
|---|---|---|
| `create_event` | `create_event(category, EventType.meeting, data)`, then `notify_event_creation(event)` (the RH calls it; the op does not). `modules/events/operations.py:81-139` | `category.can_create_events(user)` (`EventCreationFormBase.validate_category`, `modules/events/forms.py:110-113`) |
| `propose_event` | unlisted `create_event(None, …)`, then `create_event_request(event, category)` and `notify_move_request_creation` (`operations.py:365-383`) | `can_create_unlisted_events(user)` (`modules/categories/util.py:238-244`) **and** `category.can_propose_events(user)` (`RHMoveEvent`, `modules/events/management/controllers/actions.py:95-99`) |
| `update_event` | `update_event(event, **data)` (`operations.py:142-166`). Times use `update_timetable=True`, which shifts entries through `move_start_dt`. | `RHManageEventBase`: `event.can_manage(user)` (full) + not locked, plus the `EventDatesForm` boundary rules (`management/forms.py:139-167`) |
| `add_contribution` | `create_contribution(event, {title, duration, start_dt, person_link_data, location_data: {'inheriting': True}}, extend_parent=True)` (`contributions/operations.py:56-73`), which schedules it through `create_timetable_entry` | meeting timetable page (`RHLegacyTimetableAddContribution`, `timetable/controllers/legacy.py:97-120`): full `event.can_manage(user)` + not locked |
| `update_contribution` | `update_contribution(contrib, data)` / `update_timetable_entry(contrib.timetable_entry, {'start_dt'})` | `RHLegacyTimetableEditEntry`: full event manage + not locked |
| `add_teams_room` | the `RHVCManageEventCreate` sequence (R5) | `event.can_manage(user)` + not locked + `plugin.can_manage_vc_rooms(user, event)` (`modules/vc/controllers.py:139-142`, `modules/vc/plugins.py:233-252`) |
| `attach_link` | the body of `add_attachment_link` with an explicit user (R7) | `can_manage_attachments(obj, user)` (`modules/attachments/util.py:64-83`) + not locked |
| `attach_file` | the steps of `AddAttachmentFilesMixin` from an unclaimed `File` (R7) | same as `attach_link` |
| `add_reminder` | inline, as `RHAddReminder` does: `EventReminder(creator=user, event=event, …)`, add, flush, `reminder.log(...)` (`reminders/controllers.py:131-164`) | `RHManageEventBase` (full manage) + not locked |
| `delete_created` (undo) | `event.delete(reason, user)` (`models/events.py:1036-1048`); `delete_contribution(contrib)`; the VC room goes with the event (its `event.deleted` handler) | `RHDeleteEvent` / timetable delete: full manage + not locked |

**Event log**: every operation above writes its own log entry except reminders, which the executor writes the
way the RH does. VC creation writes no log entry of its own; only its notification email is logged.

**Meeting speakers**:

- `ContributionPersonLink(person=…, is_speaker=True)`.
  - The person comes from `EventPerson.for_user(user, event)` for Indico users, or from
    `persons.util.get_event_person(event, {first_name, last_name, email})` for guests.
  - Emails must be lowercased (a DB check requires it).
- For meetings every person link must have a role, so every one is a speaker.
- `person_link_data = {link: is_submitter}`. Speakers are submitters (`True`), as the form does by default
  for meetings.

## R4. Proposing an event

**Decision**:

- `propose_event` is available only when `can_create_unlisted_events(user)` holds (unlisted events are
  enabled on the instance). The category must satisfy `can_propose_events(user)` without
  `can_create_events(user)`.
- When a category is propose-only and unlisted events are off, it is **not** listed as a choice. The plan says
  "you can only propose events in *X*, which needs unlisted events to be enabled; ask an admin".

**Rationale**: in 3.3.13 the creation form has no "propose" path. Proposing is a publish/move request for an
existing event (`create_event_request`). The only native way to propose a new meeting is to create it unlisted
and request publication. The local testbed has unlisted events off and all three categories restricted, so
integration tests enable both through fixtures.

**Alternative considered**: calling `create_event_request` on a listed event created elsewhere. That needs create
rights somewhere, and it is not what "propose" means to the user.

## R5. Adding a Teams room

**Decision**: `add_teams_room` replays the `RHVCManageEventCreate` sequence without a WTForm.

1. `VCRoom(created_by_user=user, type='teams', status=created)`.
2. Under `no_autoflush`:
   - `VCRoomEventAssociation()`;
   - `plugin.update_data_association(event, vc_room, assoc, dict(data))`;
   - `plugin.update_data_vc_room(vc_room, dict(data), is_new=True)`.

   These take **two separate dict copies**, because both pop keys. `data` must contain every key:
   `name`, `description`, `coorganizers` (a set of `User`), `recording`, `lobby_bypass`, `presenters`,
   `link_visibility`, `linking='event'`, `contribution=None`, `block=None`, `show=True`.
   `link_visibility` in particular raises `KeyError` if missing.
3. `with plugin.plugin_context(): plugin.create_room(vc_room, event)`.
4. `signals.vc.vc_room_created.send(...)`.
5. `notify_created(plugin, vc_room, assoc, event, user)`, queued until commit (R2).
6. `db.session.add(vc_room)`.

Defaults for `recording`, `lobby_bypass`, `presenters` and `link_visibility` come from the vc_teams settings,
the same ones its form uses.

**Invitees**:

- Teams attendees are the room's **co-organizers**: the requesting user and the named Indico users who have a
  tenant account (`find_tenant_email`).
- A person without a tenant account is **not** a co-organizer. The plan says so (US4 AS-3), and they get the
  event reminder, whose event link shows the join button.

**Prerequisite fixes in vc_teams** (branch `002-scale`), done first:

1. `create_room` must also catch `requests` exceptions (connection error, timeout) raised after the Graph
   event was created. It should cancel the meeting and raise `VCRoomError`. Today the meeting is orphaned.
2. vc_teams must expose `discard_pending()`, which pops its `g` keys (pending cancels, moves, dirty fields),
   and the executor calls it after a rollback. Indico has an `after_commit` signal but no rollback signal
   (`core/signals/core.py`).
3. `create_room` must reject co-organizers without a tenant email instead of silently dropping them. The
   form validates this, but in-process callers get no check.

**Rationale**:

- The sequence and its checks come from `modules/vc/controllers.py:135-180`.
- `create_room` needs the association first, because it reads `vc_room.events[0].link_object` for the times.
- Nothing listens to `vc_room_created`; it is sent for parity only.
- Time changes are already handled: `track_time_changes` → `event.times_changed` → vc_teams moves the
  meeting after commit, through a Celery job (US6).

**Alternative considered**: calling `RHVCManageEventCreate` with a faked form. It is coupled to request and
form state (`flash`, CSRF, `validate_on_submit`), so it was rejected.

## R6. Reminders

**Decision**: `add_reminder` builds the `EventReminder` directly.

- `reminder_type=standard` and `event_start_delta` set, with `scheduled_dt = event.start_dt - delta`. The delta
  comes from the admin setting `actions_reminder_minutes` (default 15) and can be edited in the plan.
- `send_to_speakers=True`.
- `recipients` = the emails of invitees who are not speakers.
- `include_summary=False`, `include_description=True`, `attach_ical=True`.
- `reply_to_address` = the user's email if it is in `event.get_allowed_sender_emails(include_noreply=True)`,
  otherwise the no-reply address.
- The executor then writes `reminder.log(EventLogRealm.management, LogKind.positive, 'Reminder', 'Event
  reminder added', user, data={'Time': …})`.

**Rationale**:

- There is no reminder operation; the RH builds it inline (`reminders/controllers.py:143-155`).
- The reminder form refuses a `scheduled_dt` before today. A reminder whose time has already passed (a meeting
  in 10 minutes) is left out, and the plan says so.
- Reminders move with the event through the `times_changed` handler (`reminders/__init__.py:36-47`).
- They are sent by Indico's periodic `send_event_reminders` task (every 5 minutes).

## R7. Links, files and chat uploads

**Decision**:

- **Links**: the 8 lines of `add_attachment_link`, with the user passed explicitly:
  - `AttachmentFolder.get_or_create_default(obj)`;
  - `Attachment(user=…, type=link, title, link_url, protection_mode=inheriting)`;
  - flush;
  - `signals.attachments.attachment_created.send(link, user=user)`, which writes the event log entry and makes
    our indexer pick it up.
- **Uploads**: a new endpoint `POST /api/assistant/chat/uploads` stores each file with
  `File.create_from_stream(stream, filename, content_type, context=('assistant', str(user.id)))` and sets
  `meta = {'assistant_user_id', 'chat_session_id'}`. The owner is kept in `meta` because `File` has no owner
  column.
  - Allowlist: pdf, docx, pptx, xlsx, txt, md, png, jpg. The plugin enforces this, by extension and by sniffed
    MIME type.
  - Limits: 25 MB per file, 5 files per message.
  - The endpoint returns the file `uuid`.
- **Attaching a file**: the steps of `AddAttachmentFilesMixin`:
  - `Attachment(folder, user, title=filename, type=file, protection_mode=inheriting)`;
  - `att.file = AttachmentFile(user, filename=secure_client_filename(...), content_type=...)`;
  - `with f.open() as fd: att.file.save(fd)`;
  - add, flush, `attachment_created`.

  The chat `File` stays unclaimed, and Indico's daily `delete_unclaimed_files` (06:00, older than 1 day) removes
  it. The papers module does the same (`modules/events/papers/operations.py:150-163`).
- **Chainlit** (`config.toml`): `[features.spontaneous_file_upload] enabled = true`, with `accept` in dict form
  (MIME → extensions), `max_files = 5` and `max_size_mb = 25`.
  - In `on_message`, every `message.elements[i].path` is forwarded to the upload endpoint **immediately**,
    because Chainlit deletes its copies when the session ends.
  - The resulting uuids go into `ChatRequest.uploads`.

**Rationale**:

- `add_attachment_link` needs a WTForm and reads `session.user`.
- Indico always copies bytes when it claims a `File`. Sharing a storage blob would let the deletion of either
  row remove the file.
- Indico has **no** attachment file-type allowlist and no size limit by default. `MAX_UPLOAD_FILE_SIZE = 0` means
  unlimited, and the attachment upload page does not call `validate_upload_file_size`. So the spec's limits are
  the plugin's own. The endpoint also applies `MAX_UPLOAD_FILE_SIZE` when it is set.
- Chainlit checks MIME types against what the browser reports, and only the frontend enforces `max_files`. The
  Indico endpoint therefore re-checks everything.

**Security notes**:

- An uploaded file can only be used by the user in its `meta` (FR-025).
- `RHDeleteFile` lets any logged-in user delete an unclaimed file by uuid. Uuids are unguessable (v4), so this
  is acceptable.
- The DEBUG instance only logs the cleanup ("Would have removed").

## R8. People

**Decision**: `find_person` calls `search_users(first_name=…, last_name=…, email=…, include_pending=True,
external=False)`, as `RHUserSearch` does (`modules/users/util.py:281`, `controllers.py:1033-1117`).

- Results are capped at 10, with exact matches first.
- When `ALLOW_PUBLIC_USER_SEARCH` is off, searching is allowed only if the user may create events somewhere or
  manages the target event, which is `RHUserSearchToken`'s rule.
- Ranking inside the result: people who share the user's linked events (last 12 months), then people named in
  the user's own chats, then Indico's order.
- One match: it is shown with name and email. Several: the plan asks. None: the plan offers a guest speaker
  (name and email) through `get_event_person`.

**Rationale**:

- `search_users` itself has no permission checks. The web rules live in the search token.
- `name=` matching cannot be combined with `exact=True`.
- The instance has no external search providers.

## R9. Categories

**Decision**: `list_categories` builds its candidates in one query:

- categories where the user, their local groups or their roles have a `create`, `event_move_request` or
  full-access entry;
- the subtrees of the full-access ones (`Category.get_subtree_ids_cte`);
- every category whose mode is `open` or `moderated`;
- for admins, every category.

It then filters the candidates with `can_create_events(user)` / `can_propose_events(user)`, which also covers
multipass groups and plugin signals.

- Labels are `' » '.join(chain_titles)` (`undefer('chain_titles')`). Indico uses "»", not "›".
- Ranking combines:
  - the user's recent activity: the number of the user's linked events in the category over the last 12
    months;
  - the chat's topic: cosine similarity between the request or chat summary and the titles of recent events in
    the category, using the existing local `EmbeddingService`.
- The top category is the suggestion. Its reason names the evidence ("your last 5 team syncs are in …").

**Rationale**:

- Indico has no helper that lists the categories a user can create events in (the picker browses one node at a
  time).
- `create` permission applies to that category only; full management is inherited by subcategories.

## R10. Availability (US8)

**Decision**: availability comes from Indico only in v1.

- It uses `get_linked_events(user, dt=window_start)` (`modules/users/util.py:121-185`) for the user and each
  resolved person, filtered with `Event.happens_between(window_start, window_end)`.
- For speaker slots it uses contribution times (`get_contributions_for_user`).
- Free slots are those inside working hours (09:00–18:00 in the user's timezone, Monday to Friday) that clash
  with no one's busy intervals. Up to three are offered, earliest first.
- The plan names its sources ("Indico: events you and Makoto manage, chair, speak in or are registered for").
- Outlook free/busy (Graph `getSchedule`) is behind the setting `actions_outlook_freebusy`, off by default.
  It is only enabled after the tenant probe confirms `Calendars.ReadBasic` works with the scoped setup
  (FR-023). It is a later task.
- People whose availability cannot be read are named as such.

**Rationale**: Indico has no free/busy function. `get_linked_events` has only a lower time bound, so the
upper bound is applied as a filter.

## R11. Times and timezones

**Decision**:

- Requests are read in the user's timezone: `user.settings.get('timezone') or config.DEFAULT_TIMEZONE`.
  "Today" is `now_utc().astimezone(tz).date()`.
- The meeting's `timezone` is the user's timezone, shown in the plan and editable ("in Zurich time").
- Past times are flagged.
- Defaults the plan shows explicitly:
  - duration: 30 minutes when nothing is given;
  - slot length: 20 minutes, Indico's contribution default;
  - a meeting that is too short for its slots is extended to fit (US1 AS-3).

**Alternative considered**: the category's timezone, which is what Indico's creation dialog pre-selects. It was
rejected because the user stated the time in their own zone. The plan shows the zone either way.

## R12. Producing the plan (LLM)

**Decision**: one structured-output call per turn, through `LLMService.generate`.

- `response_model=PlanDraft`, whose `steps` is a list discriminated on `action` (a `Literal`).
- It becomes a JSON schema (`$defs` + `oneOf`), which MD_JSON (ibis), JSON (Ollama, HF) and TOOLS (OpenAI) all
  accept.

**The LLM outputs intent, not ids**:

- people as names;
- the category as a name or "unspecified";
- times as local wall-clock strings;
- references between steps as `"$step1"`.

**Code then resolves everything deterministically**: people (R8), categories (R9), times (R11), availability
(R10), existing events for US6, and the permission pre-checks. Anything ambiguous becomes a question in the
plan.

- An invalid draft is regenerated once, with the validation errors, then turned into a question (FR-005).
- `generate` gains an optional `messages` parameter, so the planner can pass chat history as proper turns. The
  classifier and NL2SQL are unchanged.
- Planner calls run inside `collect_calls()`. The records are stored on the plan and in the message metadata
  (FR-020).

**Rationale**:

- Keeping ids and permissions out of the LLM's hands makes the plan checkable, and gives prompt injection
  (FR-017) nothing to act on. It can at most change a draft the user still sees.
- One call keeps planning within 10 s (SC-005). The resolvers are SQL and embedding lookups.

**Alternatives considered**:

- Native tool calling with an LLM loop over `find_person` / `list_categories`: slower, not supported by the
  ibis MD_JSON mode, and FR-004 allows it later.
- One call per step: too slow.

## R13. Routing write requests (FR-018)

**Decision**: in `ChatService.answer`, **before** NL2SQL:

1. If the session has an open plan (shown and not expired), the message goes to the planner as a follow-up on
   that plan. The planner returns `decision: confirm | cancel | revise | new_request | unrelated`.
   - `confirm` confirms that exact plan, through the same path as the button.
   - `unrelated` falls through to NL2SQL.
2. Otherwise, the classifier gets one more intent, `write_request` ("create, change, move, add, attach, undo
   something in Indico"). That intent goes to the planner; everything else goes to NL2SQL as today.
3. If actions are disabled, or the requested action is switched off, the reply says the feature is not
   available (FR-021).

**Rationale**: the classifier sees only the latest message, with no history. Without the open-plan check,
"make it 30 minutes" or "yes" cannot be routed. One more label keeps a single classification call.

## R14. Confirming a plan

**Decision**:

- **Endpoints**:
  - `POST /api/assistant/plans/<plan_id>/confirm` with `{"token": …}`;
  - `POST /api/assistant/plans/<plan_id>/cancel`;
  - `GET /api/assistant/plans/<plan_id>`.
- **Confirm does**:
  - checks that the user owns the plan;
  - compares the token in constant time. The token is a random `secrets.token_urlsafe(24)` stored hashed on the
    plan row and rotated with every revision;
  - one atomic `UPDATE … SET status='confirmed' WHERE id=… AND status='shown' AND expires_at > now()`, so a
    double confirmation finds no row (FR-008, US2 AS-3);
  - queues `execute_plan` and returns a job id. The client polls it like a chat job.
- **Chainlit**: `cl.Action(name='confirm_plan'|'cancel_plan', payload={plan_id, token})`, and
  `@cl.action_callback` calls the endpoint and then `message.remove_actions()`.
- **Revisions**: a revision is a new plan row; the previous one becomes `superseded`.

**Rationale**:

- Chainlit rebuilds `Action` from the client-supplied dict (`server.py:1238-1275`), so the payload is untrusted,
  and Indico checks owner, token and state.
- The atomic transition follows the claim pattern already used in teams_notes.

## R15. Storage and retention

**Decision**:

- New table `plugin_assistant.action_plans`, added by migration `007_create_action_plans`
  (down_revision `006_add_partial_sync_status`); see data-model.md.
- Expiry is computed (`status == shown and expires_at < now` reads as `expired`), so no sweeper task is needed.
- Retention: a new `RETENTION` entry `('plugin_assistant.action_plans', 'created_at', 'retention_plan_days')`,
  default 90. Undo only needs 24 hours, but the rows are also the audit trail (FR-011).

## R16. Undo (US7)

**Decision**:

- The executor records, for each step:
  - the created object ids (event, contributions, VC room, attachments, reminder);
  - for updates, the previous and new values of the fields it changed.
- "Undo" builds a new plan of `delete_created` / restore steps for a done plan the user confirmed in the last
  24 hours. If there are several, the assistant lists them.
- Before showing the plan, it compares the objects' current values with the recorded new values. Differences
  are listed and must be confirmed (US7 AS-2).
- The undo runs through the same confirm and execute path.

**Rationale**:

- Deleting the event through `event.delete(reason, user)` runs Indico's own handlers: the VC room is deleted and
  the Teams meeting cancelled, room bookings are cancelled, and requests are withdrawn.

## R17. Settings (FR-021, FR-022)

**Decision** (global plugin settings; there is no per-event override, because permission checks are already
per event):

- `actions_enabled` (bool): the master switch for writes. **Default `False`** on new installs, so that write
  access to shared data is opt-in; it is turned on locally for development.
- `actions_allowed` (`IndicoSelectMultipleCheckboxField`): the enabled actions. Default: all of them.
- `actions_reminder_minutes` (int, default 15).
- `actions_outlook_freebusy` (bool, default `False`).
- `retention_plan_days` (int, default 90; 0 keeps plans forever).

## R18. Rate limits

**Decision**:

- The planning turn is a normal chat message and counts against the `chat` limit.
- Confirm, cancel and plan reads count against `read`, so carrying out a plan does not count twice (edge case
  "Rate limits").
- Uploads count against `read`, and each upload carries the per-message cap of 5 files.

## R19. Testing strategy

- **Permission parity (FR-003, SC-003)**:
  - for each action, a parametrised test with admin, event manager, contribution submitter/speaker and
    unrelated users, built with Indico fixtures;
  - it asserts that our `check()` refuses exactly when the corresponding RH's `_check_access` does, calling the
    RH with `session.user` set;
  - locked events are included.
- **Zero writes without confirmation (SC-002)**: each action path is driven with unconfirmed, expired, revised and
  double-confirmed plans. Tests assert no new rows and no Graph calls (fake Graph records calls).
- **Rollback (SC-006)**: fault injection with vc_teams `FakeGraph.fail_next` and exceptions in later steps.
  Tests assert that no Indico rows remain, the fake Graph has no meeting, no blob is left and no email was
  queued.
- **`acting_as`**: a regression test with `memoize_request` on (R1).
- **Planner**: contract tests of `PlanDraft` against recorded LLM outputs. An eval set of 50 meeting requests
  goes in the eval repo (SC-004), as a later task.
