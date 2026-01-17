"""Unit tests for NL2SQL permissions module.

Feature: 007-tdd-gap-analysis
GAP: GAP-005 (Critical - Security)
Tasks: T032-T037

Tests the permission helpers for NL2SQL pipeline including:
- User permission filtering
- Admin full access
- Event-scoped access
- Unauthorized table access denial
"""

import pytest
from unittest.mock import MagicMock, patch

from indico_assistant.services.nl2sql.permissions import (
    get_user_accessible_event_ids,
    filter_results_by_permission,
    user_can_access_all_events,
)


class TestGetUserAccessibleEventIds:
    """Tests for get_user_accessible_event_ids function."""

    # =========================================================================
    # T033: test_filter_by_user_permissions
    # =========================================================================

    def test_filter_by_user_permissions_returns_accessible_events(self):
        """Test function returns events user can access."""
        mock_user = MagicMock()
        
        # Mock Event class and can_access
        mock_event_1 = MagicMock()
        mock_event_1.can_access.return_value = True
        
        mock_event_2 = MagicMock()
        mock_event_2.can_access.return_value = False
        
        mock_event_3 = MagicMock()
        mock_event_3.can_access.return_value = True
        
        with patch("indico.modules.events.Event") as MockEvent:
            with patch("indico.core.db.db") as mock_db:
                # Setup query mock
                mock_query = MagicMock()
                mock_query.filter.return_value = mock_query
                mock_query.all.return_value = [(1,), (2,), (3,)]
                mock_db.session.query.return_value = mock_query
                
                # Setup Event.get mock
                MockEvent.get.side_effect = lambda id: {
                    1: mock_event_1,
                    2: mock_event_2,
                    3: mock_event_3,
                }.get(id)
                
                result = get_user_accessible_event_ids(mock_user, event_ids=[1, 2, 3])
                
                # Should return only events 1 and 3 (accessible)
                assert 1 in result
                assert 2 not in result
                assert 3 in result

    def test_filter_by_user_permissions_none_user_returns_empty(self):
        """Test None user returns empty list."""
        result = get_user_accessible_event_ids(None, event_ids=[1, 2, 3])
        
        assert result == []

    def test_filter_by_user_permissions_empty_event_ids_returns_empty(self):
        """Test empty event_ids returns empty list."""
        mock_user = MagicMock()
        
        result = get_user_accessible_event_ids(mock_user, event_ids=[])
        
        assert result == []

    def test_filter_by_user_permissions_import_error_fallback(self):
        """Test ImportError fallback returns event_ids as-is."""
        mock_user = MagicMock()
        
        # Mock the module import to simulate IndoError
        # We need to patch builtins.__import__ to simulate a real import failure
        import builtins
        original_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if name == "indico.modules.events" or name.startswith("indico.modules.events"):
                raise ImportError("No indico")
            return original_import(name, *args, **kwargs)
        
        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = get_user_accessible_event_ids(mock_user, event_ids=[1, 2, 3])
            
            # Fallback returns the provided event_ids
            assert result == [1, 2, 3]

    # =========================================================================
    # T034: test_admin_full_access
    # =========================================================================

    def test_admin_full_access_returns_all_events(self):
        """Test admin user gets access to all requested events."""
        mock_admin = MagicMock()
        
        # Create events that all grant access to admin
        mock_events = {}
        for i in [1, 2, 3, 4, 5]:
            event = MagicMock()
            event.can_access.return_value = True  # Admin has access to all
            mock_events[i] = event
        
        with patch("indico.modules.events.Event") as MockEvent:
            with patch("indico.core.db.db") as mock_db:
                mock_query = MagicMock()
                mock_query.filter.return_value = mock_query
                mock_query.all.return_value = [(i,) for i in [1, 2, 3, 4, 5]]
                mock_db.session.query.return_value = mock_query
                
                MockEvent.get.side_effect = lambda id: mock_events.get(id)
                
                result = get_user_accessible_event_ids(
                    mock_admin, 
                    event_ids=[1, 2, 3, 4, 5]
                )
                
                assert len(result) == 5
                assert set(result) == {1, 2, 3, 4, 5}

    # =========================================================================
    # T035: test_event_scoped_access
    # =========================================================================

    def test_event_scoped_access_filters_correctly(self):
        """Test event-scoped access returns only accessible events."""
        mock_user = MagicMock()
        
        # User can access events 1 and 3, but not 2
        mock_event_1 = MagicMock()
        mock_event_1.can_access.return_value = True
        
        mock_event_2 = MagicMock()
        mock_event_2.can_access.return_value = False  # No access
        
        mock_event_3 = MagicMock()
        mock_event_3.can_access.return_value = True
        
        with patch("indico.modules.events.Event") as MockEvent:
            with patch("indico.core.db.db") as mock_db:
                mock_query = MagicMock()
                mock_query.filter.return_value = mock_query
                mock_query.all.return_value = [(1,), (2,), (3,)]
                mock_db.session.query.return_value = mock_query
                
                MockEvent.get.side_effect = lambda id: {
                    1: mock_event_1,
                    2: mock_event_2,
                    3: mock_event_3,
                }.get(id)
                
                result = get_user_accessible_event_ids(
                    mock_user, 
                    event_ids=[1, 2, 3]
                )
                
                assert result == [1, 3]

    def test_event_scoped_access_handles_missing_event(self):
        """Test function handles case where Event.get returns None."""
        mock_user = MagicMock()
        
        mock_event_1 = MagicMock()
        mock_event_1.can_access.return_value = True
        
        with patch("indico.modules.events.Event") as MockEvent:
            with patch("indico.core.db.db") as mock_db:
                mock_query = MagicMock()
                mock_query.filter.return_value = mock_query
                mock_query.all.return_value = [(1,), (999,)]  # 999 doesn't exist
                mock_db.session.query.return_value = mock_query
                
                MockEvent.get.side_effect = lambda id: {
                    1: mock_event_1,
                    999: None,  # Event doesn't exist
                }.get(id)
                
                result = get_user_accessible_event_ids(
                    mock_user, 
                    event_ids=[1, 999]
                )
                
                # Only event 1 should be returned
                assert result == [1]


