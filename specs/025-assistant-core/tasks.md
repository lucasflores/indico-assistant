# Tasks: Assistant core

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)
**Branches:**
- **Plugin:** `025-assistant-core` (worktree `~/indico-assistant/plugin-025`).
- **Eval:** `025-acceptance-suite` (worktree `~/indico-assistant/eval-025`).

**Tests:** test-first (constitution VI).
- In each phase, the tests come before the code they cover, and must fail before it is written.
- Plugin: `pytest tests/unit tests/contract` after each task group, and all of `pytest tests` before each PR, from
  the worktree. Eval: `uv run pytest -q`.

**Paid runs** (the acceptance suite) are pre-approved by Lucas (2026-10-05) up to these ceilings. Each is still
quoted before it runs:
- the quick subset, at most $1;
- a full run, at most $5.

**Live windows** switch the shared stack to the worktree. Follow the `indico-dev-server` skill, "Live checks from a
worktree": warn other sessions, `pg_dump` before a migration, restore afterwards.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an open task)
- **[Story]**: US1–US4 from the spec; no label = shared
- **Paths:**
  - **Plugin:** relative to `~/indico-assistant/plugin-025`.
  - **Eval:** marked `eval:`, relative to `~/indico-assistant/eval-025`.

---

## Phase 1: Setup

- [x] T001 The plugin baseline: `pytest tests` in `~/indico-assistant/plugin-025` at `main` = `f85e798`. Record the
  pass, skip and fail counts here, and name any failures already on main.
  - **Done 2026-10-05:** 2234 passed, 27 skipped, 7 failed. All 7 failures are in
    `tests/integration/test_chat_citations.py`, already failing on main.
- [x] T002 The eval worktree: `git -C ~/indico-assistant/eval worktree add ../eval-025 -b 025-acceptance-suite
  origin/main`, then `uv sync --extra dev` and `uv run pytest -q`. Record the counts here.
  - **Done:** the eval repo has no remote, so the branch is cut from local `main` (`330c804`). `uv run pytest -q`:
    129 passed.
- [x] T003 [P] eval: `pyproject.toml`. Declare `httpx` (used, never declared), and add the console script
  `indico-assistant-scenarios = indico_assistant_eval.scenarios.run:main`.

---

## Phase 2: Foundational (blocks every story)

- [x] T004 The static test identity provider (clarification 5, research R8). **Approved by Lucas on 2026-10-05.** It
  edits the shared `~/indico-assistant/instance/indico.conf`, so warn other sessions before restarting.
  - Add `AUTH_PROVIDERS`, `IDENTITY_PROVIDERS` and `PROVIDER_MAP` for a `static` provider `testidp`, with
    `trusted_email: True`, `group_cache_ttl: 0`, and the world's `idp` users and groups. Generate the users and
    groups from `eval: src/indico_assistant_eval/scenarios/world.yaml` once T013 exists, or write them by hand to
    match it.
  - Restart the web server and the worker, as the skill says.
  - Check: local login still works, and the group search shows `testidp` groups.
  - **Done 2026-10-05:** `testidp` (group `physicists`: ida) is appended to `indico.conf`, after a backup at
    `instance/backups/indico.conf.20261005-122056.bak`. The web server and worker were restarted from main with
    the usual variables (all 43 peer sessions were idle).
- [x] T005 [P] The world's documents (spec, Assumptions: public sources, never committed).
  - Record a source URL and sha256 for each of the study's files:
    - arXiv 1704.07983, 1706.03762v7 and 2410.15319v1;
    - CERN-THESIS-2011-112 from CDS.
  - `IDATalk_sm_reduced.pdf` (Lucas's seminar slides) and `transcript-2026-02-07-2100.txt` (the Aurora
    transcript) are committed to the eval repo: **approved by Lucas on 2026-10-05**. Never the CV.
  - **Done:** every file is cached by sha256 in `~/.cache/indico-assistant-eval/files/`, seeded from the dev
    archive.
  - **Sources:**
    - arXiv 1704.07983v2, 1706.03762v7 and 2410.15319v1 match their URLs byte for byte.
    - The thesis is CDS record 1388275. CDS blocks scripted downloads with a proof-of-work page, so it comes only
      from the cache.
    - The IDA talk (33 MB) and the transcript are in eval: `data/world/`.

---

- [x] T006 The eval constitution 1.1.0: eval: `.specify/memory/constitution.md`, in the eval worktree (T002).
  - Add a Sync Impact Report.
  - Scope §I (deterministic ground truth), §III (headless NL2SQL) and §IV (a clean database after every run) to the
    NL2SQL atoms harness.
  - Add a principle for the scenario suite:
    - it talks to the assistant only through the chat API;
    - it uses a versioned, namespaced test world in the dev database, built once per definition hash and removable
      with one command, with every world event tagged `__eval__`;
    - each run cleans up its chats, and those left by an interrupted run;
    - verdicts are binary per check;
    - an LLM judge counts only once its agreement with human labels is measured.
  - §V (MLflow) applies to scenario runs too.
  - Version 1.1.0, amended 2026-10-05, as Lucas approved.
  - **Done:** eval commit `2fbf89a`.

