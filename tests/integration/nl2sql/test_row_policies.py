"""The read-only role's row policies against Indico's own models (the test database, not the live one).

The setup script is applied inside the test transaction and queries switch to the role with SET LOCAL
ROLE, so everything is rolled back with the test. Complements test_readonly_role.py, which checks the
role on a real database but can only use whatever data that database happens to hold.
"""

import pytest
from sqlalchemy import text

from indico.core.db.sqlalchemy.protection import ProtectionMode
from indico.modules.attachments.models.folders import AttachmentFolder
from indico.modules.events.notes.models.notes import EventNote, RenderMode

from indico_assistant.services.nl2sql import readonly_db
from indico_assistant.services.nl2sql.readonly_db import POLICIES, RO_ROLE, QueryContext, setup_sql


pytestmark = pytest.mark.integration

NOBODY = 999999  # a user with no grants anywhere


@pytest.fixture
def ro(db, monkeypatch):
    conn = db.session.connection()
    existing = {}
    for schema, table, column in conn.execute(text(
            'SELECT table_schema, table_name, column_name FROM information_schema.columns')):
        existing.setdefault(f'{schema}.{table}', set()).add(column)
    sql = setup_sql({table: [] for table in POLICIES}, existing, conn.execute(text('SELECT current_user')).scalar())
    conn.exec_driver_sql(sql.replace('BEGIN;', '').replace('COMMIT;', ''))
    secret = conn.execute(text('SELECT secret FROM plugin_assistant.nl2sql_secret')).scalar()
    monkeypatch.setattr(readonly_db, '_get_secret', lambda: secret)

    def query(sql, event_id=None):
        db.session.flush()
        conn.exec_driver_sql(f'SET LOCAL ROLE {RO_ROLE}')
        try:
            conn.execute(text("SELECT set_config('indico_assistant.ctx', :ctx, true)"),
                         {'ctx': readonly_db.sign(QueryContext(NOBODY, event_id, False))})
            return {row[0] for row in conn.execute(text(sql))}
        finally:
            conn.exec_driver_sql('RESET ROLE')
    return query


def test_contribution_inherits_its_sessions_protection(ro, dummy_event, create_session, create_contribution):
    public_session = create_session(dummy_event, 'Open')
    protected_session = create_session(dummy_event, 'Closed', protection_mode=ProtectionMode.protected)
    visible = create_contribution(dummy_event, 'In the open session', session=public_session)
    hidden = create_contribution(dummy_event, 'In the closed session', session=protected_session)
    hidden_folder = AttachmentFolder(object=hidden, title='Slides')

    assert ro('SELECT id FROM events.contributions') == {visible.id}
    assert hidden_folder.id not in ro('SELECT id FROM attachments.folders')


def test_subcontribution_material_follows_its_contribution(ro, dummy_event, dummy_user, create_contribution,
                                                           create_subcontribution):
    public = create_subcontribution(create_contribution(dummy_event, 'Public talk'), 'Part 1')
    protected = create_subcontribution(
        create_contribution(dummy_event, 'Closed talk', protection_mode=ProtectionMode.protected), 'Part 1')
    folders, notes = {}, {}
    for sub in (public, protected):
        folders[sub] = AttachmentFolder(object=sub, title='Slides')
        notes[sub] = EventNote.get_or_create(sub)
        notes[sub].create_revision(RenderMode.markdown, 'Minutes', dummy_user)

    assert ro('SELECT id FROM attachments.folders') == {folders[public].id}
    assert ro('SELECT id FROM events.notes') == {notes[public].id}


def test_events_follow_indicos_protection_modes(ro, create_category, create_event):
    # ProtectionMode: 0 public, 1 inheriting (the default), 2 protected
    closed = create_category(title='Closed', protection_mode=ProtectionMode.protected)
    inside = create_category(title='Inherits from Closed', parent=closed)
    inheriting = create_event(title='Inherits', category=inside)
    public = create_event(title='Public anyway', category=inside, protection_mode=ProtectionMode.public)
    listed = create_event(title='Open')

    visible = ro('SELECT id FROM events.events')
    assert {public.id, listed.id} <= visible and inheriting.id not in visible
    assert ro('SELECT id FROM categories.categories') & {closed.id, inside.id} == set()


def test_unlisted_events_are_not_listed(ro, create_event):
    unlisted = create_event(title='Unlisted', category=None)  # unlisted events always inherit

    assert unlisted.id not in ro('SELECT id FROM events.events')
    # an event-scoped question (already checked with can_access) still sees it
    assert ro('SELECT id FROM events.events', event_id=unlisted.id) == {unlisted.id}


def test_policies_need_their_tables_allowlisted():
    with pytest.raises(ValueError, match='events.sessions'):
        setup_sql({'events.notes': [], 'events.events': [], 'events.contributions': []}, {}, 'indico')
