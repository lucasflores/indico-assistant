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

    def query(sql, event_id=None, user_id=NOBODY, admin=False):
        db.session.flush()
        conn.exec_driver_sql(f'SET LOCAL ROLE {RO_ROLE}')
        try:
            conn.execute(text("SELECT set_config('indico_assistant.ctx', :ctx, true)"),
                         {'ctx': readonly_db.sign(QueryContext(user_id, event_id, admin))})
            return {row[0] for row in conn.execute(text(sql))}
        finally:
            conn.exec_driver_sql('RESET ROLE')
    return query


def test_contribution_inherits_its_sessions_protection(ro, dummy_event, create_session, create_contribution):
    public_session = create_session(dummy_event, 'Open')
    protected_session = create_session(dummy_event, 'Closed', protection_mode=ProtectionMode.protected)
    visible = create_contribution(dummy_event, 'In the open session', session=public_session)
    hidden = create_contribution(dummy_event, 'In the closed session', session=protected_session)
    folders = {c: AttachmentFolder(object=c, title='Slides') for c in (visible, hidden)}

    assert ro('SELECT id FROM events.contributions') == {visible.id}
    visible_folders = ro('SELECT id FROM attachments.folders')  # flushes: the folder ids exist from here
    assert folders[visible].id in visible_folders and folders[hidden].id not in visible_folders


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


def test_each_grant_path_makes_protected_events_visible(ro, create_category, create_event, create_user,
                                                       create_group):
    group = create_group(1)
    reader, member, category_reader, manager = (create_user(2001), create_user(2002, groups=[group]),
                                                create_user(2003), create_user(2004))
    closed = create_category(title='Closed', protection_mode=ProtectionMode.protected)
    in_closed = create_event(title='Inherits from Closed', category=closed)
    protected_in_closed = create_event(title='Protected in Closed', category=closed,
                                       protection_mode=ProtectionMode.protected)
    protected = create_event(title='Protected', protection_mode=ProtectionMode.protected)
    protected.update_principal(reader, read_access=True)
    protected.update_principal(group, read_access=True)
    closed.update_principal(category_reader, read_access=True)
    closed.update_principal(manager, full_access=True)

    def events(user_id, admin=False):
        return ro('SELECT id FROM events.events', user_id=user_id, admin=admin) & {
            in_closed.id, protected_in_closed.id, protected.id}

    assert events(NOBODY) == set()
    assert events(reader.id) == {protected.id}  # direct event grant
    assert events(member.id) == {protected.id}  # through a local group
    assert events(category_reader.id) == {in_closed.id}  # category read: inheriting events only
    assert events(manager.id) == {in_closed.id, protected_in_closed.id}  # category managers see all below
    assert events(NOBODY, admin=True) == {in_closed.id, protected_in_closed.id, protected.id}
    assert closed.id in ro('SELECT id FROM categories.categories', user_id=category_reader.id)
    assert closed.id not in ro('SELECT id FROM categories.categories')


def test_unlisted_events_are_not_listed(ro, create_event):
    unlisted = create_event(title='Unlisted', category=None)  # unlisted events always inherit

    assert unlisted.id not in ro('SELECT id FROM events.events')
    # an event-scoped question (already checked with can_access) still sees it
    assert ro('SELECT id FROM events.events', event_id=unlisted.id) == {unlisted.id}


def test_policies_need_their_tables_allowlisted():
    with pytest.raises(ValueError, match='events.sessions'):
        setup_sql({'events.notes': [], 'events.events': [], 'events.contributions': []}, {}, 'indico')
