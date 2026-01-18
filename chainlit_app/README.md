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
