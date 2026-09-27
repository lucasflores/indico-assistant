"""Unit tests for widget configuration.

Tests for get_vars_js() method and widget settings.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestWidgetConfig:
    """widget_config(): per-user config for the uncached /widget/config.js route."""

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
