"""A small Indico for the lookups: users with every kind of access, events, talks, registrations and notes."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from indico.core.db import db
from indico.core.db.sqlalchemy.descriptions import RenderMode
from indico.core.db.sqlalchemy.protection import ProtectionMode
from indico.modules.events.contributions.models.persons import ContributionPersonLink
from indico.modules.events.contributions.operations import create_contribution
from indico.modules.events.notes.models.notes import EventNote
from indico.modules.events.persons.util import get_event_person
from indico.modules.groups import GroupProxy
from indico.modules.groups.models.groups import LocalGroup
from indico.util.date_time import now_utc

PROVIDER = "testidp"


class FakeGroup:
    """An identity provider's group, as flask-multipass gives it: ``identifier in group``."""

    def __init__(self, members):
        self.members = set(members)

    def __contains__(self, identifier):
        return identifier in self.members


@pytest.fixture
def idp(monkeypatch):
    """A static identity provider with one group, "physicists", whose members are given by identifier."""
    from indico.core.auth import multipass

    groups = {"physicists": FakeGroup({"ida"})}
    monkeypatch.setattr(
        multipass, "get_group", lambda provider, name: groups.get(name) if provider == PROVIDER else None
    )
    monkeypatch.setattr(multipass, "search_identities", lambda **kwargs: [])
    return groups


def note(obj, text, user):
    with db.session.no_autoflush:
        n = EventNote.get_or_create(obj)
        n.create_revision(RenderMode.markdown, text, user)
    db.session.flush()
    return n


def talk(event, title, speaker, start_dt=None, duration=20):
    """A scheduled contribution given by ``speaker`` (a user, or (first, last, email))."""
    if isinstance(speaker, tuple):
        person = get_event_person(event, {"first_name": speaker[0], "last_name": speaker[1], "email": speaker[2]})
    else:
        person = get_event_person(
            event, {"first_name": speaker.first_name, "last_name": speaker.last_name, "email": speaker.email}
        )
    link = ContributionPersonLink(person=person, is_speaker=True)
    contribution = create_contribution(
        event,
        {
            "title": title,
            "duration": timedelta(minutes=duration),
            "start_dt": start_dt or event.start_dt,
            "person_link_data": {link: False},
            "location_data": {"inheriting": True},
        },
        extend_parent=True,
    )
    db.session.flush()
    return contribution


@pytest.fixture
def world(db, create_user, create_identity, create_category, create_event, idp):
    """Users: nora (nobody), dana (a direct grant), lou (a local group), ida (the idp group), cat (a category
    grant), manager (manages Team Meetings). Events: a public Sync, a protected Briefing (dana), a Lab meeting (lab
    members), a Forum (physicists), a Roadmap review in the Restricted category (cat), an unlisted one of nora's."""
    nora, dana, lou, ida, cat, manager = (
        create_user(n, first_name=f, last_name="Test", email=f"{f.lower()}@example.test")
        for n, f in ((51, "Nora"), (52, "Dana"), (53, "Lou"), (54, "Ida"), (55, "Cat"), (56, "Manager"))
    )
    create_identity(ida, PROVIDER, "ida")
    lab = LocalGroup(name="lab-members")
    lab.members.add(lou)
    db.session.add(lab)
    db.session.flush()
    team = create_category(title="Team Meetings")
    team.update_principal(manager, full_access=True)
    restricted = create_category(title="Restricted Projects", protection_mode=ProtectionMode.protected)
    restricted.update_principal(cat, read_access=True)
    t0 = now_utc().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=7)  # (mid-day: an event
    # ending at midnight is "on" the next day too, as Indico's inclusive overlap counts it)

    def event(title, category, days, **kwargs):
        start = t0 + timedelta(days=days)
        e = create_event(title=title, category=category, start_dt=start, end_dt=start + timedelta(hours=1), **kwargs)
        db.session.flush()
        return e

    sync = event("Team Sync", team, 1)
    briefing = event("Briefing: Supplier Contracts", team, 2, protection_mode=ProtectionMode.protected)
    briefing.update_principal(dana, read_access=True)
    lab_meeting = event("Lab Members Meeting", team, 3, protection_mode=ProtectionMode.protected)
    lab_meeting.update_principal(lab.proxy, read_access=True)
    forum = event("Physicists Forum", team, 4, protection_mode=ProtectionMode.protected)
    forum.update_principal(GroupProxy("physicists", provider=PROVIDER), read_access=True)
    roadmap = event("Restricted Roadmap Review", restricted, 5)
    unlisted = create_event(
        title="Nora's Draft",
        category=None,
        creator=nora,
        creator_has_privileges=True,
        start_dt=t0 + timedelta(days=6),
        end_dt=t0 + timedelta(days=6, hours=1),
    )
    # (as Indico creates an unlisted event: its creator gets full access, operations.py)
    db.session.flush()
    return SimpleNamespace(
        nora=nora,
        dana=dana,
        lou=lou,
        ida=ida,
        cat=cat,
        manager=manager,
        sync=sync,
        briefing=briefing,
        lab=lab_meeting,
        forum=forum,
        roadmap=roadmap,
        unlisted=unlisted,
        t0=t0,
    )
