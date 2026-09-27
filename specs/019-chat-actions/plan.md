# Implementation Plan: Creating and editing meetings from the chat (chat actions)

**Branch**: `025-chat-actions` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/019-chat-actions/spec.md`

## Summary

The chat gains **actions**: when a user asks for a change ("Create a Teams meeting for today at 2pm with Makoto,
add both of us as contributors with 20 min slots"), the assistant answers with a **plan**. The plan is a
plain-language list of every object it will create or change, with the questions it needs answered and optional
suggestions from context. Nothing is written until the user confirms that exact plan.

A confirmed plan runs in the Celery worker **as the user**:

- It calls Indico's own operation functions (`create_event`, `create_contribution`, `update_event`, the VC-room
  creation sequence, the reminder and attachment steps).
- Each step first passes the permission check of the Indico page that does the same thing by hand.
- The whole plan runs in one transaction, with the Teams meeting created last. Any failure leaves nothing
  behind.

**Technical approach** (research.md):

1. **One LLM call per turn produces an intent draft** (`PlanDraft`): names, wall-clock times, "it".
2. **Deterministic resolvers turn it into a checked plan**: people via `search_users`, categories via
   candidates plus `can_create_events`, times in the user's timezone, availability from Indico involvement,
   and permission pre-checks. Anything ambiguous becomes a question.
3. **Plans are rows** in `plugin_assistant.action_plans`, confirmed by an atomic state transition with a token.
4. **The executor wraps everything in `acting_as(user)`**, which sets `session['_user_id']` inside a Celery
   request context (not `set_session_user`, which is silently broken here), plus `track_time_changes` /
   `track_location_changes`.
5. **Chainlit renders** the plan with `cl.Action` buttons, and forwards chat uploads to a new endpoint that
   stores them as unclaimed Indico `File`s.

## Technical Context

**Language/Version**: Python 3.12 (Indico venv; the constitution's minimum is 3.11)
**Primary Dependencies**:

- Indico 3.3.13 operations: `indico.modules.events.operations`, `.contributions.operations`,
  `.timetable.operations`, `modules.vc`, `modules.attachments`, `modules.files`, `modules.events.reminders`,
  `modules.users.util.search_users`.
- Instructor 1.17 through `LLMService`.
- Chainlit 2.9.5: `cl.Action`, spontaneous file upload.
- The local `indico-plugin-vc-teams`, branch `002-scale`, with three prerequisite fixes (research R5).

**Storage**:

- PostgreSQL. A new table `plugin_assistant.action_plans` (migration `007`).
- Uploads go in Indico's `indico.files` (unclaimed) and are copied to attachment storage on use.

**Testing**:

- pytest with Indico fixtures (`indico.testing.fixtures`) on the throwaway test database.
- FakeGraph from vc_teams for Teams.
- Recorded LLM outputs for planner contract tests.
- A new 50-request eval set in `~/indico-assistant/eval` (SC-004).

**Target Platform**: the Indico web workers (planning endpoints) and Celery workers (queue `assistant`), Linux.
**Project Type**: a single project (Indico plugin), plus a small change in the sibling vc_teams plugin.
**Performance Goals**: plan shown in ≤ 10 s p50 (one LLM call plus SQL and embedding lookups); plan carried out
in ≤ 15 s p50 including Teams (SC-005).
**Constraints**:

- No write without confirmation of the exact plan (SC-002).
- Permission parity with Indico's pages (SC-003).
- One transaction per plan, with no leftover Indico objects, Teams meeting, attachment blob or queued email on
  failure (SC-006).
- Content read from Indico is data, never instructions (FR-017).
- ≤ 25 steps per plan.

**Scale/Scope**:

- 10 write actions and 4 read resolvers;
- 5 new endpoints and 1 changed;
- 1 new table and 5 settings;
- about 9 new modules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design (below).*

| Principle | Status | Notes |
|---|---|---|
| **I. Official Indico plugin architecture** | ✅ PASS | New routes on the existing `IndicoPluginBlueprint`. Signals are used, not bypassed: operations emit them, we emit `attachment_created` and `vc_room_created` as the pages do. Settings live in `SettingsForm` / `default_settings`. The table is in the `plugin_assistant` schema; the model uses Indico's `db`. |
| **II. API-first** | ✅ PASS | Plans, confirm, cancel and uploads are REST endpoints (contracts/api.md). Chainlit only renders them, and typing "yes" goes through the same confirm function. |
| **III. LLM provider abstraction** | ✅ PASS | The planner uses `LLMService.generate` with a Pydantic `response_model`. The optional `messages` parameter is added to that abstraction, not around it. It works on every provider mode, including ibis MD_JSON. |
| **IV. Graceful degradation** | ✅ PASS | The master switch defaults to off. Without vc_teams, meetings are created without Teams, and the plan says so. A Graph failure rolls back the plan and reports it. Planning failures fall back to a question; NL2SQL reads are unaffected. |
| **V. Configuration hierarchy** | ✅ PASS (justified) | The switches are global only. No per-event override: every action is already gated by the event's own permissions, and an event manager has no need to disable the assistant for their event separately. |
| **VI. Test-first** | ✅ PASS | Parity, zero-write, rollback and `acting_as` tests are written before each action (research R19). |
| **Security requirements** | ✅ PASS | No generated SQL writes: actions call operations. Parameterised queries for the candidates and resolvers. Rate limits: planning counts as a chat message; confirm and uploads use `read`. The plan rows are the audit log, with user, steps, outcome and LLM calls. Chat uploads are type- and size-checked on the server. |

**Verdict**: ✅ approved, with no violations. Re-check after design: still ✅. The design adds no new external
service and no per-event settings, and it keeps all writes on Indico's operations.

## Project Structure

### Documentation (this feature)

```text
specs/019-chat-actions/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0: R1–R19
├── data-model.md        # Phase 1: ActionPlan, PlanStep, Question, Suggestion, StepResult, settings
├── quickstart.md        # Phase 1: local walkthrough + tests
├── contracts/
│   ├── api.md           # REST: job response plan, /chat/uploads, /plans/<id>[/confirm|/cancel]
│   ├── actions.md       # the action catalogue: args, parity check, execute, revert
│   └── plan-draft.md    # the LLM response model and prompt inputs
└── tasks.md             # Phase 2 (/speckit.tasks, not created here)
```

### Source Code

```text
indico_assistant/
├── models/
│   └── action_plan.py            # NEW  ActionPlan (plugin_assistant.action_plans)
├── migrations/
│   └── 007_create_action_plans.py  # NEW  down_revision 006_add_partial_sync_status
├── services/
│   ├── actions/                  # NEW
│   │   ├── __init__.py           #      catalogue registry, enabled-actions filter (FR-021)
│   │   ├── base.py               #      Action protocol, StepResult, refusal helpers (locked event, …)
│   │   ├── context.py            #      acting_as(user), user timezone/today, context block for suggestions
│   │   ├── events.py             #      create_event, propose_event, update_event, find_event, delete_created
│   │   ├── contributions.py      #      add_contribution, update_contribution (person links)
│   │   ├── teams.py              #      add_teams_room (the RHVCManageEventCreate sequence)
│   │   ├── materials.py          #      attach_link, attach_file, add_reminder
│   │   ├── resolve.py            #      find_person, list_categories, suggest_times, draft → plan
│   │   ├── planner.py            #      prompt, LLM call, validation + one regeneration, suggestions
│   │   └── executor.py           #      confirm transition, run steps in one transaction, rollback/cancel, undo
│   ├── llm/
│   │   ├── service.py            # MOD  generate(..., messages=None)
│   │   └── models/plan.py        # NEW  PlanDraft (contracts/plan-draft.md)
│   ├── nl2sql/classifier.py      # MOD  + write_request intent
│   └── chat/service.py           # MOD  route: open plan → planner; write_request → planner; else NL2SQL
├── tasks/
│   ├── actions.py                # NEW  execute_plan (request_context=True, plugin='assistant', queue assistant)
│   ├── chat.py                   # MOD  request_context=True (planning pre-checks need session.user)
│   └── cleanup.py                # MOD  RETENTION + action_plans
├── controllers/
│   ├── actions.py                # NEW  RHPlan, RHPlanConfirm, RHPlanCancel, RHChatUpload
│   └── chat.py                   # MOD  uploads in POST /chat; plan in the job response
├── schemas/
│   ├── actions.py                # NEW  PlanView, ConfirmRequest, UploadResponse
│   └── chat.py                   # MOD  ChatRequest.uploads, ChatResponse.plan
├── blueprint.py                  # MOD  5 routes
├── default_settings.py, forms.py # MOD  actions_* settings, retention_plan_days
└── __init__.py                   # MOD  import tasks.actions

