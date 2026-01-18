"""Integration test for feedback bridge.

Requires running Indico + Chainlit with INDICO_FEEDBACK_URL configured.
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skip(reason="Requires running Indico + Chainlit")] 


def test_feedback_bridge_placeholder():
    """Placeholder to validate feedback bridge wiring.

    Steps (manual/external):
    1. Trigger a feedback event in Chainlit UI (thumbs up/down).
    2. Verify POST is sent to INDICO_FEEDBACK_URL with Authorization header.
    3. Verify payload contains message_id, rating, comment.
    """
    assert True
