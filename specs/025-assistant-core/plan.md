# Implementation Plan: Assistant core

**Branch**: `025-assistant-core` | **Date**: 2026-10-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/025-assistant-core/spec.md`

## Summary

Four user stories, one PR each:
1. **An acceptance suite in the eval repo:** scripted multi-turn scenarios, driven only through the chat API,
   against a versioned test world in the dev database. It produces the baseline.
2. **Documents read with their structure,** inside a new single answering turn that becomes the only entry point. The
   six-way route split and the old document path are deleted.
3. **The turn generalised to every ability,** with conversation memory. The connector's own loop and the state notes
   are deleted.
4. **Typed lookups over Indico's own access checks.** NL2SQL and its row-level-security copy go, unless the suite
   shows they're needed.

**Technical approach (research.md):**
- **No agent framework (R1):** the plugin's GitHub tool loop is generalised into the turn loop, so every model call
  stays in `LLMService` and Instructor.
- **Fast path (R2):** Jev, with the study's measured "revised 2" wording, answers simple messages before the loop.
- **Parsing (R3):** `pypdf` with outlines or numbered headings, python-docx headings, and python-pptx for slides,
  instead of PyPDF2. Docling is rejected for its footprint.
- **Search (R4):** hybrid tsvector and pgvector in plain PG14, fused by reciprocal rank.
- **Access (R6, R7):** every check runs as the acting user, through `acting_as`.

## Technical Context

**Language/Version**: Python 3.12.9 for both the Indico virtualenv and the eval repo (uv)
**Primary Dependencies**:
- **Plugin:**
  - Indico 3.3.13 and Celery;
  - instructor 1.17 through `LLMService`;
  - pgvector and sentence-transformers (bge-small-en-v1.5, 384-d, local);
  - pypdf 6.15 (already installed; replaces PyPDF2) and python-docx;
  - **python-pptx 1.0.2** (the only new dependency).
- **Eval:** httpx (declared at last), PyYAML. The world builder runs with the Indico virtualenv's Python.

**Storage**: PostgreSQL 14 with pgvector, `plugin_assistant` schema (data-model.md)
**Testing**:
- **Plugin:** pytest with Indico fixtures (unit, contract and integration). Model calls are mocked.
- **Eval:** offline pytest; the dry run spends nothing.
- **Acceptance:** the suite itself, live and paid, run only on Lucas's go.

**Target Platform**: the Indico web app and Celery worker (queues `assistant` and `assistant_bulk`). Development is
on the local stack, Teams in fake mode.
**Project Type**: an Indico plugin, plus its separate eval package
**Performance Goals**:
- 95% of answering turns within 60 s; median lookup turn ≤ $0.02 (SC-006).
- Simple messages no slower or costlier than the baseline (SC-005).
- A full suite run ≤ $5, the quick subset ≤ $1.

**Constraints**:
- Celery's soft limit is 120 s, so a turn wraps up at 75 s.
- The chat API allows 10 messages a minute and 200 a day per user, so the suite spreads its turns across test users.
- No new database extension, service, or heavy dependency for sites.
- Every paid run is quoted first and waits for Lucas's go.

**Scale/Scope**: small sites (tens to hundreds of users), tens of documents per event, thousands of chunks. The
suite has about 200 scenarios and about 340 turns.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| **I. Official plugin architecture** | New tables (`documents`, `document_chunks`) are in `plugin_assistant`, with Alembic migrations (upgrade and downgrade). Signals are unchanged (`attachment_*`). | Pass |
| **II. API first** | Additive: `metadata.citations`. Removal: the old `/search` endpoint (FR-027). The suite uses only the API (FR-004). | Pass |
| **III. LLM provider abstraction** | No framework (R1). Every text-generating call is `LLMService.generate` through Instructor. Jev stays under the decision-model exception, with its key, timeout, fallback and validation as today. | Pass, no amendment |
| **IV. Graceful degradation** | Fast path skipped → agent turn. Model provider down → a clear message (FR-028). A turn hitting a limit answers with what it found (FR-025). Indexing failures become a status (R5), not silence. | Pass |
| **V. Configuration hierarchy** | The new turn and fast-path settings are global, like today's routing and LLM settings. None is per-event, since they tune the engine, not the event. API keys are unchanged. | Pass (same scope as existing engine settings) |
| **VI. Test-first** | Each story's PR adds unit tests for new services (loop, tools, structure, search, memory, lookups) and integration tests for the changed endpoints, written first. Coverage gates as today. | Pass |
| **Security** | Hybrid search is parameterised SQL. NL2SQL keeps its validator while it exists. Tool results are marked untrusted (FR-024). Rate limits are unchanged. Spec 024 records every step. | Pass |
| **Code quality gates** | Each plugin PR runs `ruff check`, `black --check`, `mypy` and `pytest tests --cov` (≥ 80% on services) before hand-over (tasks T054, T065, T076). | Pass |
| **Eval constitution (eval repo, 1.0.0)** | Its §III (headless NL2SQL) and §IV (a clean database after every run) conflict with the API-driven suite and its kept world (clarification 4). Amended to 1.1.0 in US1's PR (task T006): §I, §III and §IV scoped to the NL2SQL atoms harness, plus a scenario-suite principle. §V (MLflow) is met: scenario runs log to MLflow. | Pass after the amendment |

**Post-design re-check:** still passing.
- data-model.md adds no out-of-schema table.
- The contracts change the API additively plus one removal.
- R9 records why no amendment is needed.

## Project Structure

### Documentation (this feature)

```text
specs/025-assistant-core/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/agent-tools.md, contracts/chat-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit.tasks
```

### Source Code

```text
# Plugin (this repo), by story
indico_assistant/
├── services/turn/                 # NEW (story 2)
│   ├── loop.py                    #   the turn loop, generalised from services/connectors/loop.py
│   ├── tools.py                   #   Tool registry, ctx, result truncation, untrusted marking, step recording
│   ├── memory.py                  #   read/write metadata_json["touched"], resolve references, re-check access
│   ├── citations.py               #   [p.N] → validated metadata.citations
│   ├── rules.py                   #   the turn's instructions, plus the event's custom_system_prompt
│   └── answer.py                  #   entry point: fast path (gate.decide) → loop; limits; model pinning
├── services/document/             # REWRITTEN (story 2)
│   ├── extractor.py               #   pypdf (pages, NFKC), python-docx (heading styles), python-pptx (slides), txt/md
│   ├── structure.py               #   outline / numbered headings → sections with page ranges
│   ├── chunker.py                 #   page-bounded chunks with section path (existing chunker reused)
│   ├── store.py                   #   documents + document_chunks writes, status transitions
│   ├── search.py                  #   hybrid tsvector + pgvector, RRF, access-scoped
│   └── reader.py                  #   start / pages / section reads with [p.N] labels
├── services/lookups/              # NEW (story 4): events.py, timetable.py, registrations.py, notes.py
├── services/knowledge/gate.py     # CHANGED (story 2): fast-path question only (revised-2 wording)
├── services/chat/service.py       # CHANGED (story 2): dispatch replaced by turn.answer
├── services/connectors/github.py  # KEPT as tools; connectors/loop.py deleted once turn/loop.py covers GitHub (story 3)
├── services/vector_search/        # DELETED (story 2): rag/search/store/validation, with controllers/search.py
├── services/nl2sql/               # story 2: document template + extracted_documents removed; story 4: removed or kept per suite
├── models/document.py             # CHANGED (story 2): Document, DocumentChunk; ExtractedDocument removed
├── migrations/012_documents.py    # NEW (story 2)
└── tasks/indexing.py, tasks/sync.py  # CHANGED (story 2): status rows, new store

