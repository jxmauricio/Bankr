"""Opt-in agent evals: they call the real configured model, so they're skipped
unless RUN_EVALS=1 and never run in normal `pytest` or CI.

  RUN_EVALS=1 pytest tests/evals -q -s
  EVAL_TRIALS=5            trials per task (default 3)
  EVAL_TASKS=net_worth,... only these task ids

Every trial lands in tests/evals/results/<timestamp>_<model>.json with the
full reply and tool-call transcript -- read the failures there.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from app.config import settings
from app.services import money_query as mq
from app.services.sync_service import sync_user_accounts
from tests.golden_ledger import FROZEN_NOW, golden_aggregator

RESULTS: list[dict] = []
RESULTS_DIR = Path(__file__).parent / "results"

_KEY_BY_PROVIDER = {
    "openrouter": settings.openrouter_api_key,
    "anthropic": settings.anthropic_api_key,
    "openai_compatible": settings.agent_api_key,
}
_MODEL_BY_PROVIDER = {
    "openrouter": settings.openrouter_model,
    "anthropic": settings.anthropic_model,
    "openai_compatible": settings.agent_model,
}


def trials() -> int:
    return max(1, int(os.environ.get("EVAL_TRIALS", "3")))


def model_name() -> str:
    return f"{settings.agent_provider}:{_MODEL_BY_PROVIDER.get(settings.agent_provider, '?')}"


@pytest.fixture(autouse=True)
def _require_opt_in():
    if os.environ.get("RUN_EVALS") != "1":
        pytest.skip("agent evals call the real model; set RUN_EVALS=1 to run them")
    if not _KEY_BY_PROVIDER.get(settings.agent_provider):
        pytest.skip(f"no API key configured for AGENT_PROVIDER={settings.agent_provider}")


@pytest.fixture
def ledger(db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: FROZEN_NOW)
    sync_user_accounts(db, user.id, "golden-token", aggregator=golden_aggregator())
    return user


def _rate(passed: int, k: int) -> tuple[float, float]:
    """(pass^k, pass@k) estimated from k trials: all pass / any pass."""
    return (1.0 if passed == k else 0.0), (1.0 if passed else 0.0)


def pytest_terminal_summary(terminalreporter):
    if not RESULTS:
        return
    by_task: dict[str, list[dict]] = {}
    for r in RESULTS:
        by_task.setdefault(r["task_id"], []).append(r)

    tw = terminalreporter
    tw.section(f"agent evals -- {model_name()}")
    tw.write_line(f"{'task':28} {'suite':11} {'passed':>7}  pass^k  pass@k")
    suites: dict[str, list[float]] = {}
    for task_id, rows in by_task.items():
        k, passed = len(rows), sum(r["passed"] for r in rows)
        all_k, any_k = _rate(passed, k)
        suites.setdefault(rows[0]["suite"], []).append(all_k)
        tw.write_line(f"{task_id:28} {rows[0]['suite']:11} {f'{passed}/{k}':>7}  {all_k:>6.0%}  {any_k:>6.0%}")
        for r in rows:
            if not r["passed"]:
                tw.write_line(f"    trial {r['trial']}: " + " | ".join(r["failed_checks"] or [r.get("error", "?")]))
    for suite, vals in suites.items():
        tw.write_line(f"{suite}: {sum(vals):.0f}/{len(vals)} tasks pass^k")

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"{stamp}_{model_name().replace('/', '_').replace(':', '_')}.json"
    path.write_text(json.dumps({"model": model_name(), "trials": trials(), "results": RESULTS}, indent=2, default=str))
    tw.write_line(f"transcripts: {path}")
