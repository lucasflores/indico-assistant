"""Finding the right people (US4): Indico's search rules, never a silent pick, context ranking, guest
speakers; and the flags for times in the past and clashes (spec edge cases)."""

from datetime import timedelta

import pytest
from flask import g

from indico.modules.categories.models.categories import EventCreationMode
from indico.modules.events import Event
from indico.util.date_time import now_utc

from indico_assistant.models import ChatMessage, ChatSession
from indico_assistant.services.actions import executor, resolve
from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.actions.resolve import find_people, known_people, user_search_allowed
from indico_assistant.services.llm.models.plan import PersonRef, PlanDraft


@pytest.fixture
def meetings(create_category, people):
    category = create_category(title='Meetings', event_creation_mode=EventCreationMode.restricted)
    category.update_principal(people['manager'], permissions={'create'})
    return category


def plan(user, **meeting):
    step = {'action': 'create_meeting', 'category': 'Meetings', 'when': {'date': 'tomorrow', 'time': '10:00'},
            **meeting}
    with acting_as(user):
        return resolve.draft_to_plan(PlanDraft.model_validate({'decision': 'new_request', 'steps': [step]}), user,
                                     chat_session_id=None)


def test_search_follows_indicos_user_search(create_user):
    create_user(50, first_name='Kaori', last_name='Ito')
    create_user(51, first_name='Kaori', last_name='Blocked').is_blocked = True
    create_user(52, first_name='Kaori', last_name='Deleted').is_deleted = True
    create_user(53, first_name='Kaori', last_name='Pending').is_pending = True
    assert sorted(u.last_name for u in find_people(PersonRef(name='Kaori'))) == ['Ito', 'Pending']


def test_who_may_search_when_public_search_is_off(people, dummy_event, patch_indico_config):
    patch_indico_config('ALLOW_PUBLIC_USER_SEARCH', False)
    assert user_search_allowed(people['stranger'], can_create_somewhere=True)
    assert user_search_allowed(people['manager'], event=dummy_event)
    assert not user_search_allowed(people['stranger'], event=dummy_event)


def test_several_matches_are_asked_ranked_by_who_you_meet(db, people, meetings, create_user, dummy_event):
    lucas = people['manager']
    sato = create_user(60, first_name='Makoto', last_name='Sato', email='sato@aithoth.com')
    sato.affiliation = 'Tokyo'
    dummy_event.update_principal(sato, full_access=True)  # Sato shares Lucas's meeting; Tanaka does not
    assert known_people(lucas)[sato.id] == 1
    result = plan(lucas, people=['Makoto'])
    (question,) = [q for q in result.questions if q['id'] == 'person:makoto']
    assert [c['label'] for c in question['choices']] == ['Makoto Sato <sato@aithoth.com>, Tokyo',
                                                         'Makoto Tanaka <makoto@aithoth.com>']


def test_names_from_your_own_chats_rank_next(db, people, meetings, create_user):
    lucas = people['manager']
    create_user(61, first_name='Makoto', last_name='Sato', email='sato@aithoth.com')
    mine = ChatSession(user_id=lucas.id)
    theirs = ChatSession(user_id=people['stranger'].id)
    db.session.add_all([mine, theirs])
    db.session.flush()
    db.session.add_all([ChatMessage(session_id=mine.id, role='user', content='Ask Makoto Tanaka about it'),
                        ChatMessage(session_id=theirs.id, role='user', content='Makoto Sato, Makoto Sato')])
    db.session.flush()
    order = [u.last_name for u in find_people(PersonRef(name='Makoto'), lucas, {})]
    assert order == ['Tanaka', 'Sato']  # someone else's chat does not count


def test_unknown_people_can_be_guest_speakers(db, people, meetings):
    lucas = people['manager']
    asked = plan(lucas, slots=[{'speaker': 'Kaori Ito'}])
    assert 'guest speaker' in [q for q in asked.questions if q['id'] == 'person:kaori ito'][0]['text']

    result = plan(lucas, people=[{'name': 'Kaori Ito', 'email': 'Kaori@Example.org'}],
                  slots=[{'speaker': {'name': 'Kaori Ito', 'email': 'Kaori@Example.org'}, 'duration_minutes': 20}])
    assert result.questions == []
    talk = result.steps[1]
    assert talk['args']['speakers'] == [{'user_id': None, 'first_name': 'Kaori', 'last_name': 'Ito',
                                         'email': 'kaori@example.org'}]
    assert '(guest)' in talk['description']

    chat = ChatSession(user_id=lucas.id)
    db.session.add(chat)
    db.session.flush()
    saved, token = executor.create_plan(lucas, chat.id, steps=result.steps, summary=result.summary)
    executor.confirm(saved.id, lucas, token)
    g.email_queue = []
    assert executor.run(saved.id).status == 'done'
    (link,) = Event.query.filter_by(title=result.steps[0]['args']['title']).one().contributions[0].person_links
    assert (link.person.user, link.person.email, link.is_speaker) == (None, 'kaori@example.org', True)


