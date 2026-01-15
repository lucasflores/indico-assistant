"""Blueprint for Indico Assistant plugin HTTP endpoints.

This module defines the URL routes for the plugin's REST API,
including health check and chat API endpoints.

Feature: 004-chat-api
"""

from indico.core.plugins import IndicoPluginBlueprint

# Create the blueprint with /api/assistant prefix
blueprint = IndicoPluginBlueprint(
    "assistant",
    __name__,
    url_prefix="/api/assistant",
)


def _register_routes():
    """Register all routes for the blueprint.

    This is called after controllers are imported to avoid circular imports.
    """
    from indico_assistant.controllers import RHHealth
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


# Defer route registration to avoid circular imports
_register_routes()
