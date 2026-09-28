"""A meeting's talks (contributions) and their speakers (research R3; contracts/actions.md)."""

from datetime import datetime, timedelta

from pydantic import BaseModel, model_validator

from indico.modules.events import Event
from indico.modules.events.contributions.models.contributions import Contribution
from indico.modules.events.contributions.models.persons import AuthorType, ContributionPersonLink
from indico.modules.events.contributions.operations import create_contribution, delete_contribution
from indico.modules.events.models.persons import EventPerson
from indico.modules.events.persons.util import get_event_person
from indico.modules.users import User

from indico_assistant.services.actions import register
from indico_assistant.services.actions.base import Action, ActionArgs, refuse_if_locked


class Speaker(BaseModel):
    user_id: int | None = None
    first_name: str = ''
    last_name: str = ''
    email: str = ''

    @model_validator(mode='after')
    def _someone(self):
        if self.user_id is None and not (self.last_name and self.email):
            raise ValueError('A guest speaker needs a last name and an email')
        return self

    def label(self):
        if self.user_id is not None:
            user = User.get(self.user_id)
            return f'{user.full_name} <{user.email}>'
        return f'{self.first_name} {self.last_name} <{self.email}> (guest)'.strip()


class AddContributionArgs(ActionArgs):
    event_id: int
    title: str
    start_dt: datetime
    duration_minutes: int
    speakers: list[Speaker] = []


def _manage_refusal(event, user):
    """The meeting timetable pages (RHManageTimetableBase without a session): full event management."""
    if event is None:
        return 'That meeting no longer exists'
    if reason := refuse_if_locked(event):
        return reason
    if not event.can_manage(user):
        return f'You cannot manage the event “{event.title}”'
    return None


@register
class AddContribution(Action):
    """Adding a contribution in a meeting's timetable (RHLegacyTimetableAddContribution)."""

    name = 'add_contribution'
    Args = AddContributionArgs

    def check(self, user, args):
        return _manage_refusal(Event.get(args.event_id, is_deleted=False), user)

    def describe(self, args):
        who = ', '.join(s.label() for s in args.speakers) or 'no speaker'
        return f'Add the talk “{args.title}” ({args.duration_minutes} min) with {who}', []

    def execute(self, user, args):
        event = Event.get(args.event_id)
        links = {}
        for speaker in args.speakers:
            if speaker.user_id is not None:
                person = EventPerson.for_user(User.get(speaker.user_id), event)
            else:
                person = get_event_person(event, {'first_name': speaker.first_name, 'last_name': speaker.last_name,
                                                  'email': speaker.email.lower()})
            # every person of a meeting contribution is a speaker, and speakers may submit material
            links[ContributionPersonLink(person=person, is_speaker=True, author_type=AuthorType.none)] = True
        contribution = create_contribution(event, {
            'title': args.title,
            'duration': timedelta(minutes=args.duration_minutes),
            'start_dt': args.start_dt,
            'person_link_data': links,
            'location_data': {'inheriting': True},
        }, extend_parent=True)
        return {'created': {'contribution_id': contribution.id}}

    def revert(self, user, result):
        delete_contribution(Contribution.get(result['created']['contribution_id']))
