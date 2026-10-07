"""Registrations as Indico shows them to the user (spec 025 story 4, T070, FR-031)."""

import pytest
from indico.core.db import db
from indico.modules.events.registration.models.forms import RegistrationForm
from indico.modules.events.registration.models.registrations import PublishRegistrationsMode, RegistrationVisibility
from indico.modules.events.registration.util import create_personal_data_fields, create_registration

from indico_assistant.services.actions.context import acting_as
from indico_assistant.services.lookups import registrations


@pytest.fixture
def workshop(db, world):
    form = RegistrationForm(
        event=world.sync,
        title="Registration",
        currency="EUR",
        publish_registrations_public=PublishRegistrationsMode.show_with_consent,
        publish_registrations_participants=PublishRegistrationsMode.show_all,
    )
    create_personal_data_fields(form)
    for field in form.sections[0].fields:
        field.is_enabled = True
    db.session.add(form)
    db.session.flush()
    for first, last, consent in (
        ("Jamie", "Lee", "all"),
        ("Rosa", "Partner", "participants"),
        ("Quinn", "Quiet", "nobody"),
    ):
        create_registration(
            form,
            {
                "first_name": first,
                "last_name": last,
                "email": f"{first.lower()}@example.test",
                "affiliation": "Nothing Labs",
                "consent_to_publish": RegistrationVisibility[consent],
            },
            management=False,
            notify_user=False,
        )
    db.session.flush()
    return form


def names(found):
    return sorted(
        r.get("Name") or r.get("name") or " ".join(v for k, v in r.items() if k in ("First Name", "Last Name"))
        for t in found.get("tables", [])
        for r in t["rows"]
    )


def test_a_manager_sees_the_management_list(world, workshop):
    with acting_as(world.manager):
        found = registrations.registrations(world.manager, world.sync)
    assert found["view"] == "manager" and found["count"] == 3
    assert sorted(r["name"] for r in found["registrations"]) == ["Jamie Lee", "Quinn Quiet", "Rosa Partner"]
    assert all(r["email"].endswith("@example.test") and r["state"] == "complete" for r in found["registrations"])


@pytest.mark.parametrize("merged", [True, False])  # (Indico's merged list, or one table per form)
def test_a_non_manager_sees_exactly_the_published_list(world, workshop, merged):
    from indico.modules.events.registration import registration_settings

    registration_settings.set(world.sync, "merge_registration_forms", merged)
    with acting_as(world.nora):
        found = registrations.registrations(world.nora, world.sync)
    assert found["view"] == "published" and found["published"] and found["shown"] == 1
    rows = [r for t in found["tables"] for r in t["rows"]]
    assert len(rows) == 1 and "Jamie" in " ".join(str(v) for v in rows[0].values())  # (consent "all" only)
    assert all("email" not in k.lower() for r in rows for k in r)  # (the columns Indico shows, by default no email)
    assert not any("Quinn" in str(r) for r in rows)


def test_a_hidden_list_shows_nothing(world, workshop):
    workshop.publish_registrations_public = PublishRegistrationsMode.hide_all
    db.session.flush()
    with acting_as(world.nora):
        found = registrations.registrations(world.nora, world.sync)
    assert found == {"view": "published", "published": False, "note": registrations.NOT_PUBLISHED}
