"""Client factory for LLM providers.

This module provides factory functions to create Instructor clients
for different LLM providers.
"""

from __future__ import annotations

import logging
from typing import Any

import instructor
from openai import OpenAI

from indico_assistant.services.llm.errors import LLMError, ErrorType


logger = logging.getLogger(__name__)


def create_instructor_client(
    provider: str,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
) -> instructor.Instructor:
    """Create an Instructor client for the specified provider.
    
    Args:
        provider: Provider name ("ollama", "huggingface", "openai", or other OpenAI-compatible).
        model: Model name to use.
        base_url: Optional custom base URL for the provider.
        api_key: Optional API key for authentication.
    
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
    else:
        # Try as generic OpenAI-compatible provider
        if base_url and api_key:
            logger.info(f"Using generic OpenAI-compatible client for provider: {provider}")
            return _create_openai_client(model, base_url, api_key)
        else:
            raise ValueError(
                f"Unsupported provider '{provider}'. Supported: ollama, huggingface, openai. "
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
    effective_base_url = base_url or "http://localhost:11434"
    
    # Ensure /v1 suffix for OpenAI compatibility
    if not effective_base_url.endswith("/v1"):
        effective_base_url = effective_base_url.rstrip("/") + "/v1"
    
    openai_client = OpenAI(
        base_url=effective_base_url,
        api_key="ollama",  # Ollama doesn't require auth but OpenAI client needs something
    )
    
    return instructor.from_openai(
        openai_client,
        mode=instructor.Mode.JSON,  # Ollama works best with JSON mode
    )


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
    
    effective_base_url = base_url or "https://api-inference.huggingface.co/v1/"
    
    openai_client = OpenAI(
        base_url=effective_base_url,
        api_key=api_key,
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
        client_kwargs["base_url"] = base_url
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        # For proxies that don't need auth
        client_kwargs["api_key"] = "not-needed"
    
    openai_client = OpenAI(**client_kwargs)
    
    # Use TOOLS mode for OpenAI as it supports function calling
    return instructor.from_openai(
        openai_client,
        mode=instructor.Mode.TOOLS,
    )
