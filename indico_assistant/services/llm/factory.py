"""Client factory for LLM providers.

This module provides factory functions to create Instructor clients
for different LLM providers.
"""

from __future__ import annotations

import logging
from typing import Any

import instructor
from openai import OpenAI

from indico_assistant.default_settings import DEFAULT_SETTINGS
from indico_assistant.services.llm.errors import LLMError, ErrorType


logger = logging.getLogger(__name__)


def _normalize_openai_base_url(base_url: str | None, default: str) -> str:
    """Normalize OpenAI-compatible base URLs to include /v1 suffix.

    Args:
        base_url: Provided base URL (may be None or missing /v1).
        default: Default base URL to use when base_url is not provided.

    Returns:
        Normalized base URL ending with /v1.
    """
    effective_base_url = base_url or default
    normalized = effective_base_url.rstrip("/")
    if not normalized.endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


#: How the ibis client asks for structured output, by the ``llm_ibis_mode`` setting; the keys are
#: default_settings.IBIS_MODE_CHOICES'. json_schema is NOT strict: instructor 1.15.1 sends no
#: ``strict`` in JSON_SCHEMA, and refuses its strict OpenRouter mode for an OpenAI client, so the
#: schema guides the model rather than binding it. Every mode is validated by instructor either way.
IBIS_MODES = {
    "tools": instructor.Mode.TOOLS,              # a function call carrying the schema
    "json_schema": instructor.Mode.JSON_SCHEMA,  # response_format with the schema, answered as content
    "md_json": instructor.Mode.MD_JSON,          # JSON asked for in the prompt and parsed from the text
}


def create_instructor_client(
    provider: str,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    ibis_mode: str | None = None,
) -> instructor.Instructor:
    """Create an Instructor client for the specified provider.
    
    Args:
        provider: Provider name ("ollama", "huggingface", "openai", "ibis", or other OpenAI-compatible).
        model: Model name to use.
        base_url: Optional custom base URL for the provider.
        api_key: Optional API key for authentication.
        ibis_mode: For the ibis provider, a key of ``IBIS_MODES``; None is the settings default.
    
    Returns:
        Configured Instructor client.
    
    Raises:
        LLMError: If the provider is not supported or configuration is invalid.
    
    Examples:
        >>> # Ollama (local)
        >>> client = create_instructor_client("ollama", "llama3.2")
        
        >>> # HuggingFace
        >>> client = create_instructor_client(
        ...     "huggingface",
        ...     "meta-llama/Llama-3-8b",
        ...     base_url="https://api-inference.huggingface.co/v1/",
        ...     api_key="hf_xxx"
        ... )
        
        >>> # OpenAI-compatible
        >>> client = create_instructor_client(
        ...     "openai",
        ...     "gpt-4",
        ...     api_key="sk-xxx"
        ... )
    """
    provider_lower = provider.lower() if provider else ""
    
    if provider_lower == "ollama":
        return _create_ollama_client(model, base_url)
    elif provider_lower == "huggingface":
        return _create_huggingface_client(model, base_url, api_key)
    elif provider_lower in ("openai", "openai-compatible"):
        return _create_openai_client(model, base_url, api_key)
    elif provider_lower == "ibis":
        return _create_ibis_client(base_url, api_key, ibis_mode)
    else:
        # Try as generic OpenAI-compatible provider
        if base_url and api_key:
            logger.info(f"Using generic OpenAI-compatible client for provider: {provider}")
            return _create_openai_client(model, base_url, api_key)
        else:
            raise ValueError(
                f"Unsupported provider '{provider}'. Supported: ollama, huggingface, openai, ibis. "
                f"For other providers, ensure base_url and api_key are configured."
            )


def _create_ollama_client(
    model: str,
    base_url: str | None = None,
) -> instructor.Instructor:
    """Create an Instructor client for Ollama.
    
    Ollama uses an OpenAI-compatible API, so we use the OpenAI client
    with Ollama's base URL.
    
    Args:
        model: Ollama model name (e.g., "llama3.2", "mistral").
        base_url: Ollama server URL (default: http://localhost:11434).
    
    Returns:
        Configured Instructor client for Ollama.
    """
    effective_base_url = _normalize_openai_base_url(
        base_url, "http://localhost:11434"
    )
    
    openai_client = OpenAI(
        base_url=effective_base_url,
        api_key="ollama",  # Ollama doesn't require auth but OpenAI client needs something
        http_client=_http_client(),
    )
    
    return instructor.from_openai(
        openai_client,
        mode=instructor.Mode.JSON,  # Ollama works best with JSON mode
    )


