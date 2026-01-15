"""Integration tests for the health endpoint."""

import pytest
from unittest.mock import MagicMock, patch

from indico_assistant.services.llm.models import HealthStatus


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
        
        # Mock llm_service.health_check() to return connected status
        mock_health_status = HealthStatus(
            status="connected",
            latency_ms=50,
            provider="ollama",
            model="llama3.2"
        )
        mock_plugin.llm_service.health_check.return_value = mock_health_status

        response = controller._compute_health_status(mock_plugin)

        assert response["status"] == "healthy"
        assert response["llm"]["status"] == "connected"
        assert response["llm"]["latency_ms"] == 50

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
        
        # Mock llm_service.health_check() to return unavailable status
        mock_health_status = HealthStatus(
            status="unavailable",
            provider="ollama",
            model="llama3.2",
            error="Connection refused"
        )
        mock_plugin.llm_service.health_check.return_value = mock_health_status

        response = controller._compute_health_status(mock_plugin)

        assert response["status"] == "degraded"
        assert response["llm"]["status"] == "unavailable"
        assert response["llm"]["error"] == "Connection refused"

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
        
        # Even if LLM is connected, plugin disabled means unhealthy
        mock_health_status = HealthStatus(
            status="connected",
            latency_ms=50,
            provider="ollama",
            model="llama3.2"
        )
        mock_plugin.llm_service.health_check.return_value = mock_health_status

        response = controller._compute_health_status(mock_plugin)

        assert response["status"] == "unhealthy"

    def test_health_returns_not_configured_when_no_provider(self):
        """Should return 'not_configured' when LLM provider not set."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(return_value=None)

        response = controller._compute_health_status(mock_plugin)

        assert response["llm"]["status"] == "not_configured"

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
        
        # Mock health check
        mock_health_status = HealthStatus(
            status="connected",
            latency_ms=50,
            provider="ollama",
            model="llama3.2"
        )
        mock_plugin.llm_service.health_check.return_value = mock_health_status

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
        assert response["llm"]["status"] == "not_configured"
        assert response["settings_valid"] is False

    def test_health_handles_health_check_exception(self):
        """Should handle unexpected exceptions from health_check gracefully."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
            "enabled": True,
            "llm_provider": "ollama",
            "llm_model": "llama3.2",
        }.get(k))
        
        # Simulate exception in health_check
        mock_plugin.llm_service.health_check.side_effect = RuntimeError("Unexpected error")

        response = controller._compute_health_status(mock_plugin)

        # Should gracefully handle and return unavailable
        assert response["status"] == "degraded"
        assert response["llm"]["status"] == "unavailable"
        assert "Unexpected error" in response["llm"]["error"]

    def test_health_includes_latency_when_connected(self):
        """Health response should include latency when LLM is connected."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
            "enabled": True,
            "llm_provider": "ollama",
            "llm_model": "llama3.2",
        }.get(k))
        
        mock_health_status = HealthStatus(
            status="connected",
            latency_ms=123,
            provider="ollama",
            model="llama3.2"
        )
        mock_plugin.llm_service.health_check.return_value = mock_health_status

        response = controller._compute_health_status(mock_plugin)

        assert response["llm"]["latency_ms"] == 123
        assert response["llm"]["provider"] == "ollama"
        assert response["llm"]["model"] == "llama3.2"

    def test_health_returns_timeout_status(self):
        """Should return timeout status when LLM times out."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
            "enabled": True,
            "llm_provider": "ollama",
            "llm_model": "llama3.2",
        }.get(k))
        
        mock_health_status = HealthStatus(
            status="timeout",
            provider="ollama",
            model="llama3.2",
            error="Request timed out after 10s"
        )
        mock_plugin.llm_service.health_check.return_value = mock_health_status

        response = controller._compute_health_status(mock_plugin)

        assert response["status"] == "degraded"
        assert response["llm"]["status"] == "timeout"
        assert "timed out" in response["llm"]["error"]
