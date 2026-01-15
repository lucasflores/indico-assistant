"""Forms for Indico Assistant plugin settings.

This module defines WTForms form classes for plugin configuration,
including global settings and per-event settings.
"""

from wtforms.fields import BooleanField, IntegerField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Optional, URL, ValidationError

from indico.web.forms.base import IndicoForm


class SettingsForm(IndicoForm):
    """Global settings form for the Indico Assistant plugin.

    Displayed in the admin panel under Plugins → Assistant → Settings.
    """

    enabled = BooleanField(
        "Enable Assistant",
        description="Master switch to enable/disable the assistant plugin",
    )

    llm_provider = SelectField(
        "LLM Provider",
        choices=[
            ("ollama", "Ollama (Local)"),
            ("huggingface", "HuggingFace Router"),
            ("openai", "OpenAI-compatible API"),
        ],
        validators=[DataRequired()],
        description="Select the LLM provider to use for AI queries",
    )

    llm_model = StringField(
        "LLM Model",
        validators=[DataRequired()],
        description="Model name/identifier (e.g., llama3.2, gpt-4)",
    )

    llm_base_url = StringField(
        "LLM Base URL",
        validators=[Optional(), URL(message="Please enter a valid URL")],
        description="Base URL for the LLM API (e.g., http://localhost:11434 for Ollama)",
    )

    llm_api_key = PasswordField(
        "API Key",
        validators=[Optional()],
        description="API key for cloud providers (stored securely, not displayed)",
    )

    timeout_seconds = IntegerField(
        "Timeout (seconds)",
        validators=[DataRequired(), NumberRange(min=5, max=300)],
        description="Request timeout for LLM calls (5-300 seconds)",
    )

    max_tokens = IntegerField(
        "Max Tokens",
        validators=[DataRequired(), NumberRange(min=100, max=32000)],
        description="Maximum response tokens (100-32000)",
    )


class EventSettingsForm(IndicoForm):
    """Per-event settings form for the Indico Assistant plugin.

    Displayed in event management under the Assistant settings section.
    """

    enabled = SelectField(
        "Enable for this event",
        choices=[
            ("", "Inherit from global settings"),
            ("true", "Enabled"),
            ("false", "Disabled"),
        ],
        validators=[Optional()],
        description="Override global enable setting for this event",
    )

    custom_system_prompt = TextAreaField(
        "Custom System Prompt",
        validators=[Optional()],
        description="Custom prompt to include in AI interactions for this event",
    )

    allowed_tables = StringField(
        "Allowed Tables",
        validators=[Optional()],
        description="Comma-separated list of table names the assistant can query (leave empty for all)",
    )

    def validate_enabled(self, field):
        """Convert string enabled value to boolean or None."""
        if field.data == "":
            field.data = None
        elif field.data == "true":
            field.data = True
        elif field.data == "false":
            field.data = False

    def validate_allowed_tables(self, field):
        """Convert comma-separated string to list or None."""
        if field.data:
            tables = [t.strip() for t in field.data.split(",") if t.strip()]
            field.data = tables if tables else None
        else:
            field.data = None
