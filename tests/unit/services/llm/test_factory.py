"""Unit tests for LLM client factory.

These tests verify that the factory correctly creates Instructor clients
for different providers.
"""

import pytest
from unittest.mock import patch, MagicMock

from indico_assistant.services.llm.factory import (
    create_instructor_client,
    _create_ollama_client,
    _create_huggingface_client,
    _create_openai_client,
)


class TestOllamaProvider:
    """Tests for Ollama provider client creation."""
    
    @patch("indico_assistant.services.llm.factory.instructor")
    @patch("indico_assistant.services.llm.factory.OpenAI")
    def test_ollama_client_creation(self, mock_openai, mock_instructor):
        """create_instructor_client creates Ollama client correctly."""
        mock_openai_instance = MagicMock()
        mock_openai.return_value = mock_openai_instance
        mock_instructor_instance = MagicMock()
        mock_instructor.from_openai.return_value = mock_instructor_instance
        
        client = create_instructor_client(
            provider="ollama",
            model="llama3.2",
            base_url="http://localhost:11434"
        )
        
        # Verify OpenAI client was created with Ollama URL
        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args.kwargs
        assert "localhost:11434" in call_kwargs["base_url"]
        assert call_kwargs["api_key"] == "ollama"
        
        # Verify instructor wrapper was created
        mock_instructor.from_openai.assert_called_once()
    
    @patch("indico_assistant.services.llm.factory.instructor")
    @patch("indico_assistant.services.llm.factory.OpenAI")
    def test_ollama_default_base_url(self, mock_openai, mock_instructor):
        """Ollama uses default localhost URL when not specified."""
        create_instructor_client(
            provider="ollama",
            model="llama3.2"
        )
        
        call_kwargs = mock_openai.call_args.kwargs
        assert "localhost:11434" in call_kwargs["base_url"]
    
    @patch("indico_assistant.services.llm.factory.instructor")
    @patch("indico_assistant.services.llm.factory.OpenAI")
    def test_ollama_adds_v1_suffix(self, mock_openai, mock_instructor):
        """Ollama base URL gets /v1 suffix added."""
        create_instructor_client(
            provider="ollama",
            model="llama3.2",
            base_url="http://custom:8080"
        )
        
        call_kwargs = mock_openai.call_args.kwargs
        assert call_kwargs["base_url"].endswith("/v1")


class TestHuggingFaceProvider:
    """Tests for HuggingFace provider client creation."""
    
    @patch("indico_assistant.services.llm.factory.instructor")
    @patch("indico_assistant.services.llm.factory.OpenAI")
    def test_huggingface_client_creation(self, mock_openai, mock_instructor):
        """create_instructor_client creates HuggingFace client correctly."""
        mock_openai_instance = MagicMock()
        mock_openai.return_value = mock_openai_instance
        
        client = create_instructor_client(
            provider="huggingface",
            model="meta-llama/Llama-3-8b",
            api_key="hf_test_key"
        )
        
        # Verify OpenAI client was created with HF URL
        call_kwargs = mock_openai.call_args.kwargs
        assert "huggingface.co" in call_kwargs["base_url"]
        assert call_kwargs["api_key"] == "hf_test_key"
    
    def test_huggingface_requires_api_key(self):
        """HuggingFace raises error when API key not provided."""
        with pytest.raises(ValueError, match="API key"):
            create_instructor_client(
                provider="huggingface",
                model="meta-llama/Llama-3-8b"
            )
    
    @patch("indico_assistant.services.llm.factory.instructor")
    @patch("indico_assistant.services.llm.factory.OpenAI")
    def test_huggingface_custom_base_url(self, mock_openai, mock_instructor):
        """HuggingFace accepts custom base URL."""
        create_instructor_client(
            provider="huggingface",
            model="model",
            base_url="https://custom-hf.example.com/v1/",
            api_key="hf_key"
        )
        
        call_kwargs = mock_openai.call_args.kwargs
        assert call_kwargs["base_url"] == "https://custom-hf.example.com/v1/"


