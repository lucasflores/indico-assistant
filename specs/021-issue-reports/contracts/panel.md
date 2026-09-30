# Panel and chat contract: Issue reports from the chat

**Feature**: 021-issue-reports | **Extends**: `specs/020-chat-persistence/contracts/panel.md`

## Page → frame (new row)

| `type` | Fields | When |
|---|---|---|
| `report` | — | The title bar's Report button was clicked. The page posts it to the frame at the Chainlit origin. Chainlit's front end forwards it to the server as `window_message` (R2) |

The frame script (`indico_panel.js`) doesn't handle it: Chainlit's own listener forwards every message. The
server's `@cl.on_window_message` acts only on `{source: "indico-assistant", type: "report"}`, and ignores every
other message.

## Title bar

`#assistant-panel-bar` becomes `[Indico Assistant] … [⚑ Report] [»]`.

- **`#assistant-panel-report`**: a `<button type="button" aria-label="Report a problem" title="Report a
  problem">`. It stays `disabled` until the frame reports `ready`, and is disabled again on `unavailable`.
- **A click** posts `report`. It doesn't move the panel or the page. Focus goes into the frame so the user can
  type, which is allowed: the user pressed a button (spec 020 FR-003 covers only a reopening after navigation).

## Chat side (`chainlit_app/app_chnlit.py`)

| Trigger | The app sends | Answer id |
|---|---|---|
| `on_window_message` `report` | the form, empty, with no category preselected. `can_attach` is `session.has_first_interaction` | none |
| `on_feedback`, thumbs down, once per answer per session | "Sorry that answer missed. Tell the team about it?", with a `report_open` action | `feedback.forId` |
| `_show_answer`, an answer with `metadata.problem` | the answer, with a `report_open` action | the job's `message_id` |
| `_show_answer` / `_after_resume`, no answer (timeout, `>= 500`, unreachable, unanswered) | the error message, with a `report_open` action | none |
| `report_open` action | the form: category `wrong_answer` when there is an answer, text from the payload, `can_attach` true | from the payload |

- **`report_submit`** (from the form) POSTs `/api/assistant/reports` as the user (`X-Assistant-Auth`). It
  returns `{ok, report_id, url}` or `{ok: false, message}` to the card.
- **`report_cancel`** removes the form's message.

None of these runs inside an `on_message` run, except the offer under an answer, which is the answer itself. So
the forms, offers and "Report sent" carry no thumbs (spec FR-007a).

## The form element (`public/elements/IssueReport.jsx`)

**Props**: `form_key`, `answer_id`, `category`, `text`, `can_attach`.

**States**:

- **draft**: Send is disabled until a category is chosen and the text isn't blank;
- **sending**: Send is disabled, so a second click does nothing (and R8 guards the server);
- **sent**: "Report #12 sent. See your reports." The link is absolute to Indico, so `indico_panel.js` opens it
  in the page;
- **error**: the message, with the text kept.

The result line is `aria-live="polite"`.

## Test hooks

| Hook | Meaning |
|---|---|
| `#assistant-panel-report[disabled]` | the title bar's button |
| `#issue-report`, `#issue-kind-<category>[aria-checked]`, `#issue-text`, `#issue-attach`, `#issue-send`, `#issue-cancel` | the form |
| `#issue-report-sent a[href]` | the sent state and its link |
| an action button whose label is "Report a problem" | an offer |
