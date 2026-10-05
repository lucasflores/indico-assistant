# Contract: the agent turn's tools

- **What a tool is:** a plain Python function, `(ctx, **typed args) -> result`. `ctx` carries:
  - the acting user;
  - the chat session;
  - the page event;
  - the conversation memory;
  - the turn's limits.
- **Results** are short text or small JSON, truncated to a fixed size, never a whole document unless that is the
  request.
- **Rules for every tool:**
  - It runs inside `acting_as(user)` and checks access itself (research R6, R7).
  - It records itself as a spec 024 `tool` step.
  - It returns a plain error string instead of raising, except on the worker's time limit.
  - Tools are plain functions so the framework stays replaceable (review caveat).

## Documents (story 2)

| Tool | Arguments | Returns | Access |
|---|---|---|---|
| `list_documents` | `scope`: `page` \| `conversation` \| `event:<id>` | id, filename, status, pages, outline (top level) for each document in scope | only documents whose attachment `can_access(user)` |
| `read_document` | `document`; one of `start: bool`, `pages: [int]` (≤ 5), `section: str` (number or title) | the text of those pages or that section, each page labelled `[p.N]` | same |
| `search_documents` | `query` (the model writes it); `document?` or `event?` | top 8 passages: document, page, section, text | scope filtered by access before ranking |

- **The model writes the search query,** not the user's raw message (study: the misses where naming words dominated).
- **A document that isn't `ready`** returns its status ("still being read", "has no text") instead of text.

## Abilities wrapped from today's pipelines (story 2, reshaped in story 3)

| Tool | Arguments | Wraps | Notes |
|---|---|---|---|
| `query_data` | `question` | the NL2SQL pipeline (`services/nl2sql/`), unchanged | removed in story 4 unless the suite shows it's needed (decision 4) |
| `ask_guide` | `question` | the knowledge answer (`services/knowledge/answer.py`) | returns the guide passages and links |
| `ask_github` | `question` | the connector's whole answer (`services/connectors/loop.py`, `answer()`), unchanged | story 2 only; only when the user has connected GitHub; marks the turn private |
| `github_*` | as today (`services/connectors/github.py`) | the connector's own tools, called by the turn directly | story 3: replaces `ask_github`, and `connectors/loop.py` is deleted |
| `propose_change` | `request` (what to change, with the ids the turn found) | the planner (`services/actions/planner.py`) | creates the plan; the answer shows the plan card. Confirmation stays outside the turn (button or a typed "yes", as in spec 019), so the agent never applies a change. |

## Typed lookups (story 4)

| Tool | Arguments | Returns |
|---|---|---|
| `find_events` | `text?`, `from?`, `to?`, `category?` | up to 20 events the user can open: id, title, dates, place |
| `get_event` | `event` | details, managers' contact only if Indico shows them, link |
| `get_timetable` | `event` | entries via `TimetableSerializer(user=user)`; nothing for unpublished contributions unless Indico shows them to this user |
| `get_registrations` | `event` | the manager view, or the published participant list (clarification 3) |
| `get_notes` | `event` or a contribution | note text for objects the user can open |

## The turn

- **Every message starts with the fast path** (research R2). If it doesn't answer, the agent runs with the tools
  above, the conversation (user and assistant text), the memory list and the page.
- **Limits** come from the turn settings (data-model). On hitting one, the turn answers with what it found and says
  it stopped (FR-025).
- **The final answer** is text with `[p.N]` citations. They're validated into `metadata.citations`; one whose quote
  isn't on its page is dropped and logged.
- **The answer message stores** `touched` (the memory) and `route.tools`.
