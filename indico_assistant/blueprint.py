"""Blueprint for Indico Assistant plugin HTTP endpoints and widget assets.

This module defines the URL routes for the plugin's REST API,
including health check and chat API endpoints, and also exposes the
Chainlit widget bundle so it can be loaded from an absolute path.

Feature: 004-chat-api
Feature: 005-langfuse-observability (T023 - request teardown flush)
Feature: 006-vector-search-rag (search endpoints)
"""

import functools
import hashlib
import os

from flask import g, send_from_directory
from indico.core.plugins import plugin_engine
from indico.core.plugins import IndicoPluginBlueprint

# Create the blueprint with /api/assistant prefix
blueprint = IndicoPluginBlueprint(
    "assistant",
    __name__,
    url_prefix="/api/assistant",
)

_STATIC_JS = os.path.join(os.path.dirname(__file__), "static", "js")
_STATIC_CSS = os.path.join(os.path.dirname(__file__), "static", "css")
_WIDGET_JS = "chat_widget.js"
_ONE_YEAR = 365 * 24 * 3600


@functools.cache
def _widget_version():
    with open(os.path.join(_STATIC_JS, _WIDGET_JS), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def widget_script_url():
    """Versioned URL of the widget script: browsers cache it for a year and refetch when it changes."""
    return f"{blueprint.url_prefix}/widget/{_WIDGET_JS}?v={_widget_version()}"


@blueprint.route(f"/widget/{_WIDGET_JS}")
def widget_script():
    return send_from_directory(_STATIC_JS, _WIDGET_JS, max_age=_ONE_YEAR)


@blueprint.route("/widget/css/<path:filename>")
def widget_static_css(filename):
    """Serve widget CSS alongside the script."""
    return send_from_directory(_STATIC_CSS, filename, max_age=_ONE_YEAR)


@blueprint.route("/widget/config")
def widget_config():
    """Per-user widget config with a fresh Chainlit token; fetched only when the widget is opened."""
    from flask import jsonify, request, session

    if session.user is None:
        return jsonify({"error": "UNAUTHORIZED"}), 401
    plugin = plugin_engine.get_plugin("assistant")
    event_id = request.args.get("event_id", type=int)  # scope of the page the widget was opened on
    response = jsonify(plugin.widget_config(session.user, event_id=event_id))
    # Contains a per-user token: never cache it in the browser, a proxy, or a CDN
    response.headers["Cache-Control"] = "private, no-store"
    return response


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
    from indico_assistant.controllers.chat import RHChat, RHChatJob
    from indico_assistant.controllers.feedback import RHFeedback, RHFeedbackDelete
    from indico_assistant.controllers.sessions import (
        RHSessionDelete,
        RHSessionDetail,
        RHSessionList,
        RHSessionOpen,
        RHSessionRename,
    )

    # Health check
    blueprint.add_url_rule("/health", "health", RHHealth, methods=["GET"])
    
    # Chat API endpoints (Feature 004)
    blueprint.add_url_rule("/chat", "chat", RHChat, methods=["POST"])
    blueprint.add_url_rule("/chat/jobs/<job_id>", "chat_job", RHChatJob, methods=["GET"])

    # Chat actions: plans to confirm (Feature 019)
    from indico_assistant.controllers.actions import RHChatUpload, RHPlan, RHPlanCancel, RHPlanConfirm, RHPlanToken

    blueprint.add_url_rule("/chat/uploads", "chat_upload", RHChatUpload, methods=["POST"])
    blueprint.add_url_rule("/plans/<plan_id>", "plan", RHPlan, methods=["GET"])
    blueprint.add_url_rule("/plans/<plan_id>/confirm", "plan_confirm", RHPlanConfirm, methods=["POST"])
    blueprint.add_url_rule("/plans/<plan_id>/cancel", "plan_cancel", RHPlanCancel, methods=["POST"])
    blueprint.add_url_rule("/plans/<plan_id>/token", "plan_token", RHPlanToken, methods=["POST"])
    
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
    blueprint.add_url_rule("/sessions/<session_id>", "session_rename", RHSessionRename, methods=["PATCH"])  # (020)
    blueprint.add_url_rule("/sessions/<session_id>", "session_open", RHSessionOpen, methods=["PUT"])  # (020)
    
    # Feedback endpoint (Feature 004, User Story 3)
    blueprint.add_url_rule("/feedback", "feedback", RHFeedback, methods=["POST"])
    blueprint.add_url_rule("/feedback/<feedback_id>", "feedback_delete", RHFeedbackDelete, methods=["DELETE"])  # (020)
    
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
