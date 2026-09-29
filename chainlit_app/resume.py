"""What a resumed conversation must draw again that Chainlit cannot (spec 020 R7).

Chainlit redraws a thread's messages from the data layer, but not their buttons, and not an answer still
being written when the user left the page. The thread's metadata (read with its history) names both: the
plan still waiting for confirmation, whose card needs its confirm token (R10), and the job of an unanswered
question (R9). Nothing is read twice (review, PR #5).
"""

from __future__ import annotations

import httpx

UNANSWERED = "Your last question went unanswered while you were away. Please ask it again."


async def reissue(client: httpx.AsyncClient, token: str, plan_id: str) -> dict | None:
    """The waiting plan, ready to render with its confirm token; None once it is no longer waiting."""
    response = await client.post(f"/api/assistant/plans/{plan_id}/token", headers={"X-Assistant-Auth": token})
    return response.json() if response.status_code == 200 else None
