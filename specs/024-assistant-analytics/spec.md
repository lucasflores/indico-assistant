# Feature Specification: Assistant analytics and traces

**Feature Branch**: `024-assistant-analytics`
**Created**: 2026-10-02
**Status**: Draft
**Input**: Lucas, 2026-10-02: "We will probably very soon want very rich stats and traces. Just take a look at our
ibis-chat user activity stats page for example … let's try to anticipate the kinds of stats we would be interested
and support that now."

## Context

**What we're building:**
- An admin page in Indico that shows how the assistant is used, what it costs, how fast and how well it answers,
  and how its routes and agent steps behave.
- A trace for every answer: the route decision, each model call, query, search and tool call, with timings,
  tokens, cost, errors and (for 30 days) the full text.
- Everything is stored in the plugin's own tables and shown inside Indico. There's no separate service to host.

**Why now:**
- An answer now takes one of six routes and can make up to about eight model calls, plus a GitHub tool loop or a
  plan.
- The plugin already collects a record of every model call (stage, model, tokens, cost), then throws it away.
- The Langfuse integration (feature 005) was never wired up: no traces are sent, and its stats tables stay empty.

**Decided before this spec (Lucas, 2026-10-02):**
- The stat list proposed on 10-02 is the one to build: adoption, routing, quality, cost and tokens, latency, agent
  depth, errors.
- Own tables plus one Indico admin page, modelled on ibis-chat's "Router Analytics" page.
- The full text of prompts and answers is stored, visible to admins only, and kept 30 days.
- The Langfuse code is deleted.
- Expected traffic is small for a long time, so the page computes its numbers live from the tables, with no
  rollups.

**Kept from ibis-chat** (`ibis-chat/ibis_chat/stats.py`, `db/views.sql`, `db/deltas.sql`):
- **Stamped once:** a turn is recorded when it happens, with the facts of that moment (who, admin or not, which
  model). It's never recomputed later.
- **Outlives the chat:** a turn's record has no foreign key to the chat tables, so a deleted chat doesn't take its
  numbers with it. Its text does go.
- **Unknown stays unknown:** a field nobody measured is left empty, never written as zero. Cost the provider didn't
  report is "unknown", never estimated from a price table (ibis-chat measured such estimates at 2.08× too high).
- **One query per number.**
- **Rates need data:** no rate is shown below a minimum number of answers. Satisfaction gets a 95% Wilson interval.
- **Links reproduce views:** the page keeps its filters in the URL, so a link shows the same view.

**One thing ibis-chat doesn't have:** a record per step inside a turn. Its turns make one model call; ours make
many.

**Decided in this spec, for Lucas to confirm:**
1. **GitHub answers store no text, and neither do later answers in the same chat.** Their prompts carry the user's
   private GitHub data, which an Indico admin can't otherwise see, and spec 023 records "never what they read". The
   chat history then carries that answer into every later prompt in the chat. Such turns are marked private: their
   steps, timings, tokens and cost are still recorded, but no text is kept, and the trace shows neither their
   question nor their answer.
2. **Turn records without text are kept until an admin sets a limit.** The default is 0, meaning forever, so trends
   outlive the chats' 90-day retention. Text follows its own 30-day setting.
3. **Admin traffic:** turns by Indico admins are flagged when they happen. The page shows them separately from
   users', like ibis-chat's "ours".
4. **Cost comes only from the provider's own bill:** ibis's `cost_usd`, or OpenRouter's `usage.cost`. Otherwise it
   is unknown, and the page shows the unknown share.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An admin sees usage, cost and speed (Priority: P1)

Lucas opens "Assistant analytics" in Indico's admin menu. He picks "last 30 days" and sees:
- **Tiles:** turns, active users, spend, median answer time, and satisfaction (once there are enough ratings).
- **Adoption:** turns per day split by route; active users per day and per week; chats and turns per chat;
  returning users; the events and categories asked about most.
