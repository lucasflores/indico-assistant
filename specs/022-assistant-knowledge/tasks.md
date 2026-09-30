# Tasks: The assistant knows Indico, and knows what it can do

**Input**: [spec.md](spec.md), [plan.md](plan.md) · **Branch**: `022-assistant-knowledge`

**Tests**: test-first (constitution VI). In each phase the tests come before the code they cover, and must fail
before it is written. Run `pytest tests/unit tests/contract` after each phase (1207 pass on main at 2e52051; there is
no CI).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an open task)
- **[Story]**: US1–US4 from the spec; no label = shared

---

## Phase 1: Setup — the guide copy

- [ ] T001 `indico assistant guide-build --commit <sha>` in `indico_assistant/cli.py`, with its logic in
  `indico_assistant/services/knowledge/guide_build.py`:
  - fetch the GitHub tarball of `indico/indico-user-docs` at the commit;
  - split each page by heading (up to about 350 words; strip screenshots and HTML);
  - embed each piece with `BAAI/bge-small-en-v1.5`, normalised;
  - write `indico_assistant/knowledge_guide/{manifest.json, chunks.json, vectors.npy}`.

  Test first: `tests/unit/services/knowledge/test_guide_build.py`, on a two-page fixture tree with a fake embedder: the
  chunking, the manifest fields, and the page URLs (`index.md` → `/`, `a/b.md` → `/a/b/`).
- [ ] T002 Run T001 at `e7e0016` and commit the three files. Expect 163 chunks and 54 pages.
- [ ] T003 `pyproject.toml`: `[tool.setuptools.package-data]` for `knowledge_guide/*` and `config_modules/*.yaml`.
  Check by building a wheel and listing it.

## Phase 2: Foundational (blocks every story)

### Tests first

- [ ] T004 [P] `tests/unit/services/knowledge/test_links.py`:
  - a page-list path with any host is rebased onto `base_url`;
  - a path not in the list becomes plain text;
  - a fake guide URL becomes plain text;
  - docs.getindico.io is kept;
  - bare URLs and markdown links are both handled.
- [ ] T005 [P] `tests/unit/services/knowledge/test_guide.py`:
  - loads a fixture index;
  - `excerpts()` returns the nearest 6;
  - a manifest whose model or dimensions differ gives "unavailable", not an exception;
  - the plugin's embedding service is reused when the models match.
- [ ] T006 [P] `tests/unit/services/knowledge/test_answer.py`, with a mocked `LLMService`:
  - the prompt order (rules → excerpts → pages → capabilities → question);
  - `KnowledgeAnswer(reply, offer)` is parsed;
  - links are checked before the reply is returned;
  - the route record fields (plan, Design 7);
  - with no guide, the prompt says so and the answer still comes.
- [ ] T007 [P] `tests/unit/services/actions/test_availability.py`, the consistency test (FR-009): for every action in
  `ACTIONS`, with fixture users, events and categories, `available()` giving a reason implies `check()` refuses.
  Cases:
  - a non-manager;
  - a locked event;
  - an action switched off;
  - Teams not installed;
  - a user who can't create events anywhere;
  - a speaker adding material to their own talk.
- [ ] T008 [P] `tests/unit/services/knowledge/test_capabilities.py`:
  - the instance-wide lines (creatable and proposable categories, manages any meeting);
  - the event lines;
  - no event page;
  - the fixed never-does list, including payments and "an email of its own";
  - disabled actions are listed with their reason.

### Implementation

- [ ] T009 Settings (plan, Design 5) in `default_settings.py` and `forms.py`: `knowledge_jev_api_key`
  (PasswordField, never displayed), `knowledge_jev_cutoff` (0.20), `knowledge_jev_timeout_seconds` (1.5).
  Extend `tests/unit/test_forms.py` and `tests/unit/test_plugin.py`.
- [ ] T010 `Action.summary` and `Action.available(user, event=None, category=None)` in
  `services/actions/base.py`. Implement `available()` in `events.py`, `contributions.py`, `materials.py`,
  `teams.py`, and for undo, from the same helpers each `check()` uses. T007 passes.
- [ ] T011 [P] `services/knowledge/links.py` (T004 passes).
- [ ] T012 [P] `services/knowledge/guide.py` (T005 passes).
- [ ] T013 `services/knowledge/capabilities.py` (T008 passes).
- [ ] T014 `services/knowledge/pages.py`: `page_list(user, event=None)` from `build_menu_structure()` for the three
  menus, plus the room-booking line.
- [ ] T015 `services/knowledge/answer.py` (T006 passes), including the answer rules from the research prototype:
  - claim only listed abilities;
  - offer, don't plan;
  - give steps and a link;
  - cite guide pages;
  - say when the material doesn't cover the question.
- [ ] T016 `tests/integration/knowledge/test_lists.py`, against the dev DB as users 1 and 6 on event 657:
  - the page lists differ as in the research (18 management pages against none);
  - the profile menu is present for both;
  - room booking is off;
  - the capability lists: Lucas can create meetings in 3 categories, Makoto nowhere.

**Checkpoint**: the knowledge answer works when called directly.

## Phase 3: User Story 1 — "How do I…?" (P1) 🎯 MVP

### Tests first

- [ ] T017 [P] [US1] `tests/unit/services/nl2sql/test_classifier_knowledge.py`: the prompt has the `knowledge` intent and
  its priority rule. `NL2SQLPipeline.process` returns `knowledge_request=True` for it, with no SQL generated.
