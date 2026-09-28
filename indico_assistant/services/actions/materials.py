"""Reminders (and, later, links and files) on a meeting (research R6, R7; contracts/actions.md)."""

from datetime import timedelta

from indico.core.config import config
from indico.core.db import db
from indico.modules.events import Event
from indico.modules.events.reminders.models.reminders import EventReminder, ReminderType
from indico.modules.logs import EventLogRealm, LogKind
from indico.util.date_time import now_utc

from indico_assistant.services.actions import register
from indico_assistant.services.actions.base import Action, ActionArgs
from indico_assistant.services.actions.contributions import _manage_refusal


class AddReminderArgs(ActionArgs):
    event_id: int
    minutes_before: int
    recipients: list[str] = []
    send_to_speakers: bool = True


@register
class AddReminder(Action):
    """An event reminder as the reminders page creates it (RHAddReminder)."""

    name = 'add_reminder'
    Args = AddReminderArgs

    def check(self, user, args):
        return _manage_refusal(Event.get(args.event_id, is_deleted=False), user)

    def describe(self, args):
        to = (['the speakers'] if args.send_to_speakers else []) + args.recipients
        return (f'Send a reminder {args.minutes_before} minutes before the meeting to {", ".join(to)}',
                [f'Reminder email to {", ".join(to)}'])

    def execute(self, user, args):
        event = Event.get(args.event_id)
        delta = timedelta(minutes=args.minutes_before)
        if event.start_dt - delta <= now_utc():
            return {'created': None}  # too late for a reminder by now; the plan said when it would go out
        senders = event.get_allowed_sender_emails(include_noreply=True)
        reminder = EventReminder(creator=user, event=event, reminder_type=ReminderType.standard,
                                 scheduled_dt=event.start_dt - delta, event_start_delta=delta,
                                 recipients=[r.lower() for r in args.recipients],
                                 send_to_speakers=args.send_to_speakers, send_to_participants=False,
                                 include_summary=False, include_description=True, attach_ical=True,
                                 reply_to_address=user.email if user.email in senders else config.NO_REPLY_EMAIL)
        db.session.add(reminder)
        db.session.flush()
        # the page logs this itself (there is no reminder operation)
        reminder.log(EventLogRealm.management, LogKind.positive, 'Reminder', 'Event reminder added', user,
                     data={'Time': reminder.scheduled_dt.isoformat()})
        return {'created': {'reminder_id': reminder.id}}

    def revert(self, user, result):
        reminder = EventReminder.get(result['created']['reminder_id'])
        if reminder is not None and not reminder.is_sent:
            db.session.delete(reminder)
