"""Today's abilities as the turn's tools, unchanged inside (spec 025 story 2, FR-016, contracts/agent-tools.md).

- ``query_data``: the NL2SQL pipeline, offered only while NL2SQL is on for the event, with the event's allowed tables.
- ``ask_guide``: the knowledge answer (the user guide, the pages and what the assistant can do).
- ``ask_github``: the connector's whole answer, offered while GitHub is on; it marks the turn private.
- ``propose_change``: the chat-action planner. It makes a plan; the answer shows the plan card, and confirming stays
  outside the turn (a button or a typed "yes", spec 019), so the agent never applies a change.
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from typing import Any, Literal

from indico.core.db import db
from pydantic import BaseModel, Field

from indico_assistant.services.connectors import Tool
from indico_assistant.services.knowledge.gate import INTENTS
from indico_assistant.services.turn.tools import Ctx

logger = logging.getLogger(__name__)


def _plugin() -> Any:
    from indico_assistant.plugin import AssistantPlugin

    return AssistantPlugin.instance


# --- data ---------------------------------------------------------------------------------------------------------


Kind = Literal[tuple(INTENTS)]  # type: ignore[valid-type]  # the classifier's data intents


class QueryDataArgs(BaseModel):
    """Look up information stored in Indico with one question in plain words: events and meetings (dates, places,
    descriptions), talks and their speakers, sessions, timetables, registrations, minutes and notes, attached files'
    names. Ask exactly what is needed, with the dates and names; "this event" is the page's event."""

    tool: Literal["query_data"]
    question: str
    kind: Kind | None = Field(  # type: ignore[valid-type]
        None,
        description="The kind of question, when clear: "
        + "; ".join(f"{name}: {text}" for name, text in INTENTS.items())
        + " (who speaks or presents is speaker_query; when something starts, ends or how long it lasts is "
        "schedule_query)",
    )


def _query_data(ctx: Ctx, args: QueryDataArgs) -> str:
    from indico.modules.events import Event

    from indico_assistant.services.nl2sql import create_nl2sql_pipeline_from_plugin

    pipeline = create_nl2sql_pipeline_from_plugin(_plugin(), allowed_tables=ctx.allowed_tables)
    viewer = SimpleNamespace(id=ctx.user.id, is_admin=bool(ctx.user.is_admin))
    result = pipeline.process(
        question=args.question,
        user_id=viewer.id,
        user=viewer,
        event_ids=[ctx.page_event_id] if ctx.page_event_id else None,
        conversation_history=ctx.history,
        # the kind the agent named, as Jev's intent was before (spec 022): the classifier took "Who is speaking at Q3
        # Planning?" for a topic search, whose template has no speakers (story 2's full run)
        **({"intent": args.kind} if args.kind else {}),
    )
    for flag, use in (
        ("write_request", "use propose_change"),
        ("knowledge_request", "use ask_guide"),
        ("connector_request", "use ask_github"),
        ("chat_request", "answer it from the conversation"),
    ):
        if getattr(result, flag, False):
            return f"That is not a question about stored data: {use}."
    if not result.success:
        return f"The lookup failed: {result.error.user_message if result.error else 'no answer'}"
    ids = list(getattr(result, "source_event_ids", None) or [])
    for event in Event.query.filter(Event.id.in_(ids), ~Event.is_deleted).all() if ids else []:
        ctx.memory.add("event", {"event_id": event.id}, event.title)
    ctx.data.setdefault("sql", []).append(result.generated_sql)
    ctx.data.setdefault("event_ids", []).extend(i for i in ids if i not in ctx.data.get("event_ids", []))
    ctx.data.setdefault("evidence", []).append(
        {"intent": result.intent, "row_count": result.row_count, "corrections": result.correction_attempts}
    )
    return result.answer or "(no rows)"


# --- the guide ----------------------------------------------------------------------------------------------------


class AskGuideArgs(BaseModel):
    """How to do something in Indico, where a page or setting is, or what the assistant can do: answered from
    Indico's user guide, the pages this user can open, and the assistant's own abilities, with links."""

    tool: Literal["ask_guide"]
    question: str


def _ask_guide(ctx: Ctx, args: AskGuideArgs) -> str:
    from indico.modules.events import Event

    from indico_assistant.services.actions.context import acting_as
    from indico_assistant.services.knowledge import answer as knowledge
    from indico_assistant.services.knowledge.capabilities import capability_list
    from indico_assistant.services.knowledge.guide import get_guide
    from indico_assistant.services.knowledge.pages import page_list

    event = Event.get(ctx.page_event_id, is_deleted=False) if ctx.page_event_id else None
    with acting_as(ctx.user):
        caps, pages = capability_list(ctx.user, event, ctx.settings), page_list(ctx.user, event)
    db.session.commit()  # plain lists now: no transaction stays open through the model call
    guide = get_guide()
    result = knowledge.answer(
        args.question, ctx.history, llm=ctx.llm, caps=caps, pages=pages, guide=guide, base_url=ctx.base_url, event=event
    )
    if result.failed:
        return "The guide could not be asked just now."
    ctx.link_paths.update(p.path for p in pages)
    ctx.guide_urls.update(guide.page_urls or ())
    if result.offer:
        ctx.knowledge_offer = result.offer
    return str(result.text) + (f"\n(Offer to the user: {result.offer})" if result.offer else "")


# --- GitHub -------------------------------------------------------------------------------------------------------


