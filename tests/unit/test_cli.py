"""Unit tests for CLI commands."""

import pytest
from unittest.mock import MagicMock, patch
from click.testing import CliRunner


class TestCLICommands:
    """Tests for the assistant CLI commands."""

    def test_cli_group_exists(self):
        """CLI group 'assistant' should exist."""
        from indico_assistant.cli import cli

        assert cli.name == "assistant"

    def test_health_command_exists(self):
        """Health command should be registered."""
        from indico_assistant.cli import cli

        commands = list(cli.commands.keys())
        assert "health" in commands

    def test_config_command_exists(self):
        """Config command should be registered."""
        from indico_assistant.cli import cli

        commands = list(cli.commands.keys())
        assert "config" in commands


class TestHealthCLICommand:
    """Tests for the 'indico assistant health' command."""

    def test_health_command_shows_plugin_status(self):
        """Health command should display plugin status."""
        from indico_assistant.cli import health_command
        from click.testing import CliRunner

        runner = CliRunner()

        with patch("indico_assistant.cli.plugin_engine") as mock_engine:
            mock_plugin = MagicMock()
            mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
                "enabled": True,
                "llm_provider": "ollama",
                "llm_base_url": "http://localhost:11434",
            }.get(k))
            mock_plugin.llm_client = None
            mock_engine.get_plugin.return_value = mock_plugin

            result = runner.invoke(health_command)

            assert "Plugin Status:" in result.output
            assert "Version:" in result.output
            assert "LLM Status:" in result.output

    def test_health_command_handles_unloaded_plugin(self):
        """Health command should handle plugin not loaded."""
        from indico_assistant.cli import health_command
        from click.testing import CliRunner

        runner = CliRunner()

        with patch("indico_assistant.cli.plugin_engine") as mock_engine:
            mock_engine.get_plugin.return_value = None

            result = runner.invoke(health_command)

            assert "NOT LOADED" in result.output


class TestConfigCLICommand:
    """Tests for the 'indico assistant config' command."""

    def test_config_command_shows_settings(self):
        """Config command should display current settings."""
        from indico_assistant.cli import config_command
        from click.testing import CliRunner

        runner = CliRunner()

        with patch("indico_assistant.cli.plugin_engine") as mock_engine:
            mock_plugin = MagicMock()
            mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
                "enabled": True,
                "llm_provider": "ollama",
                "llm_model": "llama3.2",
                "llm_base_url": "http://localhost:11434",
                "llm_api_key": "sk-test-key-12345678",
                "timeout_seconds": 30,
                "max_tokens": 2048,
            }.get(k))
            mock_engine.get_plugin.return_value = mock_plugin

            result = runner.invoke(config_command)

            assert "Current Configuration:" in result.output
            assert "LLM Provider: ollama" in result.output
            assert "LLM Model: llama3.2" in result.output

    def test_config_command_masks_api_key_by_default(self):
        """Config command should mask API key by default."""
        from indico_assistant.cli import config_command
        from click.testing import CliRunner

        runner = CliRunner()

        with patch("indico_assistant.cli.plugin_engine") as mock_engine:
            mock_plugin = MagicMock()
            mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
                "enabled": True,
                "llm_provider": "ollama",
                "llm_model": "llama3.2",
                "llm_base_url": "http://localhost:11434",
                "llm_api_key": "sk-test-key-12345678",
                "timeout_seconds": 30,
                "max_tokens": 2048,
            }.get(k))
            mock_engine.get_plugin.return_value = mock_plugin

            result = runner.invoke(config_command)

            # API key should be masked
            assert "sk-test-key-12345678" not in result.output
            assert "****" in result.output or "sk-t" in result.output

    def test_config_command_shows_api_key_with_flag(self):
        """Config command should show API key with --show-secrets flag."""
        from indico_assistant.cli import config_command
        from click.testing import CliRunner

        runner = CliRunner()

        with patch("indico_assistant.cli.plugin_engine") as mock_engine:
            mock_plugin = MagicMock()
            mock_plugin.settings.get = MagicMock(side_effect=lambda k: {
                "enabled": True,
                "llm_provider": "ollama",
                "llm_model": "llama3.2",
                "llm_base_url": "http://localhost:11434",
                "llm_api_key": "sk-test-key-12345678",
                "timeout_seconds": 30,
                "max_tokens": 2048,
            }.get(k))
            mock_engine.get_plugin.return_value = mock_plugin

            result = runner.invoke(config_command, ["--show-secrets"])

            # API key should be visible
            assert "sk-test-key-12345678" in result.output


class TestExtendCLI:
    """Tests for the CLI extension signal handler."""

    def test_extend_cli_returns_cli_group(self):
        """extend_cli should return the CLI group."""
        from indico_assistant.cli import extend_cli, cli

        result = extend_cli(None)

        assert result == cli
