"""Integration tests for the health endpoint."""

import pytest
from unittest.mock import MagicMock, patch


class TestHealthEndpointIntegration:
    """Integration tests for the health check endpoint."""

    def test_health_returns_healthy_when_all_services_up(self):
        """Should return 'healthy' status when LLM is connected."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
            "enabled": True,
            "llm_provider": "ollama",
            "llm_model": "llama3.2",
        }.get(k))
        mock_plugin.llm_client = MagicMock()  # Connected

        response = controller._compute_health_status(mock_plugin)

        assert response["status"] == "healthy"
        assert response["llm_status"] == "connected"

    def test_health_returns_degraded_when_llm_unavailable(self):
        """Should return 'degraded' status when LLM is unavailable."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
            "enabled": True,
            "llm_provider": "ollama",
            "llm_model": "llama3.2",
        }.get(k))
        mock_plugin.llm_client = None  # Unavailable

        response = controller._compute_health_status(mock_plugin)

        assert response["status"] == "degraded"
        assert response["llm_status"] == "unavailable"

    def test_health_returns_unhealthy_when_disabled(self):
        """Should return 'unhealthy' status when plugin is disabled."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
            "enabled": False,
            "llm_provider": "ollama",
            "llm_model": "llama3.2",
        }.get(k))
        mock_plugin.llm_client = None

        response = controller._compute_health_status(mock_plugin)

        assert response["status"] == "unhealthy"

    def test_health_returns_not_configured_when_no_provider(self):
        """Should return 'not_configured' when LLM provider not set."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(return_value=None)
        mock_plugin.llm_client = None

        response = controller._compute_health_status(mock_plugin)

        assert response["llm_status"] == "not_configured"

    def test_settings_valid_true_when_required_settings_present(self):
        """Should validate settings_valid as True when required settings exist."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
            "enabled": True,
            "llm_provider": "ollama",
            "llm_model": "llama3.2",
        }.get(k))

        response = controller._compute_health_status(mock_plugin)

        assert response["settings_valid"] is True

    def test_settings_valid_false_when_required_settings_missing(self):
        """Should validate settings_valid as False when required settings missing."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
            "enabled": True,
            "llm_provider": None,  # Missing
            "llm_model": "llama3.2",
        }.get(k))

        response = controller._compute_health_status(mock_plugin)

        assert response["settings_valid"] is False


class TestHealthEndpointEdgeCases:
    """Tests for edge cases in health endpoint."""

    def test_health_handles_plugin_none(self):
        """Should handle case where plugin is not loaded."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        response = controller._compute_health_status(None)

        assert response["status"] == "unhealthy"
        assert response["llm_status"] == "not_configured"
        assert response["settings_valid"] is False

    def test_health_response_time_under_500ms(self):
        """Health computation should complete quickly (target < 500ms)."""
        import time
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(return_value=True)
        mock_plugin.llm_client = None

        start = time.time()
        response = controller._compute_health_status(mock_plugin)
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 500, f"Health computation took {elapsed_ms}ms, expected < 500ms"
