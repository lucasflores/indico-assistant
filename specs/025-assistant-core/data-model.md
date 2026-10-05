# Data model: Assistant core (Phase 1)

There are no users (spec, Assumptions), so tables are replaced rather than migrated. Each new table lives in
`plugin_assistant` (constitution I), with an Alembic migration that has an upgrade and a downgrade.

## Plugin (this repo)

### `documents` (new, story 2): one row per attachment

| Field | Type | Notes |
|---|---|---|
| `attachment_id` | int, PK | Indico attachment |
| `event_id` | int | for scoping by page; indexed |
| `file_id` | int | the attachment's current file; a new file means re-read |
| `filename`, `content_type` | text | |
| `status` | enum | `queued` → `reading` → `ready` \| `no_text` \| `failed` \| `unsupported` |
| `error` | text, null | why it failed (shown to admins only) |
| `page_count` | int, null | pages, or slides for PowerPoint |
| `outline` | JSONB, null | `[{number, title, level, page_start, page_end}]` from the PDF outline, numbered headings, Word heading styles or slide titles (research R3) |
| `updated_at` | timestamptz | |

- **Status changes:**
  - **Queued:** when the attachment signal is collected (`plugin.py` `after_commit`).
  - **Reading:** when the task starts.
  - **Done:** `ready` (chunks written), `no_text` (no text layer), `unsupported` (type) or `failed` (an exception, kept
    in `error`).
  - A new `file_id` returns the row to `queued`. A deleted attachment deletes the row and its chunks.
- **Validation:** `outline` page numbers fall within `1..page_count`. Sections are ordered by `page_start`.

### `document_chunks` (replaces `extracted_documents`, story 2)

| Field | Type | Notes |
|---|---|---|
| `id` | bigint, PK | |
| `attachment_id` | int, FK → `documents`, on delete cascade | |
| `chunk_index` | int | order within the document |
| `page` | int | chunks never cross a page |
| `section` | text, null | the section path, e.g. "4.4.1 Fit Quality Measure" |
| `text` | text | page text, NFKC-normalised |
| `embedding` | vector(384) | of `title + section + text` (research R3) |
| `search` | tsvector, generated stored | `to_tsvector('simple', title ‖ section ‖ text)`, GIN index |

- Unique key: (`attachment_id`, `chunk_index`).
- Chunks are about 1,000 characters with a 200-character overlap, within a page. This is the study's setting; the
  suite can tune it.
- **No approximate-nearest-neighbour index.** An exact scan is fine for the thousands of chunks a site holds.
  `ponytail:` add HNSW if a site passes about 100k chunks.

### Conversation memory (story 2 for documents, story 3 for everything): no new table

It's kept on each answer message, as `chat_messages.metadata_json["touched"]`:

```json
[{"kind": "document", "ref": {"attachment_id": 17}, "title": "CERN-THESIS-2011-112.pdf", "position": 1},
 {"kind": "event", "ref": {"event_id": 657}, "title": "Budget Review", "position": 1},
 {"kind": "plan", "ref": {"plan_id": "…"}, "title": "Move 'Budget' to 15:00", "position": 1},
 {"kind": "github_item", "ref": {"repo": "o/r", "number": 16}, "title": "…", "position": 2}]
```

- **Kinds:** `event`, `contribution`, `session`, `document`, `note`, `plan`, `github_item`, `result`.
- **Position** is the order the answer presented things in, so "the second one" resolves.
- **No access is stored.** Every use re-checks access as the acting user (FR-021). A GitHub item is kept only in a
  private turn's message, as spec 024 already marks it.
- **Lifetime:** a chat's memory goes with the chat (spec 020's retention and deletion), and needs no table of its
  own.
- **Rationale:** the agent needs identifiers, not past tool results (research R1, context engineering). Old tool
  results aren't replayed into later turns. Their full text stays in spec 024's trace for admins, for 30 days.

### Answer metadata (existing `metadata_json` of the answer message)

- **`citations`** (new): `[{attachment_id, page, quote}]`, one per cited passage. Each is validated: the quote must
  appear on that page (FR-013).
- **`route`** keeps its shape:
  - `route` = `fast:chat`, `fast:out_of_scope` or `agent`;
  - `tools` = the tools the turn called, in order;
  - plus `jev{…}` and `failed`.

### Analytics (spec 024 tables): no schema change

- **The turn's steps:**
  - `jev` for the fast-path decision;
  - `llm` for each model request;
  - `tool` for each tool call (`name` = the tool);
  - `sql` inside the data tool, as today.
- **`turns.route`** takes the values above. The analytics page lists the routes it finds, so it needs no change.

