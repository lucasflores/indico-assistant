# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Permission helpers for NL2SQL pipeline.

Provides utilities for checking user permissions on events and
filtering query results based on access rights.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from indico.modules.users import User


def get_user_accessible_event_ids(
    user: "User | None",
    event_ids: list[int] | None = None,
) -> list[int]:
    """
    Get list of event IDs the user has access to.

    This function integrates with Indico's permission system to determine
    which events a user can view. It supports filtering to a subset of
    events if provided.

    Args:
        user: The Indico User object. If None, returns empty list.
        event_ids: Optional list of event IDs to filter. If None,
            returns all events the user can access.

    Returns:
        List of event IDs the user has permission to view.
        Returns empty list if user is None or has no accessible events.

    Note:
        This function queries the database and should be called sparingly.
        Consider caching results for repeated queries within the same request.
    """
    if user is None:
        return []

    try:
        from indico.modules.events import Event
        from indico.core.db import db

        # Build base query
        query = db.session.query(Event.id)

        # Filter to specific events if provided
        if event_ids is not None:
            if not event_ids:
                return []
            query = query.filter(Event.id.in_(event_ids))

        # Get all event IDs first
        all_event_ids = [row[0] for row in query.all()]

        # Filter to events user can access
        # Indico's can_access checks permissions
        accessible = []
        for event_id in all_event_ids:
            event = Event.get(event_id)
            if event and event.can_access(user):
                accessible.append(event_id)

        return accessible

    except ImportError:
        # Indico not available (testing environment)
        return list(event_ids) if event_ids else []
    except Exception:
        # Log error and return empty for safety
        return []


def filter_results_by_permission(
    results: list[dict[str, Any]],
    user: "User | None",
    event_id_key: str = "event_id",
) -> list[dict[str, Any]]:
    """
    Filter query results to only include rows from accessible events.

    This is a post-query permission check to ensure users only see
    results from events they have access to. This provides defense
    in depth against permission bypass.

    Args:
        results: List of result dictionaries from query execution.
        user: The Indico User object. If None, returns empty list.
        event_id_key: The key in result dicts containing the event ID.

    Returns:
        Filtered list containing only rows from accessible events.
        Returns empty list if user is None.

    Note:
        This function performs permission checks on each unique event ID
        in the results, which can be slow for large result sets.
    """
    if user is None:
        return []

    if not results:
        return []

    # Extract unique event IDs from results
    event_ids_in_results: set[int] = set()
    for row in results:
        if event_id_key in row and row[event_id_key] is not None:
            event_ids_in_results.add(int(row[event_id_key]))

    if not event_ids_in_results:
        # No event IDs in results - might be aggregate query
        # Allow these through (they don't expose individual event data)
        return results

    # Get accessible event IDs
    accessible_ids = set(
        get_user_accessible_event_ids(user, list(event_ids_in_results))
    )

    # Filter results
    filtered = []
    for row in results:
        event_id = row.get(event_id_key)
        if event_id is None:
            # Row without event_id (aggregate) - include
            filtered.append(row)
        elif int(event_id) in accessible_ids:
            filtered.append(row)
        # Rows with inaccessible event_id are silently dropped

    return filtered


def user_can_access_all_events(
    user: "User | None",
    event_ids: list[int],
) -> bool:
    """
    Check if user has access to all specified events.

    Args:
        user: The Indico User object.
        event_ids: List of event IDs to check.

    Returns:
        True if user can access all events, False otherwise.
    """
    if user is None:
        return False

    if not event_ids:
        return True

    accessible = get_user_accessible_event_ids(user, event_ids)
    return set(accessible) == set(event_ids)
