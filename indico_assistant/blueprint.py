"""Blueprint for Indico Assistant plugin HTTP endpoints and widget assets.

This module defines the URL routes for the plugin's REST API,
including health check and chat API endpoints, and also exposes the
Chainlit widget bundle so it can be loaded from an absolute path.

Feature: 004-chat-api
Feature: 006-vector-search-rag (search endpoints)
"""

import functools
import hashlib
import os

from flask import send_from_directory
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
    # the stylesheet is fetched with the script's ?v=, so both go in (a CSS-only change stayed cached for a year)
    digest = hashlib.sha256()
    for path in (os.path.join(_STATIC_JS, _WIDGET_JS), os.path.join(_STATIC_CSS, "chat_widget.css")):
        with open(path, "rb") as f:
            digest.update(f.read())
    return digest.hexdigest()[:12]


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


_STATIC_ANALYTICS = os.path.join(_STATIC_JS, "analytics")


@functools.cache
def _analytics_version():
    digest = hashlib.sha256()
    for name in sorted(os.listdir(_STATIC_ANALYTICS)):
        with open(os.path.join(_STATIC_ANALYTICS, name), "rb") as f:
            digest.update(f.read())
    return digest.hexdigest()[:12]


def analytics_asset_url(filename):
    """The analytics pages' scripts and styles (spec 024), versioned like the widget's."""
    return f"{blueprint.url_prefix}/admin/analytics/assets/{filename}?v={_analytics_version()}"


@blueprint.route("/admin/analytics/assets/<path:filename>")
def analytics_asset(filename):
    return send_from_directory(_STATIC_ANALYTICS, filename, max_age=_ONE_YEAR)


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
    
    # Issue reports (Feature 021, contracts/api.md)
    from indico_assistant.controllers.report_pages import (
        RHAdminReport,
        RHAdminReports,
        RHUserReport,
        RHUserReportDelete,
        RHUserReports,
    )
    from indico_assistant.controllers.reports import (
        RHAdminReportDetail,
        RHAdminReportList,
        RHAdminReportUpdate,
        RHReportCreate,
        RHReportDelete,
        RHReportDetail,
        RHReportList,
    )

    blueprint.add_url_rule("/reports", "report_create", RHReportCreate, methods=["POST"])
    blueprint.add_url_rule("/reports", "reports", RHReportList, methods=["GET"])
    blueprint.add_url_rule("/reports/<int:report_id>", "report", RHReportDetail, methods=["GET"])
    blueprint.add_url_rule("/reports/<int:report_id>", "report_delete", RHReportDelete, methods=["DELETE"])
    blueprint.add_url_rule("/admin/reports", "admin_reports_api", RHAdminReportList, methods=["GET"])
    blueprint.add_url_rule("/admin/reports/<int:report_id>", "admin_report_api", RHAdminReportDetail, methods=["GET"])
    blueprint.add_url_rule("/admin/reports/<int:report_id>", "admin_report_update", RHAdminReportUpdate,
                           methods=["PATCH"])
    # the profile pages, outside /api/assistant ("!"), for yourself and (admins) for another user, as Indico's are
    with blueprint.add_prefixed_rules("!/user/<int:user_id>", "!/user"):
        blueprint.add_url_rule("/assistant-reports/", "user_reports", RHUserReports)
        blueprint.add_url_rule("/assistant-reports/<int:report_id>/", "user_report", RHUserReport)
        blueprint.add_url_rule("/assistant-reports/<int:report_id>/delete", "user_report_delete", RHUserReportDelete,
                               methods=["POST"])
    blueprint.add_url_rule("!/admin/assistant-reports/", "admin_reports", RHAdminReports)
    blueprint.add_url_rule("!/admin/assistant-reports/<int:report_id>/", "admin_report", RHAdminReport,
                           methods=["GET", "POST"])

    # Connected accounts (spec 023): the API, the profile page, and GitHub's one fixed callback
    from indico_assistant.controllers.connections import (
        RHConnect,
        RHConnectionDelete,
        RHConnections,
        RHConnectionsAPI,
        RHDisconnect,
        RHGitHubCallback,
    )
    from indico_assistant.services.connectors.github import CALLBACK_PATH

    blueprint.add_url_rule("/connections", "connections_api", RHConnectionsAPI, methods=["GET"])
    blueprint.add_url_rule("/connections/<service>", "connection_delete", RHConnectionDelete, methods=["DELETE"])
    with blueprint.add_prefixed_rules("!/user/<int:user_id>", "!/user"):
        blueprint.add_url_rule("/assistant-connections/", "user_connections", RHConnections)
        blueprint.add_url_rule("/assistant-connections/github/connect", "github_connect", RHConnect, methods=["POST"])
        blueprint.add_url_rule("/assistant-connections/github/disconnect", "github_disconnect", RHDisconnect,
                               methods=["POST"])
    blueprint.add_url_rule("!" + CALLBACK_PATH, "github_callback", RHGitHubCallback)

    # Analytics (spec 024): the admin-only API, and the two admin pages
    from indico_assistant.controllers.analytics import (
        RHAnalyticsExport,
        RHAnalyticsPage,
        RHAnalyticsStats,
        RHAnalyticsTurn,
        RHAnalyticsTurnPage,
        RHAnalyticsTurns,
    )

    blueprint.add_url_rule("/admin/analytics", "analytics_stats", RHAnalyticsStats, methods=["GET"])
    blueprint.add_url_rule("/admin/turns", "analytics_turns", RHAnalyticsTurns, methods=["GET"])
    blueprint.add_url_rule("/admin/turns/<int:turn_id>", "analytics_turn", RHAnalyticsTurn, methods=["GET"])
    blueprint.add_url_rule("/admin/turns/by-answer/<uuid:answer_id>", "analytics_turn_by_answer", RHAnalyticsTurn,
                           methods=["GET"])
    blueprint.add_url_rule("/admin/turns/export.<any(csv,json):fmt>", "analytics_export", RHAnalyticsExport,
                           methods=["GET"])
    blueprint.add_url_rule("!/admin/assistant-analytics/", "admin_analytics", RHAnalyticsPage)
    blueprint.add_url_rule("!/admin/assistant-analytics/turns/<int:turn_id>/", "admin_analytics_turn",
                           RHAnalyticsTurnPage)

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
