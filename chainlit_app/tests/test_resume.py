"""What a resumed conversation must redraw that Chainlit cannot (spec 020 R7): the plan still waiting for
confirmation (with its confirm token, R10) and the answer of a question pending when the history was read (R9),
from the thread's metadata, without reading the conversation again (review, PR #5)."""

import httpx
import pytest

import app_chnlit
from resume import UNANSWERED, reissue


def indico(token_status=200, job=(404, {})):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/token"):
            plan_id = request.url.path.split("/")[-2]
            return httpx.Response(token_status, json={"id": plan_id, "token": "t", "status": "shown", "steps": [],
                                                      "questions": [], "suggestions": [], "summary": "s",
                                                      "can_confirm": True} if token_status == 200 else
                                  {"error": "PLAN_NOT_CONFIRMABLE"})
        if request.url.path.startswith("/api/assistant/chat/jobs/"):
            return httpx.Response(job[0], json=job[1])
        return httpx.Response(404, json={})

    return httpx.AsyncClient(base_url="http://indico.test", transport=httpx.MockTransport(handler)), calls


async def test_a_waiting_plan_comes_back_with_its_token():
    client, calls = indico()
    assert (await reissue(client, "tok", "p2"))["token"] == "t" and calls == [("POST", "/api/assistant/plans/p2/token")]
    client, _ = indico(token_status=409)
    assert await reissue(client, "tok", "p1") is None  # answered or expired meanwhile: not redrawn


@pytest.fixture
def drawn(monkeypatch):
    """What _after_resume draws, against a fake Indico set by ``drawn['indico']``."""
    seen = {"cards": [], "answers": [], "texts": [], "indico": indico()}

    class Message:
        def __init__(self, content="", actions=None):
            self.content = content

        async def send(self):
            seen["texts"].append(self.content)
            return self

    async def show(response, message, client, token):
        seen["answers"].append((response.status_code, response.json().get("response")))

    async def client(url):
        return seen["indico"][0]

    monkeypatch.setattr(app_chnlit, "RESUME_SETTLE", 0)
    monkeypatch.setattr(app_chnlit, "POLL_INTERVAL", 0)
    monkeypatch.setattr(app_chnlit, "_get_http_client", client)
    monkeypatch.setattr(app_chnlit, "_show_answer", show)
    monkeypatch.setattr(app_chnlit, "render_plan", lambda plan: (seen["cards"].append(plan["id"]) or "card", []))
    monkeypatch.setattr(app_chnlit.cl, "Message", Message)
    monkeypatch.setattr(app_chnlit.cl, "user_session", type("S", (), {"set": lambda self, k, v: None})())
    return seen


async def test_an_answer_that_landed_after_the_history_was_read_is_shown(drawn):
    drawn["indico"] = indico(job=(200, {"status": "done", "response": "the answer"}))
    await app_chnlit._after_resume("http://indico.test", "tok", pending_job_id="job-1", waiting_plan_id="p-old")
    assert drawn["answers"] == [(200, "the answer")]
    assert drawn["cards"] == ["p-old"]  # an earlier plan still waiting is drawn too


async def test_a_landed_plan_is_drawn_once(drawn):
    drawn["indico"] = indico(job=(200, {"status": "done", "response": "the answer", "plan": {"id": "p-new"}}))
    await app_chnlit._after_resume("http://indico.test", "tok", pending_job_id="job-1", waiting_plan_id="p-new")
    assert drawn["cards"] == [] and drawn["answers"] == [(200, "the answer")]  # (the answer draws its own card)
    assert ("POST", "/api/assistant/plans/p-new/token") not in drawn["indico"][1]


async def test_an_answer_still_being_written_is_waited_for_and_a_slow_one_says_so(drawn, monkeypatch):
    drawn["indico"] = indico(job=(202, {"status": "pending"}))
    monkeypatch.setattr(app_chnlit, "ANSWER_TIMEOUT", 0)
    await app_chnlit._after_resume("http://indico.test", "tok", pending_job_id="job-1")
    assert drawn["answers"] == [(202, None)]  # _show_answer says "taking too long" for every caller


async def test_a_job_gone_from_the_cache_says_so_once(drawn):
    await app_chnlit._after_resume("http://indico.test", "tok", pending_job_id="job-old")
    assert drawn["texts"] == [UNANSWERED] and drawn["answers"] == []


async def test_nothing_waiting_reads_nothing(drawn):
    await app_chnlit._after_resume("http://indico.test", "tok")
    assert drawn["indico"][1] == [] and drawn["cards"] == drawn["answers"] == []