class AskGithubArgs(BaseModel):
    """The user's own GitHub, read with their connection: their pull requests, the reviews waiting for them, their
    issues, searches, an issue or pull request in full, a repository's activity. Ask one question in plain words."""

    tool: Literal["ask_github"]
    question: str


def _ask_github(ctx: Ctx, args: AskGithubArgs) -> str:
    from indico.core.plugins import url_for_plugin

    from indico_assistant.services.analytics import recorder
    from indico_assistant.services.chat.context_builder import get_context_builder
    from indico_assistant.services.connectors.loop import answer

    recorder.private()  # before it runs: a loop that fails half-way has read GitHub too (spec 024 FR-009)
    history = get_context_builder().connector_history(ctx.session_id, up_to=ctx.message_id)
    history = history[:-1] if history and history[-1].get("role") == "user" else history
    result = answer(
        ctx.user.id,
        args.question,
        history,
        llm=ctx.llm,
        settings=ctx.settings,
        base_url=ctx.base_url,
        profile_url=url_for_plugin("assistant.user_connections", _external=True),
        started=ctx.started,
    )
    if result.access is None:  # (the loop ran: GitHub's data is in this answer, and later prompts)
        ctx.private = True
    ctx.github_urls.update(result.urls)
    return str(result.text)


# --- changes ------------------------------------------------------------------------------------------------------


class ProposeChangeArgs(BaseModel):
    """Plan a change in Indico for the user to confirm: create or change a meeting or its talks, add a speaker, a
    reminder, a Teams meeting or material, cancel or undo. Write the request in the user's words, naming meetings and
    talks by their titles (never by ids); the page's event is "this meeting". The user sees the plan and confirms it;
    nothing changes until they do."""

    tool: Literal["propose_change"]
    request: str


def plan(
    user: Any,
    session_id: Any,
    message: str,
    history: list[dict[str, str]],
    waiting_plan: Any,
    page_event_id: int | None,
    offer: str | None = None,
) -> tuple[str, dict[str, Any], Any] | None:
    """The planner's answer as (reply, metadata, plan), or None when the message turns out to be a question.
    ``offer``: the change the last answer offered, which a plain yes plans."""
    from indico_assistant.services.actions.context import acting_as
    from indico_assistant.services.actions.planner import plan_turn

    plugin = _plugin()
    with acting_as(user):  # resolving names and checking permissions reads Indico as the user
        turn = plan_turn(
            user,
            session_id,
            message,
            history,
            waiting_plan,
            llm=plugin.llm_service,
            settings=plugin.settings.get_all(),
            page_event_id=page_event_id,
            offer=offer,
        )
    if not turn.handled:
        return None
    metadata = {"plan_id": turn.plan["id"] if turn.plan else None, "cannot_plan": turn.cannot_plan}
    if turn.problem:
        metadata["problem"] = turn.problem  # the chat offers a report under it (spec 021 R4)
    return turn.reply, metadata, turn.plan


_EVENT_ID = re.compile(
    r"\s*\(?\b(?:event|meeting)\s+(?:id\s+)?#?(\d+)\b"
    r"(?![.:]\d|\s*(?:%|[ap]\.?m\b|h\b|hrs?\b|hours?\b|min|sec|days?\b|weeks?\b|months?\b|years?\b|times?\b))\)?",
    re.I,
)  # (a quantity is not an id: "move the meeting 2 hours later")


def by_name(request: str, page_event_id: int | None) -> str:
    """The request with "event 1803" put back as the meeting's title (or "this meeting" for the page's): the
    planner finds meetings by name, and the model sometimes wrote their ids (quick run 2)."""
    from indico.modules.events import Event

    def title(match: re.Match[str]) -> str:
        event_id = int(match.group(1))
        if event_id == page_event_id:
            return " this meeting"
        event = Event.get(event_id, is_deleted=False)
        if event is None:
            return match.group(0)
        return "" if event.title.lower() in request.lower() else f' "{event.title}"'

    return _EVENT_ID.sub(title, request).strip()


def _propose_change(ctx: Ctx, args: ProposeChangeArgs) -> str:
    request = by_name(args.request, ctx.page_event_id)
    planned = plan(ctx.user, ctx.session_id, request, ctx.history, ctx.waiting_plan, ctx.page_event_id, ctx.offer)
    if planned is None or (planned[1].get("cannot_plan") and ctx.waiting_plan is None):
        return planned[0] if planned else "That is not a change the assistant can plan."
    ctx.plan = planned
    if planned[2]:
        ctx.memory.add("plan", {"plan_id": planned[2]["id"]}, planned[2].get("summary") or args.request)
    return planned[0]


QUERY_DATA = Tool("query_data", QueryDataArgs, _query_data)
ASK_GUIDE = Tool("ask_guide", AskGuideArgs, _ask_guide)
ASK_GITHUB = Tool("ask_github", AskGithubArgs, _ask_github)
PROPOSE_CHANGE = Tool("propose_change", ProposeChangeArgs, _propose_change)


def registry(ctx: Ctx, *, nl2sql: bool, github: bool) -> tuple[Tool, ...]:
    """The tools this turn offers: the document tools, the data tool while NL2SQL is on for the event, the guide,
    GitHub while an admin has it on, and changes."""
    from indico_assistant.services.turn.tools import DOCUMENT_TOOLS

    return (
        *DOCUMENT_TOOLS,
        *((QUERY_DATA,) if nl2sql else ()),
        ASK_GUIDE,
        *((ASK_GITHUB,) if github else ()),
        PROPOSE_CHANGE,
    )


__all__ = ["registry", "plan"]
