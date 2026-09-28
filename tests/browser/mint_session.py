"""LOCAL DEV ONLY: an Indico session for a user id, saved through Indico's own session interface, for the
spec 020 browser walk. Needs direct access to the instance config and its cache. Prints the cookie value."""
import sys
from flask import Response
from indico.web.flask.app import make_app
app = make_app()
user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
with app.test_request_context(base_url='http://127.0.0.1:8000'):
    from flask import session
    from indico.modules.users import User
    assert User.get(user_id, is_deleted=False) is not None
    session['_user_id'] = user_id  # (set_session_user memoizes None outside a real request: spec 019 R1)
    session.modified = True
    response = Response()
    app.session_interface.save_session(app, session, response)
    print(session.sid)
