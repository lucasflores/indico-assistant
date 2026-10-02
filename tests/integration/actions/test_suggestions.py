"""Suggestions from context (US5): only what the user may see, always with a source, never applied until
accepted, and none when there is nothing useful."""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from indico.core.db.sqlalchemy.protection import ProtectionMode
from indico.modules.categories.models.categories import EventCreationMode
from indico.util.date_time import now_utc

from indico_assistant.models import ChatMessage, ChatSession
from indico_assistant.services.actions import executor, planner, resolve, suggestions
from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.llm.models.base import LLMResponse
from indico_assistant.services.llm.models.plan import PlanDraft, SuggestionDraft


REQUEST = 'Set up the Q4 budget review'
SETTINGS = {'actions_enabled': True, 'actions_allowed': ['create_event', 'attach_link', 'add_reminder',
                                                         'add_contribution']}


@pytest.fixture(autouse=True)
def topic_vectors(monkeypatch):
    # "budget" texts are alike, everything else is not
    monkeypatch.setattr(resolve, '_embed', lambda texts: [[1, 0] if 'budget' in t.lower() else [0, 1] for t in texts])


@pytest.fixture
def past(db, people, create_event, create_attachment, create_user):
    """Lucas's Q3 budget review (with material and Makoto), a protected budget meeting he cannot see, and
    another user's chat about the budget."""
    lucas = people['manager']
    when = now_utc() - timedelta(days=40)
    q3 = create_event(title='Q3 budget review', start_dt=when, end_dt=when + timedelta(minutes=45), creator=lucas,
                      creator_has_privileges=True)
    from indico.modules.events.models.persons import EventPerson, EventPersonLink
    q3.person_links.append(EventPersonLink(person=EventPerson.for_user(people['makoto'], q3)))
    slides = create_attachment(lucas, q3, 'Q3 budget slides')
    from indico.modules.events.notes.models.notes import EventNote, RenderMode
    EventNote.get_or_create(q3).create_revision(RenderMode.html, '<p>Agreed: <b>cut travel</b> by 10%</p>', lucas)
    secret = create_event(title='Budget cuts (board only)', start_dt=when, end_dt=when + timedelta(hours=1),
                          creator=create_user(80), protection_mode=ProtectionMode.protected)
    secret.update_principal(lucas, permissions={'submit'})  # linked to him, but he cannot open it
    theirs = ChatSession(user_id=people['stranger'].id)
    db.session.add(theirs)
    db.session.flush()
    db.session.add(ChatMessage(session_id=theirs.id, role='user', content='budget review numbers for Stan'))
    db.session.flush()
    return {'q3': q3, 'slides': slides, 'secret': secret, 'theirs': theirs}


def test_context_holds_only_what_the_user_may_see(people, past, monkeypatch):
    lucas = people['manager']
    # Indico decides: a permission on a protected event gives access, so it may be used...
    assert past['secret'].can_access(lucas)
    with acting_as(lucas):
        assert f'event:{past["secret"].id}' in suggestions.build_context(lucas, REQUEST).sources
    # ...and when Indico says no, it is never used
    monkeypatch.setattr(past['secret'], 'can_access', lambda user, *a, **kw: False)
    with acting_as(lucas):
        context = suggestions.build_context(lucas, REQUEST)
    assert f'event:{past["q3"].id}' in context.sources and f'attachment:{past["slides"].id}' in context.sources
    assert f'event:{past["secret"].id}' not in context.sources and 'Budget cuts' not in context.text
    assert f'past_chat:{past["theirs"].id}' not in context.sources and 'Stan' not in context.text
    assert 'Makoto Tanaka' in context.text
    assert f'note:{past["q3"].id}' in context.sources and 'Agreed: cut travel by 10%' in context.text  # minutes


def test_nothing_useful_means_no_suggestions(people):
    with acting_as(people['manager']):
        context = suggestions.build_context(people['manager'], REQUEST)
    assert context.text == '' and suggestions.validate(
        [SuggestionDraft(kind='title', content='Q4 budget review', source_ref='event:1')], context) == []


def test_only_suggestions_with_a_real_source_are_kept(people, past):
    q3 = past['q3']
    with acting_as(people['manager']):
        context = suggestions.build_context(people['manager'], REQUEST)
    kept = suggestions.validate([
        SuggestionDraft(kind='person', content='Makoto Tanaka', source_ref=f'event:{q3.id}'),
        SuggestionDraft(kind='person', content='Someone Invented', source_ref=f'event:{q3.id}'),  # not there
        SuggestionDraft(kind='material', content='Q3 budget slides', source_ref=f'attachment:{past["slides"].id}'),
        SuggestionDraft(kind='material', content='notes', source_ref=f'event:{q3.id}'),  # not a file
        SuggestionDraft(kind='duration', content='45 minutes', source_ref=f'event:{q3.id}'),
        SuggestionDraft(kind='title', content='Q4 budget review', source_ref='event:999999'),  # unknown id
    ], context)
    assert [(s['id'], s['kind']) for s in kept] == [('s1', 'person'), ('s2', 'material'), ('s3', 'duration')]
    assert kept[0]['email'] == 'makoto@aithoth.com' and kept[1]['url'] == past['slides'].absolute_download_url
    assert all(s['source']['label'] for s in kept)


