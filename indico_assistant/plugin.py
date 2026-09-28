"""Indico Assistant Plugin - Main plugin class.

This module defines the AssistantPlugin class which integrates with
Indico's plugin system to provide AI-powered assistant capabilities.
"""

import logging
import os

from indico.core.plugins import IndicoPlugin, IndicoPluginBlueprint
from indico.core import signals
from indico.web.flask.util import get_csp_nonce

from indico_assistant.default_settings import DEFAULT_SETTINGS, EVENT_SETTINGS_DEFAULTS
from indico_assistant.forms import SettingsForm


logger = logging.getLogger(__name__)


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
        
        # Keep the document index in line with attachments (Feature 011, reworked in audit Phase 2)
        self.connect(attachment_signals.attachment_created, _on_attachment_changed)
        self.connect(attachment_signals.attachment_updated, _on_attachment_changed)
        self.connect(attachment_signals.attachment_deleted, _on_attachment_deleted)
        self.connect(attachment_signals.folder_deleted, _on_folder_deleted)
        self.connect(signals.core.after_commit, _queue_pending_indexing)

    def _setup_chat_widget(self):
        """One deferred, cacheable <script> for logged-in users; it fetches its config only when opened."""
        self.template_hook("html-head", self._render_widget_script)

    # Reserves an open panel's width before the page paints (spec 020 FR-006a); the widget builds the panel
    # later. Runs under Indico's CSP with the page's nonce. localStorage may throw: then nothing is reserved.
    _PANEL_SNIPPET = (
        "try{{var s=JSON.parse(localStorage.getItem('indico-assistant:{uid}')||'{{}}');"
        "if(s.open&&innerWidth>=768)document.documentElement.style.marginRight="
        "Math.round(Math.max(320,Math.min(s.width||440,innerWidth/2)))+'px'}}catch(e){{}}"
        "window.__assistantInitialMargin=getComputedStyle(document.documentElement).marginRight;"
    )

    def _render_widget_script(self, **kwargs):
        from flask import session
        from indico_assistant.blueprint import widget_script_url

        if session.user is None or not self.settings.get("chat_widget_enabled"):
            return None  # anonymous visitors (and a disabled widget) cost nothing
        uid = int(session.user.id)
        return (f'<script nonce="{get_csp_nonce()}">{self._PANEL_SNIPPET.format(uid=uid)}</script>'
                f'<script src="{widget_script_url()}" data-user="{uid}" defer></script>')

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

    def widget_config(self, user, event_id=None):
        """Per-user widget configuration, served only by the uncached /widget/config route.

        SECURITY: this must never be named ``get_vars_js``. Indico renders every plugin's
        ``get_vars_js()`` into the shared ``/assets/js-vars/global.js``, which is generated once
        and cached for all visitors, so a token minted here would be served to everyone.
        """
        config = {
            "enabled": self.settings.get("chat_widget_enabled"),
            "chainlitUrl": self.settings.get("chainlit_server_url"),
            "authToken": None,
            "theme": "auto",
        }
        if user is None:
            return config
        # Prefer stored secret; fall back to env var so an empty form submission doesn't clear it
        secret = self.settings.get("chainlit_auth_secret") or os.environ.get("CHAINLIT_AUTH_SECRET", "")
        if not secret:
            self.logger.warning("Chainlit auth secret not set; no JWT issued")
            return config
        from indico_assistant.services.jwt_service import create_chainlit_token
        try:
            config["authToken"] = create_chainlit_token(user, secret, event_id=event_id)
        except Exception:
            self.logger.warning("Failed to generate Chainlit token", exc_info=True)
        return config

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


_PENDING_INDEXING = 'indico_assistant_pending_indexing'


def _on_attachment_changed(attachment, **kwargs):
    """Remember the attachment; it is queued once its transaction commits (see _queue_pending_indexing).

    Indico sends these signals after flush but before commit: queueing right away let a fast worker
    look for a row that was not visible yet and give up.
    """
    from flask import g

    try:
        g.setdefault(_PENDING_INDEXING, set()).add(attachment.id)
    except Exception:
        logger.exception('Could not schedule indexing for attachment %s', getattr(attachment, 'id', None))


def _queue_pending_indexing(sender, **kwargs):
    from flask import g, has_app_context

    pending = g.pop(_PENDING_INDEXING, None) if has_app_context() else None
    if not pending:
        return
    try:
        from indico_assistant.tasks.indexing import index_attachment_task

        for attachment_id in pending:  # the task skips anything that should not be indexed
            index_attachment_task.delay(attachment_id)
    except Exception:
        logger.exception('Could not queue indexing for attachments %s', sorted(pending))


def _drop_chunks(attachment_ids):
    """Drop chunks in the deleting request's transaction, so deleted files stop being searchable at once.

    Never fails the user's delete: a savepoint keeps an error out of the outer transaction, and the
    nightly cleanup_orphaned_documents removes anything missed.
    """
    from indico.core.db import db

    from indico_assistant.services.vector_search.store import VectorStore

    try:
        with db.session.begin_nested():
            store = VectorStore()
            for attachment_id in attachment_ids:
                store.delete_attachment_chunks(attachment_id, commit=False)
    except Exception:
        logger.exception('Could not drop search chunks of attachments %s', attachment_ids)


def _on_attachment_deleted(attachment, **kwargs):
    _drop_chunks([attachment.id])


def _on_folder_deleted(folder, **kwargs):
    _drop_chunks([attachment.id for attachment in folder.attachments])
