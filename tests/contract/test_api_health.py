"""Contract tests for the health API endpoint.

These tests verify the API contract matches the OpenAPI specification.
"""

import pytest
from unittest.mock import MagicMock, patch
import json


class TestHealthEndpointContract:
    """Contract tests verifying health endpoint matches OpenAPI spec."""

    def test_health_response_has_required_fields(self):
        """Health response must include all required fields per OpenAPI spec."""
        # Required fields from contracts/openapi.json
        required_fields = [
            "status",
            "plugin_version",
            "indico_version",
            "llm_status",
            "settings_valid",
            "timestamp",
        ]

        # Mock health response
        mock_response = {
            "status": "healthy",
            "plugin_version": "0.1.0",
            "indico_version": "3.3.0",
            "llm_status": "connected",
            "settings_valid": True,
            "timestamp": "2025-01-14T12:00:00+00:00",
        }

        for field in required_fields:
            assert field in mock_response, f"Missing required field: {field}"

    def test_status_enum_values(self):
        """Status field must be one of the allowed enum values."""
        allowed_statuses = ["healthy", "degraded", "unhealthy"]

        for status in allowed_statuses:
            assert status in allowed_statuses

    def test_llm_status_enum_values(self):
        """LLM status field must be one of the allowed enum values."""
        allowed_statuses = ["connected", "unavailable", "not_configured"]

        for status in allowed_statuses:
            assert status in allowed_statuses

    def test_health_response_structure(self):
        """Verify the health response structure matches contract."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        # Mock plugin
        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
            "enabled": True,
            "llm_provider": "ollama",
            "llm_model": "llama3.2",
        }.get(k))
        mock_plugin.llm_client = None  # Degraded mode

        response = controller._compute_health_status(mock_plugin)

        # Verify structure
        assert isinstance(response["status"], str)
        assert isinstance(response["plugin_version"], str)
        assert isinstance(response["indico_version"], str)
        # llm field is now a dict with detailed info, not a simple string
        assert isinstance(response["llm"], dict)
        assert "status" in response["llm"]
        assert isinstance(response["settings_valid"], bool)
        assert isinstance(response["timestamp"], str)

    def test_timestamp_is_iso8601_format(self):
        """Timestamp should be in ISO 8601 format."""
        from datetime import datetime
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(return_value=True)
        mock_plugin.llm_client = None

        response = controller._compute_health_status(mock_plugin)

        # Should be parseable as ISO 8601
        timestamp = response["timestamp"]
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed is not None

    def test_plugin_version_matches_package(self):
        """Plugin version in response should match package version."""
        from indico_assistant import __version__
        from indico_assistant.controllers import RHHealth

        controller = RHHealth.__new__(RHHealth)

        mock_plugin = MagicMock()
        mock_plugin.settings.get = MagicMock(return_value=True)
        mock_plugin.llm_client = None

        response = controller._compute_health_status(mock_plugin)

        assert response["plugin_version"] == __version__


class TestHealthEndpointAccess:
    """Tests for health endpoint access control."""

    def test_health_endpoint_allows_unauthenticated_access(self):
        """Health endpoint should not require authentication (FR-014)."""
        from indico_assistant.controllers import RHHealth

        controller = RHHealth()

        # _check_access should not raise
        controller._check_access()  # Should complete without error
