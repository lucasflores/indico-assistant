"""The chat answer: a message answerable from the conversation so far (spec 022, the router's "chat" route).

As Lucas set it (2026-09-30): the answer comes from the chat, informed by general knowledge, so it can explain what the
conversation contains (a particle decay mentioned in a talk's abstract, say). Nothing is looked up in Indico and
nothing is changed; the only links it may give are the ones already in the conversation.
"""

from pydantic import BaseModel, Field

from indico_assistant.services.knowledge import links
from indico_assistant.services.knowledge.answer import NOT_ANSWERED, KnowledgeResult

RULES = """You are the assistant built into Indico, the event management system. The user's latest message can be
answered from the conversation so far.

Rules:
- Answer from the conversation. Use your general knowledge to explain what it contains (a term, a result, a process
  it mentions), and say when you are going beyond it.
- Never invent facts about the user's events, people or files. If the answer needs Indico information that is not in
  the conversation, say so and suggest asking for it directly.
- You do not look anything up and you do not make changes here.
- Link only to pages already linked in the conversation.
- Answer in the language of the message. Be short."""

__all__ = ["RULES", "ChatAnswer", "NOT_ANSWERED", "chat_answer"]


class ChatAnswer(BaseModel):
    reply: str = Field(..., description="The answer to the user, in markdown")


def chat_answer(message, history, *, llm, base_url):
    """Answer ``message`` from ``history`` (the conversation, oldest first) with one model call."""
    from indico_assistant.services.llm.service import collect_calls

    with collect_calls() as calls:
        response = llm.generate(f"## The latest message\n{message}", ChatAnswer, system_prompt=RULES, messages=history)
    result = KnowledgeResult(NOT_ANSWERED, llm_calls=calls)
    if not response.success:
        result.failed = True
        return result
    paths, guide = links.found_in([m.get("content") for m in history], base_url)
    result.text = links.check(response.result.reply, sorted(paths), guide, base_url)
    return result