tests/unit/{turn,document,lookups}/ and tests/integration/…, per story

# Eval repo (~/indico-assistant/eval), story 1
src/indico_assistant_eval/
├── chat.py                        # Chat client moved out of knowledge/run.py (tokens, ask, uploads, confirm, cleanup)
├── scenarios/
│   ├── world.yaml                 #   the test world (data-model.md)
│   ├── world.py                   #   builder: runs with the Indico venv's Python; versioned by hash
│   ├── sets/*.yaml                #   documents, cross, knowledge, data, github, change, chat, access
│   ├── grade.py                   #   per-turn checks (must, cites, refusal, no_lookup, plan, state)
│   ├── run.py                     #   CLI: dry run, --go, --quick, --only, --out; spreads turns across test users
│   └── compare.py                 #   two reports → changed scenarios and score deltas
└── knowledge/run.py               # uses chat.py; its sets are converted into scenarios/sets
tests/test_scenarios_*.py          # offline: schema, grading, world hash, dry run spends nothing
```

**Structure Decision**: the plugin keeps its `services/<area>/` layout. The turn gets its own `services/turn/`, so
`chat/service.py` shrinks to persistence plus one call. The suite lives in the eval repo as `scenarios/`, beside
`knowledge/`, sharing a `chat.py` client. The world builder imports Indico, so it runs with the Indico
virtualenv's Python, as `scripts/actions_eval/run.py` does today.

## Delivery: one PR per story

| PR | Repo | Story | Lands | Accepted by |
|---|---|---|---|---|
| 1 | eval | **US1 suite** | The eval constitution 1.1.0; `chat.py`; `scenarios/` (world, sets, grade, run, compare). Outside the repo: the static IdP in the dev instance's `indico.conf` (approved) and the baseline report | SC-001; a baseline full run (≤ $5, pre-approved, quoted first) |
| 2 | plugin | **US2 documents + new entry point** | This branch's spec/plan/tasks; `services/turn/` (loop, tools, memory for documents, citations, answer); `services/document/` rewrite; migration 012; gate reduced to the fast path; chat dispatch replaced; NL2SQL's document template removed. Deleted: route split, `vector_search/`, `/search`, PyPDF2 | SC-002 on the documents set; SC-004 and SC-005 against the baseline (quick runs while building, a full run to accept) |
| 3 | plugin | **US3 combined turn** | memory for every kind, GitHub tools inside the turn, `propose_change`. Deleted: `connectors/loop.py`, the state notes (`PLAN_WAITING`, `OFFERED`) | SC-003, SC-008, SC-009, SC-006 |
| 4 | plugin | **US4 access** | `services/lookups/`, measured against `query_data`; then NL2SQL and its RLS copy removed if the suite agrees (decision 4) | SC-007, SC-004 on the data set |

- **Order and gates:** a PR starts only after the previous one is merged (Lucas merges).
- **Branches:** US2 lands on `025-assistant-core`, with this spec. After each merge, the next story branches from
  main in the same worktree: `025-us3-combined-turn`, then `025-us4-access`.
- **Checks:** each PR runs the plugin's full test suite and the quick subset. Full runs are quoted first.

## Risks

| Risk | Mitigation |
|---|---|
| Instructor `md_json` steps choose tools less reliably than native tool calling | The documents set shows it in PR 2. First fix: Instructor tools mode on ibis (a setting). R1's alternatives after that. |
| The fast path leaks named-paper questions to `out_of_scope` (R2) | The documents set measures it. `fast_path_out_of_scope=False` sends them to the agent. |
| Multi-step turns exceed 60 s on Balanced | Turn limits; model pinning; SC-006 measured per run; the 75 s wrap-up. |
| The world builder fights Indico's session-bound code (`create_event`, `Contribution.can_manage`) | Everything is built inside `acting_as(world owner)`, in an app plus test request context (R6, R8). |
| The suite's cost measure is key-wide | Nothing else may use the key during a run. The report warns. |

## Complexity Tracking

No constitution violations to justify. One deliberate ceiling is recorded in research R1: one tool per step.
