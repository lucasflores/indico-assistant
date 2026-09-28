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
