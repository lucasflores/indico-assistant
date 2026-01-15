"""Indico Assistant Plugin - Main plugin class.

This module defines the AssistantPlugin class which integrates with
Indico's plugin system to provide AI-powered assistant capabilities.
"""

from indico.core.plugins import IndicoPlugin, IndicoPluginBlueprint
from indico.core import signals

from indico_assistant.default_settings import DEFAULT_SETTINGS, EVENT_SETTINGS_DEFAULTS
from indico_assistant.forms import SettingsForm


class AssistantPlugin(IndicoPlugin):
    """Indico Assistant Plugin - AI-powered assistant for events.

    This plugin provides natural language query capabilities for Indico events,
    allowing users to ask questions about event data using LLM providers.
    """

    configurable = True  # Show in admin settings panel
    settings_form = SettingsForm  # Form class for global settings

    default_settings = DEFAULT_SETTINGS
    default_event_settings = EVENT_SETTINGS_DEFAULTS

    def init(self):
        """Initialize the plugin.

        Called when the plugin is loaded. Sets up signal connections
        and lazy-initializes the LLM client.
        """
        super().init()
        self._llm_client = None  # Lazy initialization for graceful degradation
        self._llm_service = None  # Lazy initialization for LLM service
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Connect to Indico signals for extending functionality."""
        from indico_assistant.cli import extend_cli

        self.connect(signals.plugin.cli, extend_cli)

    @property
    def llm_client(self):
        """Get the LLM client, initializing lazily if needed.

        Returns:
            The LLM client instance, or None if initialization fails.
        """
        if self._llm_client is None:
            self._llm_client = self._create_llm_client()
        return self._llm_client

    def _create_llm_client(self):
        """Create an LLM client based on current settings.

        Returns:
            The LLM client instance, or None if creation fails.
        """
        # LLM client will be implemented in a later feature
        # For now, return None to indicate degraded mode
        return None

    @property
    def llm_service(self):
        """Get the LLM service, initializing lazily if needed.

        The LLM service provides structured LLM interactions with
        automatic validation, retry logic, and error handling.

        Returns:
            LLMService: The LLM service instance.
        """
        if self._llm_service is None:
            from indico_assistant.services.llm import create_llm_service

            self._llm_service = create_llm_service(self)
        return self._llm_service

    def get_blueprints(self):
        """Return the blueprints for this plugin.

        Returns:
            The plugin's blueprint.
        """
        from indico_assistant.blueprint import blueprint

        return blueprint

    def get_effective_setting(self, event, key):
        """Get a setting value with event → global fallback.

        Args:
            event: The event object (or None for global settings).
            key: The setting key to retrieve.

        Returns:
            The effective setting value.
        """
        if event is not None:
            event_value = self.event_settings.get(event, key)
            if event_value is not None:
                return event_value
        return self.settings.get(key)
