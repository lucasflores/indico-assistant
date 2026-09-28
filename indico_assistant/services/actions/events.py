"""Meetings: creating them (research R3; contracts/actions.md)."""

from datetime import datetime, timedelta

from flask import g
from pydantic import model_validator

from indico.modules.categories import Category
from indico.modules.events import Event
from indico.modules.events.models.events import EventType
from indico.modules.categories.util import can_create_unlisted_events
from indico.modules.events.notifications import notify_event_creation, notify_move_request_creation
from indico.modules.events.operations import create_event, create_event_request, update_event

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
        event = Event.get(result['created']['event_id'])
        if not event.is_deleted:
            event.delete('Undone from the assistant chat', user)


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
        event = Event.get(result['created']['event_id'])
        if not event.is_deleted:
            event.delete('Undone from the assistant chat', user)  # withdraws the request


class UpdateEventArgs(ActionArgs):
    event_id: int
    title: str | None = None
    description: str | None = None
    start_dt: datetime | None = None
    end_dt: datetime | None = None


def _event_state(event):
    return {'event_id': event.id, 'title': event.title, 'description': event.description,
            'start_dt': event.start_dt, 'end_dt': event.end_dt}


def _dates_refusal(event, start, end):
    """EventDatesForm's rules when the timetable moves with the event (update_timetable)."""
    if end <= start:
        return 'The meeting must end after it starts'
    entries = [e for e in event.timetable_entries if e.parent_id is None]
    if entries:
        room_needed = (start - event.start_dt) - (end - max(e.end_dt for e in entries))
        if room_needed > timedelta():
            return (f'The meeting is too short to fit all its talks; it must be at least '
                    f'{int(room_needed.total_seconds() // 60)} minutes longer')
    return None


@register
class UpdateEvent(Action):
    """Editing a meeting's title, description or dates (RHEditEventData, RHEditEventDates): full management.
    Moving it moves its talks, and vc_teams moves the Teams meeting (the times_changed signal)."""

    name = 'update_event'
    Args = UpdateEventArgs

    def check(self, user, args):
        from indico_assistant.services.actions.contributions import _manage_refusal

        event = Event.get(args.event_id, is_deleted=False)
        if reason := _manage_refusal(event, user):
            return reason
        if args.start_dt is not None or args.end_dt is not None:
            return _dates_refusal(event, args.start_dt or event.start_dt, args.end_dt or event.end_dt)
        return None

    def describe(self, args):
        event = Event.get(args.event_id)
        tz = event.tzinfo
        changes = []
        if args.title is not None:
            changes.append(f'rename it to “{args.title}”')
        if args.start_dt is not None or args.end_dt is not None:
            start, end = args.start_dt or event.start_dt, args.end_dt or event.end_dt
            changes.append(f'move it to {format_dt(start, tz)} to {end.astimezone(tz):%H:%M}')
        if args.description is not None:
            changes.append('update its description')
        effects = []
        if (args.start_dt is not None) and (talks := len([c for c in event.contributions if c.is_scheduled])):
            effects.append(f'Its {talks} talk{"s" if talks > 1 else ""} move with it')
        if args.start_dt is not None and event.vc_room_associations:
            effects.append('The Teams meeting moves too')
        return f'Change “{event.title}”: {"; ".join(changes)}', effects

    def execute(self, user, args):
        event = Event.get(args.event_id)
        before = _event_state(event)
        changes = {k: v for k, v in args.model_dump(exclude={'event_id'}).items()
                   if v is not None and v != before[k]}
        update_event(event, update_timetable=True, **changes)
        return {'created': None, 'before': before, 'after': _event_state(event)}

    def revert(self, user, result):
        self.execute(user, UpdateEventArgs.model_validate(result['before']))


UNDO_WINDOW = timedelta(hours=24)


class DeleteCreatedArgs(ActionArgs):
    plan_id: str


def undoable_plan(plan_id, user):
    """The user's own carried-out plan from the last 24 hours that nothing has undone yet (US7), or None."""
    from indico_assistant.models import ActionPlan

    plan = ActionPlan.query.filter_by(id=plan_id, user_id=user.id, status='done').first()
    if plan is None or plan.undoes_id is not None or plan.finished_at < _now_utc() - UNDO_WINDOW:
        return None
    if ActionPlan.query.filter_by(undoes_id=plan.id, status='done').count():
        return None
    return plan


def _now_utc():
    from indico.util.date_time import now_utc
    return now_utc()


@register
class DeleteCreated(Action):
    """Undo: every step of a plan reversed with Indico's own operations, last step first (deleting a meeting
    deletes its Teams room, which cancels the Teams meeting, as the delete page does)."""

    name = 'delete_created'
    Args = DeleteCreatedArgs

    def check(self, user, args):
        from indico_assistant.services.actions.contributions import _manage_refusal

        plan = undoable_plan(args.plan_id, user)
        if plan is None:
            return 'That can no longer be undone (only your own changes of the last 24 hours, once)'
        for result in plan.result or ():
            target = _undo_target(result)
            if target is not None and not target.is_deleted and (reason := _manage_refusal(target, user)):
                return reason  # a locked meeting too, like every other write
        return None

    def describe(self, args):
        from indico_assistant.models import ActionPlan
        plan = ActionPlan.query.get(args.plan_id)
        return f'Undo: {plan.summary}', []

    def execute(self, user, args):
        from indico_assistant.services import actions

        plan = undoable_plan(args.plan_id, user)
        for result in reversed(plan.result or ()):
            actions.ACTIONS[result['action']].revert(user, result)
        return {'created': None, 'before': {'plan_id': str(plan.id)}}


def _undo_target(result):
    """The Indico object a step result is about (to check it can still be managed)."""
    from indico.modules.events.contributions.models.contributions import Contribution

    created, before = result.get('created') or {}, result.get('before') or {}
    if 'event_id' in created or 'event_id' in before:
        return Event.get(created.get('event_id', before.get('event_id')))
    if 'contribution_id' in created or 'contribution_id' in before:
        contribution = Contribution.get(created.get('contribution_id', before.get('contribution_id')))
        return contribution.event if contribution else None
    return None
