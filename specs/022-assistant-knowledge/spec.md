# Feature Specification: The assistant knows Indico, and knows what it can do

**Feature Branch**: `022-assistant-knowledge`
**Created**: 2026-09-30
**Status**: Draft · **Revised**: 2026-09-30, after Lucas's routing decisions (Jev routes instead of the classifier;
a chat route; the plan card is the offer)
**Input**: Lucas, 2026-09-29: "Full self knowledge (what the assistant capabilities are), and Indico platform
knowledge (deep knowledge of how to use Indico, and what it can do). The assistant should be able to guide the user
to complete any action on Indico and also know what it can do itself for the user."

## Context

Users ask the assistant "how do I give someone management rights?" and "can you create meetings for me?". Today
there is no route for these questions:
- Most are sent to the change planner, which replies "I could not work out what to change".
- The rest are turned into database queries, or refused as out of scope.

On 55 real questions, none got a good answer ([research.md](research.md)).

Decided before this spec (Lucas, 2026-09-29):
- **The knowledge base** is Indico's official user guide (learn.getindico.io). A copy pinned to one version ships in
  the plugin and is searched locally.
  - No web search, no MCP.
  - The admin documentation comes later.
- **Two lists are generated for each question:**
  - what the assistant can do for this user;
  - the pages this user can open.
- **Routing (revised 2026-09-30):** one decision by Jev gives each message its route and, for data, its kind. It
  replaces the classifier's routing; the classifier routes only when Jev is unavailable, never as well as Jev.
  - Jev is called directly; every other model call goes through ibis.
  - A fifth route, **chat**: answerable from the conversation so far, informed by general knowledge.
- **"Can you do X?" (revised 2026-09-30):** a request. The planner plans it, and the plan card, which asks for
  confirmation, is the offer. What the planner cannot plan gets the knowledge answer.
- **Some things are always handed off with a link, never done:**
  - permission and protection changes;
  - deleting events;
  - emailing people;
  - registrations and payments.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - "How do I…?" gets the steps and the right page (Priority: P1)

A manager on their meeting's page asks "How do I give someone management rights on this event?". The assistant
answers:
- with the steps in a few lines;
- with a link to this event's Protection page;
- with a link to the guide page it used.

**Why this priority**: This is most of what users ask, and today it fails every time.

**Independent Test**: Ask the how-to questions from the research set as a manager, from an event page. Each answer
gives steps that would get the user there, and links only to pages this user can open.

**Acceptance Scenarios**:

1. **Given** a manager on their event's page, **When** they ask how to do something the guide covers, **Then** the
   answer gives the steps, links to the page of this event where it's done, and cites the guide page.
2. **Given** a question the guide doesn't cover (badges, API tokens, a plugin's page), **When** the page list has
   the page, **Then** the answer points to it. **When** it doesn't, the answer says so plainly and never invents
   menus or steps.
3. **Given** a feature this Indico has switched off (room booking here), **When** a user asks how to use it,
   **Then** the answer says it isn't available on this Indico, even though the guide describes it.
4. **Given** the assistant could also do the thing asked about (add a talk, add a reminder), **Then** the answer
   also offers to do it.

---

### User Story 2 - "What can you do?" is true for this user, here (Priority: P1)

Makoto, who can't create events anywhere, asks "Can you create meetings for me?". The assistant says no, and says
why: he can't create events in any category on this Indico, so he should ask a category manager. Lucas asks the same
question and gets "Yes, in Home, Nothing Science or Other Less Cool Meetings. Shall I?".

**Why this priority**: An assistant that offers what it can't do breaks trust worse than one that says no.

**Independent Test**: Ask the about-the-assistant questions as both test users. No answer claims an ability the
assistant lacks for that user. Every ability it has is offered when asked about.

**Acceptance Scenarios**:

1. **Given** any user, **When** they ask "What can you do?", **Then** the answer lists the kinds of questions it
   answers, and the changes it can make for this user here.
2. **Given** a change the assistant can make for this user, **When** they ask "Can you…?", **Then** it plans it:
   the plan card is the offer, and nothing changes until they confirm.
3. **Given** a change it can't make for this user (not a manager, action switched off by the admin, plugin not
   installed), **Then** it says no, gives the reason, and says who can.
