# Implementation Plan: Issue reports from the chat

**Branch**: `021-issue-reports-build` (worktree `~/indico-assistant/plugin-c`) | **Date**: 2026-09-30 |
**Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/021-issue-reports/spec.md`

## Summary

A user sends a report from a form drawn inside the chat panel. It comes from a Report button in the panel's
title bar, or from an offer the chat makes after a thumbs down or under a failed answer. Indico stores the
report in a new table, with a frozen copy of the conversation that Indico builds from its own store. The user
sees their reports, and can delete them, on a new profile page. Indico admins set a status and a note on a new
admin page.

The chat side:

- the form is a Chainlit custom element that calls back with `callAction`;
- the title-bar button reaches the server through `on_window_message`;
- the thumbs-down offer comes from `on_feedback`.

Each answer now records its own evidence and a `problem` flag when it is made. That is the one change to how
answers are produced.

- Research: [research.md](research.md) (R1-R13)
- Data model: [data-model.md](data-model.md)
- Contracts: [contracts/api.md](contracts/api.md), [contracts/panel.md](contracts/panel.md)
- Local walkthrough: [quickstart.md](quickstart.md)

## Technical Context

**Language/Version**: Python 3.12 (the Indico env and the Chainlit env are separate venvs); JavaScript (ES2020,
no build step) for the page script. JSX for the custom element, which Chainlit compiles in the browser.
**Primary Dependencies**: Indico 3.3.13 (plugin, RH, WP, Jinja, menu signals, `make_rate_limiter`); Chainlit
2.12.0 (`CustomElement`, `callAction`, `on_window_message`, `on_feedback`); httpx. Nothing new.
**Storage**: PostgreSQL, schema `plugin_assistant`. Migration 009 adds `issue_reports`. `chat_messages.metadata_json`
gains the `problem` and `evidence` keys, with no migration.
**Testing**:

- pytest with Indico fixtures, run as `python -m pytest` from the worktree (R13). The baseline there is 1207
  passed, 1 skipped;
- the Chainlit app's pytest suite (22 passed), run with the main checkout's Chainlit venv;
- puppeteer, with a new `tests/browser/reports.mjs`, plus the seven existing checks.

**Target Platform**: the Indico web app in desktop and mobile browsers, with the Chainlit panel from spec 020.
**Project Type**: an Indico plugin plus the Chainlit app it embeds.
**Performance Goals**: `POST /reports` answers in under 1 s on the local stack; it reads at most 50 messages
and one plan. The profile and admin menus add one indexed query per page view each.
**Constraints**:

- Admins never read the live conversation (FR-018). The copy is built server-side, from an allowlist (R6).
- A report never creates or names a conversation (FR-001, R2).
- The limit counts only reports that are actually created (R8).
- CSRF applies to session-cookie writes (R10).
- The page never breaks when Chainlit or Indico is down (constitution IV): the button stays disabled, and the
  form keeps the text on an error.

**Scale/Scope**: about 20 files touched, 12 of them new. Four user stories: US1-US3 are the MVP, and US4 (the
offers) comes after.

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | Status |
|---|---|
| I. Official plugin architecture | ✅ New `IndicoPluginBlueprint` routes, with `!` rules for the two pages. Indico `RHUserBase` / `RHAdminBase`, `WPJinjaMixinPlugin`, `signals.menu.items`, `signals.users.merged`. The table is in `plugin_assistant`, with an Alembic migration that has a downgrade |
| II. API-first | ✅ Every action is a JSON endpoint first (contracts/api.md). The pages and the chat call the same `services/reports.py` |
| III. LLM abstraction | ✅ No new LLM calls. The pipeline only returns three more fields it already computes |
| IV. Graceful degradation | ✅ The Report button is disabled until the frame is ready. Report errors show in the form, with the text kept. A report that fails to send changes nothing else |
| V. Configuration hierarchy | ✅ One global setting, `retention_report_days`, next to the other retention settings. No per-event override, as with them |
| VI. Test-first | ✅ Tests come before code in each story in tasks.md. Contract tests cover every endpoint's permissions (SC-003) |
| Security requirements | ✅ Per-user limits (`report`, counted after the idempotency check); ownership on every call, with a 404 that doesn't reveal existence; CSRF on session writes; parameterised ORM queries; nothing from the query log in a copy |
| Code quality gates | ⚠️ As in specs 019 and 020: `ruff` clean on new code; `black` and `mypy --strict` are not run in this repo today. Not a new deviation |

Post-design re-check: no violations.

- **The pages**: server-rendered, with no JavaScript (R9). That is the least new machinery for the plugin's
  first pages.
- **The form**: one custom element, the smallest thing that stays inside the frame (R1).

## Project Structure

### Documentation (this feature)

```text
specs/021-issue-reports/
├── spec.md
├── plan.md              # this file
├── research.md          # R1-R13
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── api.md           # the report endpoints, the two changed ones, the pages
│   └── panel.md         # the title-bar button, the `report` window message, the chat side, the form element
├── checklists/requirements.md
└── tasks.md             # /speckit.tasks
```

### Source Code

```text
indico_assistant/
├── models/report.py                         # NEW IssueReport (data-model.md)
├── models/__init__.py                       # + IssueReport
├── migrations/009_create_issue_reports.py   # NEW
├── services/reports.py                      # NEW create (R8), build_copy (R6), own list/get/delete, admin list/get/update (R11), open_count, has_reports
├── services/chat/rate_limiter.py            # + "report" limits; allowed() (test) and count() (hit)
├── services/chat/service.py                 # problem (R4), evidence (R5)
├── services/nl2sql/models.py                # PipelineResult + intent, intent_confidence, validation_rejection
├── services/nl2sql/pipeline.py              # the trace dict, from process into _process (R5)
├── services/actions/planner.py              # PlanTurn.problem (R4)
├── controllers/reports.py                   # NEW RHReportsAPI (CSRF, R10) + user and admin endpoints
├── controllers/report_pages.py              # NEW the profile and admin pages (R9)
├── controllers/chat.py                      # RESPONSE_METADATA + "problem"
├── controllers/sessions.py                  # detail leaves out "evidence"
├── views.py                                 # NEW WPReports(WPJinjaMixinPlugin, WPUser), WPReportsAdmin(…, WPAdmin)
├── templates/                               # NEW reports.html, report.html, report_delete.html, admin_reports.html, admin_report.html
├── blueprint.py                             # the routes (contracts/api.md)
├── plugin.py                                # the menu items, users.merged
├── default_settings.py, forms.py            # retention_report_days
├── tasks/cleanup.py                         # the RETENTION row
└── static/js/chat_widget.js, static/css/chat_widget.css   # #assistant-panel-report

chainlit_app/
├── app_chnlit.py                            # on_window_message, on_feedback, offers in _show_answer and _after_resume, report_open, report_submit, report_cancel
└── public/elements/IssueReport.jsx          # NEW the form (contracts/panel.md)

tests/
├── unit/test_reports_service.py             # NEW the copy, idempotency, transitions, retention, merge
├── unit/test_answer_evidence.py             # NEW problem and evidence on answers; PlanTurn.problem
├── contract/test_reports_api.py             # NEW every endpoint × owner, other user, admin, missing; CSRF
├── unit/test_report_pages.py                # NEW the pages render; menus; stale save; delete
└── browser/reports.mjs                      # NEW SC-001, SC-002
chainlit_app/tests/test_reports.py           # NEW the window message, the feedback hook, offers, submit
```

**Structure Decision**: the existing single plugin layout. The JSON RHs and the page RHs are separate modules
over one service module, so the page code never duplicates rules.

## Spec corrections made while planning

- **FR-003 and SC-004**: "no email or IP addresses" was too strong, since a user may type their own email into
  the chat. It now says the copy adds nothing about the reporter that the messages don't hold, such as the query
  log's email and IP.

## Complexity Tracking

No violations to justify.
