"""Unit tests for widget configuration.

Tests for get_vars_js() method and widget settings.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestWidgetConfig:
    """Tests for widget configuration via get_vars_js."""

    def test_returns_enabled_setting(self):
        """Should return enabled setting from plugin settings."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin(None, None)
        plugin._settings = {"chat_widget_enabled": True, "chainlit_server_url": "http://localhost:8000"}

        with patch("indico_assistant.plugin.current_user", None):
            config = plugin.get_vars_js()

        assert config["enabled"] is True

    def test_returns_chainlit_url(self):
        """Should return Chainlit server URL from settings."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin(None, None)
        plugin._settings = {
            "chat_widget_enabled": True,
            "chainlit_server_url": "http://custom-chainlit:9000",
        }

        with patch("indico_assistant.plugin.current_user", None):
            config = plugin.get_vars_js()

        assert config["chainlitUrl"] == "http://custom-chainlit:9000"

    def test_returns_null_auth_token_when_not_authenticated(self):
        """Should return null authToken when user is not authenticated."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin(None, None)
        plugin._settings = {"chat_widget_enabled": True, "chainlit_server_url": "http://localhost:8000"}

        mock_user = MagicMock()
        mock_user.is_authenticated = False

        with patch("indico_assistant.plugin.current_user", mock_user):
            config = plugin.get_vars_js()

        assert config["authToken"] is None

    def test_returns_auth_token_when_authenticated(self):
        """Should return JWT authToken when user is authenticated."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin(None, None)
        plugin._settings = {
            "chat_widget_enabled": True,
            "chainlit_server_url": "http://localhost:8000",
            "chainlit_auth_secret": "test-secret",
        }

        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 123
        mock_user.full_name = "Test User"
        mock_user.email = "test@example.com"

        with patch("indico_assistant.plugin.current_user", mock_user):
            config = plugin.get_vars_js()

        assert config["authToken"] is not None
        assert len(config["authToken"]) > 0

    def test_returns_null_auth_token_when_no_secret(self):
        """Should return null authToken when secret is not configured."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin(None, None)
        plugin._settings = {
            "chat_widget_enabled": True,
            "chainlit_server_url": "http://localhost:8000",
            "chainlit_auth_secret": "",  # Empty secret
        }

        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 456
        mock_user.full_name = "No Secret User"
        mock_user.email = "nosecret@example.com"

        with patch("indico_assistant.plugin.current_user", mock_user):
            config = plugin.get_vars_js()

        assert config["authToken"] is None

    def test_returns_auto_theme_by_default(self):
        """Should return 'auto' theme by default."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin(None, None)
        plugin._settings = {"chat_widget_enabled": True, "chainlit_server_url": "http://localhost:8000"}

        with patch("indico_assistant.plugin.current_user", None):
            config = plugin.get_vars_js()

        assert config["theme"] == "auto"

    def test_disabled_when_setting_is_false(self):
        """Should return enabled=False when widget is disabled."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin(None, None)
        plugin._settings = {"chat_widget_enabled": False, "chainlit_server_url": "http://localhost:8000"}

        with patch("indico_assistant.plugin.current_user", None):
            config = plugin.get_vars_js()

        assert config["enabled"] is False


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
