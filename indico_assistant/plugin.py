"""Indico Assistant Plugin - Main plugin class.

This module defines the AssistantPlugin class which integrates with
Indico's plugin system to provide AI-powered assistant capabilities.
"""

import os

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

        Called when the plugin is loaded. Sets up signal connections,
        lazy-initializes the LLM client, and injects the chat widget.
        """
        super().init()
        self._llm_client = None  # Lazy initialization for graceful degradation
        self._llm_service = None  # Lazy initialization for LLM service
        self._setup_signal_handlers()
        self._setup_chat_widget()

    def _setup_signal_handlers(self):
        """Connect to Indico signals for extending functionality."""
        from indico_assistant.cli import extend_cli
        from indico.core.signals import attachments as attachment_signals

        self.connect(signals.plugin.cli, extend_cli)
        
        # Connect to attachment_created signal for realtime indexing
        # Feature: 011-realtime-attachment-indexing
        self.connect(attachment_signals.attachment_created, _on_attachment_created)

    def _setup_chat_widget(self):
        """Inject the chat widget JavaScript bundle into all pages."""
        # The widget script will check IndicoAssistant.enabled and exit early if disabled
        self.inject_bundle("chat_widget.js")

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

    def get_vars_js(self, event_id=None):
        """Expose configuration to JavaScript as IndicoAssistant global.

        Returns a dictionary that will be available in JavaScript as:
        - IndicoAssistant.enabled: Whether the widget is enabled
        - IndicoAssistant.chainlitUrl: URL of the Chainlit server
        - IndicoAssistant.authToken: JWT token for authenticated users (null if not logged in)
        - IndicoAssistant.theme: Current theme preference ('light', 'dark', or 'auto')

        Args:
            event_id: Optional event ID from request context (Feature 013: event context)

        Returns:
            dict: Widget configuration for JavaScript.
        """
        from flask import session, g
        try:
            from flask_login import current_user
        except Exception:  # pragma: no cover
            current_user = None
        from indico.web.flask.util import send_file

        config = {
            "enabled": self.settings.get("chat_widget_enabled", False),
            "chainlitUrl": self.settings.get("chainlit_server_url", "http://localhost:8000"),
            "authToken": None,
            "theme": "auto",
        }

        # Generate auth token for authenticated users
        session_user = getattr(session, "user", None)
        g_user = getattr(g, "user", None)
        
        # Try to get current_user safely
        try:
            cu = current_user if current_user and not getattr(current_user, 'is_anonymous', True) else None
        except (AttributeError, RuntimeError):
            cu = None
        
        user = session_user or g_user or cu

        # Indico does not expose Flask-Login's current_user; use session.user instead
        if user and not getattr(user, "is_anonymous", False):
            # Prefer stored secret; fallback to env var to avoid empty submissions clearing it
            secret = self.settings.get("chainlit_auth_secret") or os.environ.get("CHAINLIT_AUTH_SECRET", "")
            if secret:
                from indico_assistant.services.jwt_service import create_chainlit_token

                try:
                    config["authToken"] = create_chainlit_token(user, secret, event_id=event_id)
                except Exception:
                    # Graceful degradation - widget will work without auth
                    self.logger.warning("Failed to generate Chainlit token", exc_info=True)
            else:
                self.logger.warning("Chainlit auth secret not set; no JWT issued")

        return config

    def inject_bundle(self, name, *args, **kwargs):  # type: ignore[override]
        # Ensure config (vars.js) loads before chat_widget.js so IndicoAssistant exists.
        if name == "chat_widget.js":
            super().inject_bundle("vars.js", *args, **kwargs)
        super().inject_bundle(name, *args, **kwargs)

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


def _on_attachment_created(attachment, **kwargs):
    """Signal handler for attachment creation events.
    
    Queues an asynchronous indexing task when a new attachment is uploaded.
    This handler must complete in <100ms to avoid blocking user operations.
    
    Args:
        attachment: The Attachment model instance that was created
        **kwargs: Additional signal arguments (ignored)
    
    Feature: 011-realtime-attachment-indexing
    Tasks: T017, T028-T030
    FR-001: Queue indexing task within 1 second of upload
    FR-002: Only index when vector search is enabled
    FR-003: Validate file size before queueing
    FR-009: Handler must complete in <100ms
    FR-011: Graceful degradation when vector search unavailable
    FR-012: Ignore unsupported file formats
    """
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        from indico_assistant.plugin import AssistantPlugin
        from indico_assistant.services.document.validation import (
            is_supported_format,
            determine_processing_tier
        )
        from indico_assistant.services.vector_search.store import VectorStore
        from indico_assistant.tasks.indexing import index_attachment_task
        from indico_assistant.models.document import ProcessingTier
        
        # FR-012: Check if file format is supported
        if not is_supported_format(attachment.file.filename):
            logger.debug(
                "Skipping indexing for unsupported file format: %s (attachment_id=%d)",
                attachment.file.filename,
                attachment.id
            )
            return  # Silently skip unsupported formats
        
        # FR-002: Check if vector search is enabled
        plugin = AssistantPlugin.instance
        if not plugin.settings.get('vector_search_enabled', False):
            logger.debug("Vector search disabled, skipping indexing (attachment_id=%d)", attachment.id)
            return  # Vector search disabled, skip indexing
        
        # FR-011: Check if pgvector is available
        if not VectorStore.is_available():
            logger.debug("pgvector unavailable, skipping indexing (attachment_id=%d)", attachment.id)
            return  # Gracefully skip if vector search unavailable
        
        # FR-003: Determine processing tier based on file size
        tier = determine_processing_tier(attachment.file.size)
        
        if tier == ProcessingTier.REJECTED:
            logger.debug(
                "Skipping indexing for file exceeding size limit: %s (attachment_id=%d, size=%d bytes)",
                attachment.file.filename,
                attachment.id,
                attachment.file.size
            )
            return  # File too large, skip indexing
        
        # FR-001: Queue indexing task with appropriate priority
        priority = 'high' if tier == ProcessingTier.FAST else 'low'
        
        index_attachment_task.apply_async(
            args=[attachment.id, attachment.event_id],
            kwargs={'force': False, 'priority': priority},
            priority=9 if priority == 'high' else 3  # Celery priority (0-9)
        )
        
        logger.info(
            "Queued indexing task for attachment: %s (attachment_id=%d, event_id=%d, tier=%s, priority=%s)",
            attachment.file.filename,
            attachment.id,
            attachment.event_id,
            tier.value,
            priority
        )
        
    except Exception as e:
        # FR-009, FR-011: Never raise exceptions from signal handler
        # Errors are logged but don't block user operations
        logger.error(
            "Error in attachment_created signal handler (attachment_id=%d): %s",
            attachment.id if attachment else None,
            str(e),
            exc_info=True
        )
        pass
