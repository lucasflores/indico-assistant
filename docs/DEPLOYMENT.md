# Deployment Guide: Chat Widget

This guide covers production setup for the Chainlit-based chat widget.

## Prerequisites
- Indico Assistant plugin installed/enabled
- Chainlit server reachable by browsers (HTTPS recommended)
- Shared JWT secret (HS256) configured in both Indico and Chainlit

## Configuration Steps
1) Chainlit
- Set CORS/allowed origins to your Indico domain:
  - `.chainlit/config.toml` → `allow_origins = ["https://your-indico-domain"]`
  - or `CHAINLIT_ALLOW_ORIGINS=https://your-indico-domain`
- Set auth secret: `CHAINLIT_AUTH_SECRET=<shared-secret>`
- (Optional) Persistence: `CHAINLIT_DATABASE_URL=postgresql://...`

2) Indico Assistant Plugin
- Admin → Plugins → Assistant → Settings
  - Chat Widget Enabled: ✓
  - Chainlit Server URL: `https://chainlit.example.com`
  - Chainlit Auth Secret: same as Chainlit
- Restart Indico after changing secrets.

3) Content Security Policy (CSP)
Add (or extend) the following directives for the Chainlit host:
- `script-src`: include the Chainlit origin (for `/copilot/index.js`)
- `connect-src`: include the Chainlit origin (WS/HTTP API)
- `frame-src`: include the Chainlit origin if iframe rendering occurs
- Example: `script-src 'self' https://chainlit.example.com; connect-src 'self' https://chainlit.example.com wss://chainlit.example.com; frame-src 'self' https://chainlit.example.com`

4) No-JS Fallback (FR-032/033)
If you want to show a message when JavaScript is disabled, add to your base template:
```html
<noscript>
  <div class="assistant-nojs-message">Indico Assistant chat requires JavaScript.</div>
</noscript>
```
The widget CSS also hides Chainlit elements unless the page is marked `data-assistant-ready`, so pages without JS will not surface the button.

5) Health Check
- Verify Chainlit reachable: `curl -I https://chainlit.example.com/copilot/index.js`
- Verify Indico exposes widget config: check `window.IndicoAssistant` in browser console on any page.

## Validation
- Run E2E (skipped by default): `pytest tests/e2e -m e2e -vv`
- Manual checks: theme sync (toggle dark mode), keyboard (Tab/Shift+Tab/Escape), screen reader (ARIA labels + live region), error bubble if Chainlit is down.

## Security Notes
- Rotate `CHAINLIT_AUTH_SECRET` periodically; update Indico settings to match.
- Keep CSP in sync when moving Chainlit to new hostnames.
- Service-to-service feedback calls from Chainlit use the configured service token (see app_chnlit.py).