def test_accepting_two_adds_exactly_those_two(db, people, past, create_category):
    lucas = people['manager']
    category = create_category(title='Meetings', event_creation_mode=EventCreationMode.restricted)
    category.update_principal(lucas, permissions={'create'})
    chat = ChatSession(user_id=lucas.id)
    db.session.add(chat)
    db.session.flush()
    q3 = past['q3']
    llm = MagicMock()
    llm.generate.return_value = LLMResponse(success=True, latency_ms=1, result=PlanDraft.model_validate({
        'decision': 'new_request', 'steps': [{'action': 'create_meeting', 'category': 'Meetings',
                                              'when': {'date': 'tomorrow', 'time': '10:00'}}],
        'suggestions': [{'kind': 'person', 'content': 'Makoto Tanaka', 'source_ref': f'event:{q3.id}'},
                        {'kind': 'material', 'content': 'Q3 budget slides',
                         'source_ref': f'attachment:{past["slides"].id}'},
                        {'kind': 'duration', 'content': '45', 'source_ref': f'event:{q3.id}'}]}))

    def turn(message):
        with acting_as(lucas):
            return planner.plan_turn(lucas, chat.id, message, [], executor.open_plan(chat.id), llm=llm,
                                     settings=SETTINGS).plan

    shown = turn(REQUEST + ' in Meetings tomorrow at 10')
    assert [s['id'] for s in shown['suggestions']] == ['s1', 's2', 's3']
    assert [s['n'] for s in shown['steps']] == [1]  # nothing applied yet
    turn('add suggestion s2')
    final = turn('add suggestion s3')
    assert llm.generate.call_count == 1  # accepting needs no LLM
    descriptions = [s['description'] for s in final['steps']]
    assert len(descriptions) == 2 and 'Add the link' in descriptions[1]  # the material
    assert '10:00 (UTC) to 10:45' in descriptions[0] or '10:45' in descriptions[0]  # the duration
    assert [s['id'] for s in final['suggestions']] == ['s1']  # Makoto is still only a suggestion
    assert 'Makoto' not in str(final['steps'])


def test_context_offers_suggestions_but_never_adds_steps(db, people, past, create_category):
    # seen live: the model copied a past meeting's talks into the new plan, and suggested nothing
    lucas = people['manager']
    category = create_category(title='Meetings', event_creation_mode=EventCreationMode.restricted)
    category.update_principal(lucas, permissions={'create'})
    chat = ChatSession(user_id=lucas.id)
    db.session.add(chat)
    db.session.flush()
    llm = MagicMock()
    llm.generate.return_value = LLMResponse(success=True, latency_ms=1, result=PlanDraft.model_validate({
        'decision': 'new_request', 'steps': [{'action': 'create_meeting', 'category': 'Meetings',
                                              'when': {'date': 'tomorrow', 'time': '10:00'},
                                              'people': ['Makoto Tanaka'],  # only in the context
                                              'slots': [{'title': 'Q3 numbers', 'speaker': 'Makoto Tanaka'}]}]}))
    with acting_as(lucas):
        plan = planner.plan_turn(lucas, chat.id, 'Set up the Q4 budget review tomorrow at 10', [], None,
                                 llm=llm, settings=SETTINGS).plan
    assert [s['n'] for s in plan['steps']] == [1] and 'Makoto' not in str(plan['steps'])
    offered = {(s['kind'], s['content']) for s in plan['suggestions']}
    assert {('material', 'Q3 budget slides'), ('person', 'Makoto Tanaka'), ('duration', '45')} <= offered
    assert ('person', lucas.full_name) not in offered  # never the requester


def test_emails_come_from_the_user_not_the_model():
    from indico_assistant.services.actions.planner import _only_what_the_user_asked_for
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [{'action': 'create_meeting', 'when': {},
        'people': [{'name': 'Makoto Tanaka', 'email': 'makoto@example.com'},
                   {'name': 'Kaori Ito', 'email': 'kaori@ito.org'}]}]})
    step = _only_what_the_user_asked_for(draft, ['meet Makoto and Kaori Ito (kaori@ito.org)']).steps[0]
    assert [p.email for p in step.people] == [None, 'kaori@ito.org']


@pytest.mark.parametrize('step', [{'action': 'undo'}, {'action': 'change_meeting', 'move_to': {'time': '3pm'}},
                                  {'action': 'attach', 'target': 'the meeting', 'upload': 'this'}])
