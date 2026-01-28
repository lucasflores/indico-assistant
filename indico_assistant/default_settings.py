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
    "max_tokens": 4096,
    # NL2SQL pipeline defaults (Feature 003)
    "nl2sql_enabled": True,
    "nl2sql_timeout": 30,
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
    # Citation settings (Feature 015)
    "base_url": "http://localhost:8000",  # Base URL for citation links (event pages, attachments)
}

EVENT_SETTINGS_DEFAULTS = {
    "enabled": None,  # None = inherit from global
    "custom_system_prompt": None,
    "allowed_tables": None,  # None = all tables allowed
    "nl2sql_enabled": None,
}
