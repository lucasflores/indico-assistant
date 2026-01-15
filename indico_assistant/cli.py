"""CLI commands for the Indico Assistant plugin.

This module defines click commands that extend Indico's CLI
with assistant-related functionality.
"""

import click
from flask.cli import with_appcontext


@click.group("assistant")
def cli():
    """Indico Assistant plugin commands."""
    pass


@cli.command("health")
@with_appcontext
def health_command():
    """Check the health status of the assistant plugin.

    Displays the same information as the /api/assistant/health endpoint.
    """
    from indico.core.plugins import plugin_engine
    from indico_assistant import __version__
    from indico_assistant.version import get_indico_version

    plugin = plugin_engine.get_plugin("assistant")

    if plugin is None:
        click.secho("Plugin Status: NOT LOADED", fg="red")
        return

    enabled = plugin.settings.get("enabled")
    provider = plugin.settings.get("llm_provider")
    base_url = plugin.settings.get("llm_base_url")

    # Determine LLM status
    if not provider:
        llm_status = "not_configured"
        status_color = "yellow"
    elif plugin.llm_client is None:
        llm_status = "unavailable"
        status_color = "yellow"
    else:
        llm_status = "connected"
        status_color = "green"

    # Determine overall status
    if not enabled:
        overall_status = "unhealthy"
        overall_color = "red"
    elif llm_status != "connected":
        overall_status = "degraded"
        overall_color = "yellow"
    else:
        overall_status = "healthy"
        overall_color = "green"

    click.echo(f"Plugin Status: ", nl=False)
    click.secho(overall_status, fg=overall_color)
    click.echo(f"Version: {__version__}")
    click.echo(f"Indico Version: {get_indico_version()}")
    click.echo(f"LLM Status: ", nl=False)
    click.secho(llm_status, fg=status_color)
    if provider and base_url:
        click.echo(f"  Provider: {provider} @ {base_url}")


@cli.command("config")
@click.option("--show-secrets", is_flag=True, help="Show API keys (masked by default)")
@with_appcontext
def config_command(show_secrets):
    """Show current configuration (secrets masked by default)."""
    from indico.core.plugins import plugin_engine

    plugin = plugin_engine.get_plugin("assistant")

    if plugin is None:
        click.secho("Plugin not loaded", fg="red")
        return

    click.echo("Current Configuration:")
    click.echo("-" * 40)

    settings_to_show = [
        ("enabled", "Enabled"),
        ("llm_provider", "LLM Provider"),
        ("llm_model", "LLM Model"),
        ("llm_base_url", "Base URL"),
        ("timeout_seconds", "Timeout (s)"),
        ("max_tokens", "Max Tokens"),
    ]

    for key, label in settings_to_show:
        value = plugin.settings.get(key)
        click.echo(f"  {label}: {value}")

    # Handle API key specially
    api_key = plugin.settings.get("llm_api_key")
    if api_key:
        if show_secrets:
            click.echo(f"  API Key: {api_key}")
        else:
            masked = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:] if len(api_key) > 8 else "****"
            click.echo(f"  API Key: {masked}")
    else:
        click.echo("  API Key: (not set)")


def extend_cli(sender, **kwargs):
    """Signal handler to extend Indico CLI with assistant commands.

    This function is connected to signals.plugin.cli in the plugin's init().
    """
    return cli
