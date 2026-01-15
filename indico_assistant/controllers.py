"""Request handlers (controllers) for Indico Assistant plugin.

This module contains RH classes that handle HTTP requests for the plugin's
REST API endpoints, following Indico's request handler pattern.
"""

from datetime import datetime, timezone

from flask import jsonify
from indico.web.rh import RH

from indico_assistant import __version__
from indico_assistant.version import get_indico_version


class RHHealth(RH):
    """Health check endpoint for the assistant plugin.

    This endpoint is publicly accessible (no authentication required)
    to support monitoring tools and load balancers.
    """

    DENY_FRAMES = False  # Allow embedding in iframes if needed

    def _check_access(self):
        """Override access check - health endpoint is public."""
        # Health endpoint is public per FR-014
        pass

    def _process(self):
        """Process the health check request.

        Returns:
            JSON response with health status information.
        """
        from indico_assistant.plugin import AssistantPlugin
        from indico.core.plugins import plugin_engine

        # Get the plugin instance
        plugin = plugin_engine.get_plugin("assistant")

        # Determine health status
        health_data = self._compute_health_status(plugin)

        return jsonify(health_data)

    def _compute_health_status(self, plugin):
        """Compute the health status of the plugin.

        Args:
            plugin: The AssistantPlugin instance.

        Returns:
            Dictionary containing health status information.
        """
        # Check if plugin is enabled
        enabled = plugin.settings.get("enabled") if plugin else False

        # Check LLM connectivity
        llm_status = self._check_llm_status(plugin)

        # Determine overall status
        if not enabled:
            status = "unhealthy"
        elif llm_status != "connected":
            status = "degraded"
        else:
            status = "healthy"

        # Check if settings are valid
        settings_valid = self._validate_settings(plugin)

        return {
            "status": status,
            "plugin_version": __version__,
            "indico_version": get_indico_version(),
            "llm_status": llm_status,
            "settings_valid": settings_valid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _check_llm_status(self, plugin):
        """Check the LLM service connectivity status.

        Args:
            plugin: The AssistantPlugin instance.

        Returns:
            String indicating LLM status: 'connected', 'unavailable', or 'not_configured'.
        """
        if plugin is None:
            return "not_configured"

        # Check if LLM is configured
        provider = plugin.settings.get("llm_provider")
        if not provider:
            return "not_configured"

        # Check if LLM client is available
        if plugin.llm_client is None:
            return "unavailable"

        return "connected"

    def _validate_settings(self, plugin):
        """Validate current plugin settings.

        Args:
            plugin: The AssistantPlugin instance.

        Returns:
            Boolean indicating if settings are valid.
        """
        if plugin is None:
            return False

        # Basic validation - check required settings exist
        required_settings = ["llm_provider", "llm_model"]
        for setting in required_settings:
            value = plugin.settings.get(setting)
            if not value:
                return False

        return True