- **Cost and tokens:** spend per day split by route, step and model; cost per turn (median and slow end) per route;
  tokens in and out per step; the most expensive users and turns; the share of calls whose cost is unknown; cost per
  answer rated helpful.
- **Speed:** end-to-end time per route; time waiting in the queue; time per step; model time per model; query time;
  Jev's time; how often answers hit the time limit.

**Why this priority**: It's the question behind the request ("our token usage in an increasingly complex agentic
workflow"), and it needs every turn recorded. That recording is also what the trace (story 2) is built on.

**Independent Test**: Seed turns with known values, open the page and the JSON API, and check every number against
a direct SQL query over the seed.

**Acceptance Scenarios**:

1. **Given** turns over the last 60 days, **When** an admin picks "last 7 days", **Then** every tile and chart covers
   exactly those 7 days. Days are counted in the admin's Indico timezone.
2. **Given** turns from admins and users, **When** the page opens, **Then** users' and admins' turns are shown
   apart. A switch includes or excludes admins, and the default excludes them.
3. **Given** a route filter, **When** an admin picks "data", **Then** every number covers data-route turns only, and
   the URL holds the filter.
4. **Given** calls with unknown cost, **When** spend is shown, **Then** it's the known sum, with "N% of calls not
   priced" next to it.
5. **Given** a non-admin, **When** they open the page or its API, **Then** they get 403.

---

### User Story 2 - An admin opens one answer's trace (Priority: P1)

A user reports that an answer was wrong. From the report (or the thumbs-down queue, or the turn list), Lucas opens
the turn and sees:
- **The answer itself:** the question, the answer, who asked and from which event page.
- **The outcome:** answered, failed, timed out, refused or couldn't plan.
- **The route decision:** Jev's route, confidence and time, or the classifier's, plus any fallback.
- **A timeline of every step,** each with its duration:
  - each model call, with its stage, the model requested and served, tokens, cost, attempts and error, and the full
    prompt and response;
  - each query, with the SQL, how long it ran, the rows it returned and a preview of them. For a document search
    the preview is the matched passages;
  - each GitHub tool call, with its name, time and result (ok or failed), but never its content;
  - the plan made, if any, and what happened to it;
  - the rating and comment.

**Why this priority**: The other half of the request ("rich … traces"). It's what a thumbs-down, an issue report or
an odd number on the page leads to.

**Independent Test**: Run one answer per route through the real pipeline, with the model mocked. Each trace must
list every model call the call records hold, in order, with matching tokens and cost.

**Acceptance Scenarios**:

1. **Given** a data answer that needed one correction, **When** its trace opens, **Then** it shows the classifier,
   the generator, the failed query with its error, the correction, the second query and the formatter, in order,
   with times that add up to no more than the turn's total.
2. **Given** a turn older than the text retention, **When** its trace opens, **Then** every step is still there, and
   each text shows "text no longer kept".
3. **Given** a GitHub answer, **When** its trace opens, **Then** the steps show tool names, times and outcomes, and
   no question, answer, prompt, response or tool text.
4. **Given** a chat that holds a GitHub answer, **When** the user asks a follow-up on any route, **Then** that turn is
   private too and keeps no text.
5. **Given** a chat the user deleted, **When** its turns' traces open, **Then** the steps and numbers remain and the
   text is gone.
6. **Given** the turn list, **When** an admin filters by route, outcome, user, event, model or date, **Then** the
   list shows matching turns newest first, paged.

---

### User Story 3 - An admin sees how well it answers (Priority: P2)

- **Satisfaction:** helpful share by route, intent and model, each with a 95% interval, and not shown below 10
  ratings. Also the share of answers left unrated.
- **Thumbs-down queue:** newest first, with the comment, route, model, cost and time, and a link to the trace.
- **Data answers:** success rate, correction rate, query timeouts, empty results and cut-off results.
- **Refusals and failures:** refusals, "couldn't plan", failed and timed-out answers, by route.
- **Issue reports** by kind, with links.

**Why this priority**: Quality depends on ratings, which build up slowly, and on story 1's recording.

