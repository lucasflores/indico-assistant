"""Memory of every kind (spec 025 story 3, T057, FR-021): what each tool touched, kept across turns by id, and
re-checked for access on use."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from indico.core.db.sqlalchemy.protection import ProtectionMode

from indico_assistant.models.message import ChatMessage
from indico_assistant.models.session import ChatSession
from indico_assistant.services.nl2sql.models import PipelineResult
from indico_assistant.services.turn import abilities, memory
from indico_assistant.services.turn.tools import Ctx


def make_ctx(user, **kwargs):
    return Ctx(
        user=user,
        session_id=uuid4(),
        message_id=None,
        page_event_id=None,
        history=[],
        settings={},
        llm=MagicMock(),
        base_url="https://indico.test",
        **kwargs,
    )


def test_the_data_tools_sources_become_events(db, dummy_user, create_event):
    budget = create_event(title="Budget Review")
    ctx = make_ctx(dummy_user)
    pipeline = MagicMock()
    pipeline.process.return_value = PipelineResult(success=True, answer="Monday.", source_event_ids=[budget.id])
    with (
        patch("indico_assistant.plugin.AssistantPlugin"),
        patch("indico_assistant.services.nl2sql.create_nl2sql_pipeline_from_plugin", return_value=pipeline),
    ):
        abilities._query_data(ctx, abilities.QueryDataArgs(tool="query_data", question="When is the budget review?"))
    assert ctx.memory.touched == [
        {"kind": "event", "ref": {"event_id": budget.id}, "title": "Budget Review", "position": 1}
    ]


def test_plans_become_plan_items(dummy_user):
    ctx = make_ctx(dummy_user)
    planned = ("Here is the plan.", {"plan_id": "p1", "cannot_plan": False}, {"id": "p1", "summary": "Move Budget"})
    with patch.object(abilities, "plan", return_value=planned):
        abilities._propose_change(ctx, abilities.ProposeChangeArgs(tool="propose_change", request="move Budget"))
    assert ctx.memory.touched == [{"kind": "plan", "ref": {"plan_id": "p1"}, "title": "Move Budget", "position": 1}]


def test_github_items_come_only_with_a_private_turn(dummy_user):
    ctx = make_ctx(dummy_user)
    tool = SimpleNamespace(run=lambda client, args: ("PR #16", ["https://github.com/o/r/pull/16"]))
    with (
        patch.object(abilities, "_client", return_value=MagicMock()),
        patch("indico_assistant.services.analytics.recorder.private"),
    ):
        abilities._github(tool, ctx, MagicMock())
    assert ctx.private and ctx.memory.touched == [
        {"kind": "github", "ref": {"url": "https://github.com/o/r/pull/16"}, "title": "o/r#16", "position": 1}
    ]
    assert not make_ctx(dummy_user).private  # (no GitHub tool, no GitHub items: they come only with one)


def test_every_kind_resolves_in_a_later_turn_while_it_can_be_opened(db, dummy_user, create_user, create_event):
    budget, hidden = create_event(title="Budget Review"), create_event(title="Board")
    hidden.protection_mode = ProtectionMode.protected
    session = ChatSession.create(user_id=dummy_user.id)
    db.session.flush()
    touched = [
        {"kind": "event", "ref": {"event_id": budget.id}, "title": "Budget Review", "position": 1},
        {"kind": "event", "ref": {"event_id": hidden.id}, "title": "Board", "position": 2},
        {"kind": "plan", "ref": {"plan_id": "p1"}, "title": "Move Budget", "position": 1},
        {"kind": "github", "ref": {"url": "https://github.com/o/r/pull/16"}, "title": "o/r#16", "position": 1},
    ]
    ChatMessage.create(session_id=session.id, role="assistant", content="...", metadata={"touched": touched})
    db.session.flush()
    remembered = memory.load(session.id, None)
    assert remembered == touched
    usable = memory.usable(create_user(77), remembered)  # (someone who can't open the protected event)
    assert [e["title"] for e in usable] == ["Budget Review", "Move Budget", "o/r#16"]
    rendered = memory.Memory(earlier=usable).render()
    assert f"event #1: Budget Review (event_id {budget.id})" in rendered and "github #1: o/r#16" in rendered


def test_the_last_answer_alone_can_be_loaded(db, dummy_user):
    session = ChatSession.create(user_id=dummy_user.id)
    db.session.flush()
    for n in (1, 2):
        item = {
            "kind": "github",
            "ref": {"url": f"https://github.com/o/r/pull/{n}"},
            "title": f"o/r#{n}",
            "position": 1,
        }
        ChatMessage.create(session_id=session.id, role="assistant", content="...", metadata={"touched": [item]})
        db.session.flush()
    assert [e["title"] for e in memory.load(session.id, None)] == ["o/r#2", "o/r#1"]
    assert [e["title"] for e in memory.load(session.id, None, 1)] == ["o/r#2"]
