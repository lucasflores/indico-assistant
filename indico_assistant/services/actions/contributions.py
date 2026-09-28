"""A meeting's talks (contributions) and their speakers (research R3; contracts/actions.md)."""

from datetime import datetime, timedelta

from flask import g
from pydantic import BaseModel, model_validator

from indico.modules.events import Event
from indico.modules.events.contributions.models.contributions import Contribution
from indico.modules.events.contributions.models.persons import AuthorType, ContributionPersonLink
from indico.modules.events.contributions.operations import (create_contribution, delete_contribution,
                                                            update_contribution)
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


def _person_links(event, speakers):
    """The contribution's person links, as its form makes them: every person of a meeting contribution is a
    speaker, and speakers may submit material."""
    links = {}
    for speaker in speakers:
        if speaker.user_id is not None:
            person = EventPerson.for_user(User.get(speaker.user_id), event)
        else:
            person = get_event_person(event, {'first_name': speaker.first_name, 'last_name': speaker.last_name,
                                              'email': speaker.email.lower()})
        links[ContributionPersonLink(person=person, is_speaker=True, author_type=AuthorType.none)] = True
    return links


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
        links = _person_links(event, args.speakers)
        if event.id in g.get('assistant_new_events', ()):
            # Indico numbers contributions per event from a separate DB session, which cannot see an event
            # this plan created and has not committed yet. Nobody else can see it either, so take the next
            # number on the event itself, as Indico's event cloning does. (Indico's test fixture shares that
            # session, so only a real database shows this.)
            event._last_friendly_contribution_id += 1
            (g.setdefault('friendly_ids', {}).setdefault(Contribution, {}).setdefault(event.id, [])
             .append(event._last_friendly_contribution_id))
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


class UpdateContributionArgs(ActionArgs):
    contribution_id: int
    title: str | None = None
    start_dt: datetime | None = None
    duration_minutes: int | None = None
    speakers: list[Speaker] | None = None  # replaces the speakers


def _contribution_state(contribution):
    return {'contribution_id': contribution.id, 'title': contribution.title, 'start_dt': contribution.start_dt,
            'duration_minutes': int(contribution.duration.total_seconds() // 60),
            'speakers': [{'user_id': link.person.user_id, 'first_name': link.first_name,
                          'last_name': link.last_name, 'email': link.email}
                         for link in contribution.person_links if link.is_speaker]}


@register
class UpdateContribution(Action):
    """Editing a talk in a meeting's timetable (RHLegacyTimetableEditEntry): full event management."""

    name = 'update_contribution'
    Args = UpdateContributionArgs

    def check(self, user, args):
        contribution = Contribution.get(args.contribution_id, is_deleted=False)
        if contribution is None or contribution.event.is_deleted:
            return 'That talk no longer exists'
        if reason := _manage_refusal(contribution.event, user):
            return reason
        if args.start_dt is not None and contribution.timetable_entry is None:
            return f'The talk “{contribution.title}” is not in the timetable'
        return None

    def describe(self, args):
        contribution = Contribution.get(args.contribution_id)
        changes = []
        if args.title is not None:
            changes.append(f'rename it to “{args.title}”')
        if args.start_dt is not None:
            changes.append(f'move it to {args.start_dt.astimezone(contribution.event.tzinfo):%H:%M}')
        if args.duration_minutes is not None:
            changes.append(f'make it {args.duration_minutes} min')
        if args.speakers is not None:
            changes.append('speakers: ' + (', '.join(s.label() for s in args.speakers) or 'none'))
        return f'Change the talk “{contribution.title}”: {"; ".join(changes)}', []

    def execute(self, user, args):
        contribution = Contribution.get(args.contribution_id)
        before = _contribution_state(contribution)
        data = {}
        if args.title is not None:
            data['title'] = args.title
        if args.duration_minutes is not None:
            data['duration'] = timedelta(minutes=args.duration_minutes)
        if args.speakers is not None:
            data['person_link_data'] = _person_links(contribution.event, args.speakers)
        if args.start_dt is not None:
            data['start_dt'] = args.start_dt
        update_contribution(contribution, data)
        return {'created': None, 'before': before, 'after': _contribution_state(contribution)}

    def revert(self, user, result):
        self.execute(user, UpdateContributionArgs.model_validate(result['before']))
