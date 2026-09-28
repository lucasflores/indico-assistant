"""From a draft (what the user said) to a checked plan (what will be done): people, categories, times,
permissions (research R8-R11). Anything ambiguous becomes a question; nothing here writes.
"""

import difflib
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from dateutil import parser as date_parser
from sqlalchemy import func, or_
from sqlalchemy.orm import undefer

from indico.core.config import config
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
from indico_assistant.services.llm.models.plan import Attach, ChangeMeeting, CreateMeeting


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
    if isinstance(step, ChangeMeeting):
        return _change_meeting(step, user, settings, chat_session_id)
    if isinstance(step, Attach):
        return _attach(step, user, chat_session_id)
    raise NotImplementedError  # Undo: T076


# --- people (research R8) ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Guest:
    """Someone who is not an Indico user, given by name and email: a guest speaker or invitee (FR-014)."""
    first_name: str
    last_name: str
    email: str
    id = None

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    @classmethod
    def from_ref(cls, ref):
        first, _, last = (ref.name or '').strip().rpartition(' ')
        return cls(first_name=first, last_name=last, email=ref.email.strip().lower())


def speaker_args(person):
    return {'user_id': person.id} if person.id is not None else {
        'first_name': person.first_name, 'last_name': person.last_name, 'email': person.email}


def user_search_allowed(user, *, can_create_somewhere=False, event=None):
    """Indico's own rule for who may search users (RHUserSearch / RHUserSearchToken)."""
    return (config.ALLOW_PUBLIC_USER_SEARCH or can_create_somewhere
            or (event is not None and event.can_manage(user)))


def known_people(user):
    """How often each Indico user took part in ``user``'s meetings of the last year (to rank matches)."""
    from indico.modules.users.util import get_linked_events

    counts = {}
    for event in list(get_linked_events(user, dt=now_utc() - timedelta(days=365)))[:50]:
        people = {link.person.user_id for link in event.person_links}
        people |= {link.person.user_id for c in event.contributions for link in c.person_links}
        people |= {entry.user_id for entry in event.acl_entries if entry.user_id}
        for user_id in people - {None, user.id}:
            counts[user_id] = counts.get(user_id, 0) + 1
    return counts


def _chat_mentions(user, candidates):
    """How often each candidate's name comes up in ``user``'s own chats (never anyone else's, FR-016)."""
    from indico_assistant.models import ChatMessage, ChatSession

    mine = ChatMessage.query.join(ChatSession).filter(ChatSession.user_id == user.id)
    return {c.id: mine.filter(func.lower(ChatMessage.content).contains(c.full_name.lower(), autoescape=True)).count()
            for c in candidates}