class TestFilterResultsByPermission:
    """Tests for filter_results_by_permission function."""

    # =========================================================================
    # T036: test_deny_unauthorized_tables (via result filtering)
    # =========================================================================

    def test_filter_results_removes_unauthorized_rows(self):
        """Test filter removes rows from inaccessible events."""
        mock_user = MagicMock()
        
        results = [
            {"event_id": 1, "title": "Event 1"},
            {"event_id": 2, "title": "Event 2"},  # User can't access
            {"event_id": 3, "title": "Event 3"},
        ]
        
        with patch(
            "indico_assistant.services.nl2sql.permissions.get_user_accessible_event_ids"
        ) as mock_get_ids:
            # User can only access events 1 and 3
            mock_get_ids.return_value = [1, 3]
            
            filtered = filter_results_by_permission(results, mock_user)
            
            assert len(filtered) == 2
            assert filtered[0]["title"] == "Event 1"
            assert filtered[1]["title"] == "Event 3"

    def test_filter_results_none_user_returns_empty(self):
        """Test None user returns empty list (safe default)."""
        results = [
            {"event_id": 1, "title": "Event 1"},
        ]
        
        filtered = filter_results_by_permission(results, None)
        
        assert filtered == []

    def test_filter_results_empty_results_returns_empty(self):
        """Test empty results returns empty list."""
        mock_user = MagicMock()
        
        filtered = filter_results_by_permission([], mock_user)
        
        assert filtered == []

    def test_filter_results_allows_aggregate_queries(self):
        """Test aggregate results without event_id are allowed through."""
        mock_user = MagicMock()
        
        # Aggregate result - no event_id
        results = [
            {"total_count": 150},
            {"avg_attendees": 45.5},
        ]
        
        with patch(
            "indico_assistant.services.nl2sql.permissions.get_user_accessible_event_ids"
        ) as mock_get_ids:
            mock_get_ids.return_value = []  # No specific events
            
            filtered = filter_results_by_permission(results, mock_user)
            
            # Aggregate results should pass through
            assert len(filtered) == 2

    def test_filter_results_custom_event_id_key(self):
        """Test filter with custom event_id key name."""
        mock_user = MagicMock()
        
        results = [
            {"my_event_id": 1, "data": "accessible"},
            {"my_event_id": 2, "data": "not accessible"},
        ]
        
        with patch(
            "indico_assistant.services.nl2sql.permissions.get_user_accessible_event_ids"
        ) as mock_get_ids:
            mock_get_ids.return_value = [1]
            
            filtered = filter_results_by_permission(
                results, 
                mock_user, 
                event_id_key="my_event_id"
            )
            
            assert len(filtered) == 1
            assert filtered[0]["data"] == "accessible"

    def test_filter_results_handles_none_event_id(self):
        """Test filter handles rows with None event_id."""
        mock_user = MagicMock()
        
        results = [
            {"event_id": 1, "data": "with event"},
            {"event_id": None, "data": "aggregate"},  # None event_id
        ]
        
        with patch(
            "indico_assistant.services.nl2sql.permissions.get_user_accessible_event_ids"
        ) as mock_get_ids:
            mock_get_ids.return_value = [1]
            
            filtered = filter_results_by_permission(results, mock_user)
            
            # Both should pass - None event_id rows are included
            assert len(filtered) == 2


