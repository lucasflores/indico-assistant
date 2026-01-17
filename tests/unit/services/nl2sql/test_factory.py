# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Unit tests for NL2SQL factory functions.

Feature: 007-tdd-gap-analysis (GAP-011)
Priority: HIGH
Coverage Target: ≥80%

Tests the NL2SQL pipeline factory:
- Pipeline creation with defaults
- Pipeline creation with custom settings
- Plugin-based pipeline creation
- Cache configuration
- Error handling
"""

import pytest
from unittest.mock import MagicMock, Mock, patch, PropertyMock

from indico_assistant.services.nl2sql.factory import (
    create_nl2sql_pipeline,
    create_nl2sql_pipeline_from_plugin,
)


class TestCreateNL2SQLPipeline:
    """Tests for create_nl2sql_pipeline factory function."""
    
    @pytest.fixture
    def mock_llm_service(self):
        """Create a mock LLM service."""
        return MagicMock()
    
    @patch('indico_assistant.services.nl2sql.factory.NL2SQLPipeline')
    @patch('indico_assistant.services.nl2sql.factory.SchemaContext')
    @patch('indico_assistant.services.nl2sql.factory.QueryCache')
    def test_create_pipeline_with_defaults(
        self, mock_cache_class, mock_schema_class, mock_pipeline_class, mock_llm_service
    ):
        """Test creating pipeline with default settings."""
        mock_schema = MagicMock()
        mock_schema_class.return_value = mock_schema
        
        mock_cache = MagicMock()
        mock_cache_class.return_value = mock_cache
        
        mock_pipeline = MagicMock()
        mock_pipeline_class.return_value = mock_pipeline
        
        result = create_nl2sql_pipeline(llm_service=mock_llm_service)
        
        assert result == mock_pipeline
        
        # Verify defaults
        mock_cache_class.assert_called_once_with(
            ttl_seconds=600,
            max_entries=1000
        )
        mock_pipeline_class.assert_called_once()
        call_kwargs = mock_pipeline_class.call_args[1]
        
        assert call_kwargs['llm_service'] == mock_llm_service
        assert call_kwargs['max_rows'] == 1000
        assert call_kwargs['timeout_seconds'] == 30
        assert call_kwargs['max_correction_attempts'] == 3
    
    @patch('indico_assistant.services.nl2sql.factory.NL2SQLPipeline')
    @patch('indico_assistant.services.nl2sql.factory.SchemaContext')
    @patch('indico_assistant.services.nl2sql.factory.QueryCache')
    def test_create_pipeline_with_custom_settings(
        self, mock_cache_class, mock_schema_class, mock_pipeline_class, mock_llm_service
    ):
        """Test creating pipeline with custom settings."""
        mock_schema = MagicMock()
        mock_schema_class.return_value = mock_schema
        
        result = create_nl2sql_pipeline(
            llm_service=mock_llm_service,
            schema_file_path="/custom/schema.yaml",
            max_rows=500,
            timeout_seconds=60,
            max_correction_attempts=5,
            cache_ttl_seconds=300,
            cache_max_entries=500,
        )
        
        # Verify custom settings
        mock_schema_class.assert_called_once_with("/custom/schema.yaml")
        mock_cache_class.assert_called_once_with(
            ttl_seconds=300,
            max_entries=500
        )
        
        call_kwargs = mock_pipeline_class.call_args[1]
        assert call_kwargs['max_rows'] == 500
        assert call_kwargs['timeout_seconds'] == 60
        assert call_kwargs['max_correction_attempts'] == 5
    
    @patch('indico_assistant.services.nl2sql.factory.NL2SQLPipeline')
    @patch('indico_assistant.services.nl2sql.factory.SchemaContext')
    def test_create_pipeline_without_cache(
        self, mock_schema_class, mock_pipeline_class, mock_llm_service
    ):
        """Test creating pipeline with cache disabled."""
        result = create_nl2sql_pipeline(
            llm_service=mock_llm_service,
            enable_cache=False
        )
        
        call_kwargs = mock_pipeline_class.call_args[1]
        assert call_kwargs['cache'] is None
    
    @patch('indico_assistant.services.nl2sql.factory.NL2SQLPipeline')
    @patch('indico_assistant.services.nl2sql.factory.SchemaContext')
    @patch('indico_assistant.services.nl2sql.factory.QueryCache')
    def test_create_pipeline_with_allowed_tables(
        self, mock_cache_class, mock_schema_class, mock_pipeline_class, mock_llm_service
    ):
        """Test creating pipeline with allowed tables restriction."""
        allowed_tables = ['events', 'registrations', 'categories']
        
        result = create_nl2sql_pipeline(
            llm_service=mock_llm_service,
            allowed_tables=allowed_tables
        )
        
        call_kwargs = mock_pipeline_class.call_args[1]
        assert call_kwargs['allowed_tables'] == allowed_tables
    
    @patch('indico_assistant.services.nl2sql.factory.NL2SQLPipeline')
    @patch('indico_assistant.services.nl2sql.factory.SchemaContext')
    @patch('indico_assistant.services.nl2sql.factory.QueryCache')
    @patch('indico.core.db.db')
    def test_create_pipeline_default_session_factory(
        self, mock_db, mock_cache_class, mock_schema_class, mock_pipeline_class, mock_llm_service
    ):
        """Test that default db session factory is created."""
        mock_session = MagicMock()
        mock_db.session = mock_session
        
        result = create_nl2sql_pipeline(llm_service=mock_llm_service)
        
        # Verify a session factory was provided
        call_kwargs = mock_pipeline_class.call_args[1]
        assert call_kwargs['db_session_factory'] is not None
        
        # Test the session factory returns the db session
        factory = call_kwargs['db_session_factory']
        assert factory() == mock_session
    
    @patch('indico_assistant.services.nl2sql.factory.NL2SQLPipeline')
    @patch('indico_assistant.services.nl2sql.factory.SchemaContext')
    @patch('indico_assistant.services.nl2sql.factory.QueryCache')
    def test_create_pipeline_custom_session_factory(
        self, mock_cache_class, mock_schema_class, mock_pipeline_class, mock_llm_service
    ):
        """Test creating pipeline with custom session factory."""
        custom_session = MagicMock()
        custom_factory = lambda: custom_session
        
        result = create_nl2sql_pipeline(
            llm_service=mock_llm_service,
            db_session_factory=custom_factory
        )
        
        call_kwargs = mock_pipeline_class.call_args[1]
        assert call_kwargs['db_session_factory'] == custom_factory


class TestCreateNL2SQLPipelineFromPlugin:
    """Tests for create_nl2sql_pipeline_from_plugin factory function."""
    
    @pytest.fixture
    def mock_plugin(self):
        """Create a mock plugin with settings."""
        plugin = MagicMock()
        plugin.settings = {
            'nl2sql_timeout': 45,
            'nl2sql_max_rows': 2000,
            'nl2sql_max_corrections': 5,
            'nl2sql_cache_ttl': 1200,
            'nl2sql_allowed_tables': ['events', 'categories']
        }
        return plugin
    
    @patch('indico_assistant.services.nl2sql.factory.create_nl2sql_pipeline')
    @patch('indico_assistant.services.llm.create_llm_service')
    def test_create_pipeline_from_plugin(
        self, mock_create_llm, mock_create_pipeline, mock_plugin
    ):
        """Test creating pipeline from plugin settings."""
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        
        mock_pipeline = MagicMock()
        mock_create_pipeline.return_value = mock_pipeline
        
        result = create_nl2sql_pipeline_from_plugin(mock_plugin)
        
        assert result == mock_pipeline
        mock_create_llm.assert_called_once_with(mock_plugin)
        mock_create_pipeline.assert_called_once()
        
        # Verify settings were passed
        call_kwargs = mock_create_pipeline.call_args[1]
        assert call_kwargs['llm_service'] == mock_llm
        assert call_kwargs['timeout_seconds'] == 45
        assert call_kwargs['max_rows'] == 2000
        assert call_kwargs['max_correction_attempts'] == 5
        assert call_kwargs['cache_ttl_seconds'] == 1200
        assert call_kwargs['allowed_tables'] == ['events', 'categories']
    
    @patch('indico_assistant.services.nl2sql.factory.create_nl2sql_pipeline')
    @patch('indico_assistant.services.llm.create_llm_service')
    def test_create_pipeline_from_plugin_defaults(
        self, mock_create_llm, mock_create_pipeline
    ):
        """Test creating pipeline with default settings when not specified."""
        mock_plugin = MagicMock()
        mock_plugin.settings = {}  # Empty settings
        
        mock_llm = MagicMock()
        mock_create_llm.return_value = mock_llm
        
        result = create_nl2sql_pipeline_from_plugin(mock_plugin)
        
        call_kwargs = mock_create_pipeline.call_args[1]
        
        # Should use default values
        assert call_kwargs['timeout_seconds'] == 30
        assert call_kwargs['max_rows'] == 1000
        assert call_kwargs['max_correction_attempts'] == 3
        assert call_kwargs['cache_ttl_seconds'] == 600
    
    @patch('indico_assistant.services.nl2sql.factory.create_nl2sql_pipeline')
    @patch('indico_assistant.services.llm.create_llm_service')
    def test_create_pipeline_cache_disabled_when_ttl_zero(
        self, mock_create_llm, mock_create_pipeline
    ):
        """Test that cache is disabled when TTL is 0."""
        mock_plugin = MagicMock()
        mock_plugin.settings = {'nl2sql_cache_ttl': 0}
        
        result = create_nl2sql_pipeline_from_plugin(mock_plugin)
        
        call_kwargs = mock_create_pipeline.call_args[1]
        assert call_kwargs['enable_cache'] is False
    
    @patch('indico_assistant.services.nl2sql.factory.create_nl2sql_pipeline')
    @patch('indico_assistant.services.llm.create_llm_service')
    def test_create_pipeline_cache_enabled_when_ttl_positive(
        self, mock_create_llm, mock_create_pipeline
    ):
        """Test that cache is enabled when TTL is positive."""
        mock_plugin = MagicMock()
        mock_plugin.settings = {'nl2sql_cache_ttl': 300}
        
        result = create_nl2sql_pipeline_from_plugin(mock_plugin)
        
        call_kwargs = mock_create_pipeline.call_args[1]
        assert call_kwargs['enable_cache'] is True
    
    @patch('indico_assistant.services.nl2sql.factory.create_nl2sql_pipeline')
    @patch('indico_assistant.services.llm.create_llm_service')
    def test_create_pipeline_allowed_tables_none(
        self, mock_create_llm, mock_create_pipeline
    ):
        """Test that allowed_tables can be None."""
        mock_plugin = MagicMock()
        mock_plugin.settings = {'nl2sql_allowed_tables': None}
        
        result = create_nl2sql_pipeline_from_plugin(mock_plugin)
        
        call_kwargs = mock_create_pipeline.call_args[1]
        assert call_kwargs['allowed_tables'] is None


class TestFactoryEdgeCases:
    """Tests for edge cases in factory functions."""
    
    @patch('indico_assistant.services.nl2sql.factory.NL2SQLPipeline')
    @patch('indico_assistant.services.nl2sql.factory.SchemaContext')
    @patch('indico_assistant.services.nl2sql.factory.QueryCache')
    def test_create_pipeline_minimum_values(
        self, mock_cache_class, mock_schema_class, mock_pipeline_class
    ):
        """Test creating pipeline with minimum valid values."""
        mock_llm = MagicMock()
        
        result = create_nl2sql_pipeline(
            llm_service=mock_llm,
            max_rows=1,
            timeout_seconds=1,
            max_correction_attempts=0,
            cache_ttl_seconds=1,
            cache_max_entries=1
        )
        
        call_kwargs = mock_pipeline_class.call_args[1]
        assert call_kwargs['max_rows'] == 1
        assert call_kwargs['timeout_seconds'] == 1
        assert call_kwargs['max_correction_attempts'] == 0
    
    @patch('indico_assistant.services.nl2sql.factory.NL2SQLPipeline')
    @patch('indico_assistant.services.nl2sql.factory.SchemaContext')
    @patch('indico_assistant.services.nl2sql.factory.QueryCache')
    def test_create_pipeline_empty_allowed_tables(
        self, mock_cache_class, mock_schema_class, mock_pipeline_class
    ):
        """Test creating pipeline with empty allowed_tables list."""
        mock_llm = MagicMock()
        
        result = create_nl2sql_pipeline(
            llm_service=mock_llm,
            allowed_tables=[]
        )
        
        call_kwargs = mock_pipeline_class.call_args[1]
        assert call_kwargs['allowed_tables'] == []
    
    @patch('indico_assistant.services.nl2sql.factory.SchemaContext')
    def test_schema_context_creation_error(self, mock_schema_class):
        """Test handling of schema context creation errors."""
        mock_llm = MagicMock()
        mock_schema_class.side_effect = FileNotFoundError("Schema file not found")
        
        with pytest.raises(FileNotFoundError):
            create_nl2sql_pipeline(
                llm_service=mock_llm,
                schema_file_path="/nonexistent/schema.yaml"
            )
    
    @patch('indico_assistant.services.llm.create_llm_service')
    def test_llm_service_creation_error(self, mock_create_llm):
        """Test handling of LLM service creation errors."""
        mock_plugin = MagicMock()
        mock_create_llm.side_effect = RuntimeError("LLM service unavailable")
        
        with pytest.raises(RuntimeError, match="LLM service unavailable"):
            create_nl2sql_pipeline_from_plugin(mock_plugin)


class TestFactoryIntegration:
    """Integration-style tests for factory functions."""
    
    @patch('indico_assistant.services.nl2sql.factory.NL2SQLPipeline')
    @patch('indico_assistant.services.nl2sql.factory.SchemaContext')
    @patch('indico_assistant.services.nl2sql.factory.QueryCache')
    def test_pipeline_receives_all_components(
        self, mock_cache_class, mock_schema_class, mock_pipeline_class
    ):
        """Test that pipeline receives all required components."""
        mock_llm = MagicMock()
        mock_schema = MagicMock()
        mock_cache = MagicMock()
        
        mock_schema_class.return_value = mock_schema
        mock_cache_class.return_value = mock_cache
        
        custom_factory = MagicMock()
        
        create_nl2sql_pipeline(
            llm_service=mock_llm,
            db_session_factory=custom_factory,
            enable_cache=True
        )
        
        call_kwargs = mock_pipeline_class.call_args[1]
        
        # Verify all components are provided
        assert call_kwargs['llm_service'] == mock_llm
        assert call_kwargs['schema_context'] == mock_schema
        assert call_kwargs['db_session_factory'] == custom_factory
        assert call_kwargs['cache'] == mock_cache
        assert 'max_rows' in call_kwargs
        assert 'timeout_seconds' in call_kwargs
        assert 'max_correction_attempts' in call_kwargs
        assert 'allowed_tables' in call_kwargs
