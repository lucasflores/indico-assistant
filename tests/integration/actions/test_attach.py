"""Files sent in the chat and attached as material (US9): checked uploads, the material pages' permission
check, the upload page's steps, and nothing left behind on failure."""

import io
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from flask import g
from werkzeug.datastructures import FileStorage

import indico_assistant.controllers.actions as actions_module
from indico.core import signals
from indico.modules.attachments.controllers.management.event import RHManageEventAttachments
from indico.modules.attachments.models.attachments import Attachment, AttachmentType
from indico.modules.attachments.settings import attachments_settings
from indico.modules.files.models.files import File
from indico.util.date_time import now_utc

from indico_assistant.controllers.actions import RHChatUpload
from indico_assistant.models import ChatMessage, ChatSession
from indico_assistant.services import actions
from indico_assistant.services.actions import ACTIONS, executor, resolve, uploads
from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.llm.models.plan import PlanDraft


PDF = b'%PDF-1.4\n1 0 obj << >> endobj\n%%EOF\n'


def _zip(*names):
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as package:
        for name in names:
            package.writestr(name, '<x/>')
    return buffer.getvalue()


DOCX = _zip('[Content_Types].xml', 'word/document.xml')


@pytest.fixture
def upload(monkeypatch, people):
    request = MagicMock()
    monkeypatch.setattr(actions_module, 'request', request)
    monkeypatch.setattr(RHChatUpload, 'plugin', MagicMock(), raising=False)
    monkeypatch.setattr(actions_module, 'enabled_actions', lambda settings: frozenset({'attach_file'}))

    def _upload(data, filename, user=people['manager']):
        request.files = {'file': FileStorage(stream=io.BytesIO(data), filename=filename)}
        request.form = {}
        rh = RHChatUpload.__new__(RHChatUpload)
        rh._user = user
        response, status = rh._process()
        return status, response.get_json()
    return _upload


# --- uploads (T061) -----------------------------------------------------------------------------------

def test_an_allowed_file_is_kept_unclaimed_for_its_uploader(upload, people):
    status, body = upload(PDF, 'slides.pdf')
    assert status == 201 and body['content_type'] == 'application/pdf' and body['size'] == len(PDF)
    file = File.query.filter_by(uuid=body['uuid']).one()
    assert not file.claimed and file.meta['assistant_user_id'] == people['manager'].id
    assert uploads.usable_upload(body['uuid'], people['manager']) == file
    assert uploads.usable_upload(body['uuid'], people['stranger']) is None  # FR-025


def test_no_uploads_unless_attaching_files_is_enabled(upload, monkeypatch):
    # (code review, PR #3) actions off (the default) or attach_file off: nothing is written to storage
    monkeypatch.setattr(actions_module, 'enabled_actions', lambda settings: frozenset({'create_event'}))
    files_before = File.query.count()
    status, body = upload(PDF, 'slides.pdf')
    assert (status, body['error']) == (403, 'ACTIONS_DISABLED') and File.query.count() == files_before


def test_an_office_package_is_accepted(upload):
    status, body = upload(DOCX, 'report.docx')
    assert status == 201 and body['content_type'].endswith('wordprocessingml.document')


@pytest.mark.parametrize(('data', 'filename', 'status', 'code'), [
    (b'MZ\x90\x00 an exe renamed', 'slides.pdf', 415, 'UNSUPPORTED_FILE_TYPE'),  # checked by content
    (PDF, 'tool.exe', 415, 'UNSUPPORTED_FILE_TYPE'),
    (b'\x00\x01binary', 'notes.txt', 415, 'UNSUPPORTED_FILE_TYPE'),
    (b'', 'empty.txt', 422, 'EMPTY_FILE'),
    (_zip('payload.sh'), 'report.docx', 415, 'UNSUPPORTED_FILE_TYPE'),  # any zip renamed (Copilot, PR #3)
    (DOCX, 'report.xlsx', 415, 'UNSUPPORTED_FILE_TYPE'),  # a Word package is not a spreadsheet
])
def test_refused_uploads(upload, data, filename, status, code):
    got, body = upload(data, filename)
    assert (got, body['error']) == (status, code)


