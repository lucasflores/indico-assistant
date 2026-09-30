"""The issue_reports table (spec 021, T002): defaults and the database's own checks."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from indico_assistant.models import IssueReport


def report(user, **fields):
    return IssueReport(**{'user_id': user.id, 'form_key': uuid4(), 'category': 'bug', 'text': 'It broke.', **fields})


def test_a_new_report_is_open_and_empty(db, create_user):
    row = report(create_user(20))
    db.session.add(row)
    db.session.flush()
    assert row.status == 'open' and row.created_at is not None and isinstance(row.id, int)
    assert (row.note, row.updated_by_id, row.updated_at, row.closed_at, row.copy) == (None, None, None, None, None)


@pytest.mark.parametrize('field', [{'category': 'rant'}, {'status': 'wontfix'}])
def test_the_database_refuses_an_unknown_category_or_status(db, create_user, field):
    with pytest.raises(IntegrityError), db.session.begin_nested():
        db.session.add(report(create_user(20), **field))
        db.session.flush()


def test_one_report_per_form_and_user(db, create_user):
    lucas, makoto = create_user(20), create_user(21)
    key = uuid4()
    db.session.add_all([report(lucas, form_key=key), report(makoto, form_key=key)])  # another user's key is theirs
    db.session.flush()
    with pytest.raises(IntegrityError), db.session.begin_nested():
        db.session.add(report(lucas, form_key=key))
        db.session.flush()
