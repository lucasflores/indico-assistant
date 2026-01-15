"""Unit tests for the settings forms."""

import pytest
from unittest.mock import MagicMock, patch


class TestSettingsForm:
    """Tests for the global SettingsForm."""

    def test_settings_form_has_required_fields(self):
        """SettingsForm should have all required fields."""
        from indico_assistant.forms import SettingsForm

        # Check field existence
        assert hasattr(SettingsForm, "enabled")
        assert hasattr(SettingsForm, "llm_provider")
        assert hasattr(SettingsForm, "llm_model")
        assert hasattr(SettingsForm, "llm_base_url")
        assert hasattr(SettingsForm, "llm_api_key")
        assert hasattr(SettingsForm, "timeout_seconds")
        assert hasattr(SettingsForm, "max_tokens")

    def test_llm_provider_choices(self):
        """LLM provider should have expected choices."""
        from indico_assistant.forms import SettingsForm

        provider_field = SettingsForm.llm_provider
        choices = [c[0] for c in provider_field.kwargs.get("choices", [])]

        assert "ollama" in choices
        assert "huggingface" in choices
        assert "openai" in choices

    def test_timeout_validation_range(self):
        """Timeout should validate between 5 and 300 seconds."""
        from wtforms.validators import NumberRange
        from indico_assistant.forms import SettingsForm

        timeout_field = SettingsForm.timeout_seconds
        validators = timeout_field.kwargs.get("validators", [])

        # Find NumberRange validator
        range_validator = None
        for v in validators:
            if isinstance(v, NumberRange):
                range_validator = v
                break

        assert range_validator is not None
        assert range_validator.min == 5
        assert range_validator.max == 300

    def test_max_tokens_validation_range(self):
        """Max tokens should validate between 100 and 32000."""
        from wtforms.validators import NumberRange
        from indico_assistant.forms import SettingsForm

        max_tokens_field = SettingsForm.max_tokens
        validators = max_tokens_field.kwargs.get("validators", [])

        # Find NumberRange validator
        range_validator = None
        for v in validators:
            if isinstance(v, NumberRange):
                range_validator = v
                break

        assert range_validator is not None
        assert range_validator.min == 100
        assert range_validator.max == 32000

    def test_api_key_is_password_field(self):
        """API key field should be a PasswordField for masking."""
        from wtforms.fields import PasswordField
        from indico_assistant.forms import SettingsForm

        api_key_field = SettingsForm.llm_api_key
        assert api_key_field.field_class == PasswordField


class TestEventSettingsForm:
    """Tests for the per-event EventSettingsForm."""

    def test_event_settings_form_has_required_fields(self):
        """EventSettingsForm should have all required fields."""
        from indico_assistant.forms import EventSettingsForm

        assert hasattr(EventSettingsForm, "enabled")
        assert hasattr(EventSettingsForm, "custom_system_prompt")
        assert hasattr(EventSettingsForm, "allowed_tables")

    def test_enabled_has_inherit_option(self):
        """Enabled field should have 'inherit from global' option."""
        from indico_assistant.forms import EventSettingsForm

        enabled_field = EventSettingsForm.enabled
        choices = [c[0] for c in enabled_field.kwargs.get("choices", [])]

        assert "" in choices  # Empty string for inherit
        assert "true" in choices
        assert "false" in choices


class TestFormValidation:
    """Tests for form validation logic."""

    def test_url_validation_accepts_valid_url(self):
        """URL field should accept valid URLs."""
        from wtforms.validators import URL
        from indico_assistant.forms import SettingsForm

        url_field = SettingsForm.llm_base_url
        validators = url_field.kwargs.get("validators", [])

        # Check URL validator is present
        has_url_validator = any(isinstance(v, URL) for v in validators)
        assert has_url_validator

    def test_required_fields_have_validators(self):
        """Required fields should have DataRequired validator."""
        from wtforms.validators import DataRequired
        from indico_assistant.forms import SettingsForm

        required_fields = ["llm_provider", "llm_model", "timeout_seconds", "max_tokens"]

        for field_name in required_fields:
            field = getattr(SettingsForm, field_name)
            validators = field.kwargs.get("validators", [])
            has_required = any(isinstance(v, DataRequired) for v in validators)
            assert has_required, f"Field {field_name} should have DataRequired validator"