def test_size_limits(upload, monkeypatch, patch_indico_config):
    monkeypatch.setattr(uploads, 'MAX_MB', 1)
    assert upload(b'%PDF-' + b'x' * (1024 * 1024), 'big.pdf')[0] == 413
    monkeypatch.setattr(uploads, 'MAX_MB', 25)
    patch_indico_config('MAX_UPLOAD_FILE_SIZE', 1)  # the instance's own limit is smaller: it wins
    assert upload(b'%PDF-' + b'x' * (1024 * 1024), 'big.pdf')[0] == 413


def test_chat_messages_only_carry_the_senders_own_uploads(upload, people, monkeypatch):
    import indico_assistant.controllers.chat as chat_module
    from indico_assistant.controllers.chat import RHChat
    _, mine = upload(PDF, 'mine.pdf', user=people['stranger'])
    request = MagicMock()
    monkeypatch.setattr(chat_module, 'request', request)
    request.get_json.return_value = {'message': 'attach this', 'uploads': [mine['uuid']]}
    rh = RHChat.__new__(RHChat)
    rh._user = people['manager']
    response, status = rh._process()
    assert (status, response.get_json()['error']) == (422, 'VALIDATION_ERROR')
    request.get_json.return_value = {'message': 'attach these', 'uploads': [mine['uuid']] * 6}
    assert rh._process()[1] == 422  # at most 5 per message


# --- parity (T062) ------------------------------------------------------------------------------------

@pytest.mark.parametrize('role', ['admin', 'manager', 'submitter', 'speaker', 'stranger'])
@pytest.mark.parametrize('managers_only', [False, True])
@pytest.mark.parametrize('target', ['event', 'contribution'])
def test_attach_parity(page_allows, action_allows, people, dummy_event, create_contribution, upload, role,
                       managers_only, target):
    attachments_settings.set(dummy_event, 'managers_only', managers_only)
    talk = create_contribution(dummy_event, 'Talk')
    if role == 'speaker':
        talk.update_principal(people['stranger'], permissions={'submit'})  # speakers who may submit get this
    user = people['stranger'] if role == 'speaker' else people[role]
    obj = dummy_event if target == 'event' else talk
    page = page_allows(RHManageEventAttachments, user, object=obj, event=dummy_event)
    link = action_allows(ACTIONS['attach_link'], user, target_type=target, target_id=obj.id, url='https://x.test/a')
    assert link == page, (role, managers_only, target)


# --- carrying it out (T063) ---------------------------------------------------------------------------

@pytest.fixture
def chat(db, people):
    chat = ChatSession(user_id=people['manager'].id)
    db.session.add(chat)
    db.session.flush()
    return chat


def run(user, chat, steps):
    plan, token = executor.create_plan(user, chat.id, steps=steps, summary='x')
    executor.confirm(plan.id, user, token)
    g.email_queue = []
    return executor.run(plan.id)


def test_a_file_becomes_material_as_the_upload_page_makes_it(upload, people, chat, dummy_event):
    lucas = people['manager']
    _, sent = upload(PDF, 'slides.pdf')
    created = []
    receiver = lambda sender, **kw: created.append((sender, kw.get('user')))  # noqa: E731
    signals.attachments.attachment_created.connect(receiver)
    try:
        plan = run(lucas, chat, [{'n': 1, 'action': 'attach_file', 'args': {
            'target_type': 'event', 'target_id': dummy_event.id, 'upload_uuid': sent['uuid']}}])
    finally:
        signals.attachments.attachment_created.disconnect(receiver)
    assert plan.status == 'done', plan.error
    attachment = Attachment.get(plan.result[0]['created']['attachment_id'])
    assert attachment.type == AttachmentType.file and attachment.folder.is_default
    assert attachment.folder.object == dummy_event and attachment.user == lucas
    with attachment.file.open() as f:
        assert f.read() == PDF  # its own copy
    assert created == [(attachment, lucas)]  # the event log entry and the document index follow this
    assert not File.query.filter_by(uuid=sent['uuid']).one().claimed  # Indico's cleanup removes it


