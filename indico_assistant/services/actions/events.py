"""Meetings: creating them (research R3; contracts/actions.md)."""

from datetime import datetime

from flask import g
from pydantic import model_validator

from indico.modules.categories import Category
from indico.modules.events import Event
from indico.modules.events.models.events import EventType
from indico.modules.categories.util import can_create_unlisted_events
from indico.modules.events.notifications import notify_event_creation, notify_move_request_creation
from indico.modules.events.operations import create_event, create_event_request

from indico_assistant.services.actions import register
from indico_assistant.services.actions.base import Action, ActionArgs, category_path, format_dt


class CreateEventArgs(ActionArgs):
    category_id: int
    title: str
    description: str = ''
    start_dt: datetime
    end_dt: datetime
    timezone: str
    venue_name: str = ''
    room_name: str = ''
    address: str = ''

    @model_validator(mode='after')
    def _ends_after_start(self):
        if self.end_dt <= self.start_dt:
            raise ValueError('The meeting must end after it starts')
        return self


@register
class CreateEvent(Action):
    """Indico's "Create meeting" dialog (RHCreateEvent)."""

    name = 'create_event'
    Args = CreateEventArgs

    def check(self, user, args):
        category = Category.get(args.category_id, is_deleted=False)
        if category is None:
            return 'That category no longer exists'
        # EventCreationFormBase.validate_category, for a listed event
        if not category.can_create_events(user):
            return f'You cannot create events in {category_path(category)}'
        return None

    def describe(self, args):
        import pytz
        tz = pytz.timezone(args.timezone)
        category = Category.get(args.category_id)
        where = f' in {category_path(category)}' if category else ''
        return (f'Create the meeting “{args.title}”{where}, {format_dt(args.start_dt, tz)} to '
                f'{args.end_dt.astimezone(tz):%H:%M}'), []

    def execute(self, user, args):
        event = create_event(Category.get(args.category_id), EventType.meeting, self._data(args))
        g.setdefault('assistant_new_events', set()).add(event.id)  # uncommitted until the plan is done
        notify_event_creation(event)  # the page does this after the operation
        return {'created': {'event_id': event.id}}

    @staticmethod
    def _data(args):
        return {
            'title': args.title, 'description': args.description, 'start_dt': args.start_dt, 'end_dt': args.end_dt,
            'timezone': args.timezone,
            'location_data': {'inheriting': False, 'venue_name': args.venue_name, 'room_name': args.room_name,
                              'address': args.address},
        }

    def revert(self, user, result):
        Event.get(result['created']['event_id']).delete('Undone from the assistant chat', user)


class ProposeEventArgs(CreateEventArgs):
    comment: str = ''


@register
class ProposeEvent(Action):
    """Proposing a meeting in a moderated category: Indico's only way is an unlisted event whose publication
    in the category is requested (RHMoveEvent), for the category's managers to approve (research R4)."""

    name = 'propose_event'
    Args = ProposeEventArgs

    def check(self, user, args):
        category = Category.get(args.category_id, is_deleted=False)
        if category is None:
            return 'That category no longer exists'
        if not can_create_unlisted_events(user):
            return 'Proposing events needs unlisted events, which are not enabled for you on this Indico'
        if not (category.can_create_events(user) or category.can_propose_events(user)):
            return f'You cannot propose events in {category_path(category)}'
        return None

    def describe(self, args):
        description, effects = CreateEvent().describe(args)
        category = Category.get(args.category_id)
        return (description.replace('Create the meeting', 'Propose the meeting', 1) + ' (needs approval)',
                [*effects, f'The managers of {category_path(category)} are asked to approve it'])

    def execute(self, user, args):
        category = Category.get(args.category_id)
        event = create_event(None, EventType.meeting, CreateEvent._data(args))  # unlisted until approved
        g.setdefault('assistant_new_events', set()).add(event.id)
        request = create_event_request(event, category, args.comment)
        notify_move_request_creation([event], category, args.comment)
        return {'created': {'event_id': event.id, 'request_id': request.id}}

    def revert(self, user, result):
        Event.get(result['created']['event_id']).delete('Undone from the assistant chat', user)  # withdraws the request
