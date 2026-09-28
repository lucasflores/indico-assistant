"""What a resumed conversation must draw again that Chainlit cannot (spec 020 R7).

Chainlit redraws a thread's messages from the data layer, but not their buttons, and not an answer still
being written when the user left the page. This finds both in Indico: the plan still waiting for
confirmation, which gets a fresh confirm token (R10), and the job of an unanswered question (R9).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

UNANSWERED = "Your last question went unanswered while you were away. Please ask it again."


@dataclass
class Restored:
    plan: dict | None = None  # PlanView with a fresh token, ready to render
    pending_job_id: str | None = None


async def restore(client: httpx.AsyncClient, token: str, thread_id: str) -> Restored:
    headers = {"X-Assistant-Auth": token}
    response = await client.get(f"/api/assistant/sessions/{thread_id}", headers=headers)
    if response.status_code != 200:
        return Restored()
    session = response.json()
    plan_ids = [(m.get("metadata") or {}).get("plan_id") for m in session.get("messages", [])
                if m.get("role") == "assistant"]
    plan = None
    if latest := next((p for p in reversed(plan_ids) if p), None):  # only the latest plan can still be waiting
        reissued = await client.post(f"/api/assistant/plans/{latest}/token", headers=headers)
        if reissued.status_code == 200:
            plan = reissued.json()
    return Restored(plan=plan, pending_job_id=session.get("pending_job_id"))
