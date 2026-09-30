"""The chat answer: from the conversation, informed by general knowledge, nothing looked up (spec 022, Lucas 09-30)."""

from types import SimpleNamespace

from indico_assistant.services.knowledge import chat
from indico_assistant.services.knowledge.links import found_in

BASE = "http://127.0.0.1:8000"
HISTORY = [{"role": "user", "content": "Which meetings do I have this week?"},
           {"role": "assistant", "content": "Three: [Sync](http://127.0.0.1:8000/event/351/) on Tuesday, "
                                            "[Retro](/event/352/) on Friday. See https://learn.getindico.io/meetings/about/."}]


class FakeLLM:
    def __init__(self, reply="", success=True):
        self.reply, self.success, self.asked = reply, success, []

    def generate(self, prompt, response_model, system_prompt=None, messages=None):
        self.asked.append({"prompt": prompt, "system": system_prompt, "messages": messages, "model": response_model})
        if not self.success:
            return SimpleNamespace(success=False, result=None, error="boom")
        return SimpleNamespace(success=True, result=response_model(reply=self.reply), error=None)


def test_links_found_in_the_conversation():
    paths, guide = found_in([m["content"] for m in HISTORY], BASE)
    assert paths == {"/event/351/", "/event/352/"} and guide == {"https://learn.getindico.io/meetings/about/"}


def test_the_answer_comes_from_the_conversation():
    llm = FakeLLM(reply="The earliest is [Sync](/event/351/).")
    result = chat.chat_answer("which of those is earliest?", HISTORY, llm=llm, base_url=BASE)
    asked = llm.asked[0]
    assert asked["system"] == chat.RULES and asked["messages"] == HISTORY and asked["model"] is chat.ChatAnswer
    assert "which of those is earliest?" in asked["prompt"]
    assert result.text == f"The earliest is [Sync]({BASE}/event/351/)." and not result.failed


def test_only_links_already_in_the_conversation_survive():
    llm = FakeLLM(reply="See [Sync](/event/351/), [the timetable](/event/351/manage/timetable/) and "
                        "[a guide page](https://learn.getindico.io/made/up/).")
    result = chat.chat_answer("where?", HISTORY, llm=llm, base_url=BASE)
    assert result.text == f"See [Sync]({BASE}/event/351/), the timetable and a guide page."


def test_a_link_in_the_latest_message_survives():
    llm = FakeLLM(reply="- [This agenda](/event/353/): Tuesday")
    result = chat.chat_answer("Rephrase [this agenda](/event/353/) as a list", HISTORY, llm=llm, base_url=BASE)
    assert result.text == f"- [This agenda]({BASE}/event/353/): Tuesday"


def test_the_rules_allow_general_knowledge_but_no_lookups():
    assert "general knowledge" in chat.RULES and "never invent" in chat.RULES.lower()


def test_a_failed_call_gives_a_plain_message():
    result = chat.chat_answer("thanks", HISTORY, llm=FakeLLM(success=False), base_url=BASE)
    assert result.failed and result.text == chat.NOT_ANSWERED
