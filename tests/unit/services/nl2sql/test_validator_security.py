"""Phase 0: bypasses found in the scalability audit must be rejected; normal queries must still pass.

The dedicated read-only database role is the real control; this validator is the first layer.
"""

from pathlib import Path

import pytest
import yaml

from indico_assistant.services.nl2sql.schema import SchemaContext
from indico_assistant.services.nl2sql.validator import SQLValidator


YAML = Path(__file__).parents[4] / 'indico_assistant' / 'config_modules' / 'available_tables.yaml'


@pytest.fixture(scope='module')
def validator():
    return SQLValidator(SchemaContext(str(YAML)))


@pytest.mark.parametrize('sql', [
    "SELECT 1; SET statement_timeout = 0; SELECT pg_sleep(100000)",           # multi-statement, timeout defeat
    "SELECT 1; LOCK TABLE events.events IN ACCESS EXCLUSIVE MODE",             # table lock
    "SELECT pg_terminate_backend(pid) FROM events.events e, pg_stat_activity",  # kill backends
    'SELECT "pg_sleep"(10) FROM events.events',                                # quoted function name
    'SELECT pg_catalog.pg_sleep(10) FROM events.events',                       # schema-qualified
    "SELECT set_config('statement_timeout', '0', false) FROM events.events",   # settings change
    "SELECT pg_advisory_lock(42) FROM events.events",                          # session lock
    "SELECT count(*) FROM events.events a, events.persons b, users.users c",   # comma join to a hidden table
    "SELECT u.email FROM users.users u",                                       # removed table
    "SELECT m.content FROM plugin_assistant.chat_messages m",                  # other users' chats
    "SELECT r.email FROM events.registrations r",                              # registrant data
    "SELECT * FROM information_schema.tables",                                 # catalogs
    "SELECT e.id FROM events.events e FOR UPDATE",                             # row locks
    "SELECT e.id INTO newtable FROM events.events e",                          # SELECT INTO creates a table
    "SELECT e.id FROM events.events e -- ; DROP TABLE x",                      # comments
    "SELECT e.id FROM events.events e WHERE e.title = 'unterminated",          # broken quoting
    "SELECT dblink_exec('host=x', 'drop table y') FROM events.events",         # remote connections
    "SELECT query_to_xml('select * from users.users', true, true, '') FROM events.events",  # SQL from a string
    "SELECT lo_import('/etc/passwd') FROM events.events",                      # file read
])
def test_rejected(validator, sql):
    result = validator.validate(sql)
    assert not result.valid, f'accepted: {sql}'


@pytest.mark.parametrize('sql', [
    "SELECT e.id, e.title FROM events.events e WHERE e.start_dt > now() - interval '7 days' "
    "ORDER BY e.start_dt DESC LIMIT 20;",
    "SELECT e.title FROM events.events e WHERE e.title ILIKE '%; drop table x --%' LIMIT 5",  # tricks inside a literal
    "SELECT c.title, p.first_name, p.last_name FROM events.contributions c "
    "JOIN events.contribution_person_links cpl ON cpl.contribution_id = c.id "
    "JOIN events.persons p ON p.id = cpl.person_id WHERE c.event_id = :event_id LIMIT 50",
    "SELECT e.id FROM events.events e, events.contributions c WHERE c.event_id = e.id LIMIT 5",  # allowed comma join
    "SELECT d.content FROM plugin_assistant.extracted_documents d ORDER BY d.embedding <=> :query_vector LIMIT 10",
])
def test_allowed(validator, sql):
    result = validator.validate(sql)
    assert result.valid, result.violations


def test_allowlist_has_no_personal_or_secret_columns():
    schema = yaml.safe_load(YAML.read_text())
    assert not {'users.users', 'events.registrations', 'events.registration_data'} & schema.keys()
    assert not [t for t in schema if t.startswith('plugin_assistant.') and t != 'plugin_assistant.extracted_documents']
    for table, spec in schema.items():
        bad = {c for c in spec['columns'] if c in {'email', 'phone', 'access_key', 'user_email', 'ip_address'}
               or 'secret' in c or 'notification_emails' in c}
        assert not bad, (table, bad)


def test_missing_allowlist_file_allows_nothing(tmp_path):
    v = SQLValidator(SchemaContext(str(tmp_path / 'missing.yaml')))
    assert not v.validate('SELECT e.id FROM events.events e').valid