def find_people(ref, user=None, known=None):
    """Indico users matching what the user said, as Indico's own user search finds them (RHUserSearch):
    no deleted, blocked or system users, pending ones included; at most 10. People from the user's
    recent meetings, then people from their own chats, come first; exact matches break ties."""
    if ref.email:
        users = search_users(exact=True, include_pending=True, email=ref.email.strip())
    else:
        users = search_users(include_pending=True, name=ref.name.strip())
    wanted = (ref.name or ref.email or '').strip().lower()
    users = [u for u in users if hasattr(u, 'full_name')]  # (external identities are never searched)
    mentions = _chat_mentions(user, users) if user is not None and len(users) > 1 else {}
    known = known or {}
    return sorted(users, key=lambda u: (-known.get(u.id, 0), -mentions.get(u.id, 0),
                                        wanted not in (u.full_name.lower(), u.email.lower()), u.full_name))[:MAX_CHOICES]


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
    known = None

    def person(ref):
        nonlocal known
        key = (ref.name or ref.email or '').strip().lower()
        if key in ME:
            return user
        if key not in resolved:
            if known is None:
                known = known_people(user)
            matches = find_people(ref, user, known)
            resolved[key] = matches[0] if len(matches) == 1 else None
            if not matches and ref.email and ref.name:
                resolved[key] = Guest.from_ref(ref)  # not an Indico user: a guest (FR-014)
            elif len(matches) > 1:
                questions.append({'id': f'person:{key}', 'kind': 'choice', 'text': f'Which {ref.name or ref.email}?',
                                  'choices': [{'value': u.email, 'label': _person_label(u), 'note': None}
                                              for u in matches]})
            elif not matches:
                questions.append({'id': f'person:{key}', 'kind': 'text',
                                  'text': f'I could not find “{ref.name or ref.email}” in Indico. Give their full '
                                          f'name and email to add them as a guest speaker, or another name.'})
        return resolved[key]

    # (creating somewhere is what lets this user search people, RHUserSearchToken; checked above)
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
    if start and start < now_utc() and not step.when.keep_past:
        questions.append({'id': 'past', 'kind': 'choice', 'text': f'{format_dt(start, tz)} has already passed.',
                          'choices': [{'value': (day + timedelta(days=1)).isoformat(),
                                       'label': f'Tomorrow at {at:%H:%M}', 'note': None},
                                      {'value': 'keep', 'label': 'Keep that time', 'note': None}]})

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
            'speakers': [speaker_args(speaker)] if speaker else [],
        }, refs={'event_id': '$1'}))
        offset += length
    speakers = {speaker.email for _, speaker in slots if speaker}
    reminder_to = sorted(p.email for p in invitees if p.email not in speakers)
    if speakers or reminder_to:
        steps.append(_step(len(steps) + 1, 'add_reminder', {
            'minutes_before': settings['actions_reminder_minutes'], 'recipients': reminder_to,
            'send_to_speakers': bool(speakers),
        }, refs={'event_id': '$1'}))
    if step.teams:
        if teams_plugin() is None:
            notes.append('Microsoft Teams is not available on this Indico, so the meeting has no Teams room.')
        else:
            everyone = [user, *others]
            with_account = [u for u in everyone if u.id is not None and tenant_email(u)]
            if without := [u.full_name for u in everyone if u not in with_account]:
                notes.append(f'{", ".join(without)} will not get a Teams invitation (no Microsoft 365 account); '
                             f'the reminder and the event page have the link.')
            steps.append(_step(len(steps) + 1, 'add_teams_room', {
                'name': title, 'coorganizer_ids': [u.id for u in with_account],
            }, refs={'event_id': '$1'}))

    if start:
        notes.extend(_clashes(user, [user, *(p for p in others if p.id is not None)], start,
                              start + timedelta(minutes=minutes)))
    _describe(steps)
    when = f', {format_dt(start, tz)}' if start else ''
    where = f' in {category_path(category)}' if category else ''
    kind = 'Teams meeting' if step.teams and teams_plugin() else 'meeting'
    verb = 'Propose' if chosen and chosen.propose else 'Create'
    if chosen and chosen.propose:
        notes.insert(0, 'It needs approval by the category\'s managers, and stays unlisted until then.')
    summary = ' '.join([f'{verb} the {kind} “{title}”{when}{where}.', *notes])
    return Resolved(steps=steps, summary=summary, questions=questions)


def _clashes(user, people, start, end):
    """Warnings (never refusals) for people already busy in Indico then (spec edge case "Clash")."""
    from indico.modules.users.util import get_linked_events

    warnings = []
    for person in people:
        for event in get_linked_events(person, dt=start):
            if event.is_deleted or not (event.start_dt < end and start < event.end_dt):
                continue
            who = 'You have' if person == user else f'{person.full_name} has'
            what = f'“{event.title}”' if event.can_access(user) else 'another event'  # never leak a title
            warnings.append(f'Note: {who} {what} at that time.')
            break
    return warnings[:3]


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


# --- changing a meeting (US6) --------------------------------------------------------------------------

IT = {'', 'it', 'this', 'that', 'the meeting', 'this meeting', 'that meeting'}
ORDINALS = {'first': 0, '1st': 0, 'second': 1, '2nd': 1, 'third': 2, '3rd': 2, 'fourth': 3, 'last': -1}


def made_in_chat(chat_session_id, user=None):
    """The meeting the user's latest carried-out plan in this chat created ("it", US6 AS-1)."""
    from indico.modules.events import Event

    from indico_assistant.models import ActionPlan
    if chat_session_id is None:
        return None
    plans = ActionPlan.query.filter_by(session_id=chat_session_id, status='done')
    if user is not None:
        plans = plans.filter_by(user_id=user.id)
    for plan in plans.order_by(ActionPlan.finished_at.desc()):
        for result in plan.result or ():
            if (event_id := (result.get('created') or {}).get('event_id')) is not None:
                if (event := Event.get(event_id, is_deleted=False)) is not None:
                    return event
    return None


def managed_meetings(user):
    """Meetings the user manages, from a month ago onwards, soonest first."""
    from indico.modules.users.util import get_linked_events

    events = [e for e in get_linked_events(user, dt=now_utc() - timedelta(days=30))
              if not e.is_deleted and e.can_manage(user)]
    return sorted(events, key=lambda e: e.start_dt)


def _event_label(event, tz):
    return f'{event.title} ({format_dt(event.start_dt, tz)})'


