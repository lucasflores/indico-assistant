"""Integration tests for settings persistence."""

import pytest
from unittest.mock import MagicMock, patch


class TestGlobalSettingsPersistence:
    """Tests for global settings persistence through Indico's plugin system."""

    def test_settings_are_accessible_via_plugin(self):
        """Plugin settings should be accessible via plugin.settings."""
        from indico_assistant.plugin import AssistantPlugin

        # Verify plugin has settings capability
        assert hasattr(AssistantPlugin, "default_settings")
        assert AssistantPlugin.configurable is True

    def test_default_settings_are_applied(self):
        """Default settings should be applied when no custom settings exist."""
        from indico_assistant.default_settings import DEFAULT_SETTINGS

        assert DEFAULT_SETTINGS["enabled"] is True
        assert DEFAULT_SETTINGS["llm_provider"] == "ollama"
        assert DEFAULT_SETTINGS["timeout_seconds"] == 30

    def test_settings_form_is_configured(self):
        """Plugin should have settings_form configured."""
        from indico_assistant.plugin import AssistantPlugin
        from indico_assistant.forms import SettingsForm

        assert AssistantPlugin.settings_form == SettingsForm


class TestEventSettingsPersistence:
    """Tests for per-event settings persistence."""

    def test_event_settings_defaults_exist(self):
        """Event settings defaults should be defined."""
        from indico_assistant.default_settings import EVENT_SETTINGS_DEFAULTS

        assert "enabled" in EVENT_SETTINGS_DEFAULTS
        assert "custom_system_prompt" in EVENT_SETTINGS_DEFAULTS
        assert "allowed_tables" in EVENT_SETTINGS_DEFAULTS

    def test_event_settings_enabled_default_is_none(self):
        """Event enabled setting should default to None (inherit)."""
        from indico_assistant.default_settings import EVENT_SETTINGS_DEFAULTS

        assert EVENT_SETTINGS_DEFAULTS["enabled"] is None

    def test_plugin_has_event_settings_defaults(self):
        """Plugin should have default_event_settings configured."""
        from indico_assistant.plugin import AssistantPlugin

        assert hasattr(AssistantPlugin, "default_event_settings")
        assert AssistantPlugin.default_event_settings["enabled"] is None


class TestSettingsInheritance:
    """Tests for settings inheritance (event → global fallback)."""

    def test_get_effective_setting_with_event_override(self):
        """Should return event setting when it overrides global."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin.__new__(AssistantPlugin)
        plugin.settings = MagicMock()
        plugin.settings.get = MagicMock(return_value=True)
        plugin.event_settings = MagicMock()
        plugin.event_settings.get = MagicMock(return_value=False)

        mock_event = MagicMock()
        result = plugin.get_effective_setting(mock_event, "enabled")

        assert result is False  # Event override takes precedence

    def test_get_effective_setting_inherits_when_event_is_none(self):
        """Should inherit global setting when event setting is None."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin.__new__(AssistantPlugin)
        plugin.settings = MagicMock()
        plugin.settings.get = MagicMock(return_value="global_prompt")
        plugin.event_settings = MagicMock()
        plugin.event_settings.get = MagicMock(return_value=None)

        mock_event = MagicMock()
        result = plugin.get_effective_setting(mock_event, "custom_system_prompt")

        assert result == "global_prompt"  # Falls back to global

    def test_get_effective_setting_without_event(self):
        """Should return global setting when no event context."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin.__new__(AssistantPlugin)
        plugin.settings = MagicMock()
        plugin.settings.get = MagicMock(return_value="global_value")

        result = plugin.get_effective_setting(None, "llm_provider")

        assert result == "global_value"
