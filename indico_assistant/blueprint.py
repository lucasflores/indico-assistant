"""Blueprint for Indico Assistant plugin HTTP endpoints.

This module defines the URL routes for the plugin's REST API,
including the health check endpoint.
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

    blueprint.add_url_rule("/health", "health", RHHealth, methods=["GET"])


# Defer route registration to avoid circular imports
_register_routes()
