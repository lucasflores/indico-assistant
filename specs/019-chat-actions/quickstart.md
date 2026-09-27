# Quickstart: Chat actions (019), local

This uses the local stack of the `indico-dev-server` skill: Indico web, Chainlit, and a Celery worker with
`-Q celery,assistant,assistant_bulk,teams_notes`. vc_teams runs in fake-Graph mode (`VC_TEAMS_FAKE_GRAPH=1`,
with `DEBUG = True` in `indico.conf`).

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

## 4. Tests

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
