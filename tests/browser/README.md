# Browser tests (spec 020)

The panel walk runs a real Chrome against the **local** stack (Indico on 127.0.0.1:8000, Chainlit on
127.0.0.1:8001, the worker). It is dev tooling only: Node is never a plugin dependency.

```bash
cd tests/browser
npm install                 # puppeteer; its Chromium download is not needed
node walk.mjs               # uses the installed Google Chrome (override with CHROME_PATH)
```

`mint_session.py` logs the walk in without a password: it saves an Indico session for a user id through
Indico's own session interface. It needs the instance config and cache, so it only works on a dev machine.
Over plain HTTP, Indico's session cookie is named `indico_session_http`.

Checks, each against the running stack:

| Script | What |
|---|---|
| `node walk.mjs` | US1: 10-page walk, restore, focus, links, Esc, width (SC-001, SC-002, SC-004) |
| `node sc003.mjs` | US2: "this event" / "this meeting" follow the page, 10 alternations (SC-003) |
| `WALK_USER=6 node us4.mjs` | US4: a new conversation is listed, rename kept after a reload, delete the open one, stale id |
| `WALK_USER=6 node hover.mjs` | Tooltips in the panel stay tooltip-sized (the Copilot-era widget.css blew them up to a blank 85vh box) |
| `WALK_USER=6 node feedback.mjs` | Thumbs: a vote with a comment is kept after a reload, switched, taken back |
| `WALK_USER=6 node tabs.mjs` | Two tabs keep their own conversation; a new tab starts on the last one |
| `WALK_USER=6 node login.mjs` | A new login starts on a new chat; within a login, the open conversation is kept. Asks nothing: it reopens one of the user's conversations |
| `WALK_USER=6 RUNS=10 node reports.mjs` | Spec 021: reports from an offer and from ⚑ listed on the profile page (SC-001); offers after thumbs down and under out-of-scope answers, a double click is one report (SC-002). Resets user 6's report and chat limits in the dev Redis, and deletes the reports it made |
| `node sidebar.mjs` | US3: Past Chats list, groups, paging, search, open, new chat (SC-006), two users (SC-005); seed first with `python seed_sc006.py`, then `python seed_sc006.py delete` |

Run the Python helpers with the Indico env and `INDICO_CONFIG` set.

Each script takes `WALK_USER=<id>` to run as another user (the chat limit is 200 questions a day per user). The walk
drafts a plan, so it needs a user who can create events (Makoto, user 6, cannot).
