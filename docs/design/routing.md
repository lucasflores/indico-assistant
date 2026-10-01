# Routing: where connector questions go

**The plan:**
- Connectors such as GitHub become **one more route** in the router that spec 022 built.
- Jev's route question gains a sixth choice, `connector`. It appears only when an admin has turned a connector on.
- A message on that route goes to a small **tool loop** over the services the user has connected.
- The loop calls the model through `LLMService.generate`, as every other route does. Each step returns a validated
  "call this tool" or "answer" object.
- So every provider keeps working, and the constitution needs no exception.
- **Cost:** a typical connector question takes 2 model calls (pick a tool, then answer). That is about what the data
  route takes today: about 10–16 s and $0.002–0.004 on ibis Balanced.

## How a message is routed today (spec 022, main `c4bf9dd`)

1. **A plain reply to a waiting plan** ("yes", "no", or one of the plan's choices) goes straight to the planner.
2. **Otherwise, one Jev call** (`services/knowledge/gate.py`) picks the route:
   - **data:** NL2SQL, which includes document search;
   - **change:** the plan-and-confirm flow of spec 019;
   - **knowledge:** how Indico works, and what the assistant can do;
   - **chat:** an answer from the conversation itself;
   - **out_of_scope:** a fixed refusal.

   The same call also gives the kind of data question.
3. **Without Jev** (no key, too slow, or an error), the LLM classifier routes instead.
4. **When the planner cannot plan a change**, the message gets the knowledge answer.

Issue reports (spec 021) are not a route: the user files one with the form, opened from "Report a problem" or the
panel's flag button. Today "can I report an issue?" gets the chat answer, which files nothing. Whether to send that
question to the form is Lucas's call, still open; this note doesn't change it.

Three of the handoff's four routes, data, changes and knowledge, already exist. Connectors are the one left. Today a
GitHub question goes to data, where it becomes SQL, or gets the out-of-scope refusal.

## Options

| | Option | For | Against |
|---|---|---|---|
| **A** | **One `connector` route in Jev**; the loop picks the service and the tool | The route question stays fixed as connectors are added; same cost as today | The loop needs a model good enough to pick tools |
| B | One route per service (`github`, `gitlab`, …) | Jev does the service pick | The route question changes, and must be re-measured, with every connector; no gain while one service exists |
| C | A tool-calling router: every route is a tool | Most general; mixed questions come for free | Replaces the Jev router Lucas chose on 2026-09-30; every message needs a tool-capable model; Jev's measured routing is lost |
| D | Chainlit's own MCP client (`features.mcp`) | Already in Chainlit 2.12 | Answers are made in the Indico worker. A client in Chainlit bypasses Indico's permissions, chat history and route records. Not taken without Lucas |

**Recommendation: A.**

## The recommended design

**The route:**
- **When it is offered:** `connector` is a Jev choice only while an admin has turned on at least one connector. Its
  criterion names those services, e.g. "a question about the user's own GitHub: their pull requests, reviews,
  issues, repositories".
- **Without Jev:** the classifier gains a `connector` intent under the same condition.
- **A user who hasn't connected GitHub** still gets the route. The answer is a fixed reply with a link to "Connect
  GitHub" on their profile, not a refusal and not SQL.
- **The knowledge route learns about connectors.** The capability list gains "read your GitHub" and says whether
  this user is connected. So "how do I connect GitHub?" gets the knowledge answer, with the link.

**The tool loop:**
- **Each step is one `generate` call.** It returns a validated `Step`: either one tool and its arguments, or the
  answer.
  - On `openai` and on ibis in `tools` mode, instructor sends that schema as a function call anyway.
  - On `ollama` and `huggingface` it is JSON.
  - So no provider loses the route, and no fallback path is needed.
- **Why not native tool calls:** they would need a raw client next to instructor. The constitution says
  "everything that generates text stays under the abstraction".
- **The ceiling:** one tool per step, with no parallel calls. A small local model may pick tools badly; the eval
  measures that.
- **Bounds:** at most 4 steps and 60 s of wall time (the worker's soft limit is 120 s). The loop also stops on a
  repeated identical call, and cuts each tool result to 4,000 characters.
  - These follow ibis-routing's `ToolLoopGenerator` (3 steps, 90 s, 2 repeats, 4,000 characters). The plugin copies
    the bounds, not the library.
- **What the loop sees:**
  - the same chat history as the other routes;
  - the read tools of the user's connected services;
  - each tool result, marked as untrusted data.

  It never sees Indico data in v1.
- **The route record** gains the tool calls: their names, how long each took, and whether it succeeded. No
  arguments or results are kept, since those can hold private repo text.

**Follow-ups and mixed questions:**
- **Follow-ups:** Jev already reads the last two exchanges.
  - "Which of those is oldest?" can be answered from the reply, so it goes to chat.
  - "What did the reviewer say on the second one?" goes back to `connector`.
  - The eval checks both.
- **Mixed questions** ("my PRs about this event's talks") are out of v1. The way to them later is to give the loop
  Indico's read tools. That is a step toward option C, to be decided with evidence then.

## Cost per question

| Route | Model calls | Time | Cost (ibis Balanced) |
|---|---|---|---|
| data, measured (thread E data eval, 30 questions) | 1.9 | 14.5 s mean | $0.003 |
| connector, typical: Jev, then pick a tool, then answer | 2 | ~10–16 s | ~$0.002–0.004 |
| connector, worst case: 4 steps | 4 | ≤ 60 s (bound) | ~$0.008 |

- **Jev's cost doesn't change:** it is one call per message whatever the routes (~$0.00004, under 1.5 s).
- **A GitHub call takes 0.4–0.7 s.** That was measured on 2026-09-30 with 9 calls: my open pull requests, reviews
  waiting on me, and issues assigned to me. The model calls dominate.

## What it changes

- **The router:** one more Jev choice in `gate.py`, one more classifier intent, and one more branch in
  `ChatService.answer`.
- **New code:** `services/connectors/`, holding the loop, the GitHub tools and the token store. Their design is the
  connector spec's job.
- **Re-measuring:**
  - the router probe with the sixth choice (~$0.006);
  - a new routing set of connector questions and their negatives;
  - the existing 24 routing negatives must stay at 24 out of 24.

## For Lucas to agree before the spec

1. One `connector` route (option A), rather than one route per service.
2. The loop runs as structured steps under the abstraction, rather than native tool calls with a constitution
   exception.
3. No Indico data in the connector loop in v1.
