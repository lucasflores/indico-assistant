"""The turn: every message's single way in (spec 025, FR-016, research R2).

First one Jev decision (the fast path): a ``chat`` or ``out_of_scope`` message Jev is sure of is answered on its
own, by today's chat answer or refusal. Everything else, and any message whose decision was skipped, is answered by
the agent with its tools (``loop.run``): documents, data, the guide, GitHub and planned changes. The plan shortcuts
(a typed yes or no, an exact reply to a plan) run before this, in the chat service, as in spec 019.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from indico_assistant.services.turn.loop import TurnResult

logger = logging.getLogger(__name__)

DISABLED = "The assistant is turned off for this event."
#: Jev's routes that need something looked up (its chat and out_of_scope don't)
LOOKUP_ROUTES = {"data", "knowledge", "connector", "change"}
DOCUMENT_WORDS = re.compile(
    r"\b(papers?|thesis|theses|reports?|slides?|talks?|documents?|surveys?|articles?|pdfs?|files?|attachments?|"
    r"minutes|notes|proposals?|chapters?|sections?|page \d+)\b",
    re.I,
)


def in_presented_order(touched: list[dict[str, Any]], presented: list[int]) -> list[dict[str, Any]]:
    """The touched list with its documents in the order the answer showed them (the ones it named, then the others,
    as looked up), positions renumbered: "the second one" is the answer's second."""
    rank = {doc: i for i, doc in enumerate(dict.fromkeys(presented))}
    documents = sorted(
        (e for e in touched if e["kind"] == "document"),
        key=lambda e: rank.get(e["ref"]["attachment_id"], len(rank)),
    )
    others = [e for e in touched if e["kind"] != "document"]
    return [{**e, "position": n} for n, e in enumerate(documents, 1)] + others


@dataclass
class Outcome:
    text: str
    metadata: dict[str, Any]
    route: str  # fast:chat | fast:out_of_scope | agent
    plan: dict[str, Any] | None = None
    decision: Any = None
    result: Any = None  # the chat answer's KnowledgeResult, or the agent's TurnResult
    tools: list[dict[str, Any]] = field(default_factory=list)
    private: bool = False
    offer: str | None = None


#: The event settings with a global one of their own (the rest, allowed_tables and custom_system_prompt, have none)
GLOBAL_OF = {"enabled": "enabled", "nl2sql_enabled": "nl2sql_enabled"}


def event_setting(plugin: Any, event: Any, key: str) -> Any:
    """An event's own setting, else the global one when there is one. The event form saves "" for "inherit" and
    "true"/"false" for its switches (``plugin.get_effective_setting`` took "" for a value)."""
    value = plugin.event_settings.get(event, key) if event is not None else None
    if value is None or value == "":
        return plugin.settings.get(GLOBAL_OF[key]) if key in GLOBAL_OF else None
    if value in ("true", "false"):
        return value == "true"
    return value


def disabled_for(event: Any) -> bool:
    from indico_assistant.plugin import AssistantPlugin

    return event is not None and event_setting(AssistantPlugin.instance, event, "enabled") is False


def answer(
    user: Any,
    session_id: UUID,
    message: str,
    message_id: UUID | None,
    context: list[dict[str, str]],
    page_event_id: int | None,
    *,
    waiting_plan: Any = None,
    offer: str | None = None,
    started: float | None = None,
    github_on: bool = False,
    embedder: Any = None,
) -> Outcome:
    """Answer ``message``: the fast path, else the agent. ``context`` is the conversation ending with the message
    (a system note of the page may come before it)."""
    from indico.modules.events import Event

    from indico_assistant.plugin import AssistantPlugin
    from indico_assistant.services.knowledge import gate
    from indico_assistant.services.knowledge.chat import chat_answer
    from indico_assistant.services.nl2sql.pipeline import OUT_OF_SCOPE_MESSAGE

    plugin = AssistantPlugin.instance
    settings = plugin.settings.get_all()
    history = _history(context)
    base_url = base_url_of(settings)

    decision = gate.decide(context, settings, connector=github_on)
    sure = not decision.skipped and (decision.confidence or 0.0) >= float(settings.get("fast_path_confidence") or 0.8)
    if sure and decision.route == "chat":
        chat = chat_answer(message, history, llm=plugin.llm_service, base_url=base_url)
        return Outcome(
            chat.text, {"problem": "failed"} if chat.failed else {}, "fast:chat", decision=decision, result=chat
        )
    if sure and decision.route == "out_of_scope" and settings.get("fast_path_out_of_scope", True):
        return Outcome(OUT_OF_SCOPE_MESSAGE, {"problem": "out_of_scope"}, "fast:out_of_scope", decision=decision)

    event = Event.get(page_event_id, is_deleted=False) if page_event_id else None
    return _agent(
        user,
        session_id,
        message,
        message_id,
        history,
        page_event_id,
        event,
        decision=decision,
        settings=settings,
        base_url=base_url,
        waiting_plan=waiting_plan,
        offer=offer,
        started=started,
        github_on=github_on,
        embedder=embedder,
    )


