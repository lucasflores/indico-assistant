# Research: Assistant core (Phase 0)

Sources:
- The document study (`scratch/indico_doc_qa_study/`);
- the industry review (`scratch/indico_stack_review/`);
- three code-research passes on 2026-10-05 (Pydantic AI and ibis; Indico 3.3.13 internals; the eval repo and the
  chat API);
- local checks run while writing this.

Paths below: `I/` = the installed Indico package; `P/` = `indico_assistant/` in this repo; `E/` = the eval repo's
`src/indico_assistant_eval/`.

## R1. The agent turn's framework

- **Decision: no agent framework.** Generalise the plugin's own tool loop (`P/services/connectors/loop.py`, 238
  lines) into the turn's loop:
  - a registry of tools instead of GitHub's;
  - more steps (the turn settings in data-model);
  - each tool reports what it touched (the memory) and any citations.
  - Every step stays one `LLMService.generate` returning a validated step model (a tool call, or the answer), so
    constitution III holds unchanged.
- **Kept as the loop has them:**
  - recorder steps, the deadline hook and the attempt count (through LLMService);
  - the measured cost (ibis `cost_usd`, never estimated);
  - the "untrusted data" marking for anything a tool returns (FR-024);
  - a repeated identical call ends the loop.
- **Added:**
  - a cost limit per turn;
  - pinning the turn's model after its first step: the first response's `ibis.chosen` is sent as the model for the
    rest of the run, which bypasses the router (ibis-service `route.py:24-40`; ibis has no session or sticky
    header). The `turn_pin_model` setting turns this off.
