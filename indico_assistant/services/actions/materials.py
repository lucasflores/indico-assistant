"""Reminders, links and files on a meeting or talk (research R6, R7; contracts/actions.md)."""

import logging
from datetime import timedelta
from typing import Literal

from pydantic import HttpUrl

from indico.core.config import config
from indico.core.db import db
from indico.modules.events import Event
from indico.modules.events.reminders.models.reminders import EventReminder, ReminderType
from indico.modules.logs import EventLogRealm, LogKind
from indico.util.date_time import now_utc

from indico_assistant.services.actions import register
from indico_assistant.services.actions.base import Action, ActionArgs, on_rollback, refuse_if_locked
from indico_assistant.services.actions.contributions import _manage_refusal


logger = logging.getLogger(__name__)


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
            return {'created': None, 'skipped': 'the meeting starts too soon for a reminder'}
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
        if not result.get('created'):
            return  # it was too late to add it, so there is nothing to undo
        reminder = EventReminder.get(result['created']['reminder_id'])
        if reminder is not None and not reminder.is_sent:
            db.session.delete(reminder)


class _AttachArgs(ActionArgs):
    target_type: Literal['event', 'contribution']
    target_id: int
    title: str | None = None


def _target(args):
    from indico.modules.events.contributions.models.contributions import Contribution

    model = Event if args.target_type == 'event' else Contribution
    obj = model.get(args.target_id, is_deleted=False)
    return None if obj is None or obj.event.is_deleted else obj


def _attach_refusal(obj, user):
    """The material pages' check (RHEventAttachmentManagementBase): can_manage_attachments, not locked."""
    from indico.modules.attachments.util import can_manage_attachments

    if obj is None:
        return 'That meeting or talk no longer exists'
    if reason := refuse_if_locked(obj.event):
        return reason
    if not can_manage_attachments(obj, user):
        return f'You cannot add material to “{obj.title}”'
    return None


def _new_attachment(obj, user, **fields):
    from indico.core.db.sqlalchemy.protection import ProtectionMode
    from indico.modules.attachments.models.attachments import Attachment
    from indico.modules.attachments.models.folders import AttachmentFolder

    folder = AttachmentFolder.get_or_create_default(linked_object=obj)
    return Attachment(folder=folder, user=user, protection_mode=ProtectionMode.inheriting, **fields)


def _announce(attachment, user):
    """What the upload page does once the attachment exists: the event log entry, our document index."""
    from indico.core import signals

    db.session.add(attachment)
    db.session.flush()
    logger.info('Attachment %s added by %s (assistant)', attachment, user)
    signals.attachments.attachment_created.send(attachment, user=user)


class AttachLinkArgs(_AttachArgs):
    url: HttpUrl


@register
class AttachLink(Action):
    """Adding a link as material (add_attachment_link, without its form)."""

    name = 'attach_link'
    Args = AttachLinkArgs

    def check(self, user, args):
        return _attach_refusal(_target(args), user)

    def describe(self, args):
        obj = _target(args)
        return f'Add the link {args.url} to {f"“{obj.title}”" if obj else "the new meeting"}', []

    def execute(self, user, args):
        from indico.modules.attachments.models.attachments import AttachmentType

        link = _new_attachment(_target(args), user, type=AttachmentType.link, title=args.title or str(args.url),
                               link_url=str(args.url))
        _announce(link, user)
        return {'created': {'attachment_id': link.id}}

    def revert(self, user, result):
        _remove_attachment(result['created']['attachment_id'], user)


class AttachFileArgs(_AttachArgs):
    upload_uuid: str


@register
class AttachFile(Action):
    """Adding a file sent in the chat as material, with the upload page's steps (AddAttachmentFilesMixin):
    the bytes are copied into the attachment's own storage, as Indico does when it uses an uploaded file."""

    name = 'attach_file'
    Args = AttachFileArgs

    def check(self, user, args):
        from indico_assistant.services.actions.uploads import usable_upload

        if reason := _attach_refusal(_target(args), user):
            return reason
        if usable_upload(args.upload_uuid, user) is None:
            return 'That file is no longer available; please send it again'
        return None

    def describe(self, args):
        from indico.modules.files.models.files import File

        file = File.query.filter_by(uuid=args.upload_uuid).first()
        name = file.filename if file else 'the file'
        return f'Attach {name} to “{_target(args).title}”', []

    def execute(self, user, args):
        from indico.modules.attachments.models.attachments import AttachmentFile, AttachmentType

        from indico_assistant.services.actions.uploads import mark_used, usable_upload

        upload = usable_upload(args.upload_uuid, user)
        attachment = _new_attachment(_target(args), user, type=AttachmentType.file,
                                     title=args.title or upload.filename)
        attachment.file = AttachmentFile(user=user, filename=upload.filename, content_type=upload.content_type)
        with upload.open() as data:
            attachment.file.save(data)
        storage, file_id = attachment.file.storage, attachment.file.storage_file_id
        on_rollback(lambda: storage.delete(file_id))  # written to storage now, not undone by a rollback
        _announce(attachment, user)
        # the chat upload stays unclaimed (Indico's own cleanup removes it, as with paper uploads), marked as
        # used so it is neither sent nor attached again
        mark_used(upload)
        return {'created': {'attachment_id': attachment.id}}

    def revert(self, user, result):
        _remove_attachment(result['created']['attachment_id'], user)


def _remove_attachment(attachment_id, user):
    from indico.core import signals
    from indico.modules.attachments.models.attachments import Attachment

    attachment = Attachment.get(attachment_id)
    if attachment is not None and not attachment.is_deleted:
        attachment.is_deleted = True
        signals.attachments.attachment_deleted.send(attachment, user=user)
