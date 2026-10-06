"""Today's abilities as the turn's tools, unchanged inside (spec 025 stories 2 and 3, FR-016, contracts/agent-tools.md).

- ``query_data``: the NL2SQL pipeline, offered only while NL2SQL is on for the event, with the event's allowed tables.
- ``ask_guide``: the knowledge answer (the user guide, the pages and what the assistant can do).
- ``github_*``: the connector's own read tools, offered while GitHub is on and the user has connected it; a turn that
  calls one is private.
- ``propose_change``: the chat-action planner. It makes a plan; the answer shows the plan card, and confirming stays
  outside the turn (a button or a typed "yes", spec 019), so the agent never applies a change.
"""

from __future__ import annotations

import logging
import re
from functools import cache, partial
from types import SimpleNamespace
from typing import Any, Literal

from indico.core.db import db
from pydantic import BaseModel, Field, create_model

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
        ("connector_request", "use the github tools"),
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
# The connector's own read tools (``connectors/github.py``), called by the turn as ``github_<name>``, over one client
# per turn made with the user's token. Offered only to a connected user; a turn that reads GitHub is private.

CONNECT = (
    "GitHub: the user hasn't connected it. To read their GitHub, they connect it on the Connected accounts page of "
    "their profile: {url}"
)
RENEW = (
    "GitHub: it no longer accepts the user's connection. They connect it again on the Connected accounts page of "
    "their profile: {url}"
)
UNAVAILABLE = "GitHub couldn't be reached just now: say so, and that the user can try again in a moment."


def _profile_url(ctx: Ctx) -> str:
    from urllib.parse import urlsplit

    from indico.core.plugins import url_for_plugin

    url = str(url_for_plugin("assistant.user_connections", _external=True))
    ctx.link_paths.add(urlsplit(url).path)  # (this Indico's page: the answer may link it)
    return url


def github_note(ctx: Ctx) -> str | None:
    """Why this user gets no GitHub tools (None: they get them). Read from the stored connection, without a call."""
    from indico_assistant.services.connectors import store

    row = store.connection(ctx.user.id)
    if row is None:
        return CONNECT.format(url=_profile_url(ctx))
    if row.needs_renewal:
        return RENEW.format(url=_profile_url(ctx))
    return None


def _client(ctx: Ctx) -> Any:
    """The turn's GitHub client (made on first use, bounded by the turn's deadline), or why there is none."""
    from indico_assistant.services.connectors import github, store

    if ctx.github is None:
        access = store.token(ctx.user.id, github.app_for(ctx.settings))
        if access.state != store.OK:
            reply = {store.RENEW: RENEW, store.UNAVAILABLE: UNAVAILABLE}.get(access.state, CONNECT)
            return reply.format(url=_profile_url(ctx))
        store.used(ctx.user.id)  # (commits: no transaction stays open through the calls)
        ctx.github = github.client_for(access.token, ctx.settings)
        ctx.github.deadline = ctx.deadline  # (every GitHub call inside the turn's time, however many one tool makes)
    return ctx.github


def _title(url: str) -> str:
    """owner/repo#12 for an item's address, owner/repo for a repository's."""
    parts = url.removeprefix("https://github.com/").split("/")
    return f"{parts[0]}/{parts[1]}#{parts[3]}" if len(parts) >= 4 and parts[3].isdigit() else "/".join(parts[:2])


def _github(tool: Tool, ctx: Ctx, args: Any) -> str:
    from indico_assistant.services.analytics import recorder
    from indico_assistant.services.connectors import github, store

    recorder.private()  # before it runs: a call that fails half-way may have read GitHub too (spec 024 FR-009)
    client = _client(ctx)
    if isinstance(client, str):
        return client
    ctx.private = True  # (GitHub's data is in this turn, and in the prompts of the chat's later turns)
    try:
        out = tool.run(client, args)
    except github.GitHubError as error:
        if error.status == 401:  # (the grant was revoked on GitHub: the stored token looked fine until now)
            store.renew(ctx.user.id)
            return RENEW.format(url=_profile_url(ctx))
        return f"GitHub error {error.status}: {error.message}"
    found: Any = out if isinstance(out, tuple) else (out, [])
    text, urls = found[0], [str(u) for u in found[1]]
    ctx.github_urls.update(urls)  # (never scraped from the text: a body or a comment can hold any address)
    for url in urls:
        ctx.memory.add("github", {"url": url}, _title(url))
    return str(text)


def _github_tool(tool: Tool) -> Tool:
    args = create_model(  # (the same arguments, named for the turn: "search" alone would be ambiguous)
        f"Github{tool.args.__name__}",
        __base__=tool.args,
        __doc__=tool.args.__doc__,
        tool=(Literal[f"github_{tool.name}"], ...),  # type: ignore[valid-type]
    )
    return Tool(f"github_{tool.name}", args, partial(_github, tool))


@cache
def _github_tools() -> tuple[Tool, ...]:
    from indico_assistant.services.connectors.github import TOOLS

    return tuple(_github_tool(t) for t in TOOLS)


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
    r"(?![.:]\d|\s*(?:%|[ap]\.?m\b|h\b|hrs?\b|hours?\b|min|sec|days?\b|weeks?\b|months?\b|years?\b|times?\b"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b))\)?",
    re.I,
)  # (a quantity or a date is not an id: "move the meeting 2 hours later", "a meeting 12 November")


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


def found_meetings(ctx: Ctx) -> str:
    """The meetings this turn has looked up, by title and date, for the planner: it finds meetings by name, and
    "move the talk the notes mention" needs the meeting the notes came from (story 3, T063)."""
    from indico.modules.events import Event

    ids = [e["ref"]["event_id"] for e in ctx.memory.touched if e["kind"] == "event"]
    events = Event.query.filter(Event.id.in_(ids), ~Event.is_deleted).all() if ids else []
    found = [
        f'"{e.title}" ({e.start_dt.astimezone(e.tzinfo):%A %d %B %Y})' for e in events if e.id != ctx.page_event_id
    ]
    return f"\n(Meetings found while answering: {'; '.join(found)})" if found else ""


def _propose_change(ctx: Ctx, args: ProposeChangeArgs) -> str:
    request = by_name(args.request, ctx.page_event_id) + found_meetings(ctx)
    planned = plan(ctx.user, ctx.session_id, request, ctx.history, ctx.waiting_plan, ctx.page_event_id, ctx.offer)
    if planned is None or (planned[1].get("cannot_plan") and ctx.waiting_plan is None):
        return planned[0] if planned else "That is not a change the assistant can plan."
    ctx.plan = planned
    if planned[2]:
        ctx.memory.add("plan", {"plan_id": planned[2]["id"]}, planned[2].get("summary") or args.request)
    return planned[0]


QUERY_DATA = Tool("query_data", QueryDataArgs, _query_data)
ASK_GUIDE = Tool("ask_guide", AskGuideArgs, _ask_guide)
PROPOSE_CHANGE = Tool("propose_change", ProposeChangeArgs, _propose_change)


def registry(ctx: Ctx, *, nl2sql: bool, github: bool) -> tuple[Tool, ...]:
    """The tools this turn offers: the document tools, the data tool while NL2SQL is on for the event, the guide,
    GitHub's while an admin has it on and the user has connected it, and changes."""
    from indico_assistant.services.turn.tools import DOCUMENT_TOOLS

    return (
        *DOCUMENT_TOOLS,
        *((QUERY_DATA,) if nl2sql else ()),
        ASK_GUIDE,
        *(_github_tools() if github else ()),
        PROPOSE_CHANGE,
    )


__all__ = ["registry", "plan"]
