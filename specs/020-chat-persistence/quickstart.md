# Quickstart: Persistent assistant with past chats (020), local

This uses the local stack of the `indico-dev-server` skill:

- Indico on `http://127.0.0.1:8000` (run with `-h 127.0.0.1`);
- Chainlit on `http://127.0.0.1:8001`;
- the worker with `-Q celery,assistant,assistant_bulk,teams_notes` and `VC_TEAMS_FAKE_GRAPH=1`.

The two origins share a site (127.0.0.1), so the panel's `SameSite=Lax` cookie works in the iframe.

## 1. Upgrade Chainlit and migrate

```bash
cd ~/indico-assistant/plugin/chainlit_app
uv pip install --python .venv/bin/python -r requirements.txt     # chainlit==2.12.0
export INDICO_CONFIG=~/indico-assistant/instance/indico.conf
~/indico-assistant/instance/env/bin/indico db --all-plugins upgrade   # 008: chat_sessions.title
```

Restart Chainlit, then check that `curl -s http://127.0.0.1:8001/auth/config` shows `"requireLogin":true`. The app
sets `CHAINLIT_CUSTOM_AUTH` itself.

## 2. Persistence across pages (US1)

1. Open any event page and open the assistant. The panel docks on the right and the page moves over.
2. Ask "Who are the speakers of this event?", then click an event link in the answer. It opens in the Indico
   page, not in the panel.
3. On the new page the panel is open at the same width, shows both messages, and the page did not jump.
   Focus is on the page: Tab moves through the page first.
4. Ask a slow question and click a link at once. On the next page the question shows, and the answer appears
   when it's ready.
5. Close the panel and navigate: it stays closed. Open it: the same conversation.
6. With a chat-action plan waiting (spec 019), navigate. The card is back and Confirm works once.

## 3. "This event" follows the page (US2)

In one conversation, ask "What is this event about?" on event A, then on event B. The answers are about A,
then B. On B, "move this meeting to 4pm" plans a change to B (if you manage it).

## 4. Past chats (US3, US4)

1. Open the sidebar (☰ in the panel). Your conversations are grouped Today / Yesterday / Previous 7 and 30
   days.
2. Open an older one and continue it. Reload: that one is restored.
3. Search a word from one conversation: only matching ones are listed.
4. Rename one and reload: the name stays. Delete one: it is gone, and if it was open a new chat starts.
5. Log out, log in as another user (for example Makoto, id 6) in the same browser: none of the first
   user's conversations show.

## 5. Feedback and look

1. Thumbs down on an answer, with a comment, then reload: still down. Thumbs up replaces it. Clicking it again
   takes the vote back.
2. The panel is light, like Indico (an event page's dark grey is only the meeting theme's backdrop). The
   header is Indico's blue and the avatar shows your name's initial. Chainlit's sun/moon switches to dark,
   and the choice is kept across pages.
3. Hovering an icon or a conversation shows a small tooltip.

## 6. Tests

```bash
cd ~
INDICO_CONFIG=~/indico-assistant/instance/indico.conf ~/indico-assistant/instance/env/bin/python -m pytest -q \
  --rootdir ~/indico-assistant/plugin ~/indico-assistant/plugin/tests
cd ~/indico-assistant/plugin/chainlit_app && .venv/bin/python -m pytest -q tests   # the data layer, fake Indico
```

The browser checks are puppeteer scripts in `tests/browser/` (see its README), run against the local stack.
Things learned running them:
- **Test runs use up the admin's chat limit** (200 questions a day). Run the scripts as Makoto
  (`WALK_USER=6`), except `walk.mjs`: it drafts a plan, and Makoto can't create events.
- **Scripted mouse moves miss the panel's sidebar drawer:** click and hover by dispatching events in the
  frame instead.
