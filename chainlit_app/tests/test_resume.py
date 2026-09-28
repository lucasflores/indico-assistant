"""What a resumed conversation must redraw that Chainlit cannot (spec 020 R7): the plan still waiting for
confirmation (with a fresh token, R10) and an answer still being written (R9)."""

import json

import httpx

from resume import UNANSWERED, restore

T1 = "3f2c0a7e-2b7e-4f0e-9a51-6f0a1c2d3e4f"


def detail(*messages, pending=None):
    return {"session_id": T1, "title": "t", "pending_job_id": pending, "messages": list(messages)}


def answer(plan_id=None):
    return {"message_id": f"m-{plan_id}", "role": "assistant", "content": "…", "created_at": "2026-09-28T09:00:00+00:00",
            "metadata": {"plan_id": plan_id} if plan_id else {}}


def indico(session, token_status=200, job=None):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == f"/api/assistant/sessions/{T1}":
            return httpx.Response(200, json=session)
        if request.url.path.endswith("/token"):
            plan_id = request.url.path.split("/")[-2]
            return httpx.Response(token_status, json={"id": plan_id, "token": "fresh", "status": "shown", "steps": [],
                                                      "questions": [], "suggestions": [], "summary": "s",
                                                      "can_confirm": True} if token_status == 200 else
                                  {"error": "PLAN_NOT_CONFIRMABLE"})
        if request.url.path.startswith("/api/assistant/chat/jobs/"):
            return httpx.Response(*job) if job else httpx.Response(404, json={})
        return httpx.Response(404, json={})

    return httpx.AsyncClient(base_url="http://indico.test", transport=httpx.MockTransport(handler)), calls


async def test_the_latest_plan_comes_back_with_a_fresh_token():
    client, calls = indico(detail(answer("p1"), {"message_id": "u", "role": "user", "content": "x",
                                                 "created_at": "2026-09-28T09:01:00+00:00"}, answer("p2")))
    restored = await restore(client, "tok", T1)
    assert restored.plan["id"] == "p2" and restored.plan["token"] == "fresh"
    assert ("POST", "/api/assistant/plans/p2/token") in calls and ("POST", "/api/assistant/plans/p1/token") not in calls


async def test_a_plan_no_longer_waiting_is_not_redrawn():
    client, _ = indico(detail(answer("p1")), token_status=409)
    assert (await restore(client, "tok", T1)).plan is None


async def test_an_answer_still_being_written_is_waited_for():
    client, _ = indico(detail(answer(), pending="job-7"),
                       job=(200, {"status": "done", "response": "Here you go", "message_id": "m9"}))
    restored = await restore(client, "tok", T1)
    assert restored.pending_job_id == "job-7" and restored.plan is None


async def test_a_job_gone_from_the_cache_says_so():
    client, _ = indico(detail(answer(), pending="job-old"))
    restored = await restore(client, "tok", T1)
    response = await client.get("/api/assistant/chat/jobs/job-old")
    assert response.status_code == 404 and "unanswered" in UNANSWERED.lower()
    assert restored.pending_job_id == "job-old"


async def test_nothing_to_redraw_for_a_plain_conversation():
    client, calls = indico(detail(answer()))
    restored = await restore(client, "tok", T1)
    assert (restored.plan, restored.pending_job_id) == (None, None)
    assert [c for c in calls if c[0] == "POST"] == []
    assert json.dumps(restored.__dict__)  # plain data
