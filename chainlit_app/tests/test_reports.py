"""The chat side of issue reports (spec 021, contracts/panel.md): the title bar's Report message, the form's
callbacks, and (US4) the offers. Against a fake Indico and a fake Chainlit context."""

import json
from types import SimpleNamespace
from uuid import UUID

import app_chnlit
import httpx
import pytest


def indico(status=201, body=None, raises=None):
    seen = []

    def handler(request):
        seen.append({"method": request.method, "path": request.url.path, "auth": request.headers.get("X-Assistant-Auth"),
                     "json": json.loads(request.content) if request.content else None})
        if raises:
            raise raises
        return httpx.Response(status, json=body if body is not None else
                              {"report_id": 12, "url": "http://indico.test/user/assistant-reports/12/"},
                              headers={"Retry-After": "600"} if status == 429 else {})

    return httpx.AsyncClient(base_url="http://indico.test", transport=httpx.MockTransport(handler)), seen


@pytest.fixture
def chat(monkeypatch):
    """What the app sends, with a session that has (or has not) had a first message."""
    sent = {"forms": [], "messages": [], "removed": [], "indico": indico()}
    session = SimpleNamespace(has_first_interaction=True, thread_id="thread-1", token="tok")
    store = {}

    class Element:
        def __init__(self, name, props, display):
            self.name, self.props, self.display = name, props, display

    class Message:
        def __init__(self, content="", elements=None, actions=None):
            self.content, self.elements, self.actions = content, elements or [], actions or []

        async def send(self):
            (sent["forms"] if self.elements else sent["messages"]).append(self)
            return self

        async def remove(self):
            sent["removed"].append(self)

    async def client(url):
        return sent["indico"][0]

    monkeypatch.setattr(app_chnlit.cl, "CustomElement", Element)
    monkeypatch.setattr(app_chnlit.cl, "Message", Message)
    monkeypatch.setattr(app_chnlit.cl, "context", SimpleNamespace(session=session))
    monkeypatch.setattr(app_chnlit.cl, "user_session", SimpleNamespace(get=lambda k, d=None: store.get(k, d),
                                                                       set=store.__setitem__))
    monkeypatch.setattr(app_chnlit, "_get_http_client", client)
    monkeypatch.setattr(app_chnlit, "_get_indico_api_url", lambda: "http://indico.test")
    sent["session"] = session
    return sent


def props(chat, i=-1):
    element = chat["forms"][i].elements[0]
    assert element.name == "IssueReport" and element.display == "inline"
    return element.props


def action(**payload):
    return SimpleNamespace(payload=payload)


# --- the title bar's Report button (R2) -------------------------------------------------------------------

async def test_the_report_message_opens_an_empty_form(chat):
    await app_chnlit.on_window_message({"source": "indico-assistant", "type": "report"})
    form = props(chat)
    assert UUID(form["form_key"]) and form["answer_id"] is None and form["category"] is None and form["text"] == ""
    assert form["can_attach"] is True


async def test_in_a_new_chat_there_is_nothing_to_attach(chat):
    chat["session"].has_first_interaction = False
    await app_chnlit.on_window_message({"source": "indico-assistant", "type": "report"})
    assert props(chat)["can_attach"] is False


@pytest.mark.parametrize("data", [{"source": "indico-assistant", "type": "login", "token": "secret"},
                                  "report", {"source": "elsewhere", "type": "report"}, None])
async def test_any_other_window_message_does_nothing(chat, data):
    await app_chnlit.on_window_message(data)
    assert chat["forms"] == chat["messages"] == []


async def test_each_form_gets_its_own_key(chat):
    for _ in range(2):
        await app_chnlit.on_window_message({"source": "indico-assistant", "type": "report"})
    assert props(chat, 0)["form_key"] != props(chat, 1)["form_key"]


# --- the form's callbacks ---------------------------------------------------------------------------------

async def test_an_offer_opens_the_form_for_its_answer(chat):
    await app_chnlit.on_report_open(action(answer_id="a1", category="wrong_answer", text="the date is wrong"))
    form = props(chat)
    assert (form["answer_id"], form["category"], form["text"], form["can_attach"]) == ("a1", "wrong_answer",
                                                                                      "the date is wrong", True)


def submitted(**fields):
    return action(**{"form_key": "k1", "category": "bug", "text": "It broke.", "attach": True, "answer_id": "a1",
                     **fields})


async def test_sending_posts_the_report_as_the_user(chat):
    result = await app_chnlit.on_report_submit(submitted())
    [call] = chat["indico"][1]
    assert (call["method"], call["path"], call["auth"]) == ("POST", "/api/assistant/reports", "tok")
    assert call["json"] == {"form_key": "k1", "category": "bug", "text": "It broke.", "attach": True,
                            "session_id": "thread-1", "answer_id": "a1"}
    assert result == {"ok": True, "report_id": 12, "url": "http://indico.test/user/assistant-reports/12/"}


async def test_unticked_sends_no_conversation(chat):
    await app_chnlit.on_report_submit(submitted(attach=False))
    assert chat["indico"][1][0]["json"]["session_id"] is None


async def test_a_resent_form_is_still_a_success(chat):
    chat["indico"] = indico(status=200)
    assert (await app_chnlit.on_report_submit(submitted()))["ok"] is True


@pytest.mark.parametrize("status,body,raises,says", [
    (404, {"error": "NOT_FOUND"}, None, "untick"),
    (422, {"error": "VALIDATION_ERROR", "message": "Text is too long"}, None, "Text is too long"),
    (429, {"error": "RATE_LIMITED"}, None, "11 minutes"),
    (503, {"error": "INTERNAL_ERROR"}, None, "try again"),
    (201, None, httpx.ConnectError("gone"), "reach"),
])
async def test_a_failed_send_says_why_in_one_sentence(chat, status, body, raises, says):
    chat["indico"] = indico(status=status, body=body, raises=raises)
    result = await app_chnlit.on_report_submit(submitted())
    assert result["ok"] is False and says in result["message"] and result["message"].count(".") == 1


async def test_cancel_removes_the_form(chat):
    await app_chnlit.on_window_message({"source": "indico-assistant", "type": "report"})
    await app_chnlit.on_report_cancel(action(form_key=props(chat)["form_key"]))
    assert chat["removed"] == [chat["forms"][0]]
