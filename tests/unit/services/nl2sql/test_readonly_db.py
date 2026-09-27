"""The generated setup script quotes what it does not control."""

from indico_assistant.services.nl2sql.readonly_db import setup_sql


def test_indico_role_name_is_quoted():
    """Role names such as indico-web are valid in Postgres but need quoting; unquoted they broke the script."""
    script = setup_sql({'events.events': ['id', 'title']}, {'events.events': {'id', 'title', 'is_deleted'}},
                       'indico-web', password="it's")
    assert 'GRANT SELECT ON plugin_assistant.nl2sql_secret TO "indico-web";' in script
    assert "PASSWORD 'it''s'" in script
    assert setup_sql({}, {}, 'odd"name').count('"odd""name"') == 1
