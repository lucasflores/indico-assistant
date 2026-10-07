"""Events the user can open: by words, dates, category or a person's name (research R7)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from indico.core.db import db
from indico.core.db.sqlalchemy.util.queries import get_n_matching
from indico.modules.categories import Category
from indico.modules.events import Event
from indico.modules.events.contributions import contribution_settings
from indico.modules.events.contributions.models.contributions import Contribution
from indico.modules.events.contributions.models.persons import ContributionPersonLink
from indico.modules.events.models.persons import EventPerson
from indico.util.string import html_to_plaintext
from sqlalchemy import or_
from sqlalchemy.orm import selectinload, undefer

from indico_assistant.services.actions.context import user_timezone

LIMIT = 20
#: ponytail: a category's events are read a page of candidates at a time (get_n_matching), 5 × LIMIT per page
DESCRIPTION_CHARS = 600


def _bounds(user: Any, since: date | None, until: date | None) -> tuple[datetime | None, datetime | None]:
    """Local days as the user reads them, from the start of ``since`` to the end of ``until``."""
    tz = user_timezone(user)
    start = tz.localize(datetime.combine(since, time.min)) if since else None
    end = tz.localize(datetime.combine(until, time.max)) if until else None
    return start, end


def _category_ids(text: str) -> list[int]:
    """The categories named like ``text``, with everything under them."""
    ids = [c.id for c in Category.query.filter(~Category.is_deleted, Category.title.ilike(f"%{text}%"))]
    if not ids:
        return []
    subtree = Category.get_subtree_ids_cte(ids)
    return [row.id for row in db.session.query(subtree.c.id)]


def _names(name: str) -> Any:
    """A person-link filter: the full name, or either name alone, as typed ("Priya", "Shah", "Priya Shah")."""
    words = [w for w in name.split() if w]
    full = db.func.concat(EventPerson.first_name, " ", EventPerson.last_name)
    return or_(full.ilike(f"%{name}%"), *(full.ilike(f"%{w}%") for w in words if len(words) > 1))


def find_events(
    user: Any,
    *,
    text: str | None = None,
    since: date | None = None,
    until: date | None = None,
    category: str | None = None,
    person: str | None = None,
    limit: int = LIMIT,
) -> list[Event]:
    """Up to ``limit`` events the user can open, soonest first, among those matching every filter given. Unlisted
    events only when the user created them (as Indico lists them)."""
    start, end = _bounds(user, since, until)
    query = Event.query.filter(
        ~Event.is_deleted,
        or_(~Event.is_unlisted, Event.creator_id == user.id),
        Event.happens_between(start, end),
    )
    if text:
        query = query.filter(or_(Event.title.ilike(f"%{text}%"), Event.description.ilike(f"%{text}%")))
    if category:
        ids = _category_ids(category)
        if not ids:
            return []
        query = query.filter(Event.category_id.in_(ids))
    if person:
        talks = (
            db.session.query(Contribution.event_id)
            .join(ContributionPersonLink, ContributionPersonLink.contribution_id == Contribution.id)
            .join(EventPerson, EventPerson.id == ContributionPersonLink.person_id)
            .filter(~Contribution.is_deleted, _names(person))
        )
        chairs = (
            db.session.query(EventPerson.event_id).filter(
                EventPerson.event_links.any(), _names(person)
            )  # (chairpersons of the event itself)
        )
        query = query.filter(or_(Event.id.in_(talks.subquery()), Event.id.in_(chairs.subquery())))
    query = query.options(undefer("effective_protection_mode"), selectinload("acl_entries")).order_by(Event.start_dt)
    return list(get_n_matching(query, limit, lambda e: e.can_access(user)))


def talks_by(user: Any, name: str, events: list[Event]) -> dict[int, list[Contribution]]:
    """The talks ``name`` gives in ``events``, as the user may see them: a programme not yet published shows none
    to non-managers (``api.py``), and a protected talk only to those who can open it."""
    ids = [e.id for e in events]
    if not ids:
        return {}
    links = (
        ContributionPersonLink.query.join(EventPerson)
        .join(Contribution, Contribution.id == ContributionPersonLink.contribution_id)
        .filter(Contribution.event_id.in_(ids), ~Contribution.is_deleted, _names(name))
        .options(selectinload("contribution"))
    )
    found: dict[int, list[Contribution]] = {}
    for link in links:
        c = link.contribution
        if not contribution_settings.get(c.event, "published") and not c.event.can_manage(user):
            continue
        if c.can_access(user) and c not in found.setdefault(c.event_id, []):
            found[c.event_id].append(c)
    return found


def when(event: Event) -> str:
    """ "Wednesday 14 October 2026, 10:00–11:00 Europe/Zurich" in the event's own time zone."""
    tz = event.display_tzinfo
    start, end = event.start_dt.astimezone(tz), event.end_dt.astimezone(tz)
    day = f"{start:%A %d %B %Y}"
    if start.date() == end.date():
        return f"{day}, {start:%H:%M}–{end:%H:%M} {tz.zone}"
    return f"{day} {start:%H:%M} to {end:%A %d %B %Y} {end:%H:%M} {tz.zone}"


def where(obj: Any) -> str:
    parts = [p for p in (obj.room_name, obj.venue_name) if p]
    return ", ".join(parts)


def plain(html: str | None, limit: int = DESCRIPTION_CHARS) -> str:
    text = html_to_plaintext(html) if html and html.strip() else ""
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def describe(event: Event, user: Any, *, full: bool = False) -> dict[str, Any]:
    """An event as a small record. ``full``: its description, chairpersons, contact and (to its managers) managers."""
    record: dict[str, Any] = {
        "event": event.id,
        "title": event.title,
        "type": event.type_.name,
        "when": when(event),
        "where": where(event) or None,
        "category": " » ".join(event.category.chain_titles[1:]) if event.category else None,
        "url": event.external_url,
    }
    if full:
        record["description"] = plain(event.description) or None
        record["chairpersons"] = [
            f"{p.full_name}" + (f" ({p.affiliation})" if p.affiliation else "") for p in event.person_links
        ] or None
        if event.contact_emails:
            record["contact"] = f"{event.contact_title}: {', '.join(event.contact_emails)}"
        if event.can_manage(user):  # (Indico shows the managers' list to managers only; the category's count)
            record["managers"] = sorted(p.name for p in event.get_manager_list(recursive=True))
        if event.keywords:
            record["keywords"] = list(event.keywords)
    return {k: v for k, v in record.items() if v is not None}


def get_event(user: Any, event_id: int) -> Event | None:
    """One event, if the user can open it (a protected one they can't is "not found": its existence stays hidden)."""
    event = Event.get(event_id, is_deleted=False)
    return event if event is not None and event.can_access(user) else None


def week_of(day: date) -> tuple[date, date]:
    """Monday to Sunday of the week ``day`` is in (for "next week": the model writes both bounds)."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)
