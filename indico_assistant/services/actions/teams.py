"""A Microsoft Teams meeting for an event, via the vc_teams plugin (research R5; contracts/actions.md).

Replays what Indico's "Create videoconference room" page does (RHVCManageEventCreate), without its form.
It is the last step of a plan: it calls Microsoft Graph, and cancels the meeting again if the plan fails.
"""

from flask import current_app

from indico.core import signals
from indico.core.db import db
from indico.modules.events import Event
from indico.modules.users import User
from indico.modules.vc.models.vc_rooms import VCRoom, VCRoomEventAssociation, VCRoomStatus
from indico.modules.vc.notifications import notify_created
from indico.modules.vc.util import get_vc_plugins
from indico.web.flask.util import url_for

from indico_assistant.services.actions import register
from indico_assistant.services.actions.base import Action, ActionArgs, on_rollback
from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.actions.contributions import _manage_refusal


def teams_plugin():
    return get_vc_plugins().get('teams')


def tenant_email(user):
    """The user's Microsoft 365 address, or None: only they can be co-organizers (Teams invitees)."""
    from indico_vc_teams.util import find_tenant_email
    return find_tenant_email(user)


class AddTeamsRoomArgs(ActionArgs):
    event_id: int
    name: str
    coorganizer_ids: list[int] = []
    description: str = ''


@register
class AddTeamsRoom(Action):
    name = 'add_teams_room'
    Args = AddTeamsRoomArgs
    external = True
    summary = 'add a Microsoft Teams meeting to a meeting'

    def available(self, user, event=None, category=None):
        from indico_assistant.services.actions.contributions import _manage_available

        if (plugin := teams_plugin()) is None:
            return 'Microsoft Teams is not available on this Indico'
        if reason := _manage_available(user, event):
            return reason
        if not plugin.can_manage_vc_rooms(user, event):  # the plugin's own list; it does not depend on the event
            return 'You are not allowed to create Teams meetings'
        return None

    def check(self, user, args):
        if (plugin := teams_plugin()) is None:
            return 'Microsoft Teams is not available on this Indico'
        if reason := _manage_refusal(Event.get(args.event_id, is_deleted=False), user):
            return reason
        if not plugin.can_manage_vc_rooms(user, Event.get(args.event_id)):
            return 'You are not allowed to create Teams meetings'
        if missing := [u.full_name for u in map(User.get, args.coorganizer_ids) if tenant_email(u) is None]:
            return f'No Microsoft 365 account found for: {", ".join(missing)}'
        return None

    def describe(self, args):
        invited = [User.get(i).email for i in args.coorganizer_ids]
        effects = [f'Teams invitations to {", ".join(invited)}'] if invited else []
        return f'Add a Microsoft Teams meeting “{args.name}”', effects

    def execute(self, user, args):
        plugin = teams_plugin()
        event = Event.get(args.event_id)
        data = plugin.get_vc_room_form_defaults(event) | {
            'name': args.name, 'description': args.description,
            'coorganizers': {User.get(i) for i in args.coorganizer_ids},
            'linking': 'event', 'contribution': None, 'block': None, 'show': True,
        }
        vc_room = VCRoom(created_by_user=user, type=plugin.service_name, status=VCRoomStatus.created)
        with db.session.no_autoflush:
            assoc = VCRoomEventAssociation()
            # separate copies: each call pops the keys it uses (as each gets its own form.data on the page)
            plugin.update_data_association(event, vc_room, assoc, dict(data))
            plugin.update_data_vc_room(vc_room, dict(data), is_new=True)
            with plugin.plugin_context():
                plugin.create_room(vc_room, event)
            graph_event_id = vc_room.data['event_id']
            on_rollback(lambda: _cancel(graph_event_id))
            signals.vc.vc_room_created.send(vc_room, event=event, assoc=assoc)
        # Indico's email template links with a relative endpoint ('.manage_vc_rooms'), which only resolves
        # inside the VC pages; render it from that page's URL, as the page itself would (queued until commit)
        with current_app.test_request_context(url_for('vc.manage_vc_rooms', event)), acting_as(user):
            notify_created(plugin, vc_room, assoc, event, user)
        db.session.add(vc_room)
        db.session.flush()
        return {'created': {'vc_room_id': vc_room.id, 'graph_event_id': graph_event_id}}

    def revert(self, user, result):
        """The "Remove" of the videoconference page (RHVCManageEventRemove, all of it): the room goes, and
        vc_teams cancels the Teams meeting after the commit. (When the plan also created the event, this
        runs first and the event's deletion finds no room left.)"""
        vc_room = VCRoom.get(result['created']['vc_room_id'])
        if vc_room is None or vc_room.status == VCRoomStatus.deleted or not vc_room.events:
            return
        event = vc_room.events[0].event
        plugin = teams_plugin()
        # the "deleted" email, like the "created" one, links relative to the VC page
        with current_app.test_request_context(url_for('vc.manage_vc_rooms', event)), acting_as(user), \
                plugin.plugin_context():
            vc_room.delete(user, event=event)


def _cancel(graph_event_id):
    from indico_vc_teams import graph
    graph.get_client().cancel_event(graph_event_id, 'The meeting could not be set up from Indico.')
