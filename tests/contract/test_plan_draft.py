"""The planner's LLM contract: a schema every provider mode accepts, and the drafts we expect parse."""

import json

import pytest
from pydantic import ValidationError

from indico_assistant.services.llm.models.plan import ChangeMeeting, CreateMeeting, PlanDraft

EXAMPLE = {  # "Create a Teams meeting for today at 2pm with Makoto, add both of us as contributors with 20 min slots."
    'decision': 'new_request',
    'steps': [{'action': 'create_meeting', 'teams': True, 'when': {'date': 'today', 'time': '2pm'},
               'people': [{'name': 'Makoto'}],
               'slots': [{'speaker': {'name': 'me'}, 'duration_minutes': 20},
                         {'speaker': {'name': 'Makoto'}, 'duration_minutes': 20}]}],
    'reply': 'Here is the plan. Which category should the meeting go in?',
}


def test_schema_is_plain_json_schema():
    # MD_JSON (ibis) and JSON modes paste this schema into the prompt; TOOLS passes it as parameters
    schema = PlanDraft.model_json_schema()
    json.dumps(schema)
    step_union = schema['properties']['steps']['items']
    assert step_union['discriminator']['propertyName'] == 'action' and len(step_union['oneOf']) == 4


def test_the_example_request_parses():
    draft = PlanDraft.model_validate(EXAMPLE)
    (step,) = draft.steps
    assert isinstance(step, CreateMeeting) and step.teams and step.category is None
    assert [s.speaker.name for s in step.slots] == ['me', 'Makoto']


def test_follow_ups_parse():
    draft = PlanDraft.model_validate({'decision': 'revise', 'reply': 'Moved.',
                                      'steps': [{'action': 'change_meeting', 'move_to': {'time': '15:00'}}]})
    assert isinstance(draft.steps[0], ChangeMeeting) and draft.steps[0].meeting == 'it'
    assert PlanDraft.model_validate({'decision': 'confirm', 'reply': 'Creating it now.'}).steps == []


@pytest.mark.parametrize('bad', [
    {**EXAMPLE, 'decision': 'delete_everything'},
    {**EXAMPLE, 'steps': [{'action': 'run_sql', 'sql': 'DELETE FROM events.events'}]},
    {**EXAMPLE, 'steps': [EXAMPLE['steps'][0]] * 11},
])
def test_anything_else_is_rejected(bad):
    with pytest.raises(ValidationError):
        PlanDraft.model_validate(bad)


def test_what_real_models_send_is_accepted():
    # seen from gpt-4o-mini: speakers as plain names, no reply
    draft = PlanDraft.model_validate({'decision': 'new_request', 'steps': [
        {'action': 'create_meeting', 'when': {'date': '2026-09-28', 'time': '14:00'}, 'people': ['Makoto'],
         'slots': [{'speaker': 'Makoto', 'duration_minutes': 20}]}]})
    assert draft.steps[0].slots[0].speaker.name == 'Makoto' and draft.steps[0].people[0].name == 'Makoto'
    assert draft.reply == ''
