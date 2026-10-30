"""Run each eval task k times against the real model and the golden ledger.

A trial passes only if every check passes. A regression task must pass all k
trials (pass^k); a capability task is reported but xfails instead of failing."""

import os
import time

import pytest

from app.agent.claude_agent import run_agent_turn
from app.services.memory_service import add_fact
from tests.evals.conftest import RESULTS, trials
from tests.evals.tasks import TASKS

_ONLY = {t.strip() for t in os.environ.get("EVAL_TASKS", "").split(",") if t.strip()}
_SELECTED = [t for t in TASKS if not _ONLY or t.id in _ONLY]


@pytest.mark.parametrize("task", _SELECTED, ids=lambda t: t.id)
def test_task(task, db, ledger):
    for text, kind in task.memory:
        add_fact(db, ledger.id, text, kind)
    db.commit()
    k = trials()
    failures = 0
    for trial in range(1, k + 1):
        started = time.monotonic()
        row = {"task_id": task.id, "suite": task.suite, "trial": trial, "prompt": task.prompt}
        try:
            messages = [*task.history, {"role": "user", "content": task.prompt}]
            reply, sources = run_agent_turn(db, ledger.id, messages)
            outcomes = [(check.__name__, *check(reply, sources)) for check in task.checks]
            failed = [f"{name}: {detail}" for name, ok, detail in outcomes if not ok]
            row.update(reply=reply, sources=sources, failed_checks=failed, passed=not failed)
        except Exception as exc:  # a crashed trial is a failed trial, not a crashed run
            row.update(reply="", sources=[], failed_checks=[], passed=False, error=f"{type(exc).__name__}: {exc}")
        row["seconds"] = round(time.monotonic() - started, 2)
        RESULTS.append(row)
        failures += not row["passed"]

    if failures:
        message = f"{task.id}: {k - failures}/{k} trials passed"
        if task.suite == "capability":
            pytest.xfail(message)
        pytest.fail(message)