**Independent Test**: Seed ratings and outcomes. Check the rates and intervals against hand-computed values, and
check that a rate with 9 ratings is hidden.

**Acceptance Scenarios**:

1. **Given** 9 ratings for the knowledge route, **When** the page opens, **Then** that rate shows "not enough
   ratings (9 of 10)" instead of a number.
2. **Given** a thumbs-down with a comment, **When** the queue opens, **Then** it's at the top, with its comment and a
   working trace link.

---

### User Story 4 - An admin sees routing and the agent's work (Priority: P2)

- **Routing:**
  - how the routes split over time;
  - Jev's confidence spread;
  - how often Jev is skipped, falls back, or hands over to the classifier or the planner;
  - which routes draw thumbs-down and issue reports.
- **Depth:**
  - model calls per turn, by route;
  - correction loops;
  - GitHub tool-loop steps, and calls per tool with their failure rate;
  - time per step.
- **Plans:**
  - shown → confirmed → carried out → undone;
  - failures by action;
  - how long people take to confirm.

**Why this priority**: These numbers tune routing and the agent. They matter once there's traffic to tune on.

**Independent Test**: Seed turns across routes, plus plans in every status, and check each chart against SQL.

---

### User Story 5 - An admin exports, and watches errors (Priority: P3)

- **Errors by type over time:** provider rate limits and server errors, query errors, permission errors, timeouts,
  lost answers.
- **Export:** a CSV or JSON of turns for the current filters, with or without text. Each export is logged with who
  made it, when and with which filters.

**Independent Test**: Export with filters, and check the rows against the turn list and that the log line was
written.

### Edge Cases

- **Failing before any route:** an answer that fails first (access denied, a lost session) still gets a turn
  record with its outcome, and no steps.
- **The soft time limit:** the outcome is "timeout", and the steps finished before it are kept.
- **A worker killed outright:** the hard limit or a crash means no code runs at the end. The turn is recorded when
  the worker starts it, so one with no end record after the hard limit is counted as lost.
- **Asking again:** each attempt is its own turn.
- **A failure answered politely:** an answer saved as a failure ("I couldn't…", from a failed query or model call) is
  recorded as failed, not answered.
- **Carrying out a plan** runs in its own task and isn't a turn. Its progress already lives in the plans table,
  which the plan numbers read.
- **Model retries:** a call that needed several attempts is one step, with its attempt count. An attempt that
  failed after the router may have billed it is recorded with unknown cost, as today.
- **Missing token counts:** if the provider reports none, the field stays empty.
- **Long text:** a text over 100,000 characters is stored cut off, with a mark saying so.
- **Recording fails:** if writing the record fails (a database error), the answer is unaffected, and the failure is
  logged.
  - A failed start write means the turn is missing.
  - A failed end write leaves a turn with no end record, counted with the lost ones. The page calls them "no end
    record" (the worker died, or the final write failed), and the log tells the two apart.
- **Deleted events and users:**
  - A deleted event keeps its id on old turns, and the page shows it as deleted.
  - A deleted or anonymised user's turns lose the user id and their text.
  - A merged user's turns move to the account that remains.
- **No data yet:** the page shows "no turns in this range", not empty charts.

## Requirements *(mandatory)*

### Functional Requirements

**Recording (stories 1, 2):**
- **FR-001**: Every chat answer the worker starts MUST get exactly one turn record, whatever its outcome:
  answered, failed, timeout, access denied, refusal or couldn't plan.
  - An answer saved as a failure message counts as failed.
  - A record with no end past the hard time limit counts as lost.
  - A soft time limit MUST be recorded as a timeout wherever it fires: in a model call, a query or Jev's call.
