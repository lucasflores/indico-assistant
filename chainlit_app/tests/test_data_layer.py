"""The data layer reads and writes conversations through Indico's API, as the requesting user (spec 020 R4)."""

import json
import os
from datetime import datetime, UTC

import httpx
import jwt
import pytest
from chainlit.types import Pagination, ThreadFilter

from indico_data_layer import CURRENT_TOKEN, IndicoDataLayer

SECRET = os.environ["CHAINLIT_AUTH_SECRET"]
LUCAS = jwt.encode({"identifier": "20", "metadata": {"name": "Lucas Flores"}}, SECRET, algorithm="HS256")
MAKOTO = jwt.encode({"identifier": "21", "metadata": {"name": "Makoto Tanaka"}}, SECRET, algorithm="HS256")
T1 = "3f2c0a7e-2b7e-4f0e-9a51-6f0a1c2d3e4f"

SESSION = {
    "session_id": T1, "event_id": 351, "created_at": "2026-09-27T10:00:00+00:00",
    "updated_at": "2026-09-28T09:00:00+00:00", "title": "Move the weekly sync", "pending_job_id": None,
    "messages": [
        {"message_id": "a1", "role": "user", "content": "move it to 3pm", "created_at": "2026-09-28T08:59:00+00:00",
         "metadata": {"event_id": 351, "uploads": [{"uuid": "u1", "filename": "agenda.pdf"}]}},
        {"message_id": "a2", "role": "assistant", "content": "Here is the plan.", "created_at": "2026-09-28T09:00:00+00:00",
         "metadata": {"plan_id": "p1"}, "feedback": {"id": "f1", "value": 1, "comment": None}},
    ],
}


class FakeIndico:
    """Sessions belong to Lucas; Makoto gets 403, as Indico answers."""

    def __init__(self):
        self.calls = []
        self.status = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path, dict(request.url.params),
                           json.loads(request.content) if request.content else None))
        token = request.headers.get("X-Assistant-Auth")
        if token != LUCAS:
            return httpx.Response(403, json={"error": "ACCESS_DENIED"})
        path = request.url.path
        if (request.method, path) in self.status:
            return httpx.Response(self.status[(request.method, path)], json={})
        if request.method == "GET" and path == f"/api/assistant/sessions/{T1}":
            return httpx.Response(200, json=SESSION)
        if request.method == "GET" and path == "/api/assistant/sessions":
            item = {k: SESSION[k] for k in ("session_id", "title", "updated_at", "created_at", "event_id")}
            return httpx.Response(200, json={"sessions": [item], "total": 3, "limit": 1, "offset": 0,
                                             "next_cursor": "CUR2"})
        if request.method == "POST" and path == "/api/assistant/feedback":
            return httpx.Response(201, json={"feedback_id": "f9"})
        if request.method == "DELETE" and path.startswith("/api/assistant/feedback/"):
            return httpx.Response(204)
        if request.method in ("PATCH", "DELETE", "PUT"):
            return httpx.Response(200, json={})
        return httpx.Response(404, json={})


@pytest.fixture
def indico():
    return FakeIndico()


@pytest.fixture
def layer(indico):
    return IndicoDataLayer("http://indico.test", transport=httpx.MockTransport(indico.handler))


@pytest.fixture
def as_lucas():
    reset = CURRENT_TOKEN.set(LUCAS)
    yield
    CURRENT_TOKEN.reset(reset)


async def test_a_session_becomes_a_thread(layer, as_lucas):
    thread = await layer.get_thread(T1)
    assert (thread["id"], thread["name"], thread["userIdentifier"]) == (T1, "Move the weekly sync", "20")
    assert thread["createdAt"] == SESSION["updated_at"]  # the sidebar groups by last activity
    user, run, answer = thread["steps"]
    assert (user["id"], user["type"], user["threadId"]) == ("a1", "user_message", T1)
    assert user["output"] == "move it to 3pm\n\n📎 agenda.pdf"
    # the answer is in a run, as Chainlit draws a live one; its thumbs are the run's, under the answer's id
    assert (run["id"], run["type"], run["name"], run["parentId"]) == ("a2", "run", "on_message", "a1")
    assert run["feedback"] == {"forId": "a2", "id": "f1", "value": 1, "comment": None}
    assert (answer["type"], answer["parentId"], answer["output"]) == ("assistant_message", "a2", "Here is the plan.")
    assert answer["id"] != "a2" and "feedback" not in answer
    assert thread["metadata"] == {"started_on_event_id": 351, "pending_job_id": None, "waiting_plan_id": None}
    assert thread["elements"] == []


async def test_the_list_is_a_page_with_a_cursor(layer, indico, as_lucas):
    page = await layer.list_threads(Pagination(first=1, cursor="CUR1"), ThreadFilter(search="sync", userId="ignored"))
    assert [t["id"] for t in page.data] == [T1] and page.data[0]["name"] == "Move the weekly sync"
    assert page.data[0]["steps"] == []
    assert (page.pageInfo.hasNextPage, page.pageInfo.endCursor) == (True, "CUR2")
    method, path, params, _ = indico.calls[-1]
    assert (method, path, params) == ("GET", "/api/assistant/sessions", {"limit": "1", "cursor": "CUR1", "search": "sync"})


async def test_the_author_is_whoever_indico_lets_in(layer, as_lucas):
    assert await layer.get_thread_author(T1) == "20"
    CURRENT_TOKEN.set(MAKOTO)  # someone else's thread: Indico says 403, Chainlit then refuses
    assert await layer.get_thread_author(T1) == ""
    assert await layer.get_thread(T1) is None


