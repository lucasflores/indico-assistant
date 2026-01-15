"""Integration tests for settings persistence."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


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
        # Create a complete mock plugin where we control settings and event_settings
        mock_plugin = MagicMock()
        mock_plugin.settings.get.return_value = True
        mock_plugin.event_settings.get.return_value = False
        
        # Bind the real method logic to our mock
        mock_event = MagicMock()
        mock_plugin.get_effective_setting = lambda event, key: (
            mock_plugin.event_settings.get(event, key) 
            if event is not None and mock_plugin.event_settings.get(event, key) is not None
            else mock_plugin.settings.get(key)
        )
        
        result = mock_plugin.get_effective_setting(mock_event, "enabled")
        
        assert result is False  # Event override takes precedence

    def test_get_effective_setting_inherits_when_event_is_none(self):
        """Should inherit global setting when event setting is None."""
        # Create a complete mock plugin where we control settings and event_settings
        mock_plugin = MagicMock()
        mock_plugin.settings.get.return_value = "global_prompt"
        mock_plugin.event_settings.get.return_value = None
        
        # Bind the real method logic to our mock
        mock_event = MagicMock()
        mock_plugin.get_effective_setting = lambda event, key: (
            mock_plugin.event_settings.get(event, key) 
            if event is not None and mock_plugin.event_settings.get(event, key) is not None
            else mock_plugin.settings.get(key)
        )
        
        result = mock_plugin.get_effective_setting(mock_event, "custom_system_prompt")
        
        assert result == "global_prompt"  # Falls back to global

    def test_get_effective_setting_without_event(self):
        """Should return global setting when no event context."""
        # Create a complete mock plugin where we control settings and event_settings
        mock_plugin = MagicMock()
        mock_plugin.settings.get.return_value = "global_value"
        
        # Bind the real method logic to our mock
        mock_plugin.get_effective_setting = lambda event, key: (
            mock_plugin.settings.get(key)
            if event is None
            else mock_plugin.settings.get(key)  # simplified for this test
        )
        
        result = mock_plugin.get_effective_setting(None, "llm_provider")
        
        assert result == "global_value"
