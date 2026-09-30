# Deployment Guide: Chat Panel

The assistant is Chainlit's full app (Chainlit 2.12.0) in a panel docked to the right of every Indico page. The panel
comes back open, on the same conversation, after every navigation, and its Past Chats sidebar lists the user's
conversations. Conversations live in Indico's database: Chainlit keeps none of its own (spec 020).

## Prerequisites
- The Indico Assistant plugin installed and enabled, with its migrations applied: `indico db --all-plugins upgrade`
  (migration 008 adds conversation titles).
- A Celery worker consuming the assistant's queues: `indico celery worker -Q celery,assistant,assistant_bulk,teams_notes`.
- A Chainlit server reachable by browsers over HTTPS, **on the same site as Indico** (see "Hosting" below).
- One shared HS256 secret, configured in both Indico and Chainlit.

## Hosting: Chainlit on the same site as Indico
The panel signs in by setting Chainlit's session cookie inside the panel's frame. Browsers send a frame's
cookies only when the frame is on the same *site* as the page, meaning the same registrable domain. So:

- **Recommended:** Chainlit on a subdomain of Indico's domain. For example, Indico at `indico.example.org` and
  Chainlit at `assistant.example.org`. The default `SameSite=Lax` cookie works.
- **Otherwise:** set `CHAINLIT_COOKIE_SAMESITE=none` on the Chainlit server, over HTTPS. Browsers that block
  third-party cookies (Safari, and Chrome for some users) will still refuse it, and the panel will then fail to
  sign in. Treat this as a fallback only.

## Configuration

### 1. Chainlit (`chainlit_app/`)
- `pip install -r requirements.txt` (pins `chainlit==2.12.0`).
- `CHAINLIT_AUTH_SECRET=<shared secret>`
- `INDICO_API_URL=<Indico's URL as the Chainlit server reaches it>` (in the environment or `chainlit_app/.env`).
- `INDICO_ORIGIN=https://indico.example.org`: only when `INDICO_API_URL` is an internal address. The Chainlit
  server allows framing only by `'self'` and this origin (`frame-ancestors`), and it defaults to
  `INDICO_API_URL`'s origin.
- `.chainlit/config.toml` → `allow_origins = ["https://indico.example.org"]`
- Login is always required: the app sets `CHAINLIT_CUSTOM_AUTH=true` itself. Without it, Chainlit would accept
  websockets with no session. There's nothing to configure; don't unset it.
- No `CHAINLIT_DATABASE_URL`: the data layer reads and writes conversations through Indico's API, as the user.

### 2. Indico Assistant plugin
- Admin → Plugins → Assistant → Settings:
  - Chat Widget Enabled: ✓
  - Chainlit Server URL: `https://assistant.example.org`
  - Chainlit Auth Secret: the same as Chainlit's
- Restart Indico after changing the secret.
- Knowledge answers (spec 022): the user-guide copy ships in the plugin. Searching it needs the embedding model
  `BAAI/bge-small-en-v1.5` in the worker's Hugging Face cache, the same model document search uses. The worker
  downloads it on first use; on an instance without internet access, pre-download it (for example
  `python -c "from sentence_transformers import SentenceTransformer as S; S('BAAI/bge-small-en-v1.5')"` where there
  is access, then copy the cache, or set `HF_HOME`). Without it, knowledge answers come from the capability and page
  lists alone, and the worker's log says "guide copy unavailable" (the health check reads only the copy's files).
- Optional: **Router key (Jev)**, an OpenRouter key. The Celery worker then needs outbound HTTPS to `openrouter.ai`
  (the decisions endpoint). Without the key, or when it is unreachable, the classifier routes.
- For a release, rebuild the guide copy from a pinned commit: `indico assistant guide-build --commit <sha>`
  (needs GitHub access at build time only), and commit `indico_assistant/knowledge_guide/`.

### 3. Content Security Policy
- Indico must allow the panel's frame: `frame-src 'self' https://assistant.example.org`.
- With Indico's `CSP_ENABLED`, the panel's inline `<head>` snippet carries Indico's nonce. Nothing else is needed.
- The page loads no script from Chainlit and makes no requests to it. Only the frame talks to Chainlit.

## Health check
- `curl https://assistant.example.org/auth/config` shows `"requireLogin":true`.
- Logged in to Indico, open any event page. The Assistant tab (on the right edge) opens the panel, and the panel
  comes back open on the next page.

## Validation
- Browser checks (local stack, installed Chrome): see `tests/browser/README.md`. `walk.mjs` covers navigation
  and restore, `sidebar.mjs` Past Chats, `us4.mjs` rename and delete, `feedback.mjs` the thumbs.
- The plugin suite: `pytest tests`. Chainlit's own tests: `cd chainlit_app && .venv/bin/python -m pytest`.

## Security notes
- The page hands the frame a fresh Indico token by `postMessage`, and only to the Chainlit origin. The token is
  never put in a URL, a log or `localStorage`.
- Every conversation read or write goes to Indico as the signed-in user. Indico returns someone else's
  conversation to no one.
- Rotate `CHAINLIT_AUTH_SECRET` periodically, updating Indico's setting to match.
