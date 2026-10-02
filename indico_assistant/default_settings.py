"""Default settings for the Indico Assistant plugin.

These values are used when no settings have been configured by an administrator.
"""

# Chat actions an admin can switch on or off one by one (Feature 019). Reads (finding people, categories,
# free times) are not switchable: they only show what the user could already look up in Indico.
WRITE_ACTIONS = (
    "create_event",
    "propose_event",
    "update_event",
    "add_contribution",
    "update_contribution",
    "add_teams_room",
    "add_reminder",
    "attach_link",
    "attach_file",
    "delete_created",
)

# How the ibis provider can ask for structured output, and what the settings form calls each. Kept
# here, free of dependencies, so the form needs no LLM import; factory.IBIS_MODES maps the same keys.
IBIS_MODE_CHOICES = (
    ("tools", "Tool call"),
    ("json_schema", "Response format with the schema (not strict)"),
    ("md_json", "JSON asked for in the prompt"),
)

DEFAULT_SETTINGS = {
    "enabled": True,
    # The ibis router (labs.aithoth.com): an sk-ibis- key is the only thing an install must add.
    # ibis/<dial> routes (Frugal, Economy, Balanced, High, Max); a concrete model id bypasses the router.
    "llm_provider": "ibis",
    "llm_model": "ibis/Balanced",
    "llm_base_url": "https://labs.aithoth.com/ibis-api",
    "llm_api_key": None,
    # How the ibis provider asks for structured output (IBIS_MODE_CHOICES). md_json, the prompt-JSON
    # form, is what every install used before this setting existed; the default moves to tools only
    # once the acceptance sweep's evidence is in, so an upgrade changes nothing by itself.
    "llm_ibis_mode": "md_json",
    "timeout_seconds": 30,
    # The router (spec 022): one Jev decision gives each message its route and, for data, its kind. Jev is called at
    # OpenRouter directly (constitution 1.1.0, Principle III); without a key the classifier routes instead.
    "jev_api_key": None,
    "jev_timeout_seconds": 1.5,
    "max_tokens": 4096,
    # NL2SQL pipeline defaults (Feature 003)
    "nl2sql_enabled": True,
    "nl2sql_timeout": 10,
    "nl2sql_max_rows": 1000,
    "nl2sql_max_corrections": 3,
    "nl2sql_cache_ttl": 600,
    "nl2sql_allowed_tables": None,
    "max_retries": 2,
    # Vector search settings (Feature 006)
    "vector_search_enabled": True,
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "embedding_dimensions": 384,
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "similarity_threshold": 0.7,
    "max_search_results": 5,
    "embedding_batch_size": 32,
    "supported_extensions": [".pdf", ".docx", ".doc", ".txt", ".md"],
    # Chat widget settings (Feature 008)
    "chat_widget_enabled": True,
    "chainlit_server_url": "http://localhost:8000",
    "chainlit_auth_secret": "",  # Shared secret for JWT signing (must match CHAINLIT_AUTH_SECRET)
    # Retention in days, applied nightly; 0 = keep forever
    "retention_chat_days": 90,  # chat sessions idle this long (their messages and feedback go with them)
    "retention_audit_days": 90,  # NL2SQL audit log: questions, emails, IP addresses
    "retention_sync_log_days": 90,
    "retention_plan_days": 90,  # chat action plans (their audit trail; undo only reaches back 24 h)
    "retention_report_days": 365,  # issue reports, counted from closing; open ones are never purged (spec 021)
    # Analytics (spec 024): every answer's turn record and steps, and their text (prompts, answers, SQL), for admins
    "analytics_trace_text": True,
    "retention_trace_text_days": 30,
    "retention_turn_days": 0,  # turn records and steps, without text: kept so trends outlive the chats
    # Chat actions (Feature 019): off until an admin enables them, since they write to shared data
    "actions_enabled": False,
    "actions_allowed": list(WRITE_ACTIONS),
    "actions_reminder_minutes": 15,
    "actions_outlook_freebusy": False,  # Outlook free/busy via Graph, once the tenant probe confirms it works
    # Connectors (spec 023): GitHub, read-only, with each user's own token. Off until an admin registers the
    # instance's GitHub App and enters its ID and secret; the tokens' key is INDICO_ASSISTANT_CONNECTOR_KEY.
    "github_enabled": False,
    "github_client_id": None,
    "github_client_secret": None,
    "github_app_url": None,  # the app's public page (https://github.com/apps/<slug>), for "add repositories"
    "github_timeout_seconds": 10,
    # Citation settings (Feature 015)
    "base_url": "http://localhost:8000",  # Base URL for citation links (event pages, attachments)
}

EVENT_SETTINGS_DEFAULTS = {
    "enabled": None,  # None = inherit from global
    "custom_system_prompt": None,
    "allowed_tables": None,  # None = all tables allowed
    "nl2sql_enabled": None,
}
