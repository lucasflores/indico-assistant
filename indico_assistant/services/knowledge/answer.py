"""The knowledge answer: "how do I…" and "can you…" (spec 022, FR-017 and FR-018).

One model call through the plugin's LLM service. The rules are the system prompt; the prompt carries the guide
excerpts, the page list and the capability list, in that order (the capability list nearest the question: the
research saw self-knowledge dilute when the guide came after it). The links are checked by code afterwards.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from indico_assistant.services.knowledge import links
from indico_assistant.services.knowledge import pages as page_list

RULES = """You are the assistant built into Indico, the event management system. The user asks how to do something in
Indico, where something is, or what you can do for them.

Rules:
- About yourself: claim only the abilities under "What I can do". For anything else, say you can't, give the reason
  when one is given, and say how the user can do it themselves, or who can (never name people).
- When you can make the change they ask about, say so and offer it ("Shall I?"); never say it is done. Put that change,
  in the user's words, in `offer`; otherwise leave `offer` empty. Say briefly how to do it by hand too.
- What is listed under "Never" is never offered: explain, and link the page where the user, or a manager, does it.
- Link to pages of this Indico only from "Pages", as markdown links with the path exactly as given. Never make up a
  URL.
- Cite the guide pages you used, as markdown links.
- The guide describes Indico in general. "Pages" and "What I can do" are the truth for this user on this Indico: when
  they disagree with the guide (a feature switched off, a page missing), they win.
- If the material does not cover the question, say so plainly. Never invent menus, buttons, pages or steps.
- Answer in the language of the question. Be short: a few sentences, or a short numbered list."""

NOT_ANSWERED = "I could not answer that just now. Please try again in a moment."


class KnowledgeAnswer(BaseModel):
    reply: str = Field(..., description="The answer to the user, in markdown")
    offer: str | None = Field(None, description="The change the reply offers to make, in the user's words; else null")


@dataclass
class KnowledgeResult:
    text: str
    offer: str | None = None
    guide_commit: str | None = None
    guide_pages: list = field(default_factory=list)  # the excerpts' pages, nearest first
    failed: bool = False
    llm_calls: list = field(default_factory=list)


def _excerpts_block(excerpts):
    if not excerpts:
        return "(no guide excerpts available)"
    return "\n\n".join(f"[{e['title']}]({e['url']})\n{e['text']}" for e in excerpts)


def answer(message, history, *, llm, caps, pages, guide, base_url, event=None):
    """Answer ``message``. ``caps`` and ``pages`` are this user's lists (built as the user by the caller)."""
    from indico_assistant.services.llm.service import collect_calls

    excerpts = guide.excerpts(message)
    prompt = "\n\n".join((
        "## Indico's user guide (excerpts; cite the ones you use)\n" + _excerpts_block(excerpts),
        "## Pages\n" + page_list.render(pages, event),
        "## What I can do\n" + caps.render(),
        "## The question\n" + message,
    ))
    with collect_calls() as calls:
        response = llm.generate(prompt, KnowledgeAnswer, system_prompt=RULES, messages=history)
    result = KnowledgeResult(NOT_ANSWERED, guide_commit=guide.commit if guide.ok else None,
                             guide_pages=[e["url"] for e in excerpts], llm_calls=calls)
    if not response.success:
        result.failed = True
        return result
    result.text = links.check(response.result.reply, [p.path for p in pages], guide.page_urls, base_url)
    result.offer = (response.result.offer or "").strip() or None
    return result
