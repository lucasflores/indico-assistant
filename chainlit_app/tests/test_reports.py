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
    context = SimpleNamespace(session=session, current_run=None)
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
    monkeypatch.setattr(app_chnlit.cl, "context", context)
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


# --- US4: the offers (R3, R4) ------------------------------------------------------------------------------

def offers(message):
    return [a for a in message.actions if a.name == "report_open"]


def feedback(value, for_id="a1", comment=None):
    return SimpleNamespace(value=value, forId=for_id, comment=comment)


async def test_a_thumbs_down_offers_a_report_once(chat):
    await app_chnlit.on_feedback(feedback(0, comment="the date is wrong"))
    [offer] = offers(chat["messages"][0])
    assert offer.label == "Report a problem" and offer.payload == {"answer_id": "a1", "category": "wrong_answer",
                                                                   "text": "the date is wrong"}
    await app_chnlit.on_feedback(feedback(0))  # the same answer again
    await app_chnlit.on_feedback(feedback(1, for_id="a2"))  # a thumbs up
    assert len(chat["messages"]) == 1


class Loading:
    def __init__(self):
        self.content, self.actions, self.sent = "", [], False

    async def send(self):
        self.sent = True


async def shown(chat, status, body=None, headers=None):
    message = Loading()
    await app_chnlit._show_answer(httpx.Response(status, json=body or {}, headers=headers or {}), message,
                                  chat["indico"][0], "tok")
    assert message.sent
    return message


async def test_an_answer_with_a_problem_carries_the_offer(chat):
    message = await shown(chat, 200, {"status": "done", "response": "I can only help with events.",
                                      "message_id": "m9", "metadata": {"problem": "out_of_scope"}})
    [offer] = offers(message)
    assert offer.payload["answer_id"] == "m9" and offer.payload["category"] == "wrong_answer"
    fine = await shown(chat, 200, {"status": "done", "response": "Two events.", "message_id": "m10", "metadata": {}})
    assert offers(fine) == []


@pytest.mark.parametrize("status,offered", [(202, True), (500, True), (504, True), (429, False), (401, False),
                                            (403, False), (422, False)])
async def test_an_error_with_no_answer_offers_a_report_without_one(chat, status, offered):
    message = await shown(chat, status, {"status": "pending"} if status == 202 else {"error": "X"})
    assert [o.payload["answer_id"] for o in offers(message)] == ([None] if offered else [])


async def test_an_unreachable_indico_offers_a_report(chat):
    chat["indico"] = indico(raises=httpx.ConnectError("gone"))
    await app_chnlit._ask("When is the Sync?")
    [message] = chat["messages"]
    assert message.content == app_chnlit.UNREACHABLE and offers(message)[0].payload["answer_id"] is None


async def test_a_resumed_question_that_got_no_answer_offers_a_report(chat, monkeypatch):
    monkeypatch.setattr(app_chnlit, "RESUME_SETTLE", 0)
    chat["indico"] = indico(status=404, body={})  # the job left the cache
    await app_chnlit._after_resume("http://indico.test", "tok", pending_job_id="job-old")
    [message] = chat["messages"]
    assert message.content == app_chnlit.UNANSWERED and offers(message)[0].payload["answer_id"] is None



@pytest.mark.parametrize("status,body,offered", [
    (200, {"status": "done", "response": "Done:", "message_id": "m1", "plan": {"status": "done"}}, None),
    (200, {"status": "done", "response": "It failed.", "message_id": "m2", "plan": {"status": "failed"}}, "m2"),
    (200, {"status": "done", "response": "I did not change anything.", "message_id": "m3", "plan": {"status": "refused"}}, "m3"),
    (500, {"error": "PLAN_FAILED"}, "none"),
    (409, {"error": "PLAN_NOT_CONFIRMABLE"}, None),  # expired or confirmed elsewhere: no failure of the assistant
])
async def test_a_confirmed_plan_that_did_not_run_offers_a_report(chat, monkeypatch, status, body, offered):
    # (fresh review, PR #16: the Confirm button's failed outcome carried no offer)
    async def planned(path, body_=None):
        return httpx.Response(status, json=body)
    monkeypatch.setattr(app_chnlit, "_plan_call", planned)
    monkeypatch.setattr(app_chnlit, "_forget_plan_buttons", lambda: _noop())
    await app_chnlit.on_confirm_plan(action(plan_id="p1", token="t"))
    got = [o.payload["answer_id"] for o in offers(chat["messages"][-1])]
    assert got == ([] if offered is None else [None if offered == "none" else offered])


async def _noop():
    return None
