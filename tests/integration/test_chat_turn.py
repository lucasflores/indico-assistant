"""A document question through the whole chat, on a real database (spec 025, T037).

POST /chat → the worker's task → the turn (Jev skipped: no key; the agent with a scripted model) → the job's answer
carries validated citations, and the session's history shows the route and what the answer touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from indico.modules.attachments.models.attachments import AttachmentFile

import indico_assistant.controllers.chat as chat_module
import indico_assistant.controllers.sessions as sessions_module
from indico_assistant.controllers.chat import RHChat, RHChatJob
from indico_assistant.controllers.sessions import RHSessionDetail
from indico_assistant.services.chat import jobs
from indico_assistant.services.llm.models import LLMResponse
from indico_assistant.services.turn import loop, tools
from indico_assistant.services.turn.citations import Citation
from indico_assistant.tasks import indexing
from indico_assistant.tasks.chat import answer_chat


class FakeCache(dict):
    def set(self, key, value, timeout=None):
        self[key] = value


class Script:
    """The model: search the documents, then answer citing p.1."""

    def __init__(self, document_id):
        self.document_id, self.n = document_id, 0

    def generate(self, prompt, response_model, **kwargs):
        self.n += 1
        if self.n == 1:
            step = response_model(call=tools.SearchDocumentsArgs(tool="search_documents", query="pile-up kinds"))
        else:
            assert "<tool_data>" in prompt and "in-time and out-of-time" in prompt
            step = response_model(
                answer=loop.Final(
                    reply="Pile-up comes in two kinds, in-time and out-of-time [p.1].",
                    citations=[Citation(document=self.document_id, page=1, quote="in-time and out-of-time")],
                )
            )
        return LLMResponse(success=True, result=step, latency_ms=1, calls=[])


@pytest.fixture
def thesis(db, dummy_user, dummy_event, create_attachment, fake_embedder):
    attachment = create_attachment(dummy_user, dummy_event, title="Thesis")
    attachment.file = AttachmentFile(user=dummy_user, filename="thesis.md", content_type="text/plain")
    attachment.file.save(b"# Thesis\nPile-up comes in two kinds: in-time and out-of-time.")
    db.session.flush()
    with patch.object(indexing, "_vector_search_enabled", return_value=True):
        assert indexing.index_attachment(attachment, embedder=fake_embedder)["status"] == "ready"
    db.session.commit()
    return attachment


def test_a_document_question_is_answered_with_citations(
    db, dummy_user, dummy_event, thesis, fake_embedder, monkeypatch
):
    monkeypatch.setattr(jobs, "_cache", FakeCache())
    request = MagicMock()
    monkeypatch.setattr(chat_module, "request", request)
    monkeypatch.setattr(sessions_module, "request", request)
    queued = []

    def rh(cls):
        controller = cls.__new__(cls)
        controller._user = dummy_user
        return controller

    from indico_assistant.default_settings import DEFAULT_SETTINGS

    plugin = MagicMock(llm_service=Script(thesis.id))  # (the plugin isn't loaded in the test app)
    plugin.settings.get_all.return_value = {**DEFAULT_SETTINGS, "jev_api_key": None}
    plugin.settings.get.side_effect = lambda key, default=None: plugin.settings.get_all.return_value.get(key, default)
    plugin.event_settings.get.return_value = None
    with (
        patch.object(answer_chat, "delay", side_effect=lambda *args: queued.append(args)),
        patch("indico_assistant.plugin.AssistantPlugin", MagicMock(instance=plugin, settings=plugin.settings)),
        patch.object(tools, "_embedder", return_value=fake_embedder),
    ):
        request.get_json.return_value = {
            "message": "What kinds of pile-up does the thesis describe?",
            "event_id": dummy_event.id,
        }
        response, status = rh(RHChat)._process()
        assert status == 202
        body = response.get_json()
        answer_chat.run(*queued[0])  # what the worker does
        request.view_args = {"job_id": body["job_id"]}
        job, status = rh(RHChatJob)._process()
        assert status == 200
        result = job.get_json()
        request.view_args = {"session_id": body["session_id"]}
        request.args = {}
        detail, _ = rh(RHSessionDetail)._process()

    assert result["response"].startswith("Pile-up comes in two kinds")
    [citation] = result["metadata"]["citations"]
    assert (citation["attachment_id"], citation["filename"], citation["page"]) == (thesis.id, "thesis.md", 1)
    assert citation["url"].endswith("#page=1")
    answer = detail.get_json()["messages"][-1]
    assert answer["metadata"]["route"]["route"] == "agent"
    assert answer["metadata"]["route"]["tools"] == ["search_documents"]
    assert answer["metadata"]["touched"] == [
        {"kind": "document", "ref": {"attachment_id": thesis.id}, "title": "thesis.md", "position": 1}
    ]


def test_the_old_search_endpoint_is_gone(app):
    assert not [rule.rule for rule in app.url_map.iter_rules() if rule.rule.startswith("/api/assistant/search")]


def test_a_lookup_then_a_proposal_then_a_typed_yes_applies_it(
    db, dummy_user, dummy_event, thesis, fake_embedder, monkeypatch
):
    """Story 3 (T060): the turn looks something up and proposes a change from what it found; nothing changes until
    the user's typed "yes", which runs the plan as spec 019 does."""
    from indico_assistant.default_settings import DEFAULT_SETTINGS
    from indico_assistant.schemas.actions import PlanView
    from indico_assistant.services.actions import executor
    from indico_assistant.services.chat.service import get_chat_service
    from indico_assistant.services.turn import abilities

    title = dummy_event.title
    dummy_event.update_principal(dummy_user, full_access=True)  # (a manager: the change is theirs to make)

    class Model:
        def __init__(self):
            self.n = 0

        def generate(self, prompt, response_model, **kwargs):
            self.n += 1
            call = {
                1: tools.SearchDocumentsArgs(tool="search_documents", query="pile-up kinds"),
                2: abilities.ProposeChangeArgs(tool="propose_change", request="rename this event to Pile-up Review"),
            }[self.n]
            return LLMResponse(success=True, result=response_model(call=call), latency_ms=1, calls=[])

    proposed = []

    def first_plan(user, session_id, message, history, waiting_plan, page_event_id, offer=None):
        proposed.append(message)
        steps = [{"n": 1, "action": "update_event", "args": {"event_id": dummy_event.id, "title": "Pile-up Review"}}]
        plan, token = executor.create_plan(user, session_id, steps=steps, summary="Rename the event")
        return (
            "Here is the plan. Confirm it to go ahead.",
            {"plan_id": str(plan.id), "cannot_plan": False},
            (PlanView.of(plan, token).model_dump(mode="json")),
        )

    plugin = MagicMock(llm_service=Model())
    plugin.settings.get_all.return_value = {**DEFAULT_SETTINGS, "jev_api_key": None, "actions_enabled": True}
    plugin.settings.get.side_effect = lambda key, default=None: plugin.settings.get_all.return_value.get(key, default)
    plugin.event_settings.get.return_value = None
    service = get_chat_service()
    session = service._session_manager.create_session(dummy_user.id, dummy_event.id)
    db.session.commit()
    real_plan = abilities.plan
    with (
        patch("indico_assistant.plugin.AssistantPlugin", MagicMock(instance=plugin, settings=plugin.settings)),
        patch.object(tools, "_embedder", return_value=fake_embedder),
        patch.object(abilities, "plan", side_effect=first_plan) as planner,
    ):
        message = service._session_manager.add_user_message(session, "Rename this event after what the thesis covers")
        db.session.commit()
        first = service.answer(dummy_user.id, session.id, message.content, message_id=message.id)
        assert first.plan is not None and dummy_event.title == title  # proposed, not applied
        assert proposed and "Pile-up Review" in proposed[0]
        planner.side_effect = real_plan
        message = service._session_manager.add_user_message(session, "yes")
        db.session.commit()
        second = service.answer(dummy_user.id, session.id, "yes", message_id=message.id)
    db.session.refresh(dummy_event)
    assert dummy_event.title == "Pile-up Review" and second.metadata["route"]["route"] == "change"
