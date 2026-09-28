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

DEFAULT_SETTINGS = {
    "enabled": True,
    "llm_provider": "ollama",
    "llm_model": "llama3.2",
    "llm_base_url": "http://localhost:11434",
    "llm_api_key": None,
    "timeout_seconds": 30,
    "max_tokens": 4096,
    # NL2SQL pipeline defaults (Feature 003)
    "nl2sql_enabled": True,
    "nl2sql_timeout": 10,
    "nl2sql_max_rows": 1000,
    "nl2sql_max_corrections": 3,
    "nl2sql_cache_ttl": 600,
    "nl2sql_allowed_tables": None,
    "max_retries": 2,
    # Langfuse observability settings (Feature 005)
    "langfuse_enabled": False,
    "langfuse_host": "https://cloud.langfuse.com",
    "langfuse_public_key": None,
    "langfuse_secret_key": None,
    "langfuse_privacy_level": "metadata",  # "metadata", "masked", or "full"
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
    "retention_error_days": 30,
    "retention_sync_log_days": 90,
    "retention_plan_days": 90,  # chat action plans (their audit trail; undo only reaches back 24 h)
    # Chat actions (Feature 019): off until an admin enables them, since they write to shared data
    "actions_enabled": False,
    "actions_allowed": list(WRITE_ACTIONS),
    "actions_reminder_minutes": 15,
    "actions_outlook_freebusy": False,  # Outlook free/busy via Graph, once the tenant probe confirms it works
    # Citation settings (Feature 015)
    "base_url": "http://localhost:8000",  # Base URL for citation links (event pages, attachments)
}

EVENT_SETTINGS_DEFAULTS = {
    "enabled": None,  # None = inherit from global
    "custom_system_prompt": None,
    "allowed_tables": None,  # None = all tables allowed
    "nl2sql_enabled": None,
}
