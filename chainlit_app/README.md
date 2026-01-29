# Chainlit backend (Indico Assistant widget)

This is a minimal Chainlit app used by the Indico Assistant plugin to serve the Copilot widget.

## Run locally

```bash
cd /Users/lucasflores/dev2/indico/plugins_lucas/indico_assistant_plugin/chainlit_app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export CHAINLIT_AUTH_SECRET=<shared-hex-secret>  # must match Indico plugin setting
export INDICO_API_URL=http://127.0.0.1:8000  # base URL for Indico API
chainlit run app_chnlit.py --host 127.0.0.1 --port 8001
```

## Configure CORS

The bundled `.chainlit/config.toml` allows `http://127.0.0.1:8000` (Indico dev). Adjust `allow_origins` if your Indico host differs.

## Plugin wiring

In Indico Admin → Plugins → Assistant set:
- Chainlit Server URL: `http://127.0.0.1:8001`
- Chainlit Auth Secret: same value as `CHAINLIT_AUTH_SECRET`

## Notes

- Auth: JWT from the plugin is validated in `app_chnlit.py` via `header_auth_callback`.
- Handler: `on_message` forwards messages to `/api/assistant/chat` on the Indico server.

## Customization

### Logos and Branding

The widget uses Indico branding via the following files in `public/`:

| File | Purpose |
|------|---------|
| `logo_light.png` | Header logo (light mode) |
| `logo_dark.png` | Header logo (dark mode) |
| `favicon.png` | Browser favicon + widget launcher button |
| `avatars/assistant.png` | Avatar shown next to assistant messages |

To customize:
1. Replace the PNG files with your own branding (maintain similar dimensions)
2. Clear browser cache to see changes
3. Chainlit auto-detects `logo_light.png` and `logo_dark.png` by filename

### Theme

Edit `public/theme.json` to customize colors and fonts. Uses Shadcn/Radix CSS variable format (HSL values).

### Custom CSS

Additional styling overrides in `public/widget.css`. Referenced in `.chainlit/config.toml`.

## Loading Animation (Feature 017)

The chat widget displays a loading animation when processing user messages:

**Behavior**:
- Loading indicator appears immediately when you send a message (<100ms)
- Animation persists while the assistant generates a response
- Loading is replaced with the actual response when ready
- Each message has independent loading state (supports rapid consecutive messages)

**Technical Details**:
- Uses Chainlit's native `cl.Message(content="").send()` → `msg.update()` pattern
- No custom CSS needed - Chainlit provides default three-dot pulsing animation
- Automatically respects theme (light/dark) and accessibility settings (reduced motion)
- All error states (network, auth, server) replace loading with error message (no orphaned loaders)

**Troubleshooting**:
- **Loading never appears**: Check that Chainlit version is 2.9.5 (`pip show chainlit`)
- **Loading doesn't disappear**: Check browser console for JavaScript errors, verify Indico API is reachable
- **Multiple messages interfere**: This should not happen - each message has isolated state. Report as bug if observed.

