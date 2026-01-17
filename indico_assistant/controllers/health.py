"""Health check endpoint controller.

Feature: 001-plugin-foundation

This module contains the health check endpoint handler.
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

        # Check LLM connectivity (returns dict with status details)
        llm_info = self._check_llm_status(plugin)
        llm_status = llm_info.get("status", "not_configured")

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
            "llm": llm_info,  # Full LLM status with details
            "settings_valid": settings_valid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _check_llm_status(self, plugin):
        """Check the LLM service connectivity status.

        Uses the LLM service's health_check() method to verify actual
        connectivity to the LLM provider.

        Args:
            plugin: The AssistantPlugin instance.

        Returns:
            Dictionary containing LLM status information:
            - status: 'connected', 'unavailable', 'timeout', or 'not_configured'
            - latency_ms: Response latency in milliseconds (if connected)
            - provider: The LLM provider name
            - model: The LLM model name
            - error: Error message (if not connected)
        """
        if plugin is None:
            return {
                "status": "not_configured",
                "provider": None,
                "model": None,
            }

        # Check if LLM is configured
        provider = plugin.settings.get("llm_provider")
        model = plugin.settings.get("llm_model")
        if not provider:
            return {
                "status": "not_configured",
                "provider": None,
                "model": None,
            }

        # Use the LLM service to perform actual health check
        try:
            health_status = plugin.llm_service.health_check()
            result = {
                "status": health_status.status,
                "provider": provider,
                "model": model,
            }
            
            # Add latency if connected
            if health_status.latency_ms is not None:
                result["latency_ms"] = health_status.latency_ms
            
            # Add error message if not connected
            if health_status.error:
                result["error"] = health_status.error
            
            return result
        except Exception as e:
            # Fallback in case of unexpected errors
            return {
                "status": "unavailable",
                "provider": provider,
                "model": model,
                "error": str(e),
            }

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
