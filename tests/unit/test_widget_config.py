"""Unit tests for widget configuration.

Tests for get_vars_js() method and widget settings.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestWidgetConfig:
    """widget_config(): per-user config for the uncached /widget/config route."""

    def _config(self, user, **settings):
        from indico_assistant.plugin import AssistantPlugin

        values = {"chat_widget_enabled": True, "chainlit_server_url": "http://chainlit.test",
                  "chainlit_auth_secret": "s3cret", **settings}

        class Plugin(AssistantPlugin):  # settings/logger are class properties that need a loaded plugin
            settings = MagicMock(get=values.get)
            logger = MagicMock()

        return Plugin.__new__(Plugin).widget_config(user)

    def test_anonymous_gets_no_token(self):
        config = self._config(None)
        assert config == {"enabled": True, "chainlitUrl": "http://chainlit.test", "authToken": None, "theme": "auto"}

    def test_logged_in_user_gets_a_token(self):
        user = MagicMock(id=7, full_name="Ada", email="ada@example.test")
        with patch("indico_assistant.services.jwt_service.create_chainlit_token", return_value="tok") as mint:
            config = self._config(user)
        assert config["authToken"] == "tok"
        assert mint.call_args.args[0] is user

    def test_no_secret_no_token(self):
        assert self._config(MagicMock(), chainlit_auth_secret="")["authToken"] is None

    def test_never_feeds_the_shared_global_js(self):
        """Indico renders get_vars_js() into global.js, cached for every visitor. Must stay unoverridden."""
        from indico.core.plugins import IndicoPlugin

        from indico_assistant.plugin import AssistantPlugin

        assert AssistantPlugin.get_vars_js is IndicoPlugin.get_vars_js
        assert AssistantPlugin.inject_vars_js is IndicoPlugin.inject_vars_js


class TestWidgetDefaultSettings:
    """Tests for widget default settings."""

    def test_default_settings_include_widget_settings(self):
        """Default settings should include chat widget configuration."""
        from indico_assistant.default_settings import DEFAULT_SETTINGS

        assert "chat_widget_enabled" in DEFAULT_SETTINGS
        assert "chainlit_server_url" in DEFAULT_SETTINGS
        assert "chainlit_auth_secret" in DEFAULT_SETTINGS

    def test_widget_enabled_by_default(self):
        """Widget should be enabled by default."""
        from indico_assistant.default_settings import DEFAULT_SETTINGS

        assert DEFAULT_SETTINGS["chat_widget_enabled"] is True

    def test_default_chainlit_url(self):
        """Default Chainlit URL should be localhost:8000."""
        from indico_assistant.default_settings import DEFAULT_SETTINGS

        assert DEFAULT_SETTINGS["chainlit_server_url"] == "http://localhost:8000"

    def test_default_auth_secret_is_empty(self):
        """Default auth secret should be empty (must be configured)."""
        from indico_assistant.default_settings import DEFAULT_SETTINGS

        assert DEFAULT_SETTINGS["chainlit_auth_secret"] == ""


class TestWidgetLoading:
    """Page views pay for the widget only when a logged-in user has it enabled, and then one cached file."""

    def _script(self, user, enabled=True, login="9b1e5c0d7a2f4e81"):
        from indico_assistant.plugin import AssistantPlugin

        class Plugin(AssistantPlugin):
            settings = MagicMock(get={"chat_widget_enabled": enabled}.get)

        session = MagicMock(user=user, get={"assistant_login": login}.get if login else {}.get)
        with patch("flask.session", session):
            return Plugin.__new__(Plugin)._render_widget_script()

    def test_anonymous_and_disabled_get_nothing(self):
        assert self._script(None) is None
        assert self._script(MagicMock(), enabled=False) is None

    def test_logged_in_gets_one_deferred_versioned_script(self):
        from indico_assistant.blueprint import widget_script_url

        with patch("indico_assistant.plugin.get_csp_nonce", return_value="N0NCE"):
            html = self._script(MagicMock(id=7))
        assert (f'<script src="{widget_script_url()}" data-user="7" data-login="9b1e5c0d7a2f4e81" '
                f'data-min-width="320" data-default-width="440" data-narrow="768" defer></script>') in html
        assert "?v=" in widget_script_url()  # (above: the widths the inline snippet reserves)

    def test_each_login_sets_a_new_token_for_the_panel(self):
        # the panel opens a new chat when it changes (Lucas, 2026-10-01); Indico's logged_in signal calls this
        from indico_assistant.plugin import LOGIN_KEY, _new_login

        session = {}
        with patch("flask.session", session):
            _new_login(MagicMock())
            first = session[LOGIN_KEY]
            _new_login(MagicMock(), admin_impersonation=True)
        assert len(first) == 16 and session[LOGIN_KEY] != first
        assert 'data-login=""' in self._script(MagicMock(id=7), login=None)  # (a session from before: no token yet)

    def test_the_version_changes_with_the_stylesheet_too(self, tmp_path, monkeypatch):
        # the stylesheet is fetched with the script's ?v=: a CSS-only change must give a new one (review, PR #10)
        from indico_assistant import blueprint

        def version(css):
            (tmp_path / "chat_widget.css").write_text(css)
            blueprint._widget_version.cache_clear()
            return blueprint._widget_version()

        monkeypatch.setattr(blueprint, "_STATIC_CSS", str(tmp_path))
        try:
            assert version("a { color: red }") != version("a { color: blue }")
        finally:
            blueprint._widget_version.cache_clear()  # (the next caller hashes the real files)

    def test_the_panels_space_is_kept_before_the_page_paints(self):
        # spec 020 FR-006a: an open panel's width is reserved by a tiny inline script, allowed by the CSP nonce
        with patch("indico_assistant.plugin.get_csp_nonce", return_value="N0NCE"):
            html = self._script(MagicMock(id=7))
        inline = html.split("</script>")[0]
        assert inline.startswith('<script nonce="N0NCE">')
        assert "indico-assistant:7" in inline and "marginRight" in inline and ".open" in inline
        assert "try" in inline and "catch" in inline  # storage may throw (private mode, blocked site data)
        assert len(inline) < 500

    def test_config_route_needs_a_user_and_is_never_cached(self, app):
        from indico_assistant import blueprint as bp

        with app.test_request_context("/api/assistant/widget/config?event_id=5"), \
                patch("flask.session", MagicMock(user=None)):
            assert bp.widget_config()[1] == 401

        plugin = MagicMock(widget_config=MagicMock(return_value={"authToken": "tok"}))
        user = MagicMock()
        with app.test_request_context("/api/assistant/widget/config?event_id=5"), \
                patch("flask.session", MagicMock(user=user)), \
                patch.object(bp.plugin_engine, "get_plugin", return_value=plugin):
            response = bp.widget_config()
        plugin.widget_config.assert_called_once_with(user, event_id=5)
        assert response.headers["Cache-Control"] == "private, no-store"
