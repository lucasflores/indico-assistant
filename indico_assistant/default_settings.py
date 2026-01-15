"""Default settings for the Indico Assistant plugin.

These values are used when no settings have been configured by an administrator.
"""

DEFAULT_SETTINGS = {
    "enabled": True,
    "llm_provider": "ollama",
    "llm_model": "llama3.2",
    "llm_base_url": "http://localhost:11434",
    "llm_api_key": None,
    "timeout_seconds": 30,
    "max_tokens": 2048,
    "max_retries": 2,
    # Langfuse observability settings (Feature 005)
    "langfuse_enabled": False,
    "langfuse_host": "https://cloud.langfuse.com",
    "langfuse_public_key": None,
    "langfuse_secret_key": None,
    "langfuse_privacy_level": "metadata",  # "metadata", "masked", or "full"
}

EVENT_SETTINGS_DEFAULTS = {
    "enabled": None,  # None = inherit from global
    "custom_system_prompt": None,
    "allowed_tables": None,  # None = all tables allowed
}
