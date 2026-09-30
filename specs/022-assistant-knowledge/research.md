# Assistant knowledge: how the assistant answers "how do I…" and "can you…"

**Research** · 2026-09-29 · decided by Lucas 2026-09-29 (see the end) · no code yet

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

**Routing: a Jev gate in front of the classifier.**
- Jev (the decision model ibis uses for its web-search gate) is asked whether the latest message is a knowledge
  question. It sees the last two exchanges, in the format ibis's web gate uses.
- Above the cut-off, the message goes to the knowledge answer. Below it, the classifier routes it as today.
- When the planner finds nothing to change, the question goes to the knowledge answer instead of "I could not work
  out what to change". This covers "Can you [do X] for this event?", which both Jev and the classifier read as a
  request.
- "Can you do X?", when the assistant can, gets an offer first ("Yes, shall I?"). A yes then goes to the planner.

**Model: through ibis only.** Every call, the knowledge answer included, goes through the ibis API. The local
instance was switched to the Balanced dial on 2026-09-29.

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

## Routing, measured (Jev vs the classifier)

Two sets were used:
- **Single questions:** the 55 questions above and 22 ordinary ones. The ordinary ones are data questions and change
  requests, some phrased like "How many…" or "Can you move it to 3pm?".
- **Follow-up turns:** 24 cases, where the right route depends on the conversation. Examples: "yes please" after an
  offer, "how would I do it myself?", "who uploaded them?".

| Router | Knowledge questions caught (53) | Data questions and changes wrongly caught (24) | Follow-ups right (24) |
|---|---|---|---|
| Classifier with a knowledge category | 41 | 0 | 20 |
| Classifier, also shown the conversation | | | 20 |
| Jev, message only | 44 | 0 | 23 |
| **Jev, with the conversation** | 44 | 0 | **23** |

- The Jev rows use a cut-off of 0.20, fitted on the single questions. The follow-ups were not used to fit it.
- Jev's scores separate the two sets almost perfectly: AUC 0.97 on single questions.
- At this cut-off, the conversation doesn't change Jev's follow-up score. It does give more room: AUC 1.00 against
  0.98 without it. At a looser cut-off (0.08) it was 24 of 24 against 19. Keep it, as in ibis's web gate.
- A decision costs $0.000015 and takes about half a second.
- As in the ibis web-gate study, the cut-off must be refitted on real Indico traffic before it is trusted.

## Decided (Lucas, 2026-09-29)

1. **The model:** everything goes through the ibis API; the instance now uses the Balanced dial. Open: ibis has no
   route for Jev yet. The only client is `JevGate` in ibis-routing, which calls OpenRouter's decisions endpoint
   directly. So the gate needs an ibis endpoint first.
2. **Routing:** tested Jev first. It beats the classifier on single questions (44 vs 41) and on follow-ups (23 vs 20)
   (above), so it becomes the gate.
3. **The admin docs:** later.
4. **"Can you add a Teams meeting?"** when it can: offer first.
5. **The hand-off list:** agreed.

The study behind this (the question set, prototypes, every answer and grade, and the industry survey with sources)
is in Lucas's scratch notes, not in this repo. The question set moves into the eval repo when the eval gets a
"how do I" dimension.
