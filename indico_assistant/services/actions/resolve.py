"""From a draft (what the user said) to a checked plan (what will be done): people, categories, times,
permissions (research R8-R11). Anything ambiguous becomes a question; nothing here writes.
"""

import difflib
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from dateutil import parser as date_parser
from sqlalchemy import or_
from sqlalchemy.orm import undefer

from indico.core.db import db
from indico.modules.categories import Category
from indico.modules.categories.models.categories import EventCreationMode
from indico.core.db.sqlalchemy.principals import PrincipalType
from indico.modules.categories.models.principals import CategoryPrincipal
from indico.modules.categories.util import can_create_unlisted_events
from indico.modules.users.util import search_users
from indico.util.date_time import now_utc

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


def draft_to_plan(draft, user, *, chat_session_id, open_plan=None, settings=None, topic=''):
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    step = draft.steps[0]
    if isinstance(step, CreateMeeting):
        return _create_meeting(step, user, settings, topic or step.title or '')
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


def _candidates(user, permission, modes):
    """Categories where ``user`` might be allowed ``permission``, to be filtered with Indico's own check.

    Indico has no helper for this list; candidates come from the user's category permissions (and the
    subcategories of those they fully manage) and from categories whose mode allows it to everyone.
    ponytail: grants through multipass groups are not candidates; add them if an instance uses them.
    """
    query = Category.query.filter(~Category.is_deleted).options(undefer('chain_titles'))
    if user.is_admin:
        return query
    groups = [g.id for g in user.local_groups]
    roles = [r.id for r in user.category_roles]
    principals = CategoryPrincipal.query.filter(
        or_(CategoryPrincipal.user_id == user.id,
            CategoryPrincipal.local_group_id.in_(groups) if groups else False,
            CategoryPrincipal.category_role_id.in_(roles) if roles else False),
        or_(CategoryPrincipal.full_access, CategoryPrincipal.permissions.any(permission))).all()
    ids = {p.category_id for p in principals}
    if managed := [p.category_id for p in principals if p.full_access]:
        subtree = Category.get_subtree_ids_cte(managed)
        ids |= {row.id for row in db.session.query(subtree.c.id)}
    return query.filter(or_(Category.id.in_(ids), Category.event_creation_mode.in_(modes)))


def creatable_categories(user):
    """Categories where ``user`` may create events, as Indico decides it (``can_create_events``)."""
    candidates = _candidates(user, 'create', [EventCreationMode.open])
    return sorted((c for c in candidates if c.can_create_events(user)), key=category_path)


def proposable_categories(user):
    """Categories where ``user`` may only propose events (``can_propose_events``, research R4)."""
    candidates = _candidates(user, 'event_move_request', [EventCreationMode.moderated])
    return sorted((c for c in candidates if c.can_propose_events(user) and not c.can_create_events(user)),
                  key=category_path)


@dataclass(eq=False)  # (options are de-duplicated by identity)
class CategoryOption:
    category: Category
    propose: bool = False
    reason: str | None = None


def _embed(texts):
    """Sentence embeddings with the plugin's local model, or None when it is not available."""
    try:
        from indico_assistant.plugin import AssistantPlugin
        from indico_assistant.services.embedding import EmbeddingService
        return EmbeddingService(AssistantPlugin.instance).embed_batch(texts)
    except Exception:
        return None


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm = (sum(x * x for x in a) * sum(y * y for y in b)) ** 0.5
    return dot / norm if norm else 0.0


TOPIC_MATCH = 0.6  # similarity above which a past meeting counts as "on the same topic"