4. **Given** something it never does (register people, take payments, send an email of its own, change
   permissions, delete events, book rooms), **Then** it says so and links the page where the user, or a manager, does it.
5. **Given** an admin switches an action off, or a user loses management rights, **Then** the next answer reflects
   it. Nothing is cached between questions.

---

### User Story 3 - Follow-ups go where they belong (Priority: P2)

After "I can also add the talk for you", the user types "yes please", and the assistant plans it. If they type "how
would I do it myself?" instead, they get the steps. After a list of meetings, "which of those is earliest?" is
answered from the conversation, with nothing looked up.

**Why this priority**: Conversations are mostly follow-ups; each needs the route the conversation implies.

**Independent Test**: Run the follow-up set (Success Criteria). Each goes to the route its label
says.

**Acceptance Scenarios**:

1. **Given** the assistant just offered a change, **When** the user agrees ("yes", "do it"), **Then** the request
   they agreed to goes to the planner, which shows a plan to confirm.
2. **Given** any earlier exchange, **When** the latest message is a how-to question, **Then** it gets a knowledge
   answer. Data questions and change requests keep their routes.
3. **Given** the planner cannot plan a message (nothing to change, not a change after all, an action it doesn't have,
   changes switched off), **Then** with no plan waiting it gets a knowledge answer instead of "I could not work out
   what to change".
4. **Given** a message answerable from the conversation (a follow-up about the last answer, "summarise that",
   "thanks"), **Then** it gets a chat answer from the conversation, informed by general knowledge (it may explain a
   particle decay the conversation mentions), with nothing looked up or changed.
5. **Given** a plan is waiting, **When** the user sends a plain yes or one of the plan's own choices, **Then** the
   planner takes it with no routing decision at all.

---

### User Story 4 - Admins can run it privately and cheaply (Priority: P3)

An admin of a private instance, with no internet access to OpenRouter, still gets knowledge answers. So does an
admin who hasn't set up Jev.

**Why this priority**: Most Indico instances are private (CERN, universities).

**Independent Test**: With no Jev key set, the knowledge questions still route by the classifier and get answered.
With the guide index present, no question needs the internet beyond the instance's model service.

**Acceptance Scenarios**:

1. **Given** no Jev key, or Jev slower than its time budget, **Then** the classifier routes instead (the same routes,
   chat included), and the answer still comes.
2. **Given** a new plugin release, **Then** the guide copy and its index come with it. The admin runs nothing.

### Edge Cases

- **A question in another language:** the answer follows the question's language; guide citations stay in English.
- **A link the model writes:** if it isn't a page in the user's list, it is removed. So is a guide link to a page
  that doesn't exist. A path with a made-up host is rewritten to this Indico's address.
- **A non-manager asks about a management page:** the answer says only the event's managers can do it. It never
  links a page the user can't open, and doesn't name the managers.
- **A question that is both how-to and data** ("How do I add a talk, and who speaks tomorrow?"): it gets the
  knowledge answer, which suggests asking the data part on its own.
- **The guide describes an older Indico:** the page list decides what exists here; the guide explains how.
- **The model service is down:** the same error message as other questions today. Indico itself is unaffected.

## Requirements *(mandatory)*

### Functional Requirements

**Routing** (each message, in this order; revised 2026-09-30)
- **FR-001**: **The shortcut.** When the last answer offered a change and the message is a plain yes, the planner MUST
  be asked for the offered change, as a new request; an offer is newer than any waiting plan. Otherwise, when a plan
  is waiting and the message is a plain yes or no, or one of the plan's own choices or suggestions (a button, or
  typed), the planner MUST take it: it confirms, cancels or answers the plan. A plain no to an offer turns down the
  offer, not the plan. None of these needs a routing decision. Any other reply goes to Jev with a note of the offer
  and of the waiting plan (FR-006).