def test_a_failed_plan_removes_the_copied_file(upload, people, chat, dummy_event, monkeypatch):
    from indico_assistant.services.actions.base import Action, ActionArgs

    class Boom(Action):
        name = 'test_boom'
        Args = type('Args', (ActionArgs,), {})

        def check(self, user, args):
            return None

        def execute(self, user, args):
            raise RuntimeError('later step fails')

    monkeypatch.setitem(actions.ACTIONS, 'test_boom', Boom())
    from indico.testing.fixtures.storage import MemoryStorage

    def copies():
        return sum(1 for _, name, _ in MemoryStorage.files.values() if name == 'slides.pdf')

    _, sent = upload(PDF, 'slides.pdf')
    before = copies()  # (the in-memory store is shared by all tests)
    plan = run(people['manager'], chat, [
        {'n': 1, 'action': 'attach_file', 'args': {'target_type': 'event', 'target_id': dummy_event.id,
                                                   'upload_uuid': sent['uuid']}},
        {'n': 2, 'action': 'test_boom', 'args': {}}])
    assert plan.status == 'failed' and copies() == before  # the attachment's copy is gone, the upload stays
    assert Attachment.query.filter_by(title='slides.pdf').count() == 0


def test_my_contribution_is_found_or_asked(db, upload, people, chat, dummy_event, create_contribution):
    lucas = people['manager']
    dummy_event.end_dt = now_utc() + timedelta(days=1)
    _, sent = upload(PDF, 'slides.pdf')
    db.session.add(ChatMessage(session_id=chat.id, role='user', content='attach this to my talk',
                               metadata_json={'uploads': [{'uuid': sent['uuid'], 'filename': 'slides.pdf'}]}))
    db.session.flush()

    def attach(target):
        draft = PlanDraft.model_validate({'decision': 'new_request',
                                          'steps': [{'action': 'attach', 'target': target, 'upload': 'this'}]})
        with acting_as(lucas):
            return resolve.draft_to_plan(draft, lucas, chat_session_id=chat.id)

    assert 'could not find a talk' in attach('my contribution').refusal
    from indico.modules.events.contributions.models.persons import ContributionPersonLink
    from indico.modules.events.models.persons import EventPerson
    first = create_contribution(dummy_event, 'First')
    first.person_links.append(ContributionPersonLink(person=EventPerson.for_user(lucas, dummy_event),
                                                     is_speaker=True))
    db.session.flush()
    one = attach('my contribution to the meeting')
    assert one.steps[0]['args']['target_id'] == first.id and 'slides.pdf' in one.steps[0]['description']
    second = create_contribution(dummy_event, 'Second')
    second.person_links.append(ContributionPersonLink(person=EventPerson.for_user(lucas, dummy_event),
                                                      is_speaker=True))
    db.session.flush()
    (question,) = attach('my talk').questions
    assert len(question['choices']) == 2  # asked, never picked