---

## Phase 3: User Story 1 — score any build on realistic conversations (P1, eval repo)

**Goal:** one command scores the assistant on scripted multi-turn scenarios, through the chat API, against a
versioned test world. It also produces the baseline.
**Independent test:** a full run against today's assistant gives every scenario a pass or fail with the failed
check named, scores per set and per ability, and each turn's time and cost. No chats are left behind (FR-001 to
FR-008, SC-001).

### Tests first (offline)

- [x] T007 [P] [US1] eval: `tests/test_scenarios_schema.py`. The scenario validator refuses:
  - an id repeated across sets;
  - an `expect` with no check;
  - `state` without `confirm: yes` on that turn;
  - `as`, `page`, `attach` or `wait_ready` naming a key that's missing from `world_ids.json` (or from `world.yaml`
    before the world is built);
  - a `judge` check without a criterion.
- [x] T008 [P] [US1] eval: `tests/test_scenarios_grade.py`. With recorded job results and session or trace JSON as
  fixtures, check that each check passes and fails as it should:
  - `must` and `must_not` (regex, case-insensitive);
  - `cites` (document and an allowed page, read from `metadata.citations`, with `[p.N]` in the text as the fallback
    for today's assistant);
  - `refusal`;
  - `no_lookup` (no `tool` step and no `sql` step in the trace);
  - `plan` (an action and target in the plan card);
  - `state` (an SQL check run with psycopg2 against ids from `world_ids.json`, after the confirmed change);
  - `judge` (the LLM judge's verdict on a criterion, from a recorded judge response).
- [x] T009 [P] [US1] eval: `tests/test_scenarios_run.py`.
  - The dry run makes no network call (httpx monkeypatched to fail) and prints counts and the estimate.
  - Turns are spread so no user goes over 200 a day, with 10 a minute pacing per user.
  - `--quick` selects exactly the `quick: true` scenarios.
  - The report matches data-model "Run report", and `compare` lists the changed scenarios.
  - Each turn's cost comes from its trace (`turn.cost_usd`), and the run total is cross-checked against the key's
    spend.
  - A run is logged to MLflow: a parent run, per-set and per-ability metrics, the report as an artifact.
  - The preflight refuses to run when fake GitHub mode, `actions_enabled` or `attach_file` is missing, or when
    `world_ids.json` doesn't match the world's hash.
- [x] T010 [P] [US1] eval: `tests/test_world_hash.py`. The world hash doesn't change with key order, and does change
  when an attachment's sha256 or any field changes.

### Code

- [x] T011 [US1] eval: `src/indico_assistant_eval/chat.py`, moved out of `knowledge/run.py:70-171`. It provides:
  - `token`;
  - `ask(user, message, page_event_id, session_id, uploads=[], answer_id=None)`;
  - `upload(user, path) -> uuid` (`POST /chat/uploads`);
  - `confirm(user, plan_id, token)` (`POST /plans/<id>/confirm`, then poll);
  - `session(user, session_id)` (`GET /sessions/<id>`, for each answer's metadata);
  - `trace(answer_id)` (admin token, retried until `turn.finished_at`);
  - `cleanup()`.

  `knowledge/run.py` imports it. `tests/test_knowledge.py` stays green.
- [x] T012 [US1] eval: `src/indico_assistant_eval/scenarios/world.yaml` (data-model, "World definition"). It
  contains:
  - **Users:** a world owner (admin); a manager; a viewer; a GitHub-connected and an unconnected user; and one
    user per access type: direct grant, local group, idp group, category inheritance, speaker, registrant, no
    access.
  - **Events:**
    - the thesis event, with the CERN thesis;
    - a reading-group event, with the three papers;
    - the IDA seminar;
    - Budget Review, with the Aurora transcript (as T005 decides);
    - two meetings, whose notes mention talks by title;
    - one conference with unpublished contributions;
    - one protected event per access type.
  - **Registration forms:** every publishing mode, and registrants with each consent.
  - **Contributions and speakers:** enough for the data set.
- [x] T013 [US1] eval: `src/indico_assistant_eval/scenarios/world.py`, users and groups. A CLI `build | status |
  remove`, run with the Indico virtualenv's Python and `INDICO_CONFIG`. It works in an app context plus
  `test_request_context`, inside `acting_as(world owner)` (research R6, R8).
  - Users are local accounts with passwords.
  - Idp members get `Identity(provider='testidp', identifier=…)` rows.
  - Local groups get their members.
  - The GitHub-connected user gets a fake-GitHub connection (`services/connectors/store.py`), matching the fake
    seed's `octo-dev` account.
- [x] T014 [US1] `world.py`: categories and events.
  - The root category is `__eval__ world`.
  - Events are created with `create_event(category, type, data)`, then given their protection mode and ACL through
    `update_principal`, for users, local groups, `GroupProxy(name, provider='testidp')` and registration forms.
  - Contributions, sessions and timetable entries follow `I/testing/fixtures/{contribution,session,timetable}.py`.
  - The `published` setting is set for contributions.
  - Every world event carries the `__eval__` keyword (eval constitution §II).
- [x] T015 [US1] `world.py`: registrations and notes.
  - Registration forms are created with their `publish_registrations_*` modes and participant-list columns.
  - Registrations are created through `create_registration(..., management=False)`, so consent applies.
  - Notes are created with `EventNote.get_or_create(obj).create_revision(...)`, and `note_added` is sent.
- [x] T016 [US1] `world.py`: attachments, versioning and status. **Built live 2026-10-05:** 28 events, 18
  registrations, 10 documents indexed in about 45 s. Two build bugs were fixed (contribution friendly ids need a
  committed event; note autoflush). Mutable events and `reset` were added to keep the world reproducible.
  - **Attachments:**
    - Download each one and check its sha256.
    - Create it as `Attachment` + `AttachmentFile.save(bytes)` on the target event or contribution.
    - Send `attachment_created`, so the plugin's real indexing runs.
  - **Versioning:** store the world hash on the root category. `build` rebuilds only on a new hash.
  - **`status`:** waits until every world document is indexed and reports each one. Before US2, that means chunk
    rows exist for the current file id. After US2, it means `documents.status`.
  - **`world_ids.json`:** `build` and `status` write every key's id (users, events, contributions, sessions,
    attachments, registration forms) and the world hash to `eval: reports/world_ids.json`.
  - **`remove`:** deletes the category tree and the world's users.
- [x] T017 [US1] eval: `scenarios/grade.py`. The per-turn checks of T008. `state` checks are psycopg2 reads, and
  `judge` uses `knowledge/judge.py`. The scenario passes when every turn passes.
  The report names the first failed check.
- [x] T018 [US1] eval: `scenarios/run.py` and `scenarios/compare.py`.
  - **Loading:** sets are loaded and validated (T007 rules).
  - **The dry run** lists the scenarios, the users they're spread across, and the estimate per set
    (`ESTIMATE_USD`-style, calibrated after the baseline).
  - **Options:** `--go`, `--quick`, `--sets`, `--only`, `--out reports/<run-id>.json`.
  - **Running:**
    - Each scenario runs in a fresh session, with uploads sent before their turn.
    - `confirm: yes` sends a typed "yes".
    - 429s are retried after their `Retry-After`.
    - A turn with `wait_ready` first waits, by database read, until those documents are indexed. Before US2 that
      means chunk rows for the current file; after, `documents.status`.
    - Each turn's cost comes from its trace (`turn.cost_usd`, Jev included), read with the world owner's admin
      token.
    - The run total is cross-checked against the ibis key's change in `spent_usd`, with a warning that the key is
      shared.
    - Chats are cleaned up at the end, and leftovers from an interrupted run at the start.
  - **Preflight:** refuses to run unless all of these hold:
    - the stack is in fake GitHub mode (`INDICO_ASSISTANT_FAKE_GITHUB` with `DEBUG`);
    - `actions_enabled` and `attach_file` are on;
    - `world_ids.json` matches the world's current hash.
  - **MLflow:** each run is a parent MLflow run, with per-set and per-ability metrics and the report as an artifact
    (eval constitution §V).
  - **`compare`:** two reports in, changed scenarios and score deltas out.
- [x] T019 [P] [US1] eval: `scenarios/sets/documents.yaml`.
  - Source: the study's 34 items (`~/thoth/scratch/indico_doc_qa_study/questions.json`).
  - Each item becomes a scenario: history turns become earlier turns, world keys replace filenames, evidence
    phrases become `must`, and `pdf_page` becomes `cites`.
  - The four negatives get `no_lookup: true`.
  - Scenarios that attach a file in chat use `wait_ready` before asking, except the one that tests "still being
    read".
  - About 8 are marked `quick`.
- [x] T020 [P] [US1] eval: `scenarios/sets/knowledge.yaml`, `chat.yaml`, `change.yaml`, `github.yaml`.
  - Source: `knowledge/sets/{knowledge,routing,followups,connector}.yaml`, with their `must`, `must_not`, `items`
    and `mention` kept as checks.
  - Route-only expectations become outcome checks: refusal, a plan card, no lookup. Where none applies, they're
    dropped.
  - Knowledge items with `expect: guide` or `honest` become a `judge` check with that criterion.
  - Ids are renamed to be unique (the connector `f01`/`c01` collisions).
  - About 12 are marked `quick`.
- [x] T021 [P] [US1] eval: `scenarios/sets/data.yaml`.
  - About 25 data questions about the world's events, timetables, speakers, counts and notes, modelled on the data
    atoms' dimensions (`dimensions.py`), with facts the world defines.
  - About 6 are marked `quick`.
- [x] T022 [P] [US1] eval: `scenarios/sets/cross.yaml`. At least 20 scenarios (FR-007). They cover:
  - documents and data;
  - notes, then a change, then a confirmation, with `state` checked;
  - GitHub plus an event;
  - references across turns ("the second one", "that talk");
  - an ambiguous reference, which should get a question back;
  - injection text inside a world document, which should give no plan;
  - a turn that hits a limit, which should give a plain note.

  About 8 are marked `quick`.
- [x] T023 [P] [US1] eval: `scenarios/sets/access.yaml` (SC-007, clarification 3).
  - For each access-type user, questions about the protected events: answered or not, never revealed.
  - Registration questions as a manager, as a non-manager with a published list, and for a registrant without
    consent.
  - About 6 are marked `quick`.
- [x] T024 [US1] eval: `scenarios/calibrate.py` (FR-003).
  - Export at least 40 answers that need the LLM judge from a report, as a labelling file for Lucas.
  - Compute the judge's true-pass and true-fail rates against his labels.
  - The report marks judge-graded results "uncalibrated" until then.
- [x] T025 [US1] Build the world on the dev stack (after T004, T005), wait for `status` to show every document
  ready, and run both dry runs. **Quote the full and quick costs to Lucas.**
  - **Done 2026-10-05:**
    - The world (hash `baa444dbe026`) was rebuilt after giving world-managers the root, and adding `gil`, a manager
      with GitHub. All 10 documents are indexed; `reset` was checked live.
    - The sets total 273 scenarios and 346 turns: documents 36, knowledge 53, chat 14, change 28, routing_data 20,
      github 50, data 27, cross 26, access 19.
    - **Dry runs:** full $4.12, quick (40 scenarios) $0.61, both within the pre-approved ceilings.
- [x] T026 [US1] **Paid, on Lucas's go:** the baseline full run (≤ $5), saved to `eval: reports/baseline.json`.
  - Record its scores per set and ability here.
  - Then the calibration labels (T024), by Lucas.
  - **In progress (paused 2026-10-05, Lucas's request):** two paid quick runs, used to fix the suite itself.
    - **Run 1:** 12/40, $0.14 measured ($0.15 by the key). It exposed suite bugs:
      - no answer's metadata was read (the API's key is message_id);
      - fake GitHub refused the world's token;
      - world users had the default time zone;
      - an offer in words wasn't accepted as a plan.

      All four were fixed in eval `88b485f`.
    - **Run 2:** 18/40, $0.10 measured ($0.115 by the key). The six scenarios that had failed for suite reasons
      pass. Time patterns were then widened to accept "4:00 PM" (eval `d055c1a`).
    - **The full baseline is still to run:** estimated $1.58, pre-approved up to $5. Run it with the stack in fake
      GitHub mode, then restore normal mode.
  - **Baseline, 2026-10-05** (eval `reports/baseline.json`, world `baa444dbe026`, plugin main `f85e798`):
    **135/273 passed**; $0.52 measured from the traces, $0.85 on the key (the judge's calls included; the $1.58
    estimate was high).
    - By set: chat 14/14, github 43/50, change 20/28, data 16/27, routing_data 10/20, access 7/19, knowledge 14/53,
      cross 6/26, **documents 5/36**.
    - By ability: chat 21/28, github 44/56, change 23/42, data 38/89, knowledge 25/67, access 8/22, documents 7/48.
    - Knowledge's low score is mostly the judge's "partial" verdicts. They count only once the judge is calibrated
      (Lucas's 40 labels, T024's `calibrate export`).
- [x] T027 [US1] The eval PR. `uv run pytest -q` and the repo's configured linters pass first. It carries the
  constitution amendment and a README section on scenarios, the world and paid runs. Hand the link to Lucas.

  - **Done 2026-10-05:** README section committed (eval `e13d0eb`), plus a spending cap in the runner (`6f60de9`:
    `--max-usd`, default $1 quick / $5 full). The branch `025-acceptance-suite` is Lucas's to merge locally (the eval
    repo has no remote).

**Checkpoint:** the baseline exists. Every later story is accepted against it.

---

## Phase 4: User Story 2 — documents through the new single turn (P2, plugin)

**Goal:**
- Documents are read with their structure.
- A new turn (Jev fast path, then the loop with tools) becomes the only entry point. Today's abilities are wrapped
  as tools.
- The route split and the old document path are deleted.

**Independent test:** the documents set reaches ≥ 90% (SC-002). Every other set stays within 2 scenarios of the
baseline (SC-004). Fast-path messages cost no more (SC-005).

### Tests first

- [x] T028 [P] [US2] `tests/unit/document/test_extractor.py`.
  - **PDF:** pypdf gives one text per page, NFKC-normalised. A fixture with fi/ff ligatures reads "different".
  - **Word:** heading styles come out as headings.
  - **PowerPoint:** one page per slide, from a small generated .pptx.
  - **Text and Markdown:** one page.
- [x] T029 [P] [US2] `tests/unit/document/test_structure.py`.
  - The outline becomes sections with page ranges.
  - Numbered headings are detected, and the increasing-order filter drops contents-page lines and list items. Use a
    text fixture modelled on the thesis, where "4.4.1 Fit Quality Measure" must land on its page.
  - Word heading levels become sections.
- [x] T030 [P] [US2] `tests/unit/document/test_chunker.py`. Chunks never cross a page and carry their section path.
  The text to embed and index is prefixed with the title and section.
- [x] T031 [P] [US2] `tests/integration/document/test_store.py`.
  - Status goes `queued → reading → ready`, `no_text`, `failed` or `unsupported`.
  - A new `file_id` resets the row to `queued`.
  - Deleting the attachment deletes the document and its chunks.
- [x] T032 [P] [US2] `tests/integration/document/test_search.py`.
  - An exact term found only by the keyword channel ranks in the top 3.
  - Scope by document and by event works.
  - An attachment the user can't open is never returned. Its event is protected, and the test runs inside
    `acting_as`.
- [x] T033 [P] [US2] `tests/unit/turn/test_loop.py`, with the LLM mocked.
  - Tools are dispatched from the registry.
  - The request and tool-call limits hold.
  - A repeated identical call ends the loop.
  - The deadline wrap-up and the cost limit both produce an answer with the "stopped" note.
  - Tool results are marked untrusted.
  - With `turn_pin_model`, the second step sends the first response's `ibis.chosen` as the model.
  - Each model request and tool call is a recorder step.
  - A provider error (connection refused, 5xx) gives the user a clear message, and nothing is changed (FR-028).
- [x] T034 [P] [US2] `tests/unit/turn/test_memory.py`.
  - The touched documents are written to the answer's `metadata_json["touched"]`, with their positions.
  - "The second one" resolves to position 2 of the last list.
  - A document whose access was revoked is dropped on use.
- [x] T035 [P] [US2] `tests/unit/turn/test_citations.py`.
  - `[p.N]` markers parse.
  - A citation whose quote isn't on that page is dropped and logged.
  - The answer's `metadata.citations` carries `url#page=N`.
- [x] T036 [P] [US2] `tests/unit/turn/test_answer.py`.
  - The fast path answers `chat` and `out_of_scope` at or above the threshold, and below it goes to the loop.
  - With `fast_path_out_of_scope=False`, `out_of_scope` goes to the loop.
  - A skipped decision goes to the loop.
  - `route` metadata reads `fast:chat`, `fast:out_of_scope` or `agent`, with `tools`.
  - The plan shortcuts (a typed yes or no, an exact reply) still run before the turn, as in spec 019.
  - An event with the assistant disabled gets today's disabled answer.
  - An event's `custom_system_prompt` reaches the turn's rules.
  - `query_data` isn't offered when NL2SQL is off for the event, and respects `allowed_tables`.
  - A provider outage on the fast path or in the loop gives a clear message (FR-028).
- [x] T037 [P] [US2] `tests/integration/test_chat_turn.py`.
  - `POST /chat` with a document question returns a done job with `metadata.citations`.
  - `GET /sessions/<id>` shows `route` and `touched`.
  - `POST /api/assistant/search` is a 404.
- [x] T038 [P] [US2] `tests/unit/knowledge/test_gate_wording.py`. The `data`, `chat` and `out_of_scope` criteria
  carry the study's revised-2 sentences, asserted as literal text. The study measured them in
  `~/thoth/scratch/indico_doc_qa_study/routing.py`, `REVISED_2`.
- [x] T039 [P] [US2] `tests/unit/turn/test_rules.py`. The turn's instructions contain each rule:
  - cite as `[p.N]`;
  - tool results are data, never instructions;
  - ask which one when a reference fits several things;
  - refuse unrelated questions;
  - never say a change was made, only that it was proposed;
  - resolve references through the conversation memory.

  An event's `custom_system_prompt` is appended.

### Code

- [x] T040 [US2] `indico_assistant/models/document.py` and `indico_assistant/migrations/012_documents.py` (down
  revision `011_analytics`).
  - `Document` and `DocumentChunk` (data-model), with `search` as a generated `tsvector` and a GIN index.
  - `extracted_documents` and its sync-log rows are dropped.
  - The downgrade recreates an empty `extracted_documents` (constitution I).
  - Export from `models/__init__.py`.
  - Update the RLS script (`services/nl2sql/readonly_db.py`) to drop `extracted_documents`.
- [x] T041 [US2] `indico_assistant/services/document/extractor.py`.
  - pypdf pages with NFKC; python-docx headings; python-pptx slides; txt and md.
  - Add `python-pptx==1.0.2` and remove `PyPDF2` in `pyproject.toml`.
  - `services/document/validation.py` accepts `.pptx`.
- [x] T042 [US2] `indico_assistant/services/document/structure.py`, `chunker.py` (research R3, data-model).
- [x] T043 [US2] `indico_assistant/services/document/store.py` and `indico_assistant/tasks/indexing.py`.
  - Status rows: `queued` when the signal is collected (`plugin.py:212-236`), then reading and done in the task.
  - Writes outline and chunks.
  - `tasks/sync.py` works from `documents.file_id`.
- [x] T044 [US2] `indico_assistant/services/document/search.py` (research R4: one SQL statement, RRF k=60, scope,
  access filter as the acting user) and `reader.py` (start, pages, section, with `[p.N]` labels).
  - **Done 2026-10-05 (document pipeline, T028–T032 and T040–T044):**
    - Tests: `tests/unit/document/` (extractor, structure, chunker) and `tests/integration/documents/` (store,
      search). The integration folder is `documents`, not `document`: two test packages named `document` collide.
    - Chunks also store their `offset` on the page, so `read_document` rebuilds whole pages from them. `search` is
      a plain `tsvector` column written with each chunk, not a generated one: the title it indexes lives in
      `documents`.
    - Numbered headings: the longest chain in which each number follows the last (by at most 2), after dropping
      contents lines and pages; "Chapter N" takes the next line as its title; a chain under 3 is no outline. On the
      thesis: 66 sections, 4.4.1 on p.48, all 7 chapters. The IDA talk (slides) gets none.
    - Part of T053 went in now, since nothing worked without the old table: `services/vector_search/`,
      `controllers/search.py` (+ routes, schemas), the old processor and hasher, NL2SQL's document template, intent
      and `:query_vector` hook, the YAML table and its row policy, PyPDF2 and the Python `pgvector` package (raw SQL
      only), the sync log and its retention setting. A new `indico assistant sync-documents [--event N] [--force]`
      replaces the removed sync endpoints. The health check reports document status counts.
    - `pytest tests`: 2067 passed, 7 failed (T001's known `test_chat_citations.py`). New code: ruff and black
      clean, `mypy --strict` clean, coverage 92–99% on `services/document/`.
- [x] T045 [US2] `indico_assistant/services/turn/tools.py`. It holds:
  - the `Tool` registry and `ctx` (user, session, page event, memory, limits);
  - result truncation and untrusted marking, importing `_mark` from `connectors/loop.py` until US3 moves it here;
  - a `tool` recorder step per call;
  - the document tools `list_documents`, `read_document` and `search_documents` (contracts/agent-tools.md).
- [x] T046 [US2] `indico_assistant/services/turn/abilities.py`: the wrapped tools.
  - `query_data` wraps the NL2SQL pipeline.
  - `ask_guide` wraps `knowledge/answer.py`.
  - `ask_github` wraps `connectors/loop.answer`, only when connected, and marks the turn private.
  - `propose_change` wraps the planner. It creates a plan, and the answer carries the plan card.
  - `query_data` is registered only when NL2SQL is enabled for the event, and uses the event's `allowed_tables`.
- [x] T047 [US2] `indico_assistant/services/turn/loop.py`, generalised from `services/connectors/loop.py`.
  - The step model is the registry's tools plus `Final`.
  - Limits come from the settings.
  - The model is pinned after step 1.
  - The connector keeps its own loop until US3.
- [x] T048 [US2] `indico_assistant/services/turn/memory.py` and `citations.py`.
- [x] T049 [US2] `indico_assistant/services/turn/rules.py`: the turn's instructions (T039's rules), with the event's
  `custom_system_prompt` appended.
- [x] T050 [US2] `indico_assistant/services/turn/answer.py` and `indico_assistant/services/chat/service.py`.
  - `answer.py` runs the fast path through `gate.decide` (research R2), then the loop.
  - The chat service's route dispatch and classifier fallback are replaced by `turn.answer`. The plan shortcuts
    stay.
  - `metadata` gets `route`, `touched` and `citations`.
  - An event with the assistant disabled is refused before the turn, as today.
- [x] T051 [US2] `indico_assistant/services/knowledge/gate.py`: the study's revised-2 wording in full (`data`, `chat`
  and `out_of_scope`), the combination that was measured. Only `chat` and `out_of_scope` are acted on.