def _agent(
    user: Any,
    session_id: UUID,
    message: str,
    message_id: UUID | None,
    history: list[dict[str, str]],
    page_event_id: int | None,
    event: Any,
    *,
    decision: Any,
    settings: dict[str, Any],
    base_url: str,
    waiting_plan: Any,
    offer: str | None,
    started: float | None,
    github_on: bool,
    embedder: Any,
) -> Outcome:
    from indico.core.db import db

    from indico_assistant.plugin import AssistantPlugin
    from indico_assistant.services.knowledge import links
    from indico_assistant.services.turn import loop, memory
    from indico_assistant.services.turn.abilities import registry
    from indico_assistant.services.turn.citations import from_markers, validate
    from indico_assistant.services.turn.rules import rules
    from indico_assistant.services.turn.tools import Ctx

    plugin = AssistantPlugin.instance
    remembered = memory.usable(user, memory.load(session_id, message_id))
    allowed = event_setting(plugin, event, "allowed_tables") if event is not None else None
    if isinstance(allowed, str):
        allowed = [t.strip() for t in allowed.split(",") if t.strip()] or None
    ctx = Ctx(
        user=user,
        session_id=session_id,
        message_id=message_id,
        page_event_id=page_event_id,
        history=history,
        settings=settings,
        llm=plugin.llm_service,
        base_url=base_url,
        embedder=embedder,
        memory=memory.Memory(earlier=remembered),
        allowed_tables=allowed,
        waiting_plan=waiting_plan,
        offer=offer,
        started=started,
    )
    if page_event_id is not None:  # FR-011: the turn knows the page's documents without a lookup
        from indico_assistant.services.document import reader

        ctx.page_documents = reader.describe_all(reader.documents(user, event_id=page_event_id))
    nl2sql = (
        bool(event_setting(plugin, event, "nl2sql_enabled"))
        if event is not None
        else bool(settings.get("nl2sql_enabled", True))
    )
    custom = event_setting(plugin, event, "custom_system_prompt") if event is not None else None
    if github_on:  # (GitHub's tools for a connected user; otherwise the prompt says how to connect)
        from indico_assistant.services.turn.abilities import github_note

        ctx.github_note = github_note(ctx)
    db.session.commit()  # no transaction stays open through the model calls
    # the first step must look something up when documents are in play (the page's, the conversation's, or one
    # named), or when Jev routed the message to a lookup (story 3's full runs: with GitHub's seven tools offered,
    # answers "couldn't retrieve" what they never looked up went from 3 to 13). Chat stays free of lookups (FR-022).
    lookup_first = bool(
        ctx.page_documents
        or ctx.memory.documents()
        or DOCUMENT_WORDS.search(message)
        or (not decision.skipped and decision.route in LOOKUP_ROUTES)
    )
    try:
        result: TurnResult = loop.run(
            ctx,
            message,
            registry(ctx, nl2sql=nl2sql, github=github_on and ctx.github_note is None),
            system_prompt=rules(custom),
            lookup_first=lookup_first,
        )
    finally:
        if ctx.github is not None:
            ctx.github.close()

    plan = None
    if ctx.plan is not None:  # the planner's reply and plan card are the answer
        text, metadata, plan = ctx.plan
        metadata = dict(metadata)
    else:
        paths, guide = links.found_in([m.get("content") for m in history] + [message], base_url)
        urls = ctx.github_urls | earlier_github(history)
        text = (
            clean(result.text, sorted(paths | ctx.link_paths), guide | ctx.guide_urls, base_url, urls)
            or loop.NOT_ANSWERED
        )
        metadata = {"problem": "failed"} if result.failed else {}
    cited = validate(user, result.citations) if result.citations else []
    cited += from_markers(text, ctx.pages_seen, cited)
    if cited:
        metadata["citations"] = cited
    if ctx.data.get("event_ids"):
        metadata["data_sources"] = [
            {"type": "event", "event_id": i, "url": f"{base_url}/event/{i}/"} for i in ctx.data["event_ids"]
        ]
    if ctx.data.get("evidence"):  # for a report's triage (spec 021 R5): each lookup, and the SQL it ran
        metadata["evidence"] = {"queries": ctx.data["evidence"]}
        metadata["sql_generated"] = "\n\n".join(s for s in ctx.data.get("sql") or [] if s) or None
    metadata["touched"] = in_presented_order(ctx.memory.touched, result.presented)
    return Outcome(
        text,
        metadata,
        "agent",
        plan=plan,
        decision=decision,
        result=result,
        tools=result.tools,
        private=ctx.private,
        offer=ctx.knowledge_offer,
    )


GITHUB_URL = re.compile(r"https://github\.com/[^\s<>()\[\]\"'`]+")


def earlier_github(history: list[dict[str, str]]) -> set[str]:
    """The GitHub items earlier answers linked (checked when they were given): the answer may link them again."""
    return {
        u.rstrip(".,;:!?")
        for m in history
        if m.get("role") == "assistant"
        for u in GITHUB_URL.findall(m.get("content") or "")
    }


def clean(text: str, paths: list[str], guide: set[str], base_url: str, urls: set[str]) -> str | None:
    """The answer's links checked until checking changes nothing: one pass can rebuild an image out of nested
    markup, e.g. ``!![[x](…)](//evil…)`` (spec 023's fresh-review). Markup still changing after 10 passes is
    refused."""
    from indico_assistant.services.knowledge import links

    for _ in range(10):
        cleaned = links.check(links.strip_images(text), paths, guide, base_url, urls=urls, strict=True)
        if cleaned == text:
            return text
        text = cleaned
    return None


def _history(context: list[dict[str, str]]) -> list[dict[str, str]]:
    """The conversation before the message: user and assistant turns only (a page note is in the prompt)."""
    turns = [m for m in context if m.get("role") in ("user", "assistant")]
    return turns[:-1] if turns and turns[-1].get("role") == "user" else turns


def base_url_of(settings: dict[str, Any]) -> str:
    from indico.core.config import config

    return (config.BASE_URL or settings.get("base_url") or "http://localhost:8000").rstrip("/")
