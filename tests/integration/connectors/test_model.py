"""The connections table (spec 023, T004): one connection per user and service."""

import pytest
from sqlalchemy.exc import IntegrityError

from indico_assistant.models import Connection


def connection(user, **fields):
    return Connection(**{'user_id': user.id, 'service': 'github', 'account_id': 1, 'account_login': 'octo',
                         'access_token': 'ciphertext', 'refresh_token': 'ciphertext', **fields})


def test_a_new_connection_works_and_is_dated(db, create_user):
    row = connection(create_user(20))
    db.session.add(row)
    db.session.flush()
    assert row.needs_renewal is False and row.connected_at is not None and row.last_used_at is None


def test_one_connection_per_user_and_service(db, create_user):
    lucas, makoto = create_user(20), create_user(21)
    db.session.add_all([connection(lucas), connection(makoto)])  # (the same GitHub account may be connected twice)
    db.session.flush()
    with pytest.raises(IntegrityError), db.session.begin_nested():
        db.session.add(connection(lucas))
        db.session.flush()
