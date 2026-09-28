"""Chat actions: typed Indico changes the assistant plans and the user confirms (Feature 019).

See specs/019-chat-actions/ (plan.md, research.md). Every write goes through Indico's own operations, after
the permission check of the Indico page that does the same thing by hand.
"""

import re

from indico_assistant.default_settings import WRITE_ACTIONS


MAX_STEPS = 25  # FR-012: bigger requests belong in Indico's timetable

# name -> Action instance; filled by the action modules as they are added
ACTIONS = {}

_REF = re.compile(r'^\$(\d+)(?:\.(\w+))?$')


def enabled_actions(settings):
    """The actions the admin allows (FR-021); none while the master switch is off."""
    if not settings.get('actions_enabled'):
        return frozenset()
    return frozenset(settings.get('actions_allowed') or ()) & frozenset(WRITE_ACTIONS)


def parse_ref(value):
    """``'$1'`` / ``'$1.event_id'`` -> (1, 'event_id' | None), or None if not a reference."""
    if isinstance(value, str) and (m := _REF.match(value)):
        return int(m.group(1)), m.group(2)
    return None


def validate_plan(steps, enabled):
    """The shape rules a plan must pass before it is shown; returns error strings (empty = valid)."""
    if len(steps) > MAX_STEPS:
        return [f'A plan can have at most {MAX_STEPS} steps; use Indico\'s timetable for larger changes']
    errors = []
    seen_external = False
    for step in steps:
        n, name = step['n'], step['action']
        action = ACTIONS.get(name)
        if action is None:
            errors.append(f'Step {n}: unknown action {name}')
            continue
        if name not in enabled:
            errors.append(f'Step {n}: {name} is not available')
        for arg, ref in (step.get('refs') or {}).items():
            parsed = parse_ref(ref)
            if parsed is None or not 1 <= parsed[0] < n:
                errors.append(f'Step {n}: {arg} must refer to an earlier step')
        if action.external:
            seen_external = True
        elif seen_external:
            errors.append(f'Step {n}: steps that call other systems (Teams) must come last')
    return errors