def test_this_meeting_is_the_one_the_chat_was_opened_on(db, upload, people, dummy_event, create_event,
                                                        create_contribution):
    # seen live: two identical "Sync with Makoto" meetings; the file went to the other one's talk
    from indico.modules.events.contributions.models.persons import ContributionPersonLink
    from indico.modules.events.models.persons import EventPerson
    lucas = people['manager']
    dummy_event.end_dt = now_utc() + timedelta(days=1)
    twin = create_event(title=dummy_event.title, start_dt=dummy_event.start_dt, end_dt=dummy_event.end_dt,
                        creator=lucas, creator_has_privileges=True)
    for event in (dummy_event, twin):
        talk = create_contribution(event, 'Lucas Flores')
        talk.person_links.append(ContributionPersonLink(person=EventPerson.for_user(lucas, event), is_speaker=True))
    chat = ChatSession(user_id=lucas.id, event_id=twin.id)  # opened on the twin's page
    db.session.add(chat)
    db.session.flush()
    _, sent = upload(PDF, 'slides.pdf')
    db.session.add(ChatMessage(session_id=chat.id, role='user', content='attach this to my contribution',
                               metadata_json={'uploads': [{'uuid': sent['uuid'], 'filename': 'slides.pdf'}]}))
    db.session.flush()
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'attach', 'target': 'my contribution in this meeting', 'upload': 'this'}]})
    with acting_as(lucas):
        result = resolve.draft_to_plan(draft, lucas, chat_session_id=chat.id)
    assert result.questions == [] and result.steps[0]['args']['target_id'] == twin.contributions[0].id


def test_namesake_choices_can_be_told_apart():
    from indico_assistant.services.actions.resolve import _distinct
    choices = _distinct([{'value': '#351', 'label': 'Sync (Mon)'}, {'value': '#352', 'label': 'Sync (Mon)'},
                         {'value': '#c7', 'label': 'Talk'}])
    assert [c['label'] for c in choices] == ['Sync (Mon) [351]', 'Sync (Mon) [352]', 'Talk']


def test_an_attached_upload_cannot_be_used_again(db, upload, people, dummy_event):
    # (code review, PR #3) uploads stay unclaimed, so "used" is recorded by the plan that attached them
    lucas = people['manager']
    dummy_event.update_principal(lucas, full_access=True)
    _, body = upload(PDF, 'slides.pdf')
    chat = ChatSession(user_id=lucas.id)
    db.session.add(chat)
    db.session.flush()
    step = {'n': 1, 'action': 'attach_file', 'args': {'target_type': 'event', 'target_id': dummy_event.id,
                                                      'upload_uuid': body['uuid'], 'title': 'Slides'}}
    plan, token = executor.create_plan(lucas, chat.id, steps=[step, {**step, 'n': 2}], summary='x')
    executor.confirm(plan.id, lucas, token)
    g.email_queue = []
    assert executor.run(plan.id).status == 'done'  # the same plan may attach it twice (meeting and talk)
    assert uploads.usable_upload(body['uuid'], lucas) is None
    again, token = executor.create_plan(lucas, chat.id, steps=[step], summary='again')
    executor.confirm(again.id, lucas, token)
    assert executor.run(again.id).status == 'refused'


@pytest.mark.parametrize('said', ['this event', 'the event', 'this meeting'])
def test_this_event_is_the_page_s_meeting_like_this_meeting(db, upload, people, create_event, said):
    """(spec 025 baseline and full run: "Please attach this thesis to this event" was answered "I could not find
    the meeting 'this event'")"""
    lucas = people['manager']
    page = create_event(title='Thesis Club', start_dt=now_utc() + timedelta(days=1),
                        end_dt=now_utc() + timedelta(days=1, hours=1), creator=lucas, creator_has_privileges=True)
    chat = ChatSession(user_id=lucas.id, event_id=page.id)
    db.session.add(chat)
    db.session.flush()
    _, sent = upload(PDF, 'thesis.pdf')
    db.session.add(ChatMessage(session_id=chat.id, role='user', content=f'attach this thesis to {said}',
                               metadata_json={'uploads': [{'uuid': sent['uuid'], 'filename': 'thesis.pdf'}]}))
    db.session.flush()
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'attach', 'target': said, 'upload': 'this'}]})
    with acting_as(lucas):
        result = resolve.draft_to_plan(draft, lucas, chat_session_id=chat.id, page_event_id=page.id)
    assert result.questions == [] and result.steps[0]['args']['target_id'] == page.id