def _http_client():
    """The SDK's own HTTP client, telling the analytics step about every attempt (spec 024 FR-003): the SDK retries
    429s and 5xx on its own (every provider here but ibis keeps its default of 2), and instructor's hooks never see
    those retries."""
    from openai import DefaultHttpxClient

    from indico_assistant.services.analytics.recorder import count_attempt
    return DefaultHttpxClient(event_hooks={"response": [count_attempt]})


def _create_huggingface_client(
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
) -> instructor.Instructor:
    """Create an Instructor client for HuggingFace.
    
    HuggingFace provides an OpenAI-compatible endpoint through HF Router.
    
    Args:
        model: HuggingFace model name (e.g., "meta-llama/Llama-3-8b").
        base_url: HF Router URL (default: https://api-inference.huggingface.co/v1/).
        api_key: HuggingFace API token.
    
    Returns:
        Configured Instructor client for HuggingFace.
    
    Raises:
        ValueError: If api_key is not provided.
    """
    if not api_key:
        raise ValueError("HuggingFace provider requires an API key (llm_api_key setting)")
    
    effective_base_url = _normalize_openai_base_url(
        base_url, "https://router.huggingface.co"
    )
    
    openai_client = OpenAI(
        base_url=effective_base_url,
        api_key=api_key,
        http_client=_http_client(),
    )
    
    return instructor.from_openai(
        openai_client,
        mode=instructor.Mode.JSON,
    )


def _create_openai_client(
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
) -> instructor.Instructor:
    """Create an Instructor client for OpenAI or OpenAI-compatible providers.
    
    Args:
        model: Model name (e.g., "gpt-4", "gpt-3.5-turbo").
        base_url: Optional custom base URL for OpenAI-compatible providers.
        api_key: OpenAI API key (required unless using proxy).
    
    Returns:
        Configured Instructor client for OpenAI.
    
    Raises:
        ValueError: If api_key is not provided for OpenAI.
    """
    if not api_key and not base_url:
        raise ValueError("OpenAI provider requires an API key (llm_api_key setting)")
    
    client_kwargs: dict[str, Any] = {}
    if base_url:
        client_kwargs["base_url"] = _normalize_openai_base_url(base_url, base_url)
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        # For proxies that don't need auth
        client_kwargs["api_key"] = "not-needed"
    
    openai_client = OpenAI(**client_kwargs, http_client=_http_client())
    
    # Use TOOLS mode for OpenAI as it supports function calling
    return instructor.from_openai(
        openai_client,
        mode=instructor.Mode.TOOLS,
    )


def _create_ibis_client(
    base_url: str | None = None,
    api_key: str | None = None,
    mode: str | None = None,
) -> instructor.Instructor:
    """Create an Instructor client for the ibis router.

    The model setting picks the routing: ``ibis/<dial>`` (Frugal, Economy,
    Balanced, High, Max) routes, a concrete pool model id bypasses the router.

    ``mode`` picks how structured output is asked for (``IBIS_MODES``). ibis
    carries ``tools``/``tool_choice`` and ``response_format`` since
    2026-09-29 (ibis-api #17), routing only to models that can serve them.
    "md_json", the prompt-JSON form this client used while ibis refused them,
    stays the default until the acceptance sweep shows the others are no
    worse. SDK retries are off
    because a retried POST is a second routing decision and a second bill;
    instructor's validation retries still apply and each attempt is recorded
    by LLMService.

    Raises:
        ValueError: If api_key is not provided, or mode is not a known one.
    """
    if not api_key:
        raise ValueError("ibis provider requires an API key (sk-ibis-...)")
    chosen = IBIS_MODES.get((mode or DEFAULT_SETTINGS["llm_ibis_mode"]).lower())
    if chosen is None:
        raise ValueError(f"invalid configuration: llm_ibis_mode must be one of {', '.join(IBIS_MODES)}; "
                         f"got {mode!r}")

    openai_client = OpenAI(
        base_url=_normalize_openai_base_url(base_url, "https://labs.aithoth.com/ibis-api"),
        api_key=api_key,
        max_retries=0,
        http_client=_http_client(),
    )
    return instructor.from_openai(openai_client, mode=chosen)
