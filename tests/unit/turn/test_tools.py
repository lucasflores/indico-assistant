"""The turn's tools: documents (real DB) and today's abilities, wrapped (spec 025, T045/T046)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from indico.modules.attachments.models.attachments import AttachmentFile

from indico_assistant.services.connectors.loop import ConnectorResult
from indico_assistant.services.knowledge.answer import KnowledgeResult
from indico_assistant.services.turn import abilities, tools
from indico_assistant.services.turn.memory import Memory
from indico_assistant.services.turn.tools import Ctx
from indico_assistant.tasks import indexing


def make_ctx(user, page_event_id=None, **kwargs):
    return Ctx(
        user=user,
        session_id=uuid4(),
        message_id=uuid4(),
        page_event_id=page_event_id,
        history=[],
        settings={},
        llm=MagicMock(),
        base_url="https://indico.test",
        **kwargs,
    )


@pytest.fixture
def document(db, dummy_user, create_attachment, fake_embedder):
    def _document(event, content, filename):
        attachment = create_attachment(dummy_user, event, title=filename)
        attachment.file = AttachmentFile(user=dummy_user, filename=filename, content_type="text/plain")
        attachment.file.save(content.encode())
        db.session.flush()
        with patch.object(indexing, "_vector_search_enabled", return_value=True):
            indexing.index_attachment(attachment, embedder=fake_embedder)
        return attachment

    return _document


def run(tool, ctx, **args):
    return tool.run(ctx, tool.args(tool=tool.name, **args))


def by_name(name):
    return next(t for t in tools.DOCUMENT_TOOLS if t.name == name)


def test_list_documents_on_the_page_in_the_conversation_or_an_event(
    db, dummy_user, dummy_event, create_event, document
):
    other = create_event(title="Other")
    a = document(dummy_event, "# Minutes\nApproved.", "minutes.md")
    b = document(other, "Slides text.", "slides.txt")
    ctx = make_ctx(dummy_user, page_event_id=dummy_event.id)
    listed = run(by_name("list_documents"), ctx, scope="page")
    assert '"filename": "minutes.md"' in listed and "slides.txt" not in listed
    assert f'"event": "{dummy_event.id}: {dummy_event.title}"' in listed
    assert ctx.memory.touched == [
        {"kind": "document", "ref": {"attachment_id": a.id}, "title": "minutes.md", "position": 1}
    ]
    assert "slides.txt" in run(by_name("list_documents"), ctx, scope=f"event:{other.id}")
    remembered = make_ctx(
        dummy_user,
        memory=Memory(
            earlier=[{"kind": "document", "ref": {"attachment_id": b.id}, "title": "slides.txt", "position": 1}]
        ),
    )
    assert "slides.txt" in run(by_name("list_documents"), remembered, scope="conversation")
    assert run(by_name("list_documents"), make_ctx(dummy_user), scope="page") == "The user is not on an event page now."


def test_read_document_remembers_what_it_read(db, dummy_user, dummy_event, document):
    a = document(dummy_event, "# Minutes\nApproved.", "minutes.md")
    ctx = make_ctx(dummy_user)
    text = run(by_name("read_document"), ctx, document=a.id)
    assert "[p.1]" in text and text.startswith(f"(attached to event {dummy_event.id}: ")
    assert ctx.memory.documents() == [a.id] and ctx.pages_seen == {a.id: {1}}
    assert run(by_name("read_document"), make_ctx(dummy_user), document=999999).startswith("No document")


def test_search_documents_labels_each_passage(db, dummy_user, dummy_event, document, fake_embedder):
    a = document(dummy_event, "The look-up table is stored as ROOT histograms.", "talk.txt")
    ctx = make_ctx(dummy_user, embedder=fake_embedder)
    found = run(by_name("search_documents"), ctx, query="look-up table", document=a.id)
    assert found.startswith(f"document {a.id} (talk.txt, in event {dummy_event.id}: {dummy_event.title}), [p.1]")
    assert ctx.memory.documents() == [a.id] and ctx.pages_seen == {a.id: {1}}
    assert run(by_name("search_documents"), ctx, query="nothing like it", document=999999) == "No passages found."


def test_ask_guide_answers_and_keeps_its_links_and_offer(dummy_user):
    ctx = make_ctx(dummy_user)
    guide = SimpleNamespace(page_urls={"https://learn.getindico.io/x/"})
    with (
        patch("indico_assistant.services.actions.context.acting_as"),
        patch("indico_assistant.services.knowledge.capabilities.capability_list"),
        patch(
            "indico_assistant.services.knowledge.pages.page_list",
            return_value=[SimpleNamespace(path="/event/5/manage/")],
        ),
        patch("indico_assistant.services.knowledge.guide.get_guide", return_value=guide),
        patch(
            "indico_assistant.services.knowledge.answer.answer",
            return_value=KnowledgeResult("Use Lock.", offer="lock the event"),
        ),
        patch.object(abilities, "db"),
    ):
        text = abilities._ask_guide(ctx, abilities.AskGuideArgs(tool="ask_guide", question="how do I lock it?"))
    assert text == "Use Lock.\n(Offer to the user: lock the event)"
    assert ctx.knowledge_offer == "lock the event" and "/event/5/manage/" in ctx.link_paths
    assert ctx.guide_urls == {"https://learn.getindico.io/x/"}


@pytest.mark.parametrize(("access", "private"), [(None, True), ("not_connected", False)])
def test_ask_github_is_private_once_github_was_read(dummy_user, access, private):
    ctx = make_ctx(dummy_user)
    result = ConnectorResult("Open: #16", urls={"https://github.com/o/r/pull/16"}, access=access)
    builder = MagicMock()
    builder.connector_history.return_value = [{"role": "user", "content": "my PRs?"}]
    with (
        patch("indico_assistant.services.connectors.loop.answer", return_value=result) as answer,
        patch("indico_assistant.services.chat.context_builder.get_context_builder", return_value=builder),
        patch("indico.core.plugins.url_for_plugin", return_value="https://indico.test/connections"),
        patch("indico_assistant.services.analytics.recorder.private") as recorded,
    ):
        text = abilities._ask_github(ctx, abilities.AskGithubArgs(tool="ask_github", question="my PRs?"))
    assert text == "Open: #16" and ctx.private is private and recorded.called is private
    assert answer.call_args.args[2] == []  # (the question itself isn't its own history)
    assert ctx.github_urls == {"https://github.com/o/r/pull/16"}


def test_propose_change_keeps_the_plan_or_says_why_not(dummy_user):
    ctx = make_ctx(dummy_user)
    args = abilities.ProposeChangeArgs(tool="propose_change", request="move Budget to 3pm")
    with patch.object(abilities, "plan", return_value=None):
        assert abilities._propose_change(ctx, args) == "That is not a change the assistant can plan."
    with patch.object(abilities, "plan", return_value=("I can't do that.", {"cannot_plan": True}, None)):
        assert abilities._propose_change(ctx, args) == "I can't do that." and ctx.plan is None
    planned = ("Here is the plan.", {"plan_id": "p1", "cannot_plan": False}, {"id": "p1", "summary": "Move Budget"})
    with patch.object(abilities, "plan", return_value=planned):
        assert abilities._propose_change(ctx, args) == "Here is the plan."
    assert ctx.plan == planned and ctx.memory.touched[-1]["ref"] == {"plan_id": "p1"}


def test_a_waiting_plan_keeps_the_planners_reply_even_when_it_cannot_plan(dummy_user):
    ctx = make_ctx(dummy_user, waiting_plan=MagicMock())
    cannot = ("Which meeting do you mean?", {"cannot_plan": True}, None)
    with patch.object(abilities, "plan", return_value=cannot):
        abilities._propose_change(ctx, abilities.ProposeChangeArgs(tool="propose_change", request="make it 30"))
    assert ctx.plan == cannot


def test_the_registry_offers_data_and_github_only_when_on():
    ctx = make_ctx(MagicMock())
    names = [t.name for t in abilities.registry(ctx, nl2sql=False, github=False)]
    assert names == ["list_documents", "read_document", "search_documents", "ask_guide", "propose_change"]
    names = [t.name for t in abilities.registry(ctx, nl2sql=True, github=True)]
    assert "query_data" in names and "ask_github" in names