def find_meeting(name, user, chat_session_id):
    """(event, question): the meeting the user means, or a question listing the candidates."""
    from indico.modules.events import Event

    tz = user_timezone(user)
    said = (name or '').strip().lower()
    if said.startswith('#') and said[1:].isdigit():  # an answer to the "which meeting?" question
        return Event.get(int(said[1:]), is_deleted=False), None
    here = made_in_chat(chat_session_id, user)
    if here is not None and (said in IT or said in here.title.lower()):
        return here, None  # the meeting made in this chat wins over others with the same name
    candidates = managed_meetings(user)
    if said not in IT:
        matching = [e for e in candidates if said in e.title.lower()]
        if not matching:
            close = difflib.get_close_matches(said, [e.title.lower() for e in candidates], n=MAX_CHOICES, cutoff=0.6)
            matching = [e for e in candidates if e.title.lower() in close]
            candidates = matching
        elif len(matching) == 1:
            return matching[0], None
        else:
            candidates = matching
    if not candidates:
        return None, None
    return None, {'id': 'event', 'kind': 'choice', 'text': 'Which meeting?',
                  'choices': [{'value': f'#{e.id}', 'label': _event_label(e, tz), 'note': None}
                              for e in candidates[:MAX_CHOICES]]}


def _talk(which, talks):
    said = which.strip().lower()
    if said in ORDINALS:
        index = ORDINALS[said]
        return talks[index] if -len(talks) <= index < len(talks) else None
    if said.isdigit() and 0 < int(said) <= len(talks):
        return talks[int(said) - 1]
    matching = [t for t in talks if said in t.title.lower()
                or any(said in link.full_name.lower() for link in t.person_links)]
    return matching[0] if len(matching) == 1 else None


def _change_meeting(step, user, settings, chat_session_id):
    event, question = find_meeting(step.meeting, user, chat_session_id)
    if question:
        return Resolved(summary='Which meeting do you want to change?', questions=[question])
    if event is None:
        return Resolved(refusal=f'I could not find a meeting called “{step.meeting}” that you manage.')
    if not event.can_manage(user):
        return Resolved(refusal=f'You cannot manage “{event.title}”, so I cannot change it.')  # US6 AS-2

    tz = user_timezone(user)
    questions, notes, steps = [], [], []
    start, end = event.start_dt, event.end_dt
    change = {}
    if step.move_to:
        day = (resolve_date(step.move_to.date, local_today(user)) if step.move_to.date
               else event.start_dt.astimezone(tz).date())
        at = resolve_time(step.move_to.time) or event.start_dt.astimezone(tz).time()
        start = tz.localize(datetime.combine(day, at))
        end = start + (timedelta(minutes=step.move_to.duration_minutes) if step.move_to.duration_minutes
                       else event.end_dt - event.start_dt)
        if start < now_utc() and not step.move_to.keep_past:
            questions.append({'id': 'past', 'kind': 'choice', 'text': f'{format_dt(start, tz)} has already passed.',
                              'choices': [{'value': (day + timedelta(days=1)).isoformat(),
                                           'label': f'Tomorrow at {at:%H:%M}', 'note': None},
                                          {'value': 'keep', 'label': 'Keep that time', 'note': None}]})
        if (start, end) != (event.start_dt, event.end_dt):
            change.update(start_dt=start, end_dt=end)
    if step.title:
        change['title'] = step.title
    if step.description:
        change['description'] = step.description
    if change:
        steps.append(_step(1, 'update_event', {'event_id': event.id, **change}))

    shift = start - event.start_dt
    talks = sorted((c for c in event.contributions if c.is_scheduled), key=lambda c: c.start_dt)
    resolved = {}

    def person(ref):
        key = (ref.name or ref.email or '').strip().lower()
        if key in ME:
            return user
        if key not in resolved:
            matches = find_people(ref, user, known_people(user))
            resolved[key] = matches[0] if len(matches) == 1 else (
                Guest.from_ref(ref) if not matches and ref.email and ref.name else None)
            if resolved[key] is None:
                questions.append({'id': f'person:{key}', 'kind': 'text',
                                  'text': f'Who is “{ref.name or ref.email}”? Give their full name and email.'})
        return resolved[key]

    for change_ in step.change_slots:
        talk = _talk(change_.which, talks)
        if talk is None:
            questions.append({'id': f'talk:{change_.which}', 'kind': 'choice',
                              'text': f'Which talk is “{change_.which}”?',
                              'choices': [{'value': t.title, 'label': t.title, 'note': None} for t in talks]})
            continue
        args = {'contribution_id': talk.id}
        if change_.title:
            args['title'] = change_.title
        if change_.duration_minutes:
            args['duration_minutes'] = change_.duration_minutes
        if change_.speaker and (who := person(change_.speaker)) is not None:
            args['speakers'] = [speaker_args(who)]
        if change_.move_to and (at := resolve_time(change_.move_to.time)):
            args['start_dt'] = tz.localize(datetime.combine(start.astimezone(tz).date(), at))
        steps.append(_step(len(steps) + 1, 'update_contribution', args))

    after = max([t.end_dt for t in talks] + [event.start_dt]) + shift
    for slot in step.add_slots:
        length = slot.duration_minutes or DEFAULT_SLOT
        speaker = person(slot.speaker) if slot.speaker else None
        steps.append(_step(len(steps) + 1, 'add_contribution', {
            'event_id': event.id, 'title': slot.title or (speaker.full_name if speaker else 'Talk'),
            'start_dt': after, 'duration_minutes': length, 'speakers': [speaker_args(speaker)] if speaker else [],
        }))
        after += timedelta(minutes=length)
    if after > end:
        notes.append(f'The meeting is extended to end at {after.astimezone(tz):%H:%M} to fit the new talks.')

    if not steps and not questions:
        return Resolved(refusal='I did not find anything to change. What should be different?')
    if change.get('start_dt'):
        notes.extend(_clashes(user, [user], start, end))
    _describe(steps)
    return Resolved(steps=steps, questions=questions,
                    summary=' '.join([f'Change the meeting “{event.title}” ({format_dt(event.start_dt, tz)}).', *notes]))


