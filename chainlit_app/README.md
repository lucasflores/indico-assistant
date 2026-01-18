# Chainlit backend (Indico Assistant widget)

This is a minimal Chainlit app used by the Indico Assistant plugin to serve the Copilot widget.

## Run locally

```bash
cd /Users/lucasflores/dev2/indico/plugins_lucas/indico_assistant_plugin/chainlit_app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export CHAINLIT_AUTH_SECRET=<shared-hex-secret>  # must match Indico plugin setting
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
- Handler: `on_message` currently echoes input; replace with real assistant logic when ready.

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