def category_options(user, topic=''):
    """Where ``user`` can put a meeting, most relevant first (FR-013): categories holding more of their
    meetings of the last year first, then the one whose past meeting is most like this request."""
    from indico.modules.users.util import get_linked_events

    create = creatable_categories(user)
    propose = proposable_categories(user) if can_create_unlisted_events(user) else []
    mine = {}
    for event in get_linked_events(user, dt=now_utc() - timedelta(days=365)):
        if not event.is_deleted and event.category_id is not None:
            mine.setdefault(event.category_id, []).append(event.title)
    similar = {}
    if topic and (titles := sorted({t for ts in mine.values() for t in ts})):
        if (vectors := _embed([topic, *titles])) is not None:
            scores = {t: _cosine(vectors[0], v) for t, v in zip(titles, vectors[1:])}
            for category_id, ts in mine.items():
                best = max(ts, key=scores.get)
                if scores[best] >= TOPIC_MATCH:
                    similar[category_id] = (scores[best], best)
    options = [CategoryOption(c) for c in create] + [CategoryOption(c, propose=True) for c in propose]
    options.sort(key=lambda o: (-len(mine.get(o.category.id, ())), -similar.get(o.category.id, (0, ''))[0],
                                o.propose, category_path(o.category)))
    if options and (count := len(mine.get(options[0].category.id, ()))):
        reason = f'{count} of your meetings in the last year {"is" if count == 1 else "are"} here'
        if like := similar.get(options[0].category.id):
            reason += f', like “{like[1]}”'
        options[0].reason = reason
    return options


def _match_category(name, options):
    """(options, certain): certain only for a name that is in the category's title or path; a spelling
    that is merely close is offered back, never picked (US3 AS-3)."""
    wanted = name.strip().lower()
    paths = {category_path(o.category).lower(): o for o in options}
    exact = [o for o in options if wanted in (o.category.title.lower(), category_path(o.category).lower())]
    if exact:
        return exact, True
    if partial := [o for p, o in paths.items() if wanted in p]:
        return partial, True
    titles = {o.category.title.lower(): o for o in options}
    close = difflib.get_close_matches(wanted, list(titles) + list(paths), n=MAX_CHOICES, cutoff=0.6)
    return list(dict.fromkeys(titles.get(c) or paths[c] for c in close)), False


def _who_to_ask():
    """The managers of the top category (who can grant creation rights), else the admins."""
    root = Category.get_root()
    managers = sorted({entry.principal for entry in root.acl_entries
                       if entry.full_access and entry.type == PrincipalType.user}, key=lambda u: u.full_name)
    if managers:
        return ', '.join(f'{u.full_name} <{u.email}>' for u in managers[:3])
    return 'an Indico administrator'


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


def _create_meeting(step, user, settings, topic):
    from indico_assistant.services.actions.teams import teams_plugin, tenant_email

    options = category_options(user, topic)
    if not options:
        if blocked := proposable_categories(user):
            where = ', '.join(category_path(c) for c in blocked[:3])
            return Resolved(refusal=f'You can only propose events in {where}, and proposing needs unlisted events, '
                                    f'which are not enabled for you on this Indico. Ask {_who_to_ask()}.')
        return Resolved(refusal=f'You cannot create events in any category of this Indico. To get that right, ask '
                                f'{_who_to_ask()}.')
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
    chosen = None
    if step.category:
        matches, certain = _match_category(step.category, options)
        chosen = matches[0] if certain and len(matches) == 1 else None
        if chosen is None:
            questions.append(_category_question(matches or options,
                                                f'Which category did you mean by “{step.category}”?'))
    else:
        questions.append(_category_question(options, 'Which category should the meeting go in?'))
    category = chosen.category if chosen else None

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
    steps = [_step(1, 'propose_event' if chosen and chosen.propose else 'create_event', {
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
    verb = 'Propose' if chosen and chosen.propose else 'Create'
    if chosen and chosen.propose:
        notes.insert(0, 'It needs approval by the category\'s managers, and stays unlisted until then.')
    summary = ' '.join([f'{verb} the {kind} “{title}”{when}{where}.', *notes])
    return Resolved(steps=steps, summary=summary, questions=questions)


def _category_question(options, text):
    def note(option):
        if option.reason:
            return f'suggested: {option.reason}'
        return 'propose (needs approval)' if option.propose else None
    return {'id': 'category', 'kind': 'choice', 'text': text,
            'choices': [{'value': str(o.category.id), 'label': category_path(o.category), 'note': note(o)}
                        for o in options[:MAX_CHOICES]]}


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
