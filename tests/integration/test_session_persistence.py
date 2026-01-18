"""Integration test for chat session persistence.

Requires running Indico + Chainlit with CHAINLIT_DATABASE_URL configured.
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skip(reason="Requires running Indico + Chainlit")] 


def test_session_persists_across_navigation():
    """Placeholder integration test for session persistence.

    Steps (manual/external):
    1. Open Indico page, open chat widget, send a message.
    2. Navigate to another page; widget should show previous messages.
    3. Verify localStorage contains 'chainlit-copilot-thread-id'.
    """
    assert True
