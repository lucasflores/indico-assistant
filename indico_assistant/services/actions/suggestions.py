"""Suggestions from context (US5; FR-015, FR-016, FR-017): what the user's similar meetings and their own
chats hold (attendees, agenda, material, minutes), offered next to the plan, applied only when accepted.

Everything here goes through Indico's access checks, and only the user's own chats are read. The model sees
it as fenced data and may only suggest what it can point to (``source_ref``); anything else is dropped.
"""

import re
from dataclasses import dataclass, field
from datetime import timedelta
from html import unescape

from indico.util.date_time import now_utc


MAX_MEETINGS = 3
MAX_PAST_CHATS = 2
NOTE_CHARS = 400


@dataclass
class Context:
    text: str = ''
    sources: dict = field(default_factory=dict)  # id -> {'type', 'label', ...}
    attendees: dict = field(default_factory=dict)  # event:<id> -> {name: email}


def _plain(html):
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', html or ''))).strip()


def build_context(user, topic, chat_session_id=None, history=()):
    """The context block for a request about ``topic`` (empty when nothing relevant is found: no filler)."""
    from indico.modules.events.notes.models.notes import EventNote
    from indico.modules.users.util import get_linked_events

    from indico_assistant.models import ChatMessage, ChatSession
    from indico_assistant.services.actions.resolve import TOPIC_MATCH, _cosine, _embed

    context = Context()
    if not topic:
        return context
    lines = []
    if sum(1 for m in history if m.get('role') == 'user') >= 1:
        context.sources['chat'] = {'type': 'chat', 'label': 'this chat'}

    events = [e for e in get_linked_events(user, dt=now_utc() - timedelta(days=365))
              if not e.is_deleted and e.can_access(user)]
    chats = [(s, m) for s in (ChatSession.query.filter(ChatSession.user_id == user.id,
                                                       ChatSession.id != chat_session_id)
                              .order_by(ChatSession.updated_at.desc()).limit(20))
             if (m := s.messages.filter_by(role='user').order_by(ChatMessage.created_at).first())]
    texts = [e.title for e in events] + [m.content[:300] for _, m in chats]
    if not texts or (vectors := _embed([topic, *texts])) is None:
        return context
    scores = [_cosine(vectors[0], v) for v in vectors[1:]]
    similar_events = sorted(((s, e) for s, e in zip(scores, events) if s >= TOPIC_MATCH), key=lambda x: -x[0])
    similar_chats = sorted(((s, c) for s, c in zip(scores[len(events):], chats) if s >= TOPIC_MATCH),
                           key=lambda x: -x[0])

    for _, event in similar_events[:MAX_MEETINGS]:
        key = f'event:{event.id}'
        date = f'{event.start_dt:%d %b %Y}'
        context.sources[key] = {'type': 'event', 'label': f'“{event.title}”, {date}', 'event_id': event.id}
        people = {link.full_name: link.email for link in event.person_links}
        people |= {link.full_name: link.email for c in event.contributions if not c.is_deleted
                   for link in c.person_links if link.is_speaker}
        context.attendees[key] = people
        minutes = int((event.end_dt - event.start_dt).total_seconds() // 60)
        context.sources[key]['minutes'] = minutes
        lines.append(f'[{key}] Meeting “{event.title}” on {date}, {minutes} minutes. '
                     f'People: {", ".join(people) or "none"}. '
                     f'Talks: {", ".join(c.title for c in event.contributions if not c.is_deleted) or "none"}.')
        for folder in event.attachment_folders:
            for attachment in folder.attachments:
                if not attachment.is_deleted and attachment.can_access(user):
                    akey = f'attachment:{attachment.id}'
                    context.sources[akey] = {'type': 'attachment', 'label': f'{attachment.title} from “{event.title}”',
                                             'event_id': event.id, 'attachment_id': attachment.id,
                                             'url': attachment.absolute_download_url}
                    lines.append(f'[{akey}] Material of “{event.title}”: {attachment.title}')
        if (note := EventNote.get_for_linked_object(event)) is not None and note.can_access(user):
            nkey = f'note:{event.id}'
            context.sources[nkey] = {'type': 'note', 'label': f'the minutes of “{event.title}”', 'event_id': event.id}
            lines.append(f'[{nkey}] Minutes of “{event.title}”: {_plain(note.html)[:NOTE_CHARS]}')
    for _, (chat, message) in similar_chats[:MAX_PAST_CHATS]:
        ckey = f'past_chat:{chat.id}'
        context.sources[ckey] = {'type': 'past_chat', 'label': f'your chat of {message.created_at:%d %b}'}
        lines.append(f'[{ckey}] Your earlier chat: {message.content[:300]}')
    context.text = '\n'.join(lines)
    return context


def automatic(context, draft, user=None):
    """Suggestions that need no model: from the most similar past meeting, its material, the people there
    who are not invited yet, and its length when none was given (each with its source)."""
    meetings = [k for k, v in context.sources.items() if v['type'] == 'event']
    if not meetings or not draft.steps:
        return []
    step = draft.steps[0]
    best = meetings[0]  # (most similar first)
    source = context.sources[best]
    named = {(p.name or '').lower() for p in step.people} | {
        (s.speaker.name or '').lower() for s in getattr(step, 'slots', ()) if s.speaker}
    found = []
    for key, item in context.sources.items():
        if item['type'] == 'attachment' and item.get('event_id') == source['event_id']:
            found.append(SuggestionItem('material', item['label'].split(' from ')[0], key))
    for name in context.attendees.get(best, {}):
        if user is not None and name.lower() == user.full_name.lower():
            continue  # not the requester
        if name.lower() not in named and not any(name.lower().startswith(n) for n in named if n):
            found.append(SuggestionItem('person', name, best))
    if getattr(step, 'when', None) is not None and not step.when.duration_minutes and not getattr(step, 'slots', None):
        found.append(SuggestionItem('duration', str(source.get('minutes', '')), best))
    return found


@dataclass
class SuggestionItem:
    """The shape of a model's SuggestionDraft, for suggestions made without the model."""
    kind: str
    content: str
    source_ref: str


def validate(drafts, context):
    """Suggestions the plan can show: each points to a real item of the context, in a form we can apply."""
    suggestions = []
    seen = set()
    for draft in drafts:
        if (draft.kind, draft.content.strip().lower()) in seen:
            continue
        seen.add((draft.kind, draft.content.strip().lower()))
        source = context.sources.get(draft.source_ref)
        if source is None or not draft.content.strip():
            continue  # no source, no suggestion (FR-015)
        suggestion = {'kind': draft.kind, 'content': draft.content.strip(), 'source': source}
        if draft.kind == 'material':
            if source['type'] != 'attachment':
                continue
            suggestion['url'] = source['url']
        elif draft.kind == 'person':
            known = context.attendees.get(f'event:{source.get("event_id")}', {})
            email = next((e for n, e in known.items() if n.lower() == suggestion['content'].lower()), None)
            if not email:
                continue  # only people who were really there
            suggestion['email'] = email
        elif draft.kind == 'duration':
            if not (minutes := re.search(r'\d+', draft.content)):
                continue
            suggestion['minutes'] = int(minutes.group(0))
        suggestions.append(suggestion)
    for n, suggestion in enumerate(suggestions, 1):
        suggestion['id'] = f's{n}'
    return suggestions


def accept(draft, suggestion):
    """``draft`` (a PlanDraft) with ``suggestion`` applied to its meeting."""
    step = draft.steps[0]
    kind, content = suggestion['kind'], suggestion['content']
    if kind == 'title':
        step.title = content
    elif kind == 'description':
        step.description = f'{step.description}\n\n{content}' if step.description else content
    elif kind == 'agenda_item':
        from indico_assistant.services.llm.models.plan import Slot
        step.slots.append(Slot(title=content, duration_minutes=10))
    elif kind == 'person':
        from indico_assistant.services.llm.models.plan import PersonRef
        step.people.append(PersonRef(name=content, email=suggestion['email']))
    elif kind == 'material':
        step.links.append(suggestion['url'])
    elif kind == 'duration':
        step.when.duration_minutes = suggestion['minutes']
    return draft