- **FR-002**: A turn record MUST hold, stamped when the turn happens:
  - **Who and where:** the user, whether they're an Indico admin, the chat, the user's message and the answer
    message, and the event page and its category. Who and where are stamped when the worker starts the turn, so
    failed turns have them too.
  - **When:** queued, started and finished.
  - **What happened:** the route and how it was decided (Jev's route, confidence, time and skip reason, or the
    classifier; any fallback), the outcome and error code.
  - **Totals:** model calls (every `generate()` call and Jev's call), tokens in and out, known cost, and the number
    of calls with unknown cost. These are sums over the turn's steps.
  - **For data answers:** intent, corrections, rows, whether the result was cut off, query time.
  - **Other routes:** the plan id, and the number of GitHub tool calls.
- **FR-003**: Each step inside a turn MUST be recorded in order, with:
  - its kind: model call, query, Jev call, or tool call. A document search is a query over the document
    passages;
  - its stage (classifier, generator, correction, formatter, knowledge, chat, planner, tool loop, …);
  - its parent step, if any;
  - its start time within the turn and its duration;
  - whether it succeeded, and its error code. A model call that returns an error without raising counts as failed.

  Model calls MUST add the model requested and served, the ibis pick, tokens, cost and attempts. Attempts MUST count
  every HTTP request, including retries the provider's SDK makes on its own. Queries and searches MUST add the rows
  returned.
- **FR-004**: Every model call MUST go through the step recording: every `LLMService.generate()` call in every
  route, and Jev's direct HTTP call. That includes a classifier call whose question then goes to another route, and
  an attempt that failed with a rate limit or server error. A test MUST fail if a model call made during a turn is
  missing from its steps.
- **FR-005**: Cost MUST come only from the provider's own report (ibis `cost_usd`, OpenRouter `usage.cost`). With no
  report, the cost is unknown. It's never computed from a price table.
- **FR-006**: The record MUST be written by the worker, outside the answer's own transaction. A failure to write it
  MUST NOT change the answer, and MUST be logged.
- **FR-007**: The rating MUST be copied onto the turn record when the user rates the answer, and cleared when they
  remove it, so satisfaction outlives the chat. The answer's id MUST go on the turn in the transaction that saves the
  answer, so every vote, which can only come once the answer exists, finds its turn.

**Text and privacy:**
- **FR-008**: While the "keep trace text" setting is on (the default), each step MUST also keep its text:
  - for model calls, the prompt and the response;
  - for queries, the SQL and a preview of up to 20 rows (for a document search, the matched passages).

  Each text is capped at 100,000 characters.
- **FR-009**: A turn MUST be private, keeping no text, if it's a GitHub (connector) turn or its chat already holds
  a GitHub answer.
  - Text collected before the route is known (Jev, the classifier) MUST be dropped too.
  - The trace, the thumbs-down queue and the export MUST show a private turn's question and answer nowhere.
  - Tokens and secrets MUST never be stored anywhere in a trace.
- **FR-010**: Only Indico admins MAY see traces, text, the page and the API. The trace and the queue MUST show a
  turn's question and answer, which they read from the chat, only while that turn's text is kept and it isn't
  private. So admins read chat content for the same 30 days as the rest of the text.
- **FR-011**: Deleting a chat MUST delete its turns' text and keep their records.
- **FR-012**: Deleting or anonymising a user MUST clear their user id on turn records and delete their turns' text.
  Merging users MUST move the turns to the account that remains.

**Retention:**
- **FR-013**: The nightly retention MUST delete:
  - text older than "keep trace text for (days)" (default 30);
  - turn records and their steps older than "keep turn records for (days)" (default 0, meaning forever).

**The page (stories 1, 3, 4, 5):**
- **FR-014**: An "Assistant analytics" page MUST appear in Indico's admin menu, with:
  - **Range:** last 24 hours, 7, 30 and 90 days, and all time, plus a custom range.
  - **Filters:** route, model, user, event and category, and whether admins are included.
  - **Bookmarkable:** every choice MUST be kept in the URL.
- **FR-015**: The page MUST show the numbers of stories 1, 3, 4 and 5. Each number MUST come from one named query
  in `services/analytics/stats.py`, and each query has a test against seeded data.
- **FR-016**: Rates MUST be hidden below their minimum count (10 ratings for satisfaction, 10 turns for other rates).
  The page then says how many there are. Satisfaction MUST show a 95% Wilson interval.
- **FR-017**: Charts MUST be drawn in the page's own script, adapted from ibis-chat's `charts.js`, with no charting
  library. Charts MUST work in Indico's light theme, and each MUST offer PNG and SVG download.
- **FR-018**: The turn list and trace view MUST be reachable from the page, the thumbs-down queue, an issue report's
  admin page, and the chat message's id.

**API (constitution II):**
- **FR-019**: Everything the page shows MUST come from admin-only JSON endpoints:
  - the stats, for a range and filters;
  - the turn list, paged by keyset;
  - one turn's trace;
  - the export, as CSV or JSON.

  They MUST be rate-limited per user, like the other read endpoints.
- **FR-020**: The stats MUST be cached for 45 seconds per range and filter set, shared by every web process.
- **FR-021**: Each export MUST be logged with who made it, when, the filters and whether it included text.

**Removing Langfuse:**
- **FR-022**: The Langfuse integration MUST be removed:
  - the services, the tracer hook in the model service and the metrics sync;
  - the stats and error tables, which a migration drops;
  - the settings (the five `langfuse_*` settings, and `retention_error_days`, which only its error table used);
  - the `/admin/stats`, `/admin/errors` and `/admin/health` endpoints;
  - the docs, tests and the `langfuse` dependency.

  Without Langfuse, `/admin/health` reports only pgvector's status, which `/search/status` already gives. The public
  `/health` check (model and guide) stays as it is.

**Cost of recording (constitution IV):**
- **FR-023**: Recording MUST add at most two short database transactions per turn: one at the start, one at the
  end. It MUST NOT hold any lock while the answer runs.

### Key Entities

- **Turn**: one chat answer attempt, with the facts stamped when it happens. Facts nobody measured stay empty. It
  has no foreign key to chats, messages, users or events.
- **Step**: one unit of work inside a turn: a model call, query, Jev call or tool call. It records
  its timing, tokens, cost and outcome. Steps nest, so a correction can sit under its query.
- **Step text**: the prompt, response, SQL or row preview of one step, deleted on its own schedule.
- **Rating**: the existing feedback entry. Its value is copied onto the turn.
- **Plan and issue report**: existing tables. The page reads them, and links them to turns.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A test drives one answer to each outcome: answered on each route, failed, soft timeout, access
  denied, refusal and couldn't plan. Each leaves exactly one turn record, with the right outcome.
- **SC-002**: For one answer per route, run with the model mocked:
  - the trace lists every model call in the call records, and Jev's call, in order;
  - the turn's tokens and known cost equal the sum of its steps.
- **SC-003**: With 50,000 seeded turns and 400,000 steps, the stats endpoint answers in under 2 s uncached and
  under 100 ms cached. The trace endpoint answers in under 300 ms.
- **SC-004**: On the live stack, recording adds under 50 ms to an answer and two short database transactions.
  Measured in the live window.
- **SC-005**: A leak test runs a GitHub answer with known fake data and a fake token, then a follow-up on another
  route in the same chat. The data and the token appear in no stored text, step, turn record, trace response or
  export.
- **SC-006**: After the nightly retention, text older than its setting is gone and turn records remain. With turn
  retention set, old records and their steps are gone too.
- **SC-007**: Every number on the page matches an independent SQL query on a fixed seed (one golden test per query).
- **SC-008**: Every new page and endpoint returns 403 to a logged-in non-admin.

## Out of scope (v1)

- **Teams meeting minutes** (`indico_teams_notes`): their cost and failures. That plugin already records its model
  calls, so it can join later.
- **Alerts and digests**, like ibis-chat's hourly alerter and daily Teams digest.
- **A labelling queue** for marking answers correct or wrong (ibis-chat's `/admin/labels`).
- **Stats for event managers** about their own events.
- **Exporting traces** to Langfuse or OpenTelemetry. The step records are shaped so an exporter could be added later.
- **Predicted cost and forecasts.** Those are ibis-chat's router-specific charts.
