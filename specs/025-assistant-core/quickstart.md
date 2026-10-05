# Quickstart: Assistant core

How to check each story end to end on the local stack. Start the stack as the `indico-dev-server` skill describes.
The worker needs all four queues; Teams stays in fake mode. Every command marked **paid** prints its estimated cost
first and spends nothing without `--go`, and every paid run waits for Lucas's go.

## Story 1: the acceptance suite (eval repo)

```bash
cd ~/indico-assistant/eval
# 1. the test world: built in-process, so with the Indico venv's Python (idempotent: rebuilds only on a new hash)
INDICO_CONFIG=~/indico-assistant/instance/indico.conf \
  ~/indico-assistant/instance/env/bin/python -m indico_assistant_eval.scenarios.world build
#    ... wait until every world document is `ready` (the builder waits and reports each status)
~/indico-assistant/instance/env/bin/python -m indico_assistant_eval.scenarios.world status

# 2. dry run: lists the scenarios, the users they're spread across, and the estimated cost; spends nothing
uv run indico-assistant-scenarios            # full
uv run indico-assistant-scenarios --quick    # the quick subset

# 3. paid: the baseline (full, ≤ $5) on Lucas's go
uv run indico-assistant-scenarios --go --out reports/baseline.json

# 4. compare any two runs
uv run indico-assistant-scenarios compare reports/baseline.json reports/<new>.json
```

Expected:
- every scenario passes or fails with its failed check named;
- the report holds scores per set and per ability, and each turn's time and cost;
- no chats are left behind (`chats_left: 0`).

Before any paid run, the runner's preflight checks that:
- the stack runs with `INDICO_ASSISTANT_FAKE_GITHUB=1` (and `DEBUG`), so restart the web server and worker with it;
- `actions_enabled` and `attach_file` are on;
- `reports/world_ids.json` matches the world's hash.

Runs are logged to MLflow (`uv run mlflow ui`). The world is removed with `world remove`. The static test identity provider has to be in
`~/indico-assistant/instance/indico.conf` (research R8) before `world build`; ask Lucas first, since the stack is
shared.

## Story 2: documents through the new turn (plugin)

```bash
cd ~/indico-assistant/plugin-025
INDICO_CONFIG=~/indico-assistant/instance/indico.conf ../instance/env/bin/python -m pytest tests/unit tests/contract -q
# live, after `pg_dump` and `indico db --plugin assistant upgrade` (migration 012), with the stack on this worktree
# (see the indico-dev-server skill, "Live checks from a worktree"):
cd ~/indico-assistant/eval && uv run indico-assistant-scenarios --quick --go          # paid, ≤ $1
```

Expected:
- the documents set passes ≥ 90% (SC-002);
- no other set falls more than 2 scenarios below the baseline (SC-004);
- `fast:chat` turns cost no more than the baseline (SC-005).

By hand in the chat panel:
- attach a PDF and ask "summarise it" → the answer cites pages;
- ask "what does section 4.4.1 say?" on the thesis event → page 48.

## Story 3: one turn, every ability

- **Quick runs while building; a full run to accept:** the cross set ≥ 80% (SC-003), zero unconfirmed changes and
  zero followed injections (SC-008).
- `grep -rn "PLAN_WAITING\|OFFERED\|connectors/loop" indico_assistant` finds nothing (SC-009).

## Story 4: access

- `access` set: 100% agreement with Indico's own `can_access` for every world user (SC-007).
- Data set at or above the baseline (SC-004).
- If the suite shows no question that only NL2SQL answers: `nl2sql/` and the RLS script are removed. `indico
  assistant nl2sql-db-sql` no longer exists.