- **Why not Pydantic AI** (the review's pick), from reading its 2.38.0 and 2.54.0 source on 2026-10-05:
  1. **Version conflict:** 2.54 needs openai ≥ 3.19, which needs jiter ≥ 0.16. instructor 1.17 (also required by
     `indico-plugin-teams-notes`) needs jiter < 0.15. Only 2.38.0 fits.
  2. **Async only:** its OpenAI provider takes only an async client, so our httpx hooks need async wrappers. Sync
     tools run in a worker thread, where Indico's `db.session` isn't safe, so every tool must become `async def`.
  3. **Strict schemas:** it sends `strict: true` on tool schemas, which needs a profile override.
  4. **Estimated cost:** it fills in a cost from a price table when the provider gives none in its format, breaking
     spec 024's "never estimated". A model subclass is needed to copy ibis's `cost_usd` first.
  5. **A second model abstraction** beside Instructor, which needs a constitution amendment.

  That's about 150 lines of glue, plus a pinned dependency, to replace a 238-line loop that already integrates with
  everything above. Approval (deferred tools) isn't needed, because confirmation stays outside the turn
  (`contracts/agent-tools.md`, `propose_change`).
- **Ceiling:**
  - one tool per step, sequential, which the recorder's step stack needs anyway;
  - structured steps through Instructor's mode for the provider (`md_json` on ibis today).
  - `ponytail:` if the suite shows tool-choice errors that native tool calling would fix, switch Instructor's ibis
    mode to tools mode first (a setting). Revisit a framework only after that.
- **Alternatives:**
  - Pydantic AI 2.38.0 with the glue above: rejected for now.
  - OpenAI Agents SDK: sends traces to OpenAI by default, and also warns about providers without json_schema.
  - LangGraph: the heaviest option.
  - Jev through Pydantic AI's decision model: not available on OpenRouter's endpoint (research pass 1, §4).

## R2. The fast path for simple messages (decision 1, FR-022, SC-005)

- **Decision:** keep one Jev call (`P/services/knowledge/gate.py`, `decide()`) as the first step of every turn, with
  the study's "revised 2" wording in full (`data`, `chat` and `out_of_scope`), the combination that was measured.
  - That wording narrows chat to what the conversation itself says, when no file needs reading. It also says a
    named paper, thesis, report, talk or slides is never out of scope.
  - **Answered straight away:** Jev says `chat` or `out_of_scope` with confidence at or above a setting (default
    0.80). Today's chat answer and refusal handle these, unchanged.
  - **Everything else goes to the agent turn,** and so does any skipped decision (no key, timeout, error).
- **Rationale:** the cheapest path that meets SC-005, at about $0.00005 a call.
  - **Not today's wording:** that's what sent document follow-ups to chat. Only 1 of 12 document follow-ups left
    chat under it, against 10 of 12 under revision 1 (`scratch/indico_doc_qa_study/results_routing.md`).
  - **Revised 2, measured:**
    - chat 15/16 and out-of-scope 6/6 on the old sets;
    - no document question sent to chat;
    - 4 of 30 named-paper questions sent to out_of_scope (`results_routing2.md`, `results_regression.md`).
  - **That leak** is the risk. The suite's document scenarios measure it with the threshold in place. If it
    persists, an `out_of_scope` decision goes to the agent instead. That costs one model call per unrelated
    message, which is what SC-005 then has to absorb.
- **Alternatives:**
  - Pydantic AI's `DecisionModel` with Jev behind a `FallbackModel`: it reaches Jev through TypeSafe's API, not the
    OpenRouter endpoint and key we use (see R1).
  - No fast path: every "thanks" pays for an agent run, against SC-005.

## R3. Reading documents with their structure (FR-010–FR-013, decision 2)

- **Decision:** `pypdf` (already installed, 6.15.0) instead of PyPDF2, page by page, with NFKC normalisation, which
  restores the fi/ff ligatures.
  - **Sections:**
    - the PDF's outline when it has one;
    - otherwise numbered headings found in the text (`^\d+(\.\d+)*\s+[A-Z]…`), keeping only those that increase
      in order, which drops list items and contents-page lines;
    - for Word, `python-docx` heading styles (already installed).
  - **PowerPoint:** `python-pptx`, one page per slide (dry run: one new package).
  - **Chunks** stay inside one page and carry the page and the section path. The title and section path are
    prefixed to the text that is embedded and keyword-indexed: contextual retrieval without model calls.
- **Evidence (local, 2026-10-05):**
  - The three arXiv papers have outlines (20–22 entries).
  - The CERN thesis and the IDA talk have none.
  - On the thesis, the numbered-heading pattern finds "4.4.1 Fit Quality Measure" on page 48 (72 candidates; the
    noise is list items and one contents line).
- **Alternatives:**
  - **Docling:** dry run adds about 50 packages (OpenCV, an OCR stack, pandas 3, tree-sitter) and upgrades torch
    2.2.2 → 2.14.1, which risks the embedding model's pins. Too heavy for a plugin every site installs. Revisit only
    if the suite shows heading misses on unnumbered documents.
  - **PyMuPDF4LLM:** AGPL.
  - **Marker:** model-weight licence.

## R4. Searching documents (FR-012)

- **Decision:** hybrid search in plain PostgreSQL 14, scoped to the documents in play (one document, an event's
  documents, or every document the user can open).
  - A `tsvector` column with the `simple` configuration (events are multilingual) is ranked with `ts_rank_cd`.
  - pgvector does the similarity search.
  - The two lists are fused by reciprocal rank (k = 60) in one SQL statement.
- **Evidence:** the study's keyword channel raised top-10 hits from 18 to 22 of 30, and found every term question.
- **Alternatives:**
  - BM25 extensions (ParadeDB `pg_search`, VectorChord-bm25): AGPL, or a site-installed extension.
  - `pg_textsearch`: needs PG 17–18.
  - A reranker: deferred until the suite shows ranking misses inside the top 30.

## R5. Document status (story 2, scenario 6)

- **Finding:** today a document has no "in progress" state (`P/services/vector_search/store.py:94-110`). Rows are
  only inserted as completed, in one swap. "Still reading", "failed", "skipped" and "no text" all look like no rows.
- **Decision:** one status row per attachment version: `queued → reading → ready | no_text | failed | unsupported`.
  - It's written when the attachment signal is queued (`P/plugin.py:212-236`) and updated by the task.
  - The agent's document list shows the status, so "still being read" and "can't read it" are said plainly.

## R6. Access checks outside a browser request (FR-015, FR-030, decision 3)

- **Facts (`I/core/db/sqlalchemy/protection.py:184-254`):** `can_access(user)` checks, in order:
  - the `acl.can_access` plugin signal;
  - admin;
  - the access key, which is False without a request context;
  - public;
  - the ACL;
  - management;
  - inheritance.
- **What each principal type does:**
  - Multipass groups are resolved through the provider (cached in Redis for `group_cache_ttl`).
  - IP networks are denied without `request.remote_addr`, which Celery's `test_request_context` never sets. That's
    the safe direction, and it matches decision 3.
- **A trap:** `Contribution.can_manage` reads `session.user` and ignores its `user` argument (`contributions.py:561`).
  - It's reached from `can_access` on protected contributions and from `Attachment.can_access`.
- **Decision:** every lookup and access check runs inside the plugin's `acting_as(user)`
  (`P/services/actions/context.py:13`), for that same user only. The answer task already has a request context
  (`P/tasks/chat.py:20`).

## R7. Typed lookups over Indico's own code (story 4, FR-030, FR-031)

| Need | Indico code to call (all as the acting user) |
|---|---|
| **Events by text and date** | `Event.query.filter(~is_deleted, ~is_unlisted, Event.happens_between(a, b))` plus a title/description match, with `undefer(effective_protection_mode)` and `selectinload(acl_entries)`. Then `get_n_matching(query, n, lambda e: e.can_access(user))` (`I/core/db/sqlalchemy/util/queries.py:140`). `InternalSearch` matches titles only, has no date filter, and compares `object_types` with `==` against a list, so a tuple returns nothing. |
| **Timetable, talks, speakers, sessions** | `TimetableSerializer(event, management=False, user=user, api=True).serialize_timetable()` (`I/modules/events/timetable/legacy.py:22`). It filters with `entry.can_view(user)`. Respect the event's `contribution_settings['published']`: non-managers get no contributions while unpublished (`I/modules/events/api.py:71-74`). |
| **Registrations** (clarification 3) | Managers: `event.can_manage(user, permission='registration')`, then the registration rows. Others: forms with `is_participant_list_visible(is_participant)` and not `participant_list_disabled`; rows from `event.get_published_registrations(user)` (`is_publishable` covers consent, form modes and duration); columns from `registration_settings.get_participant_list_columns(event, form)`. |
| **Notes and minutes** | `EventNote.get_for_linked_object(obj)`, then `note.html`, after `obj.can_access(user)` (the view's own check). |
| **Attachments** | `folder.can_view(user)` and `attachment.can_access(user)`. Not `get_attached_folders()`, which reads `session.user`. |

- **The HTTP export API in-process: rejected.** Hooks read `request.args` and `g.current_api_user`, and
  `hook(user)` rolls back the session.
- **Decision 4:** the NL2SQL pipeline stays as one data tool through story 3. Story 4 measures the typed lookups
  against it on the suite and removes it, with its RLS copy (`P/services/nl2sql/readonly_db.py`), unless the suite
  shows questions only it answers.

## R8. The acceptance suite (story 1)

- **Driver:** the public chat API, as `E/knowledge/run.py` does:
  - signed `X-Assistant-Auth` tokens;
  - `POST /api/assistant/chat` `{message, session_id, event_id, uploads}`, then polling `/chat/jobs/<id>`;
  - files through `POST /chat/uploads`, then `uploads: [uuid]`;
  - confirmations by typing "yes", or `POST /plans/<id>/confirm {token}`;
  - an answer's metadata (route, citations, plan id) from `GET /sessions/<id>`, with no database read;
  - trace steps from `GET /admin/turns/by-answer/<uuid>` with an admin token, retried until `turn.finished_at` is
    set (the job finishes before the turn's end record is written).
- **Rate limits:** hard-coded at 10 per minute and 200 per day per user (`P/services/chat/rate_limiter.py:31-35`).
  A full run (about 340 messages) is spread across the test users, each well under 200, and paced at 10 per
  minute. The dev worker answers one job at a time (`--pool=solo`), so a full run takes about an hour and the quick
  subset about 15 minutes.
- **Cost:**
  - Each turn's cost comes from its trace (`turn.cost_usd`, Jev's OpenRouter cost included), read with the world
    owner's admin token.
  - The change in the ibis key's `spent_usd` (`E/knowledge/run.py:401-407`) is only a cross-check. It's key-wide
    and misses Jev, so nothing else may use the key during a run, and the report says so.
- **World ids:** scenarios name world keys. `world.py` (Indico virtualenv) writes `reports/world_ids.json`, and the
  runner (eval virtualenv, HTTP only) resolves keys through it.
- **Indico checks:** `state` checks and waiting for indexing are database reads (psycopg2, as `route_of` does
  today). They test Indico, not the assistant, so FR-004 holds.
- **Preflight:**
  - GitHub scenarios need fake GitHub (`INDICO_ASSISTANT_FAKE_GITHUB` with `DEBUG`, `P/services/connectors/github.py:26,184`)
    and a connected world user.
  - Change scenarios need `actions_enabled` and `attach_file`, which are off by default
    (`P/default_settings.py:17,80`).
  - The runner refuses to start without them.
- **The eval constitution (1.0.0)** was written for the NL2SQL atoms harness: headless, a clean database after
  every run, MLflow.
  - Amend it to 1.1.0 with US1: scope §I, §III and §IV to the atoms harness, and add a principle for the
    API-driven scenario suite, allowing a versioned, namespaced, removable world.
  - Keep §V: scenario runs log to MLflow.
- **The test world (clarification 4):** built in-process with Indico's own models in the Indico virtualenv. This is
  `E/data/indico_inserter.py`'s pattern, not the SQL-only `E/inserter.py`, which can't create attachments,
  registrations, users or ACLs, and fires no signals.
  - **Indico code to build from:** the creation patterns of Indico's test fixtures
    (`I/testing/fixtures/{category,event,user}.py`; `I/modules/events/registration/testing/fixtures.py`).
  - **Attachments:** `AddAttachmentFilesMixin` (`I/modules/attachments/controllers/management/base.py:110-128`),
    with `signals.attachments.attachment_created` sent so the real indexing runs.
  - **Events** are created inside `acting_as(world owner)`, because `create_event` reads `session.user`.
  - **Versioning:** a hash of the world's definition is stored with it, and a different hash means rebuild.
  - **Namespace:** a dedicated category `__eval__ world`; removing the world deletes that category's tree and the
    world's users.
- **SSO groups (clarification 5):** a `static` identity provider in `indico.conf`, with
  `AUTH_PROVIDERS`/`IDENTITY_PROVIDERS`/`PROVIDER_MAP`. Indico copies these to multipass (`I/web/flask/app.py:113-140`).
  - Use `group_cache_ttl: 0`, so membership isn't cached between runs.
  - Members are linked through `Identity(provider, identifier)` rows.
  - Today the dev instance only has the local `indico` provider, and no plugin overrides `acl.can_access`.
- **Gaps in today's eval code that the suite fixes:**
  - connector ids that collide with other sets;
  - `httpx` used but not declared;
  - hard-coded dev ids (user 1, user 6, meeting 657), replaced by the world's own.

## R9. Constitution

- **No amendment needed.** R1 keeps every model call inside `LLMService` and Instructor (Principle III). Jev stays
  under III's decision-model exception, as today.
- The turn's structured steps work on every provider the plugin supports, in Instructor's mode for that provider, so
  the spec's assumption about tool calling holds without a settings check.
