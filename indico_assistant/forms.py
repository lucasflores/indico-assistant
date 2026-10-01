"""Forms for Indico Assistant plugin settings.

This module defines WTForms form classes for plugin configuration,
including global settings and per-event settings.
"""

from wtforms.fields import BooleanField, FloatField, IntegerField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, NumberRange, Optional, URL, ValidationError

from indico.web.forms.base import IndicoForm
from indico.web.forms.fields import IndicoSelectMultipleCheckboxField

from indico_assistant.default_settings import IBIS_MODE_CHOICES, WRITE_ACTIONS


SECRETS = ("llm_api_key", "jev_api_key", "chainlit_auth_secret", "github_client_secret")
CLEAR = "-"  # typed into a secret's field, removes it


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
            ("ibis", "ibis router (model: ibis/<dial> or a pool model id)"),
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
        description="Model name/identifier (e.g., ibis/Balanced; llama3.2 for Ollama)",
    )

    llm_base_url = StringField(
        "LLM Base URL",
        validators=[Optional(), URL(message="Please enter a valid URL")],
        description="Base URL for the LLM API (e.g., https://labs.aithoth.com/ibis-api; http://localhost:11434 for Ollama)",
    )

    llm_api_key = PasswordField(
        "API Key",
        validators=[Optional()],
        description="API key for cloud providers (never displayed; leave empty to keep it, \"-\" removes it)",
    )

    llm_ibis_mode = SelectField(
        "ibis structured output",
        choices=list(IBIS_MODE_CHOICES),
        validators=[DataRequired()],
        description="With the ibis provider: how answers are asked to follow a schema. Other providers ignore it.",
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

    jev_api_key = PasswordField(
        "Router key (Jev)",
        validators=[Optional()],
        description="An OpenRouter key for Jev, which routes each message (a question about Indico, a change, a data "
                    "question, the conversation) in one decision. Optional: without it the classifier routes. "
                    "Never displayed; leave empty to keep it, \"-\" removes it.",
    )

    jev_timeout_seconds = FloatField(
        "Router timeout (seconds)",
        validators=[InputRequired(), NumberRange(min=0.2, max=10)],
        description="A slower decision is ignored and the classifier routes instead (0.2-10 seconds).",
    )

    # NL2SQL Pipeline Settings (003-nl2sql-pipeline)
    nl2sql_enabled = BooleanField(
        "Enable NL2SQL",
        description="Enable natural language to SQL query translation",
    )

    nl2sql_timeout = IntegerField(
        "NL2SQL Timeout (seconds)",
        validators=[Optional(), NumberRange(min=5, max=120)],
        description="Timeout for SQL query execution (5-120 seconds, default: 10)",
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
        description="Not used: answers depend on who asks and where, so query results are never cached",
    )

    nl2sql_allowed_tables = TextAreaField(
        "NL2SQL Allowed Tables",
        validators=[Optional()],
        description="Comma-separated list of tables allowed for NL2SQL queries (leave empty for default set)",
    )

    # Retention (applied nightly by the indico_assistant.retention task)
    retention_chat_days = IntegerField(
        "Keep chats (days)",
        validators=[InputRequired(), NumberRange(min=0)],
        description="Chat sessions idle longer than this are deleted with their messages and feedback. "
                    "0 keeps them forever.",
    )
    retention_audit_days = IntegerField(
        "Keep query audit log (days)",
        validators=[InputRequired(), NumberRange(min=0)],
        description="The audit log holds users' questions, emails and IP addresses. 0 keeps it forever.",
    )
    retention_error_days = IntegerField(
        "Keep error records (days)", validators=[InputRequired(), NumberRange(min=0)],
        description="0 keeps them forever.",
    )
    retention_sync_log_days = IntegerField(
        "Keep document sync logs (days)", validators=[InputRequired(), NumberRange(min=0)],
        description="0 keeps them forever.",
    )
    retention_plan_days = IntegerField(
        "Keep chat action plans (days)", validators=[InputRequired(), NumberRange(min=0)],
        description="What the assistant planned and did, for audit. Undo only reaches back 24 hours. "
                    "0 keeps them forever.",
    )
    retention_report_days = IntegerField(
        "Keep closed issue reports (days)", validators=[InputRequired(), NumberRange(min=0)],
        description="Counted from when a report was closed; open reports and reports under review are never "
                    "deleted. A report holds the conversation its user attached. 0 keeps them forever.",
    )

    # Chat actions (Feature 019)
    actions_enabled = BooleanField(
        "Enable chat actions",
        description="Let the assistant create and change meetings, contributions, reminders, Teams rooms and "
                    "material. Users always confirm the exact plan first, and can only do what they could do "
                    "on the corresponding Indico page.",
    )
    actions_allowed = IndicoSelectMultipleCheckboxField(
        "Allowed actions",
        choices=[(name, name.replace("_", " ").capitalize()) for name in WRITE_ACTIONS],
        description="Actions the assistant may plan. A disabled action is never offered.",
    )
    actions_reminder_minutes = IntegerField(
        "Reminder before a meeting (minutes)", validators=[InputRequired(), NumberRange(min=0)],
        description="Default for the reminder sent to a meeting's invitees and speakers; editable in each plan.",
    )
    actions_outlook_freebusy = BooleanField(
        "Use Outlook free/busy for time suggestions",
        description="Not available yet (it waits for a check of the Teams app's Microsoft 365 setup): suggestions "
                    "use Indico only, and say so.",
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
        description="Shared secret for JWT authentication with Chainlit (must match CHAINLIT_AUTH_SECRET; never "
                    "displayed; leave empty to keep it, \"-\" removes it)",
    )

    # Connectors (spec 023)
    github_enabled = BooleanField(
        "Enable GitHub",
        description="Users can connect their own GitHub account and ask the assistant about it (read-only). Needs "
                    "the GitHub App's client ID and secret, and the INDICO_ASSISTANT_CONNECTOR_KEY environment "
                    "variable (see docs/DEPLOYMENT.md).",
    )

    github_client_id = StringField("GitHub App client ID", validators=[Optional()])

    github_client_secret = PasswordField(
        "GitHub App client secret",
        validators=[Optional()],
        description="Never displayed; leave empty to keep it, \"-\" removes it.",
    )

    github_app_url = StringField(
        "GitHub App page",
        validators=[Optional(), URL(require_tld=False)],
        description="The app's public page, https://github.com/apps/<name>: users add repositories there.",
    )

    github_timeout_seconds = FloatField(
        "GitHub timeout (seconds)",
        validators=[InputRequired(), NumberRange(min=1, max=30)],
        description="For each call to GitHub (1-30 seconds).",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from indico_assistant.services.connectors.github import callback_url
        self.github_client_id.description = (f"Register the GitHub App with the callback URL {callback_url()} and "
                                             "read-only Metadata, Issues and Pull requests permissions.")

    @property
    def data(self):
        """What Indico saves (``settings.set_multi(form.data)``), without an empty secret: a password field is never
        filled in with the stored value, so empty means "keep it" (spec 022 FR-021: never displayed), and a single
        "-" removes it (to switch the router off, or drop a leaked key)."""
        data = {name: value for name, value in super().data.items() if name not in SECRETS or value}
        return {name: (None if name in SECRETS and value.strip() == CLEAR else value) for name, value in data.items()}

    def validate_github_enabled(self, field):
        """GitHub can't be turned on without the app's ID and secret and the tokens' key (spec 023 FR-002)."""
        from indico_assistant.services.connectors.store import KEY_ENV, fernet

        if not field.data:
            return
        secret = (self.github_client_secret.data or "").strip()
        secret = None if secret == CLEAR else secret or _stored("github_client_secret")
        missing = [what for what, there in (("the client ID", (self.github_client_id.data or "").strip()),
                                            ("the client secret", secret),
                                            (f"a valid {KEY_ENV} environment variable", fernet()))
                   if not there]
        if missing:
            raise ValidationError("GitHub needs " + " and ".join(missing) + ".")

    def validate_nl2sql_allowed_tables(self, field):
        """Convert comma-separated string to list or None."""
        if field.data:
            tables = [t.strip() for t in field.data.split(",") if t.strip()]
            field.data = tables if tables else None
        else:
            field.data = None


def _stored(name):
    """A setting as saved (a secret's field is never filled in), or None while the plugin isn't loaded."""
    from indico_assistant.plugin import AssistantPlugin

    try:
        return AssistantPlugin.settings.get(name)
    except RuntimeError:
        return None


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