### Settings (new, global)

| Setting | Default | Purpose |
|---|---|---|
| `fast_path_confidence` | 0.80 | Jev's confidence at or above which `chat` / `out_of_scope` is answered without the agent |
| `fast_path_out_of_scope` | True | turn off to send `out_of_scope` to the agent (research R2's fallback) |
| `turn_max_requests` | 8 | model requests per turn (FR-025) |
| `turn_max_tool_calls` | 12 | tool calls per turn |
| `turn_max_cost_usd` | 0.10 | the turn stops once its measured cost passes this |
| `turn_deadline_seconds` | 75 | the turn wraps up after this, within Celery's 120 s soft limit |
| `turn_pin_model` | True | send the first step's `ibis.chosen` as the model for the rest of the turn (research R1) |

### Removed

- **Tables:** `extracted_documents`; the RLS role and policies (story 4, if nothing uses them).
- **Settings:** the routing-only ones (knowledge route thresholds) with story 2; the RLS secret with story 4.

## Eval repo: the acceptance suite (story 1)

### World definition (`scenarios/world.yaml`, versioned by hash)

- **`users`:** `key, name, email, password, idp_username?, local_groups[], idp_groups[]`. Test users are
  `@example.test` and never real people.
- **`categories`:** `key, title, protection, acl[]`, all under one root category, `__eval__ world`.
- **`events`:** `key, category, title, type, start, end, timezone, protection, acl[], managers[], published
  (contributions), note?`.
- **`contributions`** and **`sessions`:** `key, event, title, start, duration, speakers[], session?, protection, acl[]`.
- **`registration_forms`:** `key, event, publish_public, publish_participants, columns[], registrations[{user,
  consent}]`.
- **`attachments`:** `key, target (event|contribution key), source_url, sha256, title, protection`. Files are
  downloaded and checked against `sha256` at build.

- **ACL entries** name a user key, a local group, an `idp:<group>`, or a registration form key.
- **The world's hash** is sha256 of the canonical YAML plus the attachment hashes. It's stored on the root category
  (`description`), and a different hash triggers a rebuild.
- **Every world event** carries the `__eval__` keyword (eval constitution §II).
- **`reports/world_ids.json`:** written by `build` and `status`, it maps every key (users, events, contributions,
  sessions, attachments, registration forms) to its id, with the world hash. The runner resolves scenario keys through
  it and refuses to run if its hash isn't the world's current one.

### Scenario (`scenarios/sets/*.yaml`)

```yaml
- id: doc-q10                 # unique across all sets
  set: documents              # documents | cross | knowledge | data | github | change | chat | access
  quick: true                 # in the quick subset
  abilities: [documents]      # what it exercises (report scores per ability)
  turns:
    - as: viewer              # world user key
      page: thesis_event      # world event key, or null
      attach: [thesis]        # world attachment keys uploaded with this message
      wait_ready: []          # attachment keys (or `uploads`) to wait for, by database read, before sending
      say: "Summarise the first one for me."
      confirm: null           # yes | no | null: a typed confirmation sent as the next message
      expect:
        must: ["calorimeter", "punch-through"]   # regexes, case-insensitive
        must_not: []
        cites: [{doc: thesis, pages: [1, 2, 3]}] # a citation to one of these pages
        refusal: false
        no_lookup: false      # true: the turn's trace must show no tool step
        plan: null            # {action: move_contribution, target: talk_budget} | none
        state: null           # SQL checks (psycopg2, ids from world_ids.json) after a confirmed change
        judge: null           # a criterion for the LLM judge (FR-003), e.g. guide | honest
```

- **Rules:**
  - Ids are unique across sets (fixes today's collisions).
  - Every `expect` has at least one check, and a `judge` check names its criterion.
  - `state` is only allowed after `confirm: yes`.

### Run report (`reports/<run-id>.json`)

- **Header:** `run_id, started, finished, mode (full|quick), plugin_sha, eval_sha, world_hash, model_setting,
  estimated_usd, measured_usd (sum of turn costs), key_delta_usd (the ibis key's change, a cross-check),
  key_shared_warning, mlflow_run_id`.
- **`scenarios`:** `[{id, set, abilities, pass, failed_check, turns: [{seconds, route, tools[], cost_usd, answer}]}]`.
  A turn's `cost_usd` comes from its trace (`turn.cost_usd`, Jev included).
- **`scores`:** per set and per ability, as passed / total.
- **Comparing two reports** lists the scenarios whose result changed, and the score differences.
- **Each run is also an MLflow run** (eval constitution §V): a parent run, per-set and per-ability metrics, and the
  report as an artifact.