class TestUserCanAccessAllEvents:
    """Tests for user_can_access_all_events function."""

    def test_can_access_all_returns_true_when_all_accessible(self):
        """Test returns True when user can access all events."""
        mock_user = MagicMock()
        
        with patch(
            "indico_assistant.services.nl2sql.permissions.get_user_accessible_event_ids"
        ) as mock_get_ids:
            mock_get_ids.return_value = [1, 2, 3]
            
            result = user_can_access_all_events(mock_user, [1, 2, 3])
            
            assert result is True

    def test_can_access_all_returns_false_when_some_inaccessible(self):
        """Test returns False when user cannot access some events."""
        mock_user = MagicMock()
        
        with patch(
            "indico_assistant.services.nl2sql.permissions.get_user_accessible_event_ids"
        ) as mock_get_ids:
            mock_get_ids.return_value = [1, 3]  # Missing 2
            
            result = user_can_access_all_events(mock_user, [1, 2, 3])
            
            assert result is False

    def test_can_access_all_none_user_returns_false(self):
        """Test None user returns False."""
        result = user_can_access_all_events(None, [1, 2, 3])
        
        assert result is False

    def test_can_access_all_empty_list_returns_true(self):
        """Test empty event list returns True (vacuous truth)."""
        mock_user = MagicMock()
        
        result = user_can_access_all_events(mock_user, [])
        
        assert result is True


class TestPermissionsExceptionHandling:
    """Tests for permission functions' exception handling."""

    def test_get_accessible_events_handles_db_error(self):
        """Test get_user_accessible_event_ids handles database errors."""
        mock_user = MagicMock()
        
        with patch("indico.modules.events.Event") as MockEvent:
            with patch("indico.core.db.db") as mock_db:
                # Simulate database error
                mock_db.session.query.side_effect = Exception("Database connection lost")
                
                result = get_user_accessible_event_ids(mock_user, event_ids=[1, 2])
                
                # Should return empty list on error for safety
                assert result == []

    def test_get_accessible_events_handles_permission_check_error(self):
        """Test function handles error during permission check."""
        mock_user = MagicMock()
        
        mock_event = MagicMock()
        mock_event.can_access.side_effect = Exception("Permission check failed")
        
        with patch("indico.modules.events.Event") as MockEvent:
            with patch("indico.core.db.db") as mock_db:
                mock_query = MagicMock()
                mock_query.filter.return_value = mock_query
                mock_query.all.return_value = [(1,)]
                mock_db.session.query.return_value = mock_query
                
                MockEvent.get.return_value = mock_event
                
                # Should handle error and return empty for safety
                result = get_user_accessible_event_ids(mock_user, event_ids=[1])
                
                assert result == []
