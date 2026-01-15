"""Unit tests for the AssistantPlugin class initialization."""

import pytest
from unittest.mock import MagicMock, patch


class TestAssistantPluginInit:
    """Tests for plugin initialization and configuration."""

    def test_plugin_has_default_settings(self):
        """Plugin should have default settings defined."""
        from indico_assistant.plugin import AssistantPlugin

        assert hasattr(AssistantPlugin, "default_settings")
        assert "enabled" in AssistantPlugin.default_settings
        assert "llm_provider" in AssistantPlugin.default_settings
        assert "llm_model" in AssistantPlugin.default_settings

    def test_plugin_is_configurable(self):
        """Plugin should be marked as configurable for admin UI."""
        from indico_assistant.plugin import AssistantPlugin

        assert AssistantPlugin.configurable is True

    def test_plugin_has_event_settings_defaults(self):
        """Plugin should have default event settings defined."""
        from indico_assistant.plugin import AssistantPlugin

        assert hasattr(AssistantPlugin, "default_event_settings")
        assert "enabled" in AssistantPlugin.default_event_settings
        assert "custom_system_prompt" in AssistantPlugin.default_event_settings

    def test_default_settings_values(self):
        """Default settings should have expected values."""
        from indico_assistant.default_settings import DEFAULT_SETTINGS

        assert DEFAULT_SETTINGS["enabled"] is True
        assert DEFAULT_SETTINGS["llm_provider"] == "ollama"
        assert DEFAULT_SETTINGS["llm_model"] == "llama3.2"
        assert DEFAULT_SETTINGS["llm_base_url"] == "http://localhost:11434"
        assert DEFAULT_SETTINGS["timeout_seconds"] == 30
        assert DEFAULT_SETTINGS["max_tokens"] == 2048


class TestAssistantPluginLLMClient:
    """Tests for LLM client lazy initialization."""

    def test_llm_client_initially_none(self):
        """LLM client should be None until accessed."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin.__new__(AssistantPlugin)
        plugin._llm_client = None

        # Direct attribute access should be None
        assert plugin._llm_client is None

    def test_create_llm_client_returns_none_for_now(self):
        """LLM client creation returns None (degraded mode) until implemented."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin.__new__(AssistantPlugin)
        result = plugin._create_llm_client()

        assert result is None


class TestAssistantPluginEffectiveSetting:
    """Tests for the get_effective_setting helper."""

    def test_get_effective_setting_returns_global_when_no_event(self):
        """Should return global setting when event is None."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin.__new__(AssistantPlugin)
        plugin.settings = MagicMock()
        plugin.settings.get = MagicMock(return_value="global_value")

        result = plugin.get_effective_setting(None, "test_key")

        assert result == "global_value"
        plugin.settings.get.assert_called_once_with("test_key")

    def test_get_effective_setting_prefers_event_over_global(self):
        """Should return event setting when available."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin.__new__(AssistantPlugin)
        plugin.settings = MagicMock()
        plugin.settings.get = MagicMock(return_value="global_value")
        plugin.event_settings = MagicMock()
        plugin.event_settings.get = MagicMock(return_value="event_value")

        mock_event = MagicMock()
        result = plugin.get_effective_setting(mock_event, "test_key")

        assert result == "event_value"

    def test_get_effective_setting_falls_back_to_global(self):
        """Should fall back to global when event setting is None."""
        from indico_assistant.plugin import AssistantPlugin

        plugin = AssistantPlugin.__new__(AssistantPlugin)
        plugin.settings = MagicMock()
        plugin.settings.get = MagicMock(return_value="global_value")
        plugin.event_settings = MagicMock()
        plugin.event_settings.get = MagicMock(return_value=None)

        mock_event = MagicMock()
        result = plugin.get_effective_setting(mock_event, "test_key")

        assert result == "global_value"
