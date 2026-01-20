"""Test executor transaction isolation.

Feature 013: NL2SQL prompt optimization - transaction isolation fix
Tests that SQL execution errors don't roll back parent transaction.
"""

import pytest
from unittest.mock import Mock, MagicMock
from sqlalchemy.exc import SQLAlchemyError

from indico_assistant.services.nl2sql.executor import QueryExecutor


class TestExecutorTransactionIsolation:
    """Test that executor uses nested transactions to isolate errors."""
    
    def test_sql_error_does_not_rollback_parent_transaction(self):
        """SQL execution errors should not affect parent transaction.
        
        When SQL execution fails, the executor should use a nested
        transaction (SAVEPOINT) so that rollback only affects the
        query execution, not the parent transaction (e.g., chat session
        creation).
        
        Bug: Previously, executor called session.rollback() which rolled
        back the entire transaction, causing foreign key violations when
        trying to save error messages to chat_messages table.
        
        Fix: Use session.begin_nested() to create SAVEPOINT before query
        execution. Exceptions automatically roll back to SAVEPOINT without
        affecting parent transaction.
        """
        # Mock session with nested transaction support
        mock_session = Mock()
        mock_nested = MagicMock()
        mock_session.begin_nested.return_value.__enter__ = Mock(return_value=mock_nested)
        mock_session.begin_nested.return_value.__exit__ = Mock(return_value=False)
        
        # Simulate SQL error during execution
        mock_session.execute.side_effect = SQLAlchemyError("column does not exist")
        
        session_factory = Mock(return_value=mock_session)
        executor = QueryExecutor(session_factory, max_rows=100, timeout_seconds=10)
        
        # Execute query that will fail
        result = executor.execute("SELECT invalid_column FROM events")
        
        # Should return error result, not raise
        assert not result.success
        assert "column does not exist" in result.error_message
        
        # Should have created nested transaction
        mock_session.begin_nested.assert_called_once()
        
        # Should NOT have called session.rollback() explicitly
        # (nested transaction handles rollback automatically)
        mock_session.rollback.assert_not_called()
    
    def test_successful_query_uses_nested_transaction(self):
        """Successful queries should also use nested transactions for consistency."""
        # Mock session with nested transaction
        mock_session = Mock()
        mock_nested = MagicMock()
        mock_session.begin_nested.return_value.__enter__ = Mock(return_value=mock_nested)
        mock_session.begin_nested.return_value.__exit__ = Mock(return_value=False)
        
        # Mock successful query result
        mock_result = Mock()
        mock_result.keys.return_value = ['id', 'title']
        mock_result.fetchall.return_value = [(1, 'Test Event')]
        mock_session.execute.return_value = mock_result
        
        session_factory = Mock(return_value=mock_session)
        executor = QueryExecutor(session_factory, max_rows=100, timeout_seconds=10)
        
        # Execute successful query
        result = executor.execute("SELECT id, title FROM events LIMIT 1")
        
        # Should succeed
        assert result.success
        assert len(result.rows) == 1
        assert result.rows[0]['id'] == 1
        
        # Should have used nested transaction
        mock_session.begin_nested.assert_called_once()
        
        # No rollback should have been called
        mock_session.rollback.assert_not_called()
    
    def test_execution_error_does_not_call_rollback(self):
        """ExecutionError (validation errors) should not trigger rollback."""
        from indico_assistant.services.nl2sql.executor import ExecutionError
        
        mock_session = Mock()
        mock_nested = MagicMock()
        mock_session.begin_nested.return_value.__enter__ = Mock(
            side_effect=ExecutionError("Vector search not available")
        )
        mock_session.begin_nested.return_value.__exit__ = Mock(return_value=False)
        
        session_factory = Mock(return_value=mock_session)
        executor = QueryExecutor(session_factory, max_rows=100, timeout_seconds=10)
        
        # Execute query that triggers validation error
        result = executor.execute("SELECT * FROM events WHERE embedding <-> :query_vector")
        
        # Should return error result
        assert not result.success
        assert "Vector search" in result.error_message or "Unexpected error" in result.error_message
        
        # No explicit rollback
        mock_session.rollback.assert_not_called()
    
    def test_generic_exception_does_not_call_rollback(self):
        """Generic exceptions should not trigger explicit rollback."""
        mock_session = Mock()
        mock_nested = MagicMock()
        mock_session.begin_nested.return_value.__enter__ = Mock(
            side_effect=RuntimeError("Unexpected database error")
        )
        mock_session.begin_nested.return_value.__exit__ = Mock(return_value=False)
        
        session_factory = Mock(return_value=mock_session)
        executor = QueryExecutor(session_factory, max_rows=100, timeout_seconds=10)
        
        # Execute query that triggers generic error
        result = executor.execute("SELECT * FROM events")
        
        # Should return error result
        assert not result.success
        assert "Unexpected error" in result.error_message
        
        # No explicit rollback
        mock_session.rollback.assert_not_called()
