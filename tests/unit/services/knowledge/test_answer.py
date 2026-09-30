"""The knowledge answer: one model call with its material in a fixed order, links checked after (spec 022, FR-017/018)."""

from types import SimpleNamespace

from indico_assistant.services.knowledge import answer as knowledge
from indico_assistant.services.knowledge.capabilities import CapabilityList
from indico_assistant.services.knowledge.pages import Page

BASE = "http://127.0.0.1:8000"
PAGES = [Page("The event page", "", "/event/657/"), Page("Protection", "event management", "/event/657/manage/protection")]
CAPS = CapabilityList(user_name="Lucas Flores", is_admin=False, data_questions=True, create_in=["Home"], propose_in=[],
                      can=["add a Microsoft Teams meeting to a meeting"], cannot=[], changes_enabled=True,
                      event={"id": 657, "title": "Sync", "type": "meeting", "manages": True, "locked": False})


class FakeGuide:
    def __init__(self, ok=True):
        self.ok, self.commit = ok, "e7e0016"
        self.page_urls = {"https://learn.getindico.io/categories/protection/"} if ok else set()

    def excerpts(self, question, k=6):
        return [{"url": "https://learn.getindico.io/categories/protection/", "title": "Protection",
                 "text": "Users and groups can be added with the Manage permission."}] if self.ok else []


class FakeLLM:
    def __init__(self, reply="", offer=None, success=True):
        self.reply, self.offer, self.success, self.asked = reply, offer, success, []

    def generate(self, prompt, response_model, system_prompt=None, messages=None):
        self.asked.append({"prompt": prompt, "model": response_model, "system": system_prompt, "messages": messages})
        if not self.success:
            return SimpleNamespace(success=False, result=None, error="boom")
        return SimpleNamespace(success=True, result=response_model(reply=self.reply, offer=self.offer), error=None)


def _answer(llm, guide=None, message="How do I give someone management rights?", history=()):
    return knowledge.answer(message, list(history), llm=llm, caps=CAPS, pages=PAGES, guide=guide or FakeGuide(),
                            base_url=BASE)


def test_the_material_comes_in_order_with_the_rules_as_system_prompt():
    llm = FakeLLM(reply="Open the Protection page.")
    _answer(llm, history=[{"role": "user", "content": "hi"}])
    asked = llm.asked[0]
    order = [asked["prompt"].index(h) for h in ("## Indico's user guide", "## Pages", "## What I can do", "## The question")]
    assert order == sorted(order)
    assert asked["system"] == knowledge.RULES and asked["model"] is knowledge.KnowledgeAnswer
    assert asked["messages"] == [{"role": "user", "content": "hi"}]
    assert "Users and groups can be added" in asked["prompt"] and "/event/657/manage/protection" in asked["prompt"]


def test_an_offer_is_returned():
    result = _answer(FakeLLM(reply="Yes, I can. Shall I?", offer="add a Microsoft Teams meeting to Sync"))
    assert result.offer == "add a Microsoft Teams meeting to Sync" and not result.failed
    assert _answer(FakeLLM(reply="No.", offer="  ")).offer is None


def test_links_are_checked_before_the_answer_is_returned():
    result = _answer(FakeLLM(reply="Open [Protection](https://indico.example.com/event/657/manage/protection), see "
                                   "[the guide](https://learn.getindico.io/categories/protection/) and "
                                   "[this](/event/657/manage/registration/)."))
    assert result.text == (f"Open [Protection]({BASE}/event/657/manage/protection), see "
                           "[the guide](https://learn.getindico.io/categories/protection/) and this.")


def test_without_the_guide_the_answer_still_comes():
    llm = FakeLLM(reply="Open the Protection page.")
    result = _answer(llm, guide=FakeGuide(ok=False))
    assert "(no guide excerpts available)" in llm.asked[0]["prompt"] and result.text == "Open the Protection page."
    assert result.guide_commit is None


def test_a_failed_call_gives_a_plain_message():
    result = _answer(FakeLLM(success=False))
    assert result.failed and result.text == knowledge.NOT_ANSWERED and result.offer is None


def test_the_prompt_carries_the_never_list_and_each_reason():
    """Spec 022 US2: the model is told what it can't do for this user, and why, every time."""
    from dataclasses import replace

    from indico_assistant.services.knowledge.capabilities import NEVER

    caps = replace(CAPS, can=[], cannot=[("add a Microsoft Teams meeting to a meeting",
                                          "You cannot manage the event “Sync”")])
    llm = FakeLLM(reply="No.")
    knowledge.answer("Can you add a Teams meeting?", [], llm=llm, caps=caps, pages=PAGES, guide=FakeGuide(),
                     base_url=BASE)
    prompt = llm.asked[0]["prompt"]
    assert "they cannot manage the event “Sync”" in prompt and all(item in prompt for item in NEVER)
    assert prompt.index("## What I can do") > prompt.index("## Indico's user guide")  # nearest the question


def test_reasons_are_about_the_user_not_the_assistant():
    """Run 1 (2026-09-30): "You cannot create events…" was read as the assistant's limit, and a viewer was told to
    create the meeting themselves. The list says who cannot, and the rules say not to send the user to do it."""
    from dataclasses import replace

    caps = replace(CAPS, can=[], cannot=[("create a meeting", "You cannot create events in any category on this Indico")])
    text = caps.render()
    assert "they cannot create events in any category on this Indico" in text and "You cannot" not in text
    assert "never tell the user to do it themselves" in knowledge.RULES


def test_a_follow_up_searches_the_guide_with_the_question_before_it():
    """(Copilot, PR #15) "how would I do it myself?" alone finds nothing about the thing discussed"""
    asked = []

    class Recording(FakeGuide):
        def excerpts(self, question, k=6):
            asked.append(question)
            return super().excerpts(question, k)

    history = [{"role": "user", "content": "Can you add a Teams meeting to this event?"},
               {"role": "assistant", "content": "Yes, here is the plan."}]
    knowledge.answer("how would I do it myself?", history, llm=FakeLLM(reply="Open Videoconference."), caps=CAPS,
                     pages=PAGES, guide=Recording(), base_url=BASE)
    assert asked == ["Can you add a Teams meeting to this event?\nhow would I do it myself?"]


def test_the_never_line_does_not_deny_teams():
    """(Copilot, PR #15) Teams is outside Indico and supported: only name what it has no access to"""
    text = CAPS.render()
    assert "no connection to anything outside Indico" not in text and "GitHub" in text