- [x] T052 [US2] Settings in `indico_assistant/default_settings.py` and `forms.py` (data-model, "Settings"). Remove
  the routing-only ones.
- [x] T053 [US2] Deletions (FR-027, story 2).
  - `indico_assistant/services/vector_search/` and `controllers/search.py`, with its blueprint routes.
  - NL2SQL's document template and `extracted_documents` in `services/nl2sql/` (prompts and the allowed-tables
    YAML).
  - PyPDF2.
  - What imported from `vector_search/` moves:
    - `check_pgvector_available` goes into `services/document/store.py`;
    - `plugin.py`, `tasks/sync.py`, `tasks/indexing.py`, `embedding/service.py`, `document/processor.py` and
      `services/__init__.py` use the new modules;
    - the health check reports document status counts (constitution IV, contracts/chat-api.md).
  - The README, `DEPLOYMENT.md` and `VECTOR_SEARCH_SETUP.md` updated.
  - `grep` shows no references left.
- [x] T054 [US2] The gates (constitution, "Code Quality Gates"): `ruff check`, `black --check`, `mypy`, and the
  full `pytest tests --cov` (≥ 80% on the new services), apart from T001's known failures. A test asserts that every
  chat answer goes through `turn.answer` (SC-009, story 2's half). Commit.
  - **Done 2026-10-05 (the turn, T033–T039 and T045–T054):**
    - `services/turn/`: `answer.py` (the fast path, then the agent; event settings read with "" as inherit),
      `loop.py` (generalised from the connector's: request, tool-call, measured-cost and time limits, each ending
      with an answer that says it stopped; repeated calls end the lookups; results marked `<tool_data>`; the model
      pinned to ibis's first pick; a provider outage gives a fixed message and nothing changes), `tools.py` (the
      context and the document tools), `abilities.py` (query_data, ask_guide, ask_github, propose_change; `plan()`
      also serves the chat service's shortcuts), `memory.py`, `citations.py`, `rules.py`.
    - `ChatService.answer`: the plan shortcuts, then `turn.answer`; the old route dispatch, the classifier fallback
      and `_process_with_nl2sql`/`_knowledge`/`_chat`/`_connector` are gone. A test asserts both (SC-009).
    - Choices made while building:
      - The untrusted-data mark is the loop's own `<tool_data>`, not the connector's `_mark` (its tag says
        GitHub).
      - `ask_github` is offered whenever GitHub is on. Its answer says "connect first" without a model call when
        the user isn't connected, as the connector route did. The turn becomes private only once GitHub was read,
        and `route.private` marks it: the context builder and `holds_connector_answer` read it.
      - A plan from `propose_change` ends the turn: the planner's reply and card are the answer (combining waits
        for story 3).
      - The fast path sees the page note and the conversation as before. `turns.route` was widened to 24
        characters in migration 012, since `fast:out_of_scope` has 17.
      - Nothing applied the per-event settings before. The turn now does: assistant off, NL2SQL off, allowed
        tables, custom prompt. `get_effective_setting` took "" (inherit) for a value, so the turn reads them itself.
      - The job result's metadata allowlist gains `citations`.
    - T053's docs: `docs/VECTOR_SEARCH_SETUP.md` became `docs/DOCUMENTS.md`; the README (features, settings, the
      lifecycle, the removed search API, the module tree) and `DEPLOYMENT.md` (012 upgrade, dependencies) updated.
    - Tests: `tests/unit/turn/` (loop, memory, citations, answer, tools, gate wording, rules) and
      `tests/integration/test_chat_turn.py` (a document question through POST /chat, the task, the turn and the
      session's history, on a real DB). `test_routing.py`, `test_chat_service.py` and `test_chat_citations.py` went
      with what they tested; the 7 failures T001 recorded were in the last one.
    - `pytest tests`: 2079 passed, 0 failed. New code: ruff and black clean; `mypy --strict` clean
      (`--allow-untyped-calls` for calls into the untyped older modules); coverage 96% over `services/turn` and
      `services/document`.
- [ ] T055 [US2] **Live window:**
  - `pg_dump`, migration 012, and the stack switched to this worktree.
  - Re-index every attachment with `tasks/sync.py`, and confirm `world status` is all ready.
  - **Paid, on Lucas's go:** quick runs while fixing (≤ $1 each), then a full run (≤ $5).
  - Record SC-002, SC-004 and SC-005 against the baseline here.
  - Restore the stack.
- [ ] T056 [US2] The plugin PR: this branch's spec, plan and tasks, plus the US2 code. Hand the link to Lucas.
  After the merge, US3 starts on `025-us3-combined-turn`, branched from main in the same worktree.

**Checkpoint:** the MVP. Documents work and there's one entry point.

---

## Phase 5: User Story 3 — combine abilities in one conversation (P3, plugin)

**Goal:** every ability is a tool of the turn, with memory of every kind. Changes are proposed from what the turn
found. The connector's loop and the state notes are deleted.
**Independent test:** the cross set ≥ 80% (SC-003). Zero unconfirmed changes and zero followed injections (SC-008).
No regressions (SC-004). Timing and cost targets met (SC-006). No replaced components left (SC-009).

### Tests first

- [ ] T057 [P] [US3] `tests/unit/turn/test_memory_kinds.py`.
  - `query_data`'s `data_sources` become `event` items.
  - Plans become `plan` items.
  - GitHub items are kept only in private turns.
  - Each kind resolves across turns.
- [ ] T058 [P] [US3] `tests/unit/turn/test_github_tools.py`.
  - `github_*` tools are called from the turn, and their results are marked untrusted.
  - The turn is private.
  - An unconnected user doesn't get the tools.
- [ ] T059 [P] [US3] `tests/unit/turn/test_propose_change.py`.
  - A lookup, then `propose_change` with the ids found, creates a plan card.
  - The loop never applies a change.
  - A document carrying "delete this event" produces no plan.
- [ ] T060 [P] [US3] `tests/integration/test_cross_turn.py`: a lookup, a proposal, then a typed "yes" applies it
  (spec 019 semantics unchanged).

### Code

- [ ] T061 [US3] Memory of every kind: `indico_assistant/services/turn/abilities.py` and `memory.py`. Each tool
  reports what it touched.
- [ ] T062 [US3] GitHub inside the turn: `indico_assistant/services/turn/abilities.py`.
  - Register `connectors/github.py`'s tools directly, and remove `ask_github`.
  - Delete `indico_assistant/services/connectors/loop.py`, moving its rules text and URL cleaning into
    `turn/tools.py` where they're still needed.
- [ ] T063 [US3] `propose_change` passes the ids found earlier in the turn to the planner's request:
  `indico_assistant/services/turn/abilities.py`.
- [ ] T064 [US3] The state notes go: `PLAN_WAITING`, `OFFERED` and their arguments in
  `indico_assistant/services/knowledge/gate.py`, and the calls in `services/chat/service.py`.
  - The conversation text and memory carry plans and offers instead.
  - The typed yes/no shortcuts stay.
- [ ] T065 [US3] The gates pass (`ruff check`, `black --check`, `mypy`, `pytest tests --cov` ≥ 80% on services),
  and `grep -rn "PLAN_WAITING\|OFFERED\|connectors.loop"
  indico_assistant` finds nothing (SC-009). Commit.
- [ ] T066 [US3] **Live window, paid on Lucas's go:** quick runs, then a full run. Record SC-003, SC-004, SC-006 and
  SC-008 here.
- [ ] T067 [US3] The plugin PR (US3). Hand the link to Lucas. After the merge, US4 starts on `025-us4-access`, branched
  from main.

---

## Phase 6: User Story 4 — answers that follow Indico's own access rules (P4, plugin)

**Goal:** typed lookups over Indico's own code and access checks. NL2SQL and its RLS copy are removed unless the
suite shows they're needed (decision 4).
**Independent test:** the access set agrees 100% with Indico's `can_access` (SC-007). The data set is at or above
the baseline (SC-004).

### Tests first

- [ ] T068 [P] [US4] `tests/integration/lookups/test_events.py`. `find_events` returns exactly the events each user
  can open. Cover:
  - a direct grant;
  - a local group;
  - a multipass group (`GroupProxy` with a static provider in the test config);
  - category inheritance;
  - a protected event with no grant.

  Date filters and unlisted events are covered too.
- [ ] T069 [P] [US4] `tests/integration/lookups/test_timetable.py`. Non-managers get no unpublished contributions.
  Managers do.
- [ ] T070 [P] [US4] `tests/integration/lookups/test_registrations.py`.
  - Managers see what Indico shows them.
  - Non-managers see exactly the published list.
  - A non-consenting registrant is absent, and only the configured columns appear.
- [ ] T071 [P] [US4] `tests/integration/lookups/test_notes.py`. Notes are returned only for objects the user can
  open.

### Code

- [ ] T072 [US4] `indico_assistant/services/lookups/events.py`, `timetable.py`, `registrations.py` and `notes.py`
  (research R7). All run inside `acting_as(user)` for that user only (the `Contribution.can_manage` trap).
- [ ] T073 [US4] Register `find_events`, `get_event`, `get_timetable`, `get_registrations` and `get_notes` in
  `indico_assistant/services/turn/abilities.py` (contracts/agent-tools.md). Their results report `touched`.
- [ ] T074 [US4] **Live, paid on Lucas's go:** a full run with `query_data` still registered, then a run without it.
  Compare them per data scenario.
- [ ] T075 [US4] Decision 4. If no data scenario needs `query_data`, delete:
  - `indico_assistant/services/nl2sql/`;
  - the RLS script and `indico assistant nl2sql-db-sql`;
  - the `ASSISTANT_NL2SQL_DATABASE_URI` requirement and its settings.

  Provide a drop script for the role and policies. Otherwise, keep it for the listed questions only, and record
  which ones.
- [ ] T076 [US4] The gates pass (`ruff check`, `black --check`, `mypy`, `pytest tests --cov` ≥ 80% on services). Then a full run (paid, on go), with SC-007 and SC-004 recorded here.
  Commit, then the plugin PR (US4).

---

## Phase 7: Polish

- [ ] T077 [P] `README.md` and `DEPLOYMENT.md`.
  - The new turn, the documents, and python-pptx.
  - The removed `/search`, and NL2SQL if T075 removed it.
- [ ] T078 [P] Tell Lucas which parts of the `indico-dev-server` skill change (environment variables, the quickstart
  commands), and update the skill only on his go. It's shared through the agent-skills repo.
- [ ] T079 Record the final full-run scores against every success criterion in this file, and update the stack
  review's README with the outcome.

---

## Dependencies

- **Setup (T001–T003)** → **Foundational (T004–T006)** → **US1 (T007–T027)**.
- **US1's baseline (T026) gates every later acceptance.**
- **US2 (T028–T056)** starts after the US1 PR is merged.
  - Its offline tests and code (T028–T054) need nothing from US1, and can start in parallel with T019–T027 if
    wanted.
  - Its live acceptance (T055) needs the baseline.
- **US3 (T057–T067)** needs US2 merged: the turn and the tools exist.
- **US4 (T068–T076)** needs US2 merged: the registry exists. It can run before or after US3. The spec's order is
  US3 first.
- **Polish** comes last.

## Parallel examples

- **US1:**
  - The offline tests T007–T010 together.
  - Then the set files T019–T023 together, while T013–T018 are built in order.
- **US2:**
  - Tests T028–T039 together.
  - Then T041, T042 and T044 (documents) beside T045–T049 (turn). They meet in T050.
- **US4:** tests T068–T071 together.

## Implementation strategy

- **The MVP is US1 + US2:** a measured baseline, then documents answered through the single entry point.
- **US3 and US4 are increments,** each accepted against the same suite.
- **No phase ships without its quick run.** No story is accepted without a full run, quoted first and run on
  Lucas's go.
