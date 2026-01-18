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

    # NL2SQL Pipeline Settings (003-nl2sql-pipeline)
    nl2sql_enabled = BooleanField(
        "Enable NL2SQL",
        description="Enable natural language to SQL query translation",
    )

    nl2sql_timeout = IntegerField(
        "NL2SQL Timeout (seconds)",
        validators=[Optional(), NumberRange(min=5, max=120)],
        description="Timeout for SQL query execution (5-120 seconds, default: 30)",
    )

    nl2sql_max_rows = IntegerField(
        "NL2SQL Max Rows",
        validators=[Optional(), NumberRange(min=10, max=10000)],
        description="Maximum rows returned per query (10-10000, default: 1000)",
    )

    nl2sql_max_corrections = IntegerField(
        "NL2SQL Max Corrections",
        validators=[Optional(), NumberRange(min=0, max=5)],
        description="Maximum error correction attempts (0-5, default: 3)",
    )

    nl2sql_cache_ttl = IntegerField(
        "NL2SQL Cache TTL (seconds)",
        validators=[Optional(), NumberRange(min=0, max=3600)],
        description="Cache TTL for identical queries (0=disabled, max 3600, default: 600)",
    )

    nl2sql_allowed_tables = TextAreaField(
        "NL2SQL Allowed Tables",
        validators=[Optional()],
        description="Comma-separated list of tables allowed for NL2SQL queries (leave empty for default set)",
    )

    # Chat Widget Settings (Feature 008)
    chat_widget_enabled = BooleanField(
        "Enable Chat Widget",
        description="Show floating chat widget on all Indico pages",
    )

    chainlit_server_url = StringField(
        "Chainlit Server URL",
        validators=[Optional(), URL(message="Please enter a valid URL")],
        description="URL of the Chainlit server (e.g., http://localhost:8000)",
    )

    chainlit_auth_secret = PasswordField(
        "Chainlit Auth Secret",
        validators=[Optional()],
        description="Shared secret for JWT authentication with Chainlit (must match CHAINLIT_AUTH_SECRET)",
    )

    def validate_nl2sql_allowed_tables(self, field):
        """Convert comma-separated string to list or None."""
        if field.data:
            tables = [t.strip() for t in field.data.split(",") if t.strip()]
            field.data = tables if tables else None
        else:
            field.data = None


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

    nl2sql_enabled = SelectField(
        "Enable NL2SQL for this event",
        choices=[
            ("", "Inherit from global settings"),
            ("true", "Enabled"),
            ("false", "Disabled"),
        ],
        validators=[Optional()],
        description="Override global NL2SQL setting for this event",
    )

    def validate_enabled(self, field):
        """Convert string enabled value to boolean or None."""
        if field.data == "":
            field.data = None
        elif field.data == "true":
            field.data = True
        elif field.data == "false":
            field.data = False

    def validate_nl2sql_enabled(self, field):
        """Convert string nl2sql_enabled value to boolean or None."""
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
