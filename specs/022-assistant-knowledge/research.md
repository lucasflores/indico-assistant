# Assistant knowledge: how the assistant answers "how do I…" and "can you…"

**Research** · 2026-09-29 · a proposal for Lucas to decide · no code yet

## The problem

Users ask "how do I give someone management rights?" and "can you create meetings for me?". Today's assistant
has no route for these questions. On 53 of them:
- 37 were sent to the change planner, which answers "I could not work out what to change";
- the rest were turned into SQL or refused.

None got a good answer.

## The plan

**Knowledge base: Indico's official user guide.**
- The guide is learn.getindico.io, built from the `indico/indico-user-docs` repository: 54 pages, about 28k tokens.
- A copy pinned to one docs commit ships inside the plugin, rebuilt with each release.
- **No web search:** private instances often can't reach the internet, and the guide is small and changes rarely.
- **No MCP:** no Indico docs server exists. The public one (Context7) indexes Indico's code, not its guide.

**Method: retrieval (RAG) from a local index.**
- The guide is split by heading into 163 pieces.
- Each piece is embedded with the model the plugin already uses for document search (bge-small).
- The index is a small file in the package. It needs no database table and no change to the read-only role.
- For each question, the worker takes the 6 closest pieces and puts them in the prompt.

**Two more inputs, generated from code for each question.** The guide is generic and written for Indico 3.2. It
can't know who is asking, or what this instance has switched on:
- **What the assistant can do for this user.** This comes from the actions registry, the admin's settings, and the
  permission check of each action. For example, Makoto can't create events, so the assistant must not offer to.
- **The pages this user can open.** These come from Indico's own menus, built for this user and the event they're
  on. The list includes plugin pages (Teams, meeting notes) and knows that room booking is off here. Every link in
  an answer must come from this list; code checks each one.

**Routing.**
- A `knowledge` category is added to the classifier the chat already calls.
- When the planner finds nothing to change, the question goes to the knowledge answer instead of "I could not work
  out what to change".

**Hand-off.** Changes the assistant already makes keep today's plan-and-confirm flow. It sends the user to the right
page, with a link, for:
- permission and protection changes;
- deleting events;
- emailing people;
- registrations.

## Why, in numbers

55 real questions, asked as an admin and as a user who can't manage or create events. An LLM judge graded every
answer, and code checked every link. Treat the figures as good to about ±10 points; the ranking is solid.

| What the model is given | gpt-4o-mini (today's model) | gpt-5.6-luna (same price tier) | gpt-5.6-sol (strong) |
|---|---|---|---|
| Today's assistant | 0 of 53 | | |
| Guide excerpts only | 9 | | |
| The two generated lists only | 12 | 26 | 32 |
| **Both lists + guide excerpts (the plan)** | 17 | **29** (47 useful) | 33 |
| Both lists + the whole guide | 23 | 27 | 39 |

- **On questions whose answer depends on who is asking,** the guide alone passes 0 of 8. With the lists, 3–6 of 8
  pass.
- **Cost of the plan on gpt-5.6-luna:** about $0.0008 and 3 s a question.
- **Retrieval finds the right guide page** in the top 6 for 26 of 27 questions.
- **Routing:** the added category sends 41 of 53 to the knowledge answer. The 22 ordinary data questions and change
  requests keep their routes. The planner fall-through covers the remaining "Can you do X?".

## Not chosen

- **Web search.** Needs the internet; gets generic or wrong-version answers.
- **Docs over MCP.** No Indico server exists. A hosted one can't reach private instances; a self-hosted one would be
  this same local index behind a protocol.
- **The whole guide in every prompt.** 28k tokens a question. It is better only on the strongest model, and small
  local models can't fit it.
- **Click-through tours** (Pendo/WalkMe style). They break silently when an instance changes its pages.
- **Hosted docs bots** (Kapa, Fin, Mintlify). None runs on-premises.

## Decisions for Lucas

1. **The model.** gpt-4o-mini offers to do things it can't in 11–18 of 53 answers once the guide is in the prompt;
   gpt-5.6-luna does in 2–4. Options: switch the instance's model, or send knowledge answers to another model
   through ibis.
2. **Routing.** Use the classifier category (measured above), or test a Jev gate first? The Jev gate may be better on
   follow-ups like "yes, do it". The test costs under $0.05 and waits for your go.
3. **The admin docs** (docs.getindico.io) for admins' questions: now, or later?
4. **"Can you add a Teams meeting?"** when it can: offer first, or start a plan right away?
5. **The hand-off list above:** agree?

The study behind this (the question set, prototypes, every answer and grade, and the industry survey with sources)
is in Lucas's scratch notes, not in this repo. The question set moves into the eval repo when the eval gets a
"how do I" dimension.
