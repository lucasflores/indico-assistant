"""Integration tests for NL2SQL vector search queries."""

import pytest


@pytest.mark.integration
def test_end_to_end_event_query_with_formatted_dates() -> None:
    """End-to-end event query should return formatted dates."""
    pytest.skip("Requires live NL2SQL pipeline and database fixtures")


@pytest.mark.integration
def test_end_to_end_speaker_query_with_aggregation() -> None:
    """End-to-end speaker query should return aggregated contributors."""
    pytest.skip("Requires live NL2SQL pipeline and database fixtures")


@pytest.mark.integration
def test_end_to_end_vector_search_query_with_embedding() -> None:
    """End-to-end document content query should use vector search."""
    pytest.skip("Requires live NL2SQL pipeline and vector search setup")