- **FR-002**: **One Jev decision.** Otherwise, when a Jev key is set, one call to Jev MUST answer two `choice`
  questions about the latest message: its route (knowledge, change, data, chat, out_of_scope) and, for data, its kind
  (the classifier's 11 data intents). The highest-probability route wins.
  - knowledge → the knowledge answer; chat → the chat answer; out_of_scope → the fixed refusal.
  - data → the NL2SQL pipeline with Jev's intent: the classifier MUST NOT be called, and the SQL generator reads the
    dates and names from the question itself.
  - change → the planner, given the waiting plan if there is one.
- **FR-003**: **The planner's fall-through.** When the planner cannot plan the message (no step, nothing to change,
  not a change after all, an action it doesn't have, changes or that action switched off) and no plan is waiting, the
  message MUST get the knowledge answer. With a plan waiting, the planner's reply stands.
- **FR-004**: **Without Jev.** Without a Jev key, on a timeout, an error, or an answer that isn't one of the routes,
  the classifier MUST route instead, with the same routes (it gains a `chat` category), never in addition to Jev.
  Without Jev's reading of the conversation, the last answer's offer sends the next message to the planner first.
- **FR-005**: The chat MUST never fail because of Jev. An unknown intent is dropped (the classifier then picks it).
- **FR-006**: Jev MUST be sent the latest message plus the last two exchanges, in the format ibis's web gate uses
  (each earlier reply cut to 400 characters), and a note when a plan is waiting or the last answer offered a change.
- **FR-007**: The route criteria and intents MUST be the ones the router probe measured (thread E study), with the
  chat route as decided on 2026-09-30, and a "can you …?" naming a concrete change routed as a change, as the
  classifier routes it. A general "can you create meetings?" stays knowledge.

**What the assistant can do (generated, never hand-written)**
- **FR-008**: For each knowledge question, the assistant MUST build the list of what it can do for this user. The
  list has two parts:
  - **Instance-wide:** the categories where they may create or propose meetings, and whether they manage any
    meeting.
  - **On an event page, also this event:** what it can change here (the user manages it or not; the event is locked
    or not; Teams is available or not).

  It is built from the registered actions, the admin's enabled actions, the installed plugins, and the user's
  permissions. It MUST work with no event page.
- **FR-009**: Each action MUST say whether it is available, for a user and optionally an event or category, and why
  not. It MUST use the same permission rules as the check it makes before it runs. A test MUST assert that for every
  registered action, "not available" implies the check refuses.
- **FR-010**: The list MUST name what the assistant never does itself:
  - register people;
  - take payments;
  - send an email of its own (the reminder emails and Teams invitations its changes cause are shown in the plan, as
    today);
  - change permissions or protection;
  - delete events, other than undoing its own changes;
  - book rooms;
  - review abstracts.

**The pages the user can open**
- **FR-011**: For each knowledge question, the assistant MUST list the pages this user can open, taken from Indico's
  own menus for this user: the event's management menu (when on an event page), the user's profile menu, and the top
  menu. It MUST note whether room booking is enabled.
- **FR-012**: Every link to this Indico in an answer MUST be to a page in that list. Code MUST check this after the
  model answers: remove links that aren't in the list, and rebase paths onto the instance's address.

**Indico's user guide**
- **FR-013**: The plugin MUST ship a copy of the user guide from one pinned commit of `indico/indico-user-docs`. The
  commit is recorded in the package; today's is `e7e0016`.
  - The copy is split by heading, and indexed in a file in the package: no database table, and no change to the
    read-only query role.
- **FR-014**: **The index pins its own embedding model** (`BAAI/bge-small-en-v1.5`, 384 dimensions), whatever the
  plugin's `embedding_model` setting says.
  - The model name and dimensions are recorded with the index, and checked when it loads.
  - If they don't match, or the model can't load, knowledge answers are given without excerpts (from the two lists
    only), and the health check reports it.
- **FR-015**: A documented command MUST rebuild the copy and its index from a given guide commit, for a release.
- **FR-016**: Each knowledge question MUST get the 6 guide excerpts closest to it. A guide link in an answer MUST be a
  page in the copy; others are removed.

**The answer**
- **FR-017**: The knowledge answer MUST be one model call through the plugin's LLM service (ibis). It is given the
  rules, the guide excerpts, the page list and the capability list, in that order.
- **FR-018**: The answer MUST:
  - claim only abilities in the capability list;
  - offer (not plan) a change it can make;
  - give steps and a link to the page;
  - cite the guide pages it used;
  - say plainly when the material doesn't cover the question.
- **FR-019**: A knowledge answer MUST be stored and shown like any other answer: Past Chats, feedback thumbs, and
  across page navigation.
- **FR-020**: Each answer MUST record for auditing its route (knowledge, chat, data, change, refusal); Jev's decision
  (route, intent, confidence, and whether and why it was skipped); whether the shortcut was used; any fallback
  (classifier, planner, or "planner first" when, without Jev, an offer or a waiting plan sent it to the planner and
  the planner took it); and any change the answer offered.

**Settings**
- **FR-021**: New admin settings: the router's Jev key (optional; stored like the other keys, never displayed) and
  its timeout (default 1.5 s), a deadline for the whole call. A secret left empty on the settings form keeps the
  stored one (a password field is never filled in, so saving any other setting would otherwise clear it).

**The chat answer** (revised 2026-09-30)
- **FR-023**: A chat answer MUST be one model call through ibis, given the conversation so far. It may use general
  knowledge to explain what the conversation contains; it MUST NOT look anything up in Indico, make changes, or invent
  facts about the user's events. It may link only to pages already linked in the conversation.

**The test sets**
- **FR-022**: Before the build is judged, the four sets below MUST be added to the eval repository with their labels.
  The success criteria are measured on them.

### Key Entities

- **Capability list**: what the assistant can and can't do for one user, instance-wide and on one event, with
  reasons. Built per question, never stored.
- **Page list**: titles and paths of the pages one user can open, from Indico's menus. Built per question.
- **Guide copy**: the pinned user-guide text, its commit, its excerpt index and the embedding model it was built
  with, shipped in the package.
- **Route record**: the route taken for one answer, the gate's score, whether the gate was skipped, and any offered
  request. Kept with the answer.

## Success Criteria *(mandatory)*

**The four test sets** (from the research; see FR-022). Each question has a user (an admin who manages the event, or
a user who can't manage it or create events), a page, and the expected behaviour.
- **Knowledge set:** 53 questions: how-to questions, about-the-assistant questions, questions the guide doesn't
  cover, and hand-offs.
  - The research's two plain change-request controls are not part of it; they join the routing negatives.
  - 8 of the 53 are labelled as depending on the user's rights.
- **Routing negatives:** 24 = 16 data questions + 8 change requests (the research's 6, plus its 2 controls).
- **Follow-ups:** 24 two-turn cases: 11 knowledge, 13 not.

**Criteria.** Links are scored by code; the rest by an LLM judge checked against hand labels.
- **SC-001**: At least 30 of the 53 knowledge questions fully right, and at least 45 useful (the research reached
  29 and 47).
- **SC-002**: At most 2 of the 53 answers offer or claim something the assistant can't do for that user.
- **SC-003**: No answer links a page the user can't open, or a guide page that doesn't exist.
- **SC-004**: At least 6 of the 8 rights-dependent questions are right.
- **SC-005**: **Routing** (revised 2026-09-30):
  - at least 44 of the 53 knowledge questions get the knowledge answer, or for "Can you [change]?" the planner;
  - none of the 24 routing negatives get the knowledge or chat answer;
  - at least 23 of the 24 follow-ups go to the right route, and at least 15 of 17 chat cases get the chat answer.
  - Measured offline by the router probe (Jev alone, $0.01). The live sweep was not run: Lucas chose to skip it after
    the build (2026-09-30).
- **SC-006**: The existing data-question eval scores no lower than on main.
- **SC-007**: A knowledge answer costs under $0.002 on the default ibis dial, and its median answer time is under
  10 s.

## Assumptions

- The guide is English. Instance-specific guides, such as CERN's own branch, are out of scope.
- "The event's managers" are not named in hand-offs: Indico doesn't always show them to viewers.
- Knowledge answers count against the chat rate limit, like any question.
- Runs of the test sets that call paid models are started only on Lucas's go.
- Jev is called through its own small client, under the constitution's exception for decision models (constitution
  1.1.0, Principle III). Every other model call keeps the Instructor abstraction.

## Out of Scope

- Indico's admin documentation (docs.getindico.io): later.
- Web search, MCP documentation servers, and click-through guided tours.
- Connectors such as GitHub (thread D). When they come, they add lines to the same capability list.