class TestOpenAIProvider:
    """Tests for OpenAI-compatible provider client creation."""
    
    @patch("indico_assistant.services.llm.factory.instructor")
    @patch("indico_assistant.services.llm.factory.OpenAI")
    def test_openai_client_creation(self, mock_openai, mock_instructor):
        """create_instructor_client creates OpenAI client correctly."""
        mock_openai_instance = MagicMock()
        mock_openai.return_value = mock_openai_instance
        
        client = create_instructor_client(
            provider="openai",
            model="gpt-4",
            api_key="sk-test-key"
        )
        
        # Verify OpenAI client was created
        call_kwargs = mock_openai.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-test-key"
        
        # Verify instructor wrapper was created with TOOLS mode
        mock_instructor.from_openai.assert_called_once()
    
    def test_openai_requires_api_key_without_base_url(self):
        """OpenAI raises error when API key not provided and no base URL."""
        with pytest.raises(ValueError, match="API key"):
            create_instructor_client(
                provider="openai",
                model="gpt-4"
            )
    
    @patch("indico_assistant.services.llm.factory.instructor")
    @patch("indico_assistant.services.llm.factory.OpenAI")
    def test_openai_compatible_with_base_url(self, mock_openai, mock_instructor):
        """OpenAI-compatible provider with custom base URL."""
        create_instructor_client(
            provider="openai",
            model="local-model",
            base_url="http://local-api:8080/v1",
            api_key="local-key"
        )
        
        call_kwargs = mock_openai.call_args.kwargs
        assert call_kwargs["base_url"] == "http://local-api:8080/v1"
        assert call_kwargs["api_key"] == "local-key"


class TestUnsupportedProvider:
    """Tests for unsupported provider handling."""
    
    def test_unsupported_provider_without_config(self):
        """Unsupported provider without base_url/api_key raises error."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            create_instructor_client(
                provider="unknown_provider",
                model="some-model"
            )
    
    @patch("indico_assistant.services.llm.factory.instructor")
    @patch("indico_assistant.services.llm.factory.OpenAI")
    def test_unknown_provider_with_full_config(self, mock_openai, mock_instructor):
        """Unknown provider with base_url and api_key uses generic OpenAI client."""
        create_instructor_client(
            provider="custom_provider",
            model="custom-model",
            base_url="https://custom-api.example.com/v1",
            api_key="custom-key"
        )
        
        # Should use generic OpenAI-compatible client
        call_kwargs = mock_openai.call_args.kwargs
        assert call_kwargs["base_url"] == "https://custom-api.example.com/v1"
        assert call_kwargs["api_key"] == "custom-key"
    
    def test_none_provider_treated_as_empty(self):
        """None provider string is treated as unsupported."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            create_instructor_client(
                provider="",
                model="model"
            )


class TestProviderCaseInsensitivity:
    """Tests for case-insensitive provider names."""
    
    @patch("indico_assistant.services.llm.factory.instructor")
    @patch("indico_assistant.services.llm.factory.OpenAI")
    def test_ollama_case_insensitive(self, mock_openai, mock_instructor):
        """Ollama provider name is case-insensitive."""
        for name in ["ollama", "OLLAMA", "Ollama", "OlLaMa"]:
            mock_openai.reset_mock()
            create_instructor_client(provider=name, model="llama3.2")
            assert mock_openai.called
    
    @patch("indico_assistant.services.llm.factory.instructor")
    @patch("indico_assistant.services.llm.factory.OpenAI")
    def test_huggingface_case_insensitive(self, mock_openai, mock_instructor):
        """HuggingFace provider name is case-insensitive."""
        for name in ["huggingface", "HUGGINGFACE", "HuggingFace"]:
            mock_openai.reset_mock()
            create_instructor_client(provider=name, model="model", api_key="key")
            assert mock_openai.called
    
    @patch("indico_assistant.services.llm.factory.instructor")
    @patch("indico_assistant.services.llm.factory.OpenAI")
    def test_openai_case_insensitive(self, mock_openai, mock_instructor):
        """OpenAI provider name is case-insensitive."""
        for name in ["openai", "OPENAI", "OpenAI"]:
            mock_openai.reset_mock()
            create_instructor_client(provider=name, model="gpt-4", api_key="key")
            assert mock_openai.called
