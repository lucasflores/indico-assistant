# Implementation Plan: The assistant knows Indico, and knows what it can do

**Branch**: `022-assistant-knowledge` · **Date**: 2026-09-30 · **Spec**: [spec.md](spec.md) · **Research**: [research.md](research.md)

## Summary

Revised 2026-09-30 (Lucas): Jev replaces the classifier's routing instead of sitting in front of it.

- **A plain yes, or one of a waiting plan's own choices,** goes straight to the planner.
- **Anything else gets one Jev decision:** the route (knowledge, change, data, chat, out_of_scope) and, for data, the
  kind of question. The classifier routes only when Jev is unavailable.
- **The knowledge answer** is one model call through ibis, given the rules, excerpts from a pinned local copy of
  Indico's user guide, the pages this user can open (from Indico's menus), and what the assistant can do for them
  (from the actions' own permission rules).
- **The chat answer** (new) is one call over the conversation, informed by general knowledge.
- **Data questions** carry Jev's intent into NL2SQL: no classifier call.
- **"Can you [change]?"** goes to the planner; the plan card is the offer. What the planner cannot plan gets the
  knowledge answer.
- **Code checks every link** before the answer is saved.

## Technical Context

- **Language/runtime:** Python 3.12, inside Indico 3.3.13. The answer runs in the Celery task `answer_chat`, which
  already has a request context, 120 s soft limit.
- **New dependencies:** none.
  - `httpx` (already installed with the openai SDK) calls Jev.
  - `numpy` and `sentence-transformers` (already dependencies) search the guide.
- **Storage:** nothing new in the database. The guide copy and its index are files in the package. The route record
  goes in the answer message's existing metadata.
- **API:** no new endpoint. `POST /chat` and the job poll are unchanged, except that the answer metadata gains
  `route` (below).
- **Testing:** pytest, test-first. The model and Jev are mocked in unit tests. Menus are tested against the dev
  database in the integration suite.

## Constitution Check (1.1.0)

| Principle | How this plan meets it |
|---|---|
| I. Indico plugin architecture | A CLI command on the existing `assistant` group; settings in `default_settings` and the settings form; no new tables. |
| II. API first | Knowledge answers come through the existing chat API; no UI-only behaviour. |
| III. LLM abstraction | The knowledge answer uses `LLMService.generate()` with a Pydantic model. Jev uses the 1.1.0 exception: its key and timeout are settings, it falls back to the classifier (Instructor), its score is validated, and it is mockable. |
| IV. Graceful degradation | No Jev key, or Jev slow or failing: classifier path. No guide index, or a model mismatch: answers from the two lists only, and health says so. The model service down: today's error message. |
| V. Configuration | Three new global settings. Per-event overrides are not needed. |
| VI. Test-first | Every module below lands with its tests first (see tasks). |

## Design

### 1. Routing (`services/chat/service.py`, `services/nl2sql/`, `services/actions/planner.py`)

Each message in `ChatService.answer()`, in order (revised 2026-09-30):

1. **Shortcut.** `planner.exact_reply(waiting_plan, message)`: a plain yes (`AFFIRMATIVE`), or one of the plan's
   own choices or suggestions → the planner, with no decision and no model call.
2. **Jev.** `ChatService._decide()` → `knowledge.gate.decide(messages, settings, plan_waiting=…)` → `Decision(route,
   intent, confidence, skipped, reason, …)`. One call, two `choice` questions (`route`, `intent`); the state is the
   web-gate format plus a note when a plan is waiting.
   - `knowledge` → `_knowledge()`; `chat` → `_chat()`; `out_of_scope` → `OUT_OF_SCOPE_MESSAGE`.
   - `data` → `_process_with_nl2sql(intent=…, intent_confidence=…)` → `NL2SQLPipeline.process(intent=…)` builds the
     `QueryClassification` itself; the classifier is not called; the generator reads dates and names.
   - `change` → `_plan(…, waiting_plan)`.
3. **Without Jev** (`decision.skipped`: no key, a timeout, an error, an invalid answer): the classifier routes,
   as before the router. The last answer's offer (`session_manager.offer_before`) sends the message to the planner
   first. The classifier gains a `chat` category; `_route_of(metadata)` reads its route.
4. **Fall-through.** `PlanTurn.cannot_plan` (no step, `NOTHING_TO_CHANGE`, `NOT_SUPPORTED`, `NOT_AVAILABLE`), or a
   planner that returns nothing: with no plan waiting, the knowledge answer, recorded as `fallback: planner`.

### 2. The knowledge package (`indico_assistant/services/knowledge/`)

| Module | What it does |
|---|---|
| `gate.py` | The router: `decide(messages, settings, plan_waiting=False) -> Decision`. httpx, `POST https://openrouter.ai/api/alpha/decisions`, model pinned `typesafe/jev-1.13`, two `choice` questions (`ROUTES`, `INTENTS`) with the criteria the router probe measured. Answers validated; timeout from settings. |
| `chat.py` | `chat_answer(message, history, llm, base_url)`: one call over the conversation, general knowledge allowed, no lookups or changes; links only to pages already in the conversation (`links.found_in`). |
| `capabilities.py` | `capability_list(user, event=None) -> CapabilityList`, from `ACTIONS`, `enabled_actions()`, and each action's `available()`. Instance-wide lines: the categories where the user may create or propose, and whether they manage any meeting. Event lines, when an event is given. Plus the fixed never-does list (FR-010). `render()` gives the prompt text. |
| `pages.py` | `page_list(user, event=None) -> list[Page(title, section, path)]`, from `build_menu_structure()` for `event-management-sidemenu` (with an event), `user-profile-sidemenu` and `top-menu`, plus a room-booking line from `config.ENABLE_ROOMBOOKING`. Runs inside `acting_as(user)`, which already exists. |
| `guide.py` | Loads the guide copy once per process. Checks the manifest's model and dimensions. `excerpts(question, k=6)` does a numpy cosine search. `page_urls()` gives the real guide pages. If the pinned model matches the `embedding_model` setting, it reuses the plugin's embedding service; otherwise it loads the pinned model itself. |
| `links.py` | `check(answer, pages, guide_urls, base_url) -> str`. Paths in the page list are rebased onto `base_url`, whatever host the model wrote. Other links to this Indico, and guide links that aren't real pages, become plain text. Links to docs.getindico.io are kept. |
| `answer.py` | `answer(user, event, message, history, llm, settings) -> (text, metadata)`. The prompt is in the order rules → guide excerpts → page list → capability list → question, which puts the static text first for provider caching and keeps the card nearest the question. The response model is `KnowledgeAnswer(reply: str, offer: str \| None)`, where `offer` is the change it offered, in the user's words. Then `links.check`, then the route record. |

### 3. Action availability (`services/actions/base.py` + each action module)

- `Action` gains `summary: ClassVar[str]` (one plain sentence) and `available(user, event=None, category=None) -> str | None`
  (the reason it can't, or None).
- Each action implements `available()` with the same helpers its `check()` uses: `refuse_if_locked`,
  `_manage_refusal`, `can_create_events`, `can_manage_attachments`, the Teams plugin check.
- The consistency test builds, for each registered action, the arguments its `check` needs for a fixture user and
  event. It asserts that when `available()` gives a reason, `check()` refuses too.
- Speaker material is covered: a speaker may add material to their own talk (`can_manage_attachments` on the
  contribution).

### 4. The guide copy (`indico_assistant/knowledge_guide/` + `indico assistant guide-build`)

- **Files:**
  - `manifest.json`: `{repo, commit, built_at, model, dims, pages: [url]}`
  - `chunks.json`: `[{url, title, text}]`
  - `vectors.npy`: 163 × 384 float32, about 250 KB
- **Build:** `indico assistant guide-build --commit <sha>` fetches the GitHub tarball of `indico/indico-user-docs` at
  that commit. It splits each page by heading (up to about 350 words, screenshots and HTML stripped), embeds each
  piece with `BAAI/bge-small-en-v1.5` (normalised), and writes the three files. Only a release needs network access;
  answering never does.
- **Packaging:** `pyproject.toml` gains `[tool.setuptools.package-data]` for the guide files and for
  `config_modules/*.yaml`, which today would be missing from a built wheel.
- The first build uses commit `e7e0016` and is committed with this feature.

### 5. Settings (`default_settings.py`, `forms.py`)

| Setting | Default | Form field |
|---|---|---|
| `jev_api_key` | None | PasswordField, never displayed, like `llm_api_key` |
| `jev_timeout_seconds` | 1.5 | number, 0.2–10 |

### 6. Health (`controllers/health.py`, `cli.py health`)

Adds a `knowledge` block: `{guide_commit, pages, model, ok, gate: "jev" | "classifier only"}`. A missing or
mismatched index makes the overall status `degraded`, never `unhealthy`.

### 7. The route record (answer metadata)

```json
"route": {"route": "knowledge", "shortcut": false, "fallback": null,
          "jev": {"route": "knowledge", "intent": "general_info", "confidence": 0.97, "skipped": false,
                  "reason": "score", "ms": 480, "model": "typesafe/jev-1.13"},
          "offer": null, "guide_commit": "e7e0016…", "failed": false}
```

- `route` is one of `knowledge`, `chat`, `data`, `change` or `refusal`.
- `fallback` records another road: `classifier` (Jev skipped), `planner` (it could not plan it), or both.
- Data and change answers get a record too, with their route and the gate fields, so routing can be audited on real
  traffic.

### 8. The eval dimension (`~/indico-assistant/eval`)

- **The four test sets** go in as labelled YAML (spec, Success Criteria): knowledge, routing negatives, follow-ups,
  and the rights subset.
  - Users and pages are named by role ("manager", "viewer who can't create events", "the test meeting").
  - A config maps roles to local ids (default: 1, 6, 657).
- **Runner:**
  - It asks through the live chat API, as the prototype did. The knowledge answer needs Indico's request context,
    which the headless harness lacks.
  - It paces itself under the chat rate limit, and deletes its chats with retries.
- **Scoring:**
  - Code checks links (the same `links.py` rules) and routes (from the route record).
  - An LLM judge grades the knowledge set, given the reference guide pages and the user's truth.
- **Paid runs** (the judge, the answers) start only on Lucas's go. Each run prints its estimated cost first.

## Project Structure

```text
indico_assistant/
├── services/knowledge/          # new: gate, capabilities, pages, guide, links, answer
├── knowledge_guide/             # new: manifest.json, chunks.json, vectors.npy (built)
├── services/actions/base.py     # + summary, available()
├── services/actions/*.py        # + available() per action
├── services/chat/service.py     # routing order (Design 1)
├── services/nl2sql/classifier.py, pipeline.py   # + knowledge intent / result
├── services/actions/planner.py  # + PlanTurn.cannot_plan, exact_reply()
├── default_settings.py, forms.py, cli.py, controllers/health.py
tests/unit/services/knowledge/            # new: one test file per module + the consistency test
tests/integration/knowledge/     # new: page lists and capability lists against the dev DB, as users 1 and 6
```

## Risks

- **Every message now pays for the gate:** about 0.5 s and $0.000015, even data questions. Knowledge questions save
  the classifier call. If the delay shows, the gate can skip messages the planner takes anyway (a plain "yes" to a
  waiting plan).
- **The Balanced dial is unmeasured on this set.** SC-001 and SC-002 are checked there, at the end, on Lucas's go.
- **Menus assume a request context as the user.** `acting_as` gives one in the worker. The page list must never run
  as the wrong user; the integration test checks users 1 and 6 on the same event.