async def test_indico_already_stores_every_message(layer, indico, as_lucas):
    step = {"id": "s1", "threadId": T1, "type": "user_message", "output": "hi"}
    await layer.create_step(step)
    await layer.update_step(step)
    await layer.delete_step("s1")
    await layer.create_element(object())
    await layer.delete_element("e1")
    await layer.update_thread(T1, metadata={"chat_settings": {}})
    assert indico.calls == [] and await layer.get_element(T1, "e1") is None
    assert await layer.get_favorite_steps("20") == []


async def test_a_rename_is_a_rename_and_chainlits_own_naming_is_not(layer, indico, as_lucas):
    await layer.update_thread(T1, name="x" * 500)  # the sidebar's rename
    assert indico.calls[-1][0] == "PATCH" and len(indico.calls[-1][3]["title"]) == 200
    # Chainlit names a new thread by its first message (with user_id), before the chat API has the session, then
    # lists Past Chats and opens it: Indico must have it, and the title stays the question's start (review, PR #5)
    await layer.update_thread(thread_id="new-thread", name="Who speaks?", user_id="20", tags=None)
    assert indico.calls[-1][:2] == ("PUT", "/api/assistant/sessions/new-thread")
    assert indico.calls[-1][3] == {"first_message": "Who speaks?"}


async def test_the_author_check_does_not_read_the_messages(layer, indico, as_lucas):
    await layer.get_thread_author(T1)
    assert indico.calls[-1][2] == {"messages": "0"}


async def test_delete_goes_to_indico(layer, indico, as_lucas):
    await layer.delete_thread(T1)
    assert indico.calls[-1][:2] == ("DELETE", f"/api/assistant/sessions/{T1}")


async def test_without_a_token_nothing_is_read(layer, indico):
    assert await layer.get_thread(T1) is None and await layer.get_thread_author(T1) == ""
    assert (await layer.list_threads(Pagination(first=5), ThreadFilter())).data == []
    assert indico.calls == []


async def test_the_websocket_path_uses_the_session_token(layer, monkeypatch):
    import indico_data_layer
    monkeypatch.setattr(indico_data_layer, "_websocket_token", lambda: LUCAS)
    assert (await layer.get_thread(T1))["id"] == T1


async def test_users_are_not_stored(layer):
    from chainlit.user import User
    # (seen live: a user rebuilt from the identifier replaced the signed-in one and lost the page's event)
    persisted = await layer.create_user(User(identifier="20", metadata={"name": "Lucas Flores", "event_id": 351}))
    assert (persisted.id, persisted.identifier, persisted.metadata["event_id"]) == ("20", "20", 351)
    assert await layer.get_user("20") is None
    datetime.fromisoformat(persisted.createdAt)
    assert datetime.now(UTC)  # (no Indico call, no storage)


async def test_only_indico_may_frame_the_app_and_the_cookie_is_the_token(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import indico_data_layer

    app = FastAPI()
    seen = {}

    @app.get("/probe")
    async def probe():
        seen["token"] = CURRENT_TOKEN.get()
        return {}

    indico_data_layer.install_token_middleware(app, "http://127.0.0.1:8000/")
    response = TestClient(app).get("/probe", cookies={"access_token": LUCAS})
    assert response.headers["Content-Security-Policy"] == "frame-ancestors 'self' http://127.0.0.1:8000"
    assert seen["token"] == LUCAS and CURRENT_TOKEN.get() is None


async def test_a_thumb_is_a_vote_in_indico(layer, indico, as_lucas):
    from chainlit.types import Feedback
    assert await layer.upsert_feedback(Feedback(forId="a2", value=0, comment="  wrong meeting ")) == "f9"
    # the vote and its comment in one request: Indico keeps both or neither (review, PR #5)
    assert indico.calls[-1][3] == {"message_id": "a2", "feedback_type": "thumbs_down", "value": True,
                                   "comment": "wrong meeting"}
    calls = len(indico.calls)
    await layer.upsert_feedback(Feedback(forId="a2", value=1))
    assert len(indico.calls) == calls + 1 and "comment" not in indico.calls[-1][3]
    assert await layer.delete_feedback("f9") is True and indico.calls[-1][:2] == ("DELETE", "/api/assistant/feedback/f9")


async def test_a_rename_or_delete_indico_did_not_keep_is_an_error(layer, indico, as_lucas):
    indico.status[("PATCH", f"/api/assistant/sessions/{T1}")] = 500
    with pytest.raises(RuntimeError):
        await layer.update_thread(T1, name="Weekly sync")
    indico.status[("DELETE", f"/api/assistant/sessions/{T1}")] = 500
    with pytest.raises(RuntimeError):
        await layer.delete_thread(T1)
    CURRENT_TOKEN.set(None)  # Indico unreachable or no token: not a silent success either
    with pytest.raises(RuntimeError):
        await layer.update_thread(T1, name="Weekly sync")


async def test_a_vote_indico_did_not_keep_is_an_error(layer, indico, as_lucas):
    from chainlit.types import Feedback
    indico.status[("POST", "/api/assistant/feedback")] = 404
    with pytest.raises(RuntimeError):
        await layer.upsert_feedback(Feedback(forId="gone", value=1))
    indico.status[("DELETE", "/api/assistant/feedback/f9")] = 404
    assert await layer.delete_feedback("f9") is False