# --- attaching material (US9) --------------------------------------------------------------------------

TALK_WORDS = ('contribution', 'talk', 'presentation', 'slot', 'slides')


def chat_uploads(chat_session_id, user):
    """The files of the latest message with uploads in this chat, still usable by the user."""
    from indico_assistant.models import ChatMessage
    from indico_assistant.services.actions.uploads import usable_upload

    if chat_session_id is None:
        return []
    messages = (ChatMessage.query.filter_by(session_id=chat_session_id, role='user')
                .order_by(ChatMessage.created_at.desc()))
    for message in messages:
        if uploads := (message.metadata_json or {}).get('uploads'):
            return [f for f in (usable_upload(u['uuid'], user) for u in uploads) if f is not None]
    return []


def my_talks(user, event=None):
    """Talks where ``user`` is a speaker (in ``event``, else in their meetings from a month ago on)."""
    from indico.modules.events.contributions.models.contributions import Contribution
    from indico.modules.events.contributions.models.persons import ContributionPersonLink
    from indico.modules.events.models.persons import EventPerson

    query = (Contribution.query.filter(~Contribution.is_deleted)
             .join(ContributionPersonLink).join(EventPerson)
             .filter(EventPerson.user_id == user.id, ContributionPersonLink.is_speaker))
    if event is not None:
        query = query.filter(Contribution.event_id == event.id)
    talks = [c for c in query if not c.event.is_deleted and c.event.end_dt > now_utc() - timedelta(days=30)]
    return sorted(talks, key=lambda c: (c.start_dt or c.event.start_dt))


def _attach(step, user, chat_session_id):
    tz = user_timezone(user)
    wanted = step.target.strip().lower()
    wants_talk = any(word in wanted for word in TALK_WORDS)
    here = made_in_chat(chat_session_id, user)
    questions = []
    target = None
    if wants_talk:
        talks = my_talks(user, here) or my_talks(user)
        if len(talks) == 1:
            target = ('contribution', talks[0])
        elif talks:
            questions.append({'id': 'talk_target', 'kind': 'choice', 'text': 'Which talk?',
                              'choices': [{'value': f'#c{t.id}', 'label': f'{t.title} ({_event_label(t.event, tz)})',
                                           'note': None} for t in talks[:MAX_CHOICES]]})
        else:
            return Resolved(refusal='I could not find a talk where you are a speaker.')
    elif wanted.startswith('#c') and wanted[2:].isdigit():
        from indico.modules.events.contributions.models.contributions import Contribution
        target = ('contribution', Contribution.get(int(wanted[2:]), is_deleted=False))
    else:
        name = wanted.removeprefix('the ').removesuffix(' meeting') if wanted not in IT else wanted
        event, question = find_meeting(name, user, chat_session_id)
        if question:
            questions.append(question)
        elif event is None:
            return Resolved(refusal=f'I could not find the meeting “{step.target}”.')
        else:
            target = ('event', event)

    files = chat_uploads(chat_session_id, user) if step.upload or not step.url else []
    if not files and not step.url:
        return Resolved(refusal='I did not find a file to attach. Send it in the chat together with your message.')
    steps = []
    if target is not None:
        kind, obj = target
        for file in files:
            steps.append(_step(len(steps) + 1, 'attach_file', {'target_type': kind, 'target_id': obj.id,
                                                               'upload_uuid': str(file.uuid), 'title': step.title}))
        if step.url:
            steps.append(_step(len(steps) + 1, 'attach_link', {'target_type': kind, 'target_id': obj.id,
                                                               'url': step.url, 'title': step.title}))
        for s in steps:  # the material page's own check, before anything is shown (US9 AS-2)
            action = ACTIONS[s['action']]
            if reason := action.check(user, action.Args.model_validate(s['args'])):
                return Resolved(refusal=reason)
    _describe(steps)
    what = ', '.join(f.filename for f in files) or step.url
    where = f' to “{target[1].title}”' if target else ''
    return Resolved(steps=steps, questions=questions, summary=f'Attach {what}{where}.')
