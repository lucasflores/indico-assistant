"""The meetings a user manages, for finding one by name (spec 019; spec 025 story 3's full run): management through
a group on the category counts, as Indico's own check says."""

from datetime import timedelta

from indico.modules.groups.models.groups import LocalGroup
from indico.util.date_time import now_utc

from indico_assistant.services.actions import resolve


def test_a_manager_through_the_categorys_group_finds_its_meetings(db, create_user, create_category, create_event):
    manager, viewer = create_user(31), create_user(32)
    group = LocalGroup(name="team managers")
    group.members.add(manager)
    team = create_category(title="Team Meetings")
    db.session.add(group)
    db.session.flush()
    team.update_principal(group.proxy, full_access=True)
    soon = now_utc() + timedelta(days=3)
    sync = create_event(title="Team Sync", category=team, start_dt=soon, end_dt=soon + timedelta(minutes=30))
    create_event(
        title="Long gone",
        category=team,
        start_dt=soon - timedelta(days=90),
        end_dt=soon - timedelta(days=90) + timedelta(hours=1),
    )
    db.session.flush()
    assert [e.title for e in resolve.managed_meetings(manager)] == ["Team Sync"]  # (from a month ago on)
    assert resolve.find_meeting("team sync", manager, None, None) == (sync, None)
    assert resolve.managed_meetings(viewer) == []