- [ ] T018 [P] [US1] `tests/unit/services/chat/test_knowledge_route.py`, with mocked classifier and answer:
  - a knowledge classification gets `answer.answer()` and is stored with `route.route == "knowledge"`;
  - data and write classifications keep their paths;
  - a data answer gets a route record too.

### Implementation

- [ ] T019 [US1] `CLASSIFICATION_PROMPT` gains the intent and rule measured in the research
  (`prototype/routing_probe.py` in the study). `PipelineResult.knowledge_request`. The pipeline returns it before
  SQL generation.
- [ ] T020 [US1] `ChatService.answer()`: the knowledge route (plan, Design 1, step 3) and the route record on every
  answer.
- [ ] T021 [US1] Live check on the local stack, as user 1 on event 657, with 5 how-to questions from the knowledge
  set: steps, a page link, a guide link. This is about 5 answers on ibis, well under $0.05; say so before running.

## Phase 4: User Story 2 — "What can you do?" is true (P1)

### Tests first

- [ ] T022 [P] [US2] `tests/unit/services/knowledge/test_answer_rules.py`, with the mocked LLM and a scripted reply that
  claims an unlisted ability: the prompt carries the never-does list and the reason for each unavailable action,
  for users like 1 and 6.
- [ ] T023 [P] [US2] Extend T016: a user whose rights change between two questions gets different lists (nothing
  cached, spec US2 AS-5).

### Implementation

- [ ] T024 [US2] Make the capability list's wording the one measured best in the research: the reasons in plain
  words, and "Shall I?" offers only for listed abilities. Keep `render()` short: about 900 tokens.
- [ ] T025 [US2] Live check as users 1 and 6: "What can you do?", "Can you create meetings for me?", "Can you add a
  Teams meeting to this event?". Makoto is never offered a change. About 6 answers; say so before running.

## Phase 5: User Story 3 — Follow-ups (P2)

### Tests first

- [ ] T026 [P] [US3] `tests/unit/services/knowledge/test_gate.py`, with an injected transport:
  - Jev's input format (the last two exchanges, replies cut to 400 characters);
  - at or above the cut-off → knowledge;
  - below → not;
  - no key, a timeout, an error, a score outside [0, 1] or not a number → skipped;
  - the timeout comes from the setting.
- [ ] T027 [P] [US3] `tests/unit/services/chat/test_offer_and_fallthrough.py`:
  - an answer with an `offer` sends the next message to the planner first;
  - `handled=False` continues routing;
  - `PlanTurn.nothing_to_change` with no waiting plan → the knowledge answer, with
    `fallback: planner_nothing_to_change`;
  - with a waiting plan, the planner's reply stands.
- [ ] T028 [P] [US3] `tests/unit/services/actions/test_planner_nothing_to_change.py`: no steps, and the "did not find
  anything to change" refusal, set the flag; a real refusal ("You cannot manage…") does not.

### Implementation

- [ ] T029 [US3] `services/knowledge/gate.py` (T026 passes).
- [ ] T030 [US3] `PlanTurn.nothing_to_change` in `planner.py`, set from `_apply` and the resolver refusal (T028
  passes).
- [ ] T031 [US3] `ChatService.answer()`: the gate first, the offer memory, and the fall-through (plan, Design 1,
  steps 1, 2 and 4). T027 passes.
- [ ] T032 [US3] Live check of 6 follow-up cases, including "yes please" after an offer, which gives a plan card.
  About 12 calls on ibis plus 6 Jev decisions; say so before running.

## Phase 6: User Story 4 — Private and cheap (P3)

- [ ] T033 [P] [US4] Tests: with no Jev key, T018's routes still hold. With the guide index removed or its manifest
  changed, knowledge answers come from the two lists only.
- [ ] T034 [US4] Health: the `knowledge` block in `controllers/health.py` and `indico assistant health` (plan,
  Design 6), with `tests/integration/test_health.py` and `tests/unit/test_cli.py` extended.
- [ ] T035 [US4] Live check with the Jev key unset: 3 knowledge questions still answered.

## Phase 7: The test sets and the measurement (FR-022, Success Criteria)

- [ ] T036 Eval repository: the four sets as labelled YAML, taken from the research study
  (`~/thoth/scratch/indico_E_knowledge_study/`), with users and pages named by role and a role → id config.
- [ ] T037 Eval repository: a `knowledge` runner.
  - It uses the chat API, paces itself under the chat rate limit, and deletes its chats with retries.
  - It checks links by code and routes from the route record.
  - It grades with the judge, given the reference pages.
  - It prints the estimated cost and asks before any paid call.
- [ ] T038 **On Lucas's go only:** one full run on the default ibis dial (the estimate goes with the request).
  Compare against SC-001 to SC-007, and record the numbers in the PR.
- [ ] T039 Existing data-question eval on this branch against main (SC-006). This is a paid run, on Lucas's go.

## Phase 8: Polish

- [ ] T040 [P] README settings table: the three Jev settings. `docs/DEPLOYMENT.md`: Jev needs outbound HTTPS to
  openrouter.ai (optional); the guide ships in the package; how to rebuild it for a release.
- [ ] T041 `ruff check`, and the full `pytest tests/unit tests/contract` + `tests/integration/knowledge`.
- [ ] T042 Update the PR description with the numbers from T038 and T039, and anything left open.

## Dependencies and execution order

- Phase 1 → Phase 2 → US1 → US2 (US2 needs US1's route).
- US3 needs Phase 2 and US1. US4 needs US3's gate.
- Phase 7 needs US1–US3. T038 and T039 wait for Lucas's go.
- **MVP** = Phases 1–4: knowledge answers routed by the classifier, true for the user. **US3** adds Jev and
  follow-ups.
