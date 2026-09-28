"""LOCAL DEV ONLY (spec 020 SC-006): 100 conversations for user 1 titled "SC006 seed NNN", over 30 days.
   python seed_sc006.py          # seed
   python seed_sc006.py count
   python seed_sc006.py delete   # remove exactly those (counted first)"""
import sys
from datetime import timedelta
from indico.web.flask.app import make_app
app = make_app()
with app.app_context():
    from indico.core.db import db
    from indico.util.date_time import now_utc
    from indico_assistant.models import ChatMessage, ChatSession
    if sys.argv[1:] == ['count']:
        print(ChatSession.query.filter(ChatSession.title.like('SC006 seed %')).count())
        sys.exit()
    if sys.argv[1:] == ['delete']:
        rows = ChatSession.query.filter(ChatSession.title.like('SC006 seed %'))
        print('deleting', rows.count())
        for chat in rows:
            db.session.delete(chat)
        db.session.commit()
        sys.exit()
    for n in range(100):
        when = now_utc() - timedelta(hours=7 * n + 1)  # 100 over ~29 days
        chat = ChatSession(user_id=1, title=f'SC006 seed {n:03d}')
        db.session.add(chat)
        db.session.flush()
        db.session.add_all([ChatMessage(session_id=chat.id, role='user', content=f'Seeded question number {n}', created_at=when),
                            ChatMessage(session_id=chat.id, role='assistant', content=f'Seeded answer number {n}',
                                        created_at=when + timedelta(seconds=5))])
        db.session.flush()
        chat.created_at = chat.updated_at = when
    db.session.commit()
    print('seeded', ChatSession.query.filter(ChatSession.title.like('SC006 seed %')).count())
