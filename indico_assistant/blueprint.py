"""Blueprint for Indico Assistant plugin HTTP endpoints and widget assets.

This module defines the URL routes for the plugin's REST API,
including health check and chat API endpoints, and also exposes the
Chainlit widget bundle so it can be loaded from an absolute path.

Feature: 004-chat-api
Feature: 005-langfuse-observability (T023 - request teardown flush)
Feature: 006-vector-search-rag (search endpoints)
"""

import os
import json

from flask import g, send_from_directory, current_app
from indico.core.plugins import plugin_engine
from indico.core.plugins import IndicoPluginBlueprint

# Create the blueprint with /api/assistant prefix
blueprint = IndicoPluginBlueprint(
    "assistant",
    __name__,
    url_prefix="/api/assistant",
)

_STATIC_DIST = os.path.join(os.path.dirname(__file__), "static", "dist")
_STATIC_CSS = os.path.join(os.path.dirname(__file__), "static", "css")


@blueprint.route("/widget/<path:filename>")
def widget_static(filename):
    """Serve Chainlit widget assets from a stable absolute URL.

    This avoids relative-path 404s when the widget is injected on pages with
    nested URLs (e.g., /event/123/...).
    """
    return send_from_directory(_STATIC_DIST, filename)


@blueprint.route("/widget/css/<path:filename>")
def widget_static_css(filename):
    """Serve widget CSS alongside the bundle."""
    return send_from_directory(_STATIC_CSS, filename)


@blueprint.route("/widget/config.js")
def widget_config():
    """Serve dynamic configuration as JS (defines window.IndicoAssistant)."""
    from flask import request
    import re
    
    plugin = plugin_engine.get_plugin("assistant")
    
    # Extract event_id from Referer header (Feature 013: event context)
    event_id = None
    referer = request.headers.get("Referer", "")
    if referer:
        # Match /event/123/ in URL
        match = re.search(r'/event/(\d+)/', referer)
        if match:
            event_id = int(match.group(1))
    
    # Pass event_id to get_vars_js
    config = plugin.get_vars_js(event_id=event_id) if plugin else {}
    payload = f"window.IndicoAssistant = {json.dumps(config)};"
    return current_app.response_class(payload, mimetype="application/javascript")


@blueprint.after_request
def _flush_observability_traces(response):
    """Flush Langfuse traces after each request (T023).
    
    This ensures traces are sent before the response completes,
    providing timely observability data. Uses graceful degradation -
    flush failures are logged but don't affect the response.
    
    Args:
        response: The Flask response object
        
    Returns:
        The unmodified response
    """
    # Only flush if tracer was used during this request
    tracer = getattr(g, "_observability_tracer", None)
    if tracer is not None:
        try:
            tracer.flush()
        except Exception:
            # Graceful degradation - don't fail the request
            pass
    return response


def _register_routes():
    """Register all routes for the blueprint.

    This is called after controllers are imported to avoid circular imports.
    """
    from indico_assistant.controllers.health import RHHealth
    from indico_assistant.controllers.chat import RHChat
    from indico_assistant.controllers.feedback import RHFeedback
    from indico_assistant.controllers.sessions import (
        RHSessionDelete,
        RHSessionDetail,
        RHSessionList,
    )

    # Health check
    blueprint.add_url_rule("/health", "health", RHHealth, methods=["GET"])
    
    # Chat API endpoints (Feature 004)
    blueprint.add_url_rule("/chat", "chat", RHChat, methods=["POST"])
    
    # Session management endpoints (Feature 004, User Story 2)
    blueprint.add_url_rule("/sessions", "sessions_list", RHSessionList, methods=["GET"])
    blueprint.add_url_rule(
        "/sessions/<session_id>", 
        "session_detail", 
        RHSessionDetail, 
        methods=["GET"]
    )
    blueprint.add_url_rule(
        "/sessions/<session_id>", 
        "session_delete", 
        RHSessionDelete, 
        methods=["DELETE"]
    )
    
    # Feedback endpoint (Feature 004, User Story 3)
    blueprint.add_url_rule("/feedback", "feedback", RHFeedback, methods=["POST"])
    
    # Admin API endpoints (Feature 005, T043)
    from indico_assistant.controllers.admin import (
        RHAdminErrors,
        RHAdminHealth,
        RHAdminStats,
    )
    
    blueprint.add_url_rule("/admin/stats", "admin_stats", RHAdminStats, methods=["GET"])
    blueprint.add_url_rule("/admin/errors", "admin_errors", RHAdminErrors, methods=["GET"])
    blueprint.add_url_rule("/admin/health", "admin_health", RHAdminHealth, methods=["GET"])
    
    # Vector Search API endpoints (Feature 006)
    from indico_assistant.controllers.search import (
        RHVectorSearch,
        RHSearchStatus,
        RHSyncDocuments,
        RHSyncAllDocuments,
    )
    
    blueprint.add_url_rule("/search", "search", RHVectorSearch, methods=["POST"])
    blueprint.add_url_rule("/search/status", "search_status", RHSearchStatus, methods=["GET"])
    blueprint.add_url_rule("/search/sync", "search_sync", RHSyncDocuments, methods=["POST"])
    blueprint.add_url_rule("/search/sync/all", "search_sync_all", RHSyncAllDocuments, methods=["POST"])


# Defer route registration to avoid circular imports
_register_routes()
