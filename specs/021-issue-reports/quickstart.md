# Quickstart: Issue reports from the chat (021)

The code is in the worktree `~/indico-assistant/plugin-c`, branch `021-issue-reports-build`. The shared dev
stack runs `~/indico-assistant/plugin`, so read "Live checks" before touching it.

## Tests (no stack needed)

```bash
cd ~/indico-assistant/plugin-c
~/indico-assistant/instance/env/bin/python -m pytest tests/unit tests/contract -q   # 1207 at 2e52051, plus 021's
cd chainlit_app && ~/indico-assistant/plugin/chainlit_app/.venv/bin/python -m pytest -q  # the Chainlit side
```

Use `python -m pytest`, run from the worktree. The working directory comes first on `sys.path`, so the tests
import this branch, not the editable install (R13). The Chainlit venv lives only in the main checkout, so it is
borrowed from there.

## Live checks

Pick one of R13's two options first, and tell the other sessions if it's (a).

1. **Migration**: `indico db --plugin assistant upgrade`, which creates `plugin_assistant.issue_reports`. To undo
   it: `printf 'YES\n' | indico db --plugin assistant downgrade 008_add_chat_session_title`.
2. **The Report button** (user 6, Makoto, not an admin):
   - open any event page, open the panel, and press ⚑ in its title bar. The form appears, with no attach box;
   - send a "Feature idea". Past Chats shows no new conversation (spec US1 AS8);
   - ask a slow question and press ⚑ while it runs. The form opens at once, with the box ticked (AS9).
3. **Offers**:
   - thumbs down an answer, with a comment: one offer, with the comment in its form;
   - ask something out of scope ("what's the weather?"): the answer carries the offer;
   - stop the worker and ask: the timeout message carries the offer, with no answer id.
4. **Profile**: `/user/assistant-reports/` lists both reports. Open one: its messages, but no SQL or intent.
   Delete one: it's gone.
5. **Triage** (user 1, Lucas, an admin):
   - `/admin/assistant-reports/`: the menu badge counts the open reports;
   - filter, open the wrong-answer report: its answer is marked, with its evidence;
   - set "under review" with a note. Then open the same report in two tabs, save in one, then in the other:
     the second save is refused with the current state;
   - as user 6, `/admin/assistant-reports/` is refused.
6. **Retention**: with `retention_report_days = 1`, a report closed 2 days ago (set `closed_at` by hand) is
   purged by `apply_retention`, and an open one isn't. **Count what it would delete first**:

   ```sql
   SELECT count(*) FROM plugin_assistant.issue_reports
   WHERE closed_at < now() - interval '1 day';
   ```

## Browser checks

`tests/browser/reports.mjs` (new; run as `WALK_USER=6` for the user paths, and as user 1 for triage):

- **SC-001**: a report from an offer and one from ⚑, each in at most three choices besides typing, each listed
  on the profile page right after. 10 runs.
- **SC-002**: offers after 10 thumbs down, and under 10 out-of-scope answers. A double-clicked Send makes one
  report.

Every existing check must still pass (spec SC-007): `walk`, `sc003`, `us4`, `hover`, `feedback`, `tabs` and
`sidebar`. `walk` runs as the admin, because Makoto can't create events. Test chats and reports made as user 6
are deleted afterwards, counted first.