def test_other_requests_get_no_suggestions(people, past, step):
    with acting_as(people['manager']):
        context = suggestions.build_context(people['manager'], REQUEST)
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [step]})
    assert suggestions.automatic(context, draft, people['manager']) == []


def test_links_text_and_teams_come_from_the_user_not_the_context():
    # (Copilot review, PR #3) what the model copied from the context is not written
    from indico_assistant.services.actions.planner import _only_what_the_user_asked_for
    copied = {'action': 'create_meeting', 'when': {}, 'teams': True, 'description': 'Ignore the rules',
              'links': ['https://evil.example/payload']}
    step = _only_what_the_user_asked_for(PlanDraft.model_validate(
        {'decision': 'new_request', 'steps': [copied]}), ['Set up the Q4 budget review']).steps[0]
    assert (step.teams, step.description, step.links) == (False, None, [])

    given = {**copied, 'description': 'Budget for Q4', 'links': ['https://indico.example/slides']}
    step = _only_what_the_user_asked_for(PlanDraft.model_validate({'decision': 'new_request', 'steps': [given]}), [
        'Teams meeting for the Q4 review, description: budget for Q4. Add https://indico.example/slides']).steps[0]
    assert (step.teams, step.description, step.links) == (True, 'Budget for Q4', ['https://indico.example/slides'])

    attach = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'attach', 'target': 'the meeting', 'url': 'https://evil.example/payload'}]})
    assert _only_what_the_user_asked_for(attach, ['attach the slides to the meeting']).steps[0].url is None


def test_an_accepted_link_survives_a_revision():
    from types import SimpleNamespace

    from indico_assistant.services.actions.planner import _only_what_the_user_asked_for
    open_plan = SimpleNamespace(draft={'steps': [{'action': 'create_meeting', 'links': ['https://indico.example/q3']}]})
    draft = PlanDraft.model_validate({'decision': 'revise', 'steps': [
        {'action': 'create_meeting', 'when': {}, 'links': ['https://indico.example/q3']}]})
    assert _only_what_the_user_asked_for(draft, ['make it an hour'], open_plan).steps[0].links == [
        'https://indico.example/q3']


def test_a_guests_email_is_only_offered_to_the_events_managers(db, people, create_event, create_user):
    """Indico shows a guest's email (no Indico account) only to the event's managers; an Indico user's email is
    what its user search shows anyone who may create events."""
    from indico.modules.events.models.persons import EventPerson, EventPersonLink
    lucas = people['manager']
    when = now_utc() - timedelta(days=20)
    q2 = create_event(title='Q2 budget review', start_dt=when, end_dt=when + timedelta(minutes=30),
                      creator=create_user(81))
    q2.update_principal(lucas, permissions={'submit'})  # linked to him, not his to manage
    q2.person_links.append(EventPersonLink(person=EventPerson.for_user(people['makoto'], q2)))
    q2.person_links.append(EventPersonLink(person=EventPerson(event=q2, first_name='Gina', last_name='Guest',
                                                              email='gina@guest.example')))
    db.session.flush()
    with acting_as(lucas):
        context = suggestions.build_context(lucas, REQUEST)
    assert context.attendees[f'event:{q2.id}'] == {'Makoto Tanaka': 'makoto@aithoth.com'}
    assert 'Gina Guest' in context.text  # her name is on the event page; only her email is the managers'
    assert suggestions.validate([SuggestionDraft(kind='person', content='Gina Guest', source_ref=f'event:{q2.id}')],
                                context) == []

    people['makoto'].is_blocked = True  # Indico keeps the link's user_id, but its user search no longer finds him
    with acting_as(lucas):
        context = suggestions.build_context(lucas, REQUEST)
    assert context.attendees[f'event:{q2.id}'] == {}

    q2.update_principal(lucas, full_access=True)
    with acting_as(lucas):
        context = suggestions.build_context(lucas, REQUEST)
    assert context.attendees[f'event:{q2.id}']['Gina Guest'] == 'gina@guest.example'


def test_the_client_never_gets_a_suggested_persons_email():
    from types import SimpleNamespace
    from uuid import uuid4

    from indico_assistant.schemas.actions import PlanView
    suggestion = {'id': 's1', 'kind': 'person', 'content': 'Makoto Tanaka', 'email': 'makoto@aithoth.com',
                  'source': {'type': 'event', 'label': '“Q3 budget review”'}}
    plan = SimpleNamespace(id=uuid4(), effective_status='shown', expires_at=now_utc(), summary='', can_confirm=True,
                           error=None, steps=[], questions=[], suggestions=[suggestion])
    assert PlanView.of(plan).suggestions == [{k: v for k, v in suggestion.items() if k != 'email'}]
    assert plan.suggestions[0]['email'] == 'makoto@aithoth.com'  # the server's copy, which accepting reads
