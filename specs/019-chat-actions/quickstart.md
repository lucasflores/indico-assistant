# Quickstart: Chat actions (019), local

This uses the local stack of the `indico-dev-server` skill: Indico web, Chainlit, and a Celery worker with
`-Q celery,assistant,assistant_bulk,teams_notes`. vc_teams runs in fake-Graph mode (`VC_TEAMS_FAKE_GRAPH=1`,
with `DEBUG = True` in `indico.conf`).

Learned while building it:

- **Run Indico with `indico run -h 127.0.0.1`,** matching `BASE_URL` and Chainlit. With `-h localhost`, the
  widget's session cookie goes to the wrong site and the chat shows "Could not reach the server".
- **Keep `zoom_bot` out of `PLUGINS`.** Its signal handler commits and rolls back the session mid-request,
  which breaks the executor's single transaction.
- **Restart the worker after changing plugin code.** Plans are made and carried out there, not in `indico run`.

## 1. Migrate and enable

```bash
export INDICO_CONFIG=~/indico-assistant/instance/indico.conf
~/indico-assistant/instance/env/bin/indico db --all-plugins upgrade     # adds plugin_assistant.action_plans (007)
```

In **Administration → Plugins → Assistant**, tick **Enable chat actions**. The default is off. Leave every action
allowed.

The testbed needs a category the admin can create in; any category works for the admin. To try `propose_event`:

1. enable unlisted events (**Administration → Categories → Unlisted events**);
2. set a category's event creation to **Moderated**;
3. log in as a user who is not a manager.

## 2. Try the example (US1)

In the chat widget on any Indico page:

> Create a Teams meeting for today at 2pm with Makoto, add both of us as contributors with 20 min slots.

Expected:

1. A plan card:
   - the meeting title, today 14:00–14:40 in your timezone;
   - "Makoto" resolved, or a question if several or none match. Create a test user named Makoto first, since the
     testbed has only the admin;
   - a category question listing your categories, with one suggested;
   - two 20-minute contributions, a reminder, and a Teams room with the invite side effects.
2. Pick the category. The revised plan now shows **Confirm**.
3. Confirm. Within about 15 s the reply links to the new event.
4. Check in Indico's own UI:
   - the timetable has both contributions, with speakers;
   - **Videoconference** shows the Teams room;
   - **Reminders** shows the reminder;
   - **Logs** attributes every entry to you.

## 3. Try the safety paths (US2)

- Cancel a plan: nothing appears in Indico, and the fake Graph state
  (`$CACHE_DIR/vc_teams_fake_graph.json`) gets no meeting.
- Double-click **Confirm**: one event is created.
- "make it 30 minutes" before confirming: the plan is revised, and the old card's Confirm returns "no longer
  valid".
- Wait 30 minutes: Confirm returns "expired".

## 4. Try the rest (US3–US9)

Each of these goes through the same plan and confirm steps:

- **Categories (US3).** Leave the category out: the plan asks, with your most used categories and the
  closest one by topic first. A partial name ("Nothing") is asked about, not guessed.
- **People (US4).** A name matching several users gets a choice. An unknown person with an email becomes a
  guest speaker. Emails you did not type are never used.
- **Changes (US6).** "Move it to 3pm", "rename the Q4 review", "make Makoto's talk 30 minutes". "It" means the
  meeting this chat created, or the one whose page you are on.
- **Suggestions (US5).** After a similar meeting exists ("Q3 budget review"), "Set up the Q4 budget review"
  offers its material, attendees and length, each with its source. "add suggestion s1" applies one.
- **Free times (US8).** Leave the time out ("30 minutes with Makoto next week"): the plan offers three free
  slots.
- **Files (US9).** Drop a PDF in the chat: "attach this to the meeting" or "to my talk". Unsupported
  types and files over 25 MB are refused before any plan is made.
- **Undo (US7).** "Undo that" removes what your last plan created, within 24 hours, unless someone changed it
  since.

## 5. Eval and latency

```bash
cd ~/indico-assistant/eval   # branch 019-actions-eval
INDICO_CONFIG=~/indico-assistant/instance/indico.conf \
  ~/indico-assistant/instance/env/bin/python scripts/actions_eval/run.py
```

This runs 50 requests through the real planner and model, each rolled back. The first full run
(gpt-4o-mini, 2026-09-27) scored:

- 98 % intended plan or the right question (target ≥ 90 %);
- 0 % unasked objects (target 0 %);
- plan display p50 1.43 s, max 6.1 s (target ≤ 10 s).

Carrying out a four-step plan (event, talk, reminder, Teams room) through the worker took p50 0.11 s over 10
runs with fake Graph (target ≤ 15 s). The real Graph adds its own round trips.

## 6. Tests

```bash
cd ~
INDICO_CONFIG=~/indico-assistant/instance/indico.conf ~/indico-assistant/instance/env/bin/python -m pytest -q \
  --rootdir ~/indico-assistant/plugin \
  ~/indico-assistant/plugin/tests/unit/services/actions \
  ~/indico-assistant/plugin/tests/integration/actions
```

The integration tests cover:

- parity per action;
- zero writes without confirmation;
- rollback with Graph faults injected;
- `acting_as` with request memoization on.

They build all data with Indico fixtures on the test database; the local database is never touched.