chainlit_app/
├── app_chnlit.py                 # MOD  plan card, confirm/cancel/choice actions, upload forwarding
└── .chainlit/config.toml         # MOD  spontaneous_file_upload enabled, accept/5 files/25 MB

tests/
├── unit/services/actions/        # NEW  resolvers, validator, planner contract, acting_as, token/state machine
└── integration/actions/          # NEW  parity per action, zero-write, rollback/fault injection, uploads, undo

~/indico-assistant/indico-plugin-vc-teams (branch 002-scale)   # MOD  research R5 prerequisites (3 fixes + tests)
~/indico-assistant/eval                                        # NEW  meeting-request eval set (SC-004)
```

**Structure Decision**: this is a single Indico plugin. The actions live in one package,
`services/actions/`, split by Indico module (events, contributions, teams, materials), so each file mirrors the
Indico pages it reproduces. Planning and execution are separate modules, because they run in different tasks
and have different failure rules.

## Delivery order (input for /speckit.tasks)

Each slice ends with something runnable and its tests.

1. **Foundations**:
   - vc_teams prerequisites (R5);
   - `acting_as`, with its memoization regression test;
   - the `action_plans` model and migration;
   - the settings;
   - the confirm state machine and endpoints, with a no-op test action.
   - SC-002 tests start here.
2. **US1 + US2 core**:
   - `create_event`, `add_contribution`, `add_reminder`, `add_teams_room`;
   - `find_person`, `list_categories`;
   - the planner, with `PlanDraft` and `CreateMeeting`;
   - the executor with rollback;
   - Chainlit plan card and buttons.
   - Parity and fault-injection tests.
   - **MVP**: the example sentence works end to end.
3. **US3/US4 polish**: category ranking and reasons, the propose path, guest speakers, the no-Teams-account
   warning, past-time and clash flags.
4. **US6**: `find_event`, `update_event`, `update_contribution`, "it" resolution.
5. **US9**: the uploads endpoint, Chainlit forwarding, `attach_file`, `attach_link`.
6. **US5**: the context block and suggestions, with the source-access filter.
7. **US8**: `suggest_times` (Indico-only). Outlook free/busy waits for the tenant probe.
8. **US7**: undo.
9. **Eval**: 50 meeting requests (SC-004), and a latency check (SC-005).

## Spec amendments made during planning

Applied to spec.md in the same change:

- **`propose_event`**: Indico 3.3.13 has no "propose" path in event creation. Proposing is creating an
  **unlisted** event and requesting its publication in the category. So it needs unlisted events enabled
  (`can_create_unlisted_events`). Propose-only categories are otherwise not offered, and the assistant explains
  why (research R4).
- **Category paths** use Indico's separator "»".
- **Uploads**: Indico has no attachment file-type allowlist or default size limit. The spec's limits are
  enforced by the plugin (R7).
- **Teams invitees** are the room's co-organizers. People without a tenant account get the reminder but no
  Teams invite (already the spec's US4 AS-3; now tied to `find_tenant_email`).

## Complexity Tracking

No constitution violations to justify.

One cross-repo dependency: three small fixes in vc_teams (research R5), made on its local `002-scale` branch
before slice 2. Without them, a Graph network error during execution could leave an orphan Teams meeting.
