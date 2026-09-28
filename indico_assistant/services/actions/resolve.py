"""From a draft (what the user said) to a checked plan (what will be done): people, categories, times,
permissions (research R8-R11). Anything ambiguous becomes a question; nothing here writes.
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from dateutil import parser as date_parser
from sqlalchemy import or_
from sqlalchemy.orm import undefer

from indico.core.db import db
from indico.modules.categories import Category
from indico.modules.categories.models.categories import EventCreationMode
from indico.modules.categories.models.principals import CategoryPrincipal
from indico.modules.users.util import search_users

from indico_assistant.default_settings import DEFAULT_SETTINGS
from indico_assistant.services.actions import ACTIONS
from indico_assistant.services.actions.base import category_path, format_dt
from indico_assistant.services.actions.context import local_today, user_timezone
from indico_assistant.services.llm.models.plan import CreateMeeting


DEFAULT_DURATION = 30  # minutes, when neither the meeting nor its talks have one
DEFAULT_SLOT = 20  # Indico's default contribution duration
MAX_CHOICES = 10
ME = {'me', 'i', 'myself', 'us', 'we', 'both of us'}
WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')


@dataclass
class Resolved:
    steps: list = field(default_factory=list)
    summary: str = ''
    questions: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    refusal: str | None = None  # the user cannot do this at all (the reason, as Indico would give it)


def draft_to_plan(draft, user, *, chat_session_id, open_plan=None, settings=None):
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    step = draft.steps[0]
    if isinstance(step, CreateMeeting):
        return _create_meeting(step, user, settings)
    raise NotImplementedError  # ChangeMeeting: T060; Attach: T066; Undo: T076


# --- people (research R8) ------------------------------------------------------------------------------


def find_people(ref):
    """Indico users matching what the user said, as Indico's own user search finds them (RHUserSearch):
    no deleted, blocked or system users; exact matches first; at most 10."""
    if ref.email:
        users = search_users(exact=True, include_pending=True, email=ref.email.strip())
    else:
        users = search_users(include_pending=True, name=ref.name.strip())
    wanted = (ref.name or ref.email or '').strip().lower()
    users = [u for u in users if hasattr(u, 'full_name')]  # (external identities are never searched)
    return sorted(users, key=lambda u: (wanted not in (u.full_name.lower(), u.email.lower()), u.full_name))[:MAX_CHOICES]


def _person_label(user):
    extra = f', {user.affiliation}' if user.affiliation else ''
    return f'{user.full_name} <{user.email}>{extra}'


# --- categories (research R9) ------------------------------------------------------------------------


def creatable_categories(user):
    """Categories where ``user`` may create events, as Indico decides it (``can_create_events``).

    Indico has no helper for this list; candidates come from the user's category permissions (and the
    subcategories of those they fully manage) and from open categories, then Indico's own check filters
    them. ponytail: grants through multipass groups are not candidates; add them if an instance uses them.
    """
    query = Category.query.filter(~Category.is_deleted).options(undefer('chain_titles'))
    if not user.is_admin:
        groups = [g.id for g in user.local_groups]
        roles = [r.id for r in user.category_roles]
        principals = CategoryPrincipal.query.filter(
            or_(CategoryPrincipal.user_id == user.id,
                CategoryPrincipal.local_group_id.in_(groups) if groups else False,
                CategoryPrincipal.category_role_id.in_(roles) if roles else False),
            or_(CategoryPrincipal.full_access, CategoryPrincipal.permissions.any('create'))).all()
        ids = {p.category_id for p in principals}
        if managed := [p.category_id for p in principals if p.full_access]:
            subtree = Category.get_subtree_ids_cte(managed)
            ids |= {row.id for row in db.session.query(subtree.c.id)}
        query = query.filter(or_(Category.id.in_(ids), Category.event_creation_mode == EventCreationMode.open))
    return sorted((c for c in query if c.can_create_events(user)), key=category_path)


def _match_category(name, categories):
    wanted = name.strip().lower()
    exact = [c for c in categories if wanted in (c.title.lower(), category_path(c).lower())]
    return exact or [c for c in categories if wanted in category_path(c).lower()]


# --- times (research R11) ----------------------------------------------------------------------------


def resolve_date(text, today):
    said = (text or 'today').strip().lower()
    if said == 'today':
        return today
    if said == 'tomorrow':
        return today + timedelta(days=1)
    for index, day in enumerate(WEEKDAYS):
        if said in (day, f'this {day}', f'next {day}', f'on {day}'):
            ahead = (index - today.weekday()) % 7
            return today + timedelta(days=ahead or 7)  # "Monday" on a Monday means next week's
    try:
        return date_parser.parse(said, default=datetime.combine(today, time())).date()
    except (ValueError, OverflowError):
        return None


def resolve_time(text):
    if not text:
        return None
    try:
        return date_parser.parse(text.strip(), default=datetime(2000, 1, 1)).time()
    except (ValueError, OverflowError):
        return None


# --- a new meeting -----------------------------------------------------------------------------------


def _create_meeting(step, user, settings):
    from indico_assistant.services.actions.teams import teams_plugin, tenant_email

    categories = creatable_categories(user)
    if not categories:
        return Resolved(refusal='You cannot create events in any category of this Indico. A category manager '
                                'can give you that right.')
    questions, notes = [], []

    # who
    resolved = {}

    def person(ref):
        key = (ref.name or ref.email or '').strip().lower()
        if key in ME:
            return user
        if key not in resolved:
            matches = find_people(ref)
            resolved[key] = matches[0] if len(matches) == 1 else None
            if len(matches) > 1:
                questions.append({'id': f'person:{key}', 'kind': 'choice', 'text': f'Which {ref.name or ref.email}?',
                                  'choices': [{'value': u.email, 'label': _person_label(u), 'note': None}
                                              for u in matches]})
            elif not matches:
                questions.append({'id': f'person:{key}', 'kind': 'text',
                                  'text': f'I could not find “{ref.name or ref.email}” in Indico. Give their full '
                                          f'name and email to add them as a guest speaker, or another name.'})
        return resolved[key]

    invitees = [p for p in (person(ref) for ref in step.people) if p is not None and p != user]
    slots = [(slot, person(slot.speaker) if slot.speaker else None) for slot in step.slots]
    if slots and not any(speaker for _, speaker in slots) and len(slots) == 1 + len(invitees):
        # ponytail: models sometimes drop the speakers of "a slot for each of us"; one slot per person, the
        # user first, is what was asked. The plan shows the speakers before anything is confirmed.
        slots = [(slot, who) for (slot, _), who in zip(slots, [user, *invitees])]

    # where
    category = None
    if step.category:
        matches = _match_category(step.category, categories)
        category = matches[0] if len(matches) == 1 else None
        if category is None:
            questions.append(_category_question(matches or categories,
                                                f'Which category did you mean by “{step.category}”?'))
    else:
        questions.append(_category_question(categories, 'Which category should the meeting go in?'))

    # when
    tz = user_timezone(user)
    day = resolve_date(step.when.date, local_today(user))
    at = resolve_time(step.when.time)
    if day is None:
        questions.append({'id': 'date', 'kind': 'text', 'text': f'Which day is “{step.when.date}”?'})
    if at is None:
        questions.append({'id': 'time', 'kind': 'text', 'text': 'What time should it start?'})
    slot_minutes = [slot.duration_minutes or DEFAULT_SLOT for slot, _ in slots]
    minutes = step.when.duration_minutes or sum(slot_minutes) or DEFAULT_DURATION
    if sum(slot_minutes) > minutes:
        notes.append(f'The meeting is extended to {sum(slot_minutes)} minutes to fit its talks.')
        minutes = sum(slot_minutes)
    elif not step.when.duration_minutes and not slots:
        notes.append(f'It lasts {DEFAULT_DURATION} minutes; say so if it should be longer.')
    start = tz.localize(datetime.combine(day, at)) if day and at else None

    others = [*invitees, *(s for _, s in slots if s and s != user and s not in invitees)]
    title = step.title or _default_title(others, user)
    steps = [_step(1, 'create_event', {
        'category_id': category.id if category else None, 'title': title, 'description': step.description or '',
        'start_dt': start, 'end_dt': start + timedelta(minutes=minutes) if start else None, 'timezone': tz.zone,
    })]
    offset = 0
    for (slot, speaker), length in zip(slots, slot_minutes):
        steps.append(_step(len(steps) + 1, 'add_contribution', {
            'title': slot.title or (speaker.full_name if speaker else 'Talk'),
            'start_dt': start + timedelta(minutes=offset) if start else None, 'duration_minutes': length,
            'speakers': [{'user_id': speaker.id}] if speaker else [],
        }, refs={'event_id': '$1'}))
        offset += length
    speaker_ids = {speaker.id for _, speaker in slots if speaker}
    reminder_to = sorted(u.email for u in invitees if u.id not in speaker_ids)
    if speaker_ids or reminder_to:
        steps.append(_step(len(steps) + 1, 'add_reminder', {
            'minutes_before': settings['actions_reminder_minutes'], 'recipients': reminder_to, 'send_to_speakers': bool(speaker_ids),
        }, refs={'event_id': '$1'}))
    if step.teams:
        if teams_plugin() is None:
            notes.append('Microsoft Teams is not available on this Indico, so the meeting has no Teams room.')
        else:
            everyone = [user, *others]
            with_account = [u for u in everyone if tenant_email(u)]
            if without := [u.full_name for u in everyone if u not in with_account]:
                notes.append(f'{", ".join(without)} will not get a Teams invitation (no Microsoft 365 account); '
                             f'the reminder and the event page have the link.')
            steps.append(_step(len(steps) + 1, 'add_teams_room', {
                'name': title, 'coorganizer_ids': [u.id for u in with_account],
            }, refs={'event_id': '$1'}))

    _describe(steps)
    when = f', {format_dt(start, tz)}' if start else ''
    where = f' in {category_path(category)}' if category else ''
    kind = 'Teams meeting' if step.teams and teams_plugin() else 'meeting'
    summary = ' '.join([f'Create the {kind} “{title}”{when}{where}.', *notes])
    return Resolved(steps=steps, summary=summary, questions=questions)


def _category_question(categories, text):
    return {'id': 'category', 'kind': 'choice', 'text': text,
            'choices': [{'value': str(c.id), 'label': category_path(c), 'note': None} for c in categories[:MAX_CHOICES]]}


def _default_title(invitees, user):
    if invitees:
        return 'Sync with ' + ', '.join(u.first_name or u.full_name for u in invitees[:3])
    return f'Meeting of {user.first_name or user.full_name}'


def _step(n, action, args, refs=None):
    return {'n': n, 'action': action, 'args': args, 'refs': refs or {}}


def _describe(steps):
    """Plain-language descriptions for the plan; complete steps are validated and stored as JSON."""
    for step in steps:
        action = ACTIONS[step['action']]
        args = {**step['args'], **{name: 0 for name in step['refs']}}  # (refs are filled at execution)
        try:
            validated = action.Args.model_validate(args)
        except ValueError:
            step['description'] = f'{step["action"].replace("_", " ").capitalize()} (once the questions are answered)'
            step['side_effects'] = []
            step['args'] = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in step['args'].items()}
            continue
        step['description'], step['side_effects'] = action.describe(validated)
        step['args'] = validated.model_dump(mode='json', exclude=set(step['refs']))