def test_a_time_in_the_past_is_asked_about(people, meetings):
    result = plan(people['manager'], when={'date': (now_utc() - timedelta(days=1)).date().isoformat(), 'time': '10:00'})
    (question,) = [q for q in result.questions if q['id'] == 'past']
    assert [c['label'] for c in question['choices']] == ['Tomorrow at 10:00', 'Keep that time']
    kept = plan(people['manager'], when={'date': (now_utc() - timedelta(days=1)).date().isoformat(), 'time': '10:00',
                                         'keep_past': True})
    assert not [q for q in kept.questions if q['id'] == 'past']


def test_clashes_are_warned_not_blocked(people, meetings, create_event, dummy_event):
    lucas, makoto = people['manager'], people['makoto']
    start = (now_utc() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    busy = create_event(title='Board meeting', start_dt=start, end_dt=start + timedelta(hours=1), creator=makoto,
                        creator_has_privileges=True, protection_mode=__import__(
                            'indico.core.db.sqlalchemy.protection', fromlist=['ProtectionMode']).ProtectionMode.protected)
    lucas.settings.set('timezone', 'UTC')
    result = plan(lucas, people=['Makoto Tanaka'], when={'date': start.date().isoformat(), 'time': '10:00'})
    assert 'Note: Makoto Tanaka has another event at that time.' in result.summary  # protected: no title
    assert not [q for q in result.questions if q['id'] != 'past'] and result.steps  # still plannable
    assert busy.title not in result.summary


@pytest.mark.parametrize(('answer', 'expected'), [('Tomorrow at 10:00', {'date': '2026-09-29', 'keep_past': False}),
                                                  ('Keep that time', {'date': '2026-09-27', 'keep_past': True})])
def test_answering_the_past_time_question(answer, expected):
    from types import SimpleNamespace

    from indico_assistant.services.actions.planner import answered_draft
    draft = {'decision': 'new_request', 'steps': [{'action': 'create_meeting',
                                                   'when': {'date': '2026-09-27', 'time': '10:00'}}]}
    open_plan = SimpleNamespace(draft=draft, questions=[{'id': 'past', 'kind': 'choice', 'choices': [
        {'value': '2026-09-29', 'label': 'Tomorrow at 10:00'}, {'value': 'keep', 'label': 'Keep that time'}]}])
    when = answered_draft(open_plan, answer).steps[0].when
    assert {'date': when.date, 'keep_past': when.keep_past} == expected


def test_the_model_cannot_accept_a_past_time_for_the_user(people, meetings, db):
    # seen live: answering another question, the model also set keep_past and the question vanished
    from unittest.mock import MagicMock

    from indico_assistant.services.actions import planner
    from indico_assistant.services.llm.models.base import LLMResponse
    lucas = people['manager']
    chat = ChatSession(user_id=lucas.id)
    db.session.add(chat)
    db.session.flush()
    yesterday = (now_utc() - timedelta(days=1)).date().isoformat()
    llm = MagicMock()
    llm.generate.return_value = LLMResponse(success=True, latency_ms=1, result=PlanDraft.model_validate({
        'decision': 'new_request', 'steps': [{'action': 'create_meeting', 'category': 'Meetings',
                                              'when': {'date': yesterday, 'time': '10:00', 'keep_past': True}}]}))
    settings = {'actions_enabled': True, 'actions_allowed': ['create_event']}
    with acting_as(lucas):
        result = planner.plan_turn(lucas, chat.id, 'Meeting yesterday at 10 in Meetings', [], None, llm=llm,
                                   settings=settings)
        assert [q['id'] for q in result.plan['questions']] == ['past']
        kept = planner.plan_turn(lucas, chat.id, 'Keep that time', [], executor.open_plan(chat.id), llm=llm,
                                 settings=settings)
    assert kept.plan['can_confirm']  # the user's own choice does keep it
