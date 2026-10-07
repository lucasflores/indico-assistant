"""Registrations exactly as Indico shows them to the user (FR-031, research R7, clarification 3): managers of the
event's registrations get what the management list holds; everyone else the published participant list, with the
form's visibility, each registrant's consent and the columns Indico shows (``RHParticipantList``)."""

from __future__ import annotations

from typing import Any

from indico.modules.events import Event
from indico.modules.events.registration import registration_settings
from indico.modules.events.registration.models.forms import RegistrationForm
from indico.modules.events.registration.models.items import PersonalDataType
from indico.modules.events.registration.models.registrations import Registration

NOT_PUBLISHED = "The participant list of this event is not published."


def _manager_view(event: Event) -> dict[str, Any]:
    rows = (
        Registration.query.with_parent(event)
        .filter(~Registration.is_deleted, ~RegistrationForm.is_deleted)
        .join(Registration.registration_form)
        .order_by(Registration.submitted_dt)
        .all()
    )
    return {
        "view": "manager",
        "count": len(rows),
        "by_state": {s: sum(1 for r in rows if r.state.name == s) for s in {r.state.name for r in rows}},
        "registrations": [
            {
                "name": r.full_name,
                "email": r.email,
                "affiliation": r.get_personal_data().get("affiliation") or None,
                "state": r.state.name,
                "form": r.registration_form.title,
                "registered": f"{r.submitted_dt:%Y-%m-%d}" if r.submitted_dt else None,
            }
            for r in rows
        ],
    }


def _published_view(event: Event, user: Any) -> dict[str, Any]:
    is_participant = event.is_user_registered(user)
    forms = (
        RegistrationForm.query.with_parent(event)
        .filter(
            RegistrationForm.is_participant_list_visible(is_participant), ~RegistrationForm.participant_list_disabled
        )
        .all()
    )
    if not forms:
        return {"view": "published", "published": False, "note": NOT_PUBLISHED}
    tables = []
    if registration_settings.get(event, "merge_registration_forms"):
        columns = registration_settings.get(event, "participant_list_columns")
        rows = [
            r
            for r in Registration.query.with_parent(event)
            .filter(
                Registration.is_state_publishable,
                ~RegistrationForm.is_deleted,
                ~RegistrationForm.participant_list_disabled,
            )
            .join(Registration.registration_form)
            if r.is_publishable(is_participant)
        ]
        seen: set[tuple[str, ...]] = set()
        listed = []
        for r in rows:
            data = r.get_personal_data()
            values = tuple(str(data.get(c) or "") for c in columns if c != PersonalDataType.picture.name)
            if values not in seen:  # (as Indico de-duplicates the merged list)
                seen.add(values)
                listed.append(
                    dict(zip([c for c in columns if c != PersonalDataType.picture.name], values, strict=True))
                )
        tables.append({"columns": [PersonalDataType[c].get_title() for c in columns], "rows": listed})
    else:
        for form in forms:
            active = {f.id: f for f in form.active_fields}
            column_ids = [c for c in registration_settings.get_participant_list_columns(event, form) if c in active]
            listed = []
            for r in Registration.query.with_parent(form).filter(Registration.is_state_publishable):
                if not r.is_publishable(is_participant):
                    continue
                by_field = r.data_by_field
                row = {}
                for cid in column_ids:
                    field = active[cid]
                    if field.field_impl.name == "picture":
                        continue
                    if cid in by_field:
                        row[field.title] = by_field[cid].get_friendly_data(for_humans=True)
                    elif field.personal_data_type is not None and field.personal_data_type.column is not None:
                        row[field.title] = getattr(r, field.personal_data_type.column)
                listed.append(row)
            tables.append({"form": form.title, "columns": [active[c].title for c in column_ids], "rows": listed})
    shown = sum(len(t["rows"]) for t in tables)
    return {"view": "published", "published": True, "shown": shown, "tables": tables}


def registrations(user: Any, event: Event) -> dict[str, Any]:
    """What this user may see of the event's registrations."""
    if event.can_manage(user, permission="registration"):
        return _manager_view(event)
    return _published_view(event, user)
