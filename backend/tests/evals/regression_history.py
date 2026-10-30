"""Track agent-eval runs over time and flag a regression between two runs.

The nightly job (.github/workflows/nightly-evals.yml) runs the regression
suite, then:

  python -m tests.evals.regression_history record   # results/*.json -> one history line
  python -m tests.evals.regression_history compare  # latest line vs the one before

`record` reads the newest results file conftest.py wrote (or --results) and
appends one JSON line to the history file: per task, trials passed out of k
and pass^k. `compare` prints a Markdown table of the last two lines (the job
appends it to its summary) and exits 1 when a task that passed all k trials
last time didn't this time. Works the same on a laptop after a hand run.

Offline: neither command calls a model.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
HISTORY = RESULTS_DIR / "history.jsonl"


def summarize(results: dict) -> dict:
    """One run's results file -> {task_id: {suite, passed, k, pass_k}}."""
    tasks: dict[str, dict] = {}
    for row in results["results"]:
        t = tasks.setdefault(row["task_id"], {"suite": row["suite"], "passed": 0, "k": 0})
        t["k"] += 1
        t["passed"] += bool(row["passed"])
    for t in tasks.values():
        t["pass_k"] = 1 if t["passed"] == t["k"] else 0
    return tasks


def history_line(results: dict, source: str) -> dict:
    tasks = summarize(results)
    regression = [t for t in tasks.values() if t["suite"] == "regression"]
    return {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": os.environ.get("GITHUB_SHA", ""),
        "run": os.environ.get("GITHUB_RUN_ID", ""),
        "model": results.get("model", "?"),
        "trials": results.get("trials"),
        "source": source,
        "regression_pass_k": f"{sum(t['pass_k'] for t in regression)}/{len(regression)}",
        "tasks": tasks,
    }


def read_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def regressions(previous: dict, latest: dict) -> list[str]:
    """Tasks that were pass^k last run and aren't now (or vanished: a crash)."""
    out = []
    for task_id, before in previous["tasks"].items():
        if before["suite"] != "regression" or not before["pass_k"]:
            continue
        now = latest["tasks"].get(task_id)
        if now is None:
            out.append(f"{task_id}: missing from the latest run")
        elif not now["pass_k"]:
            out.append(f"{task_id}: {before['passed']}/{before['k']} -> {now['passed']}/{now['k']}")
    return out


def report(previous: dict | None, latest: dict) -> str:
    lines = [f"### Agent evals: {latest['model']}, {latest['trials']} trials", ""]
    lines.append(f"Regression suite pass^k: **{latest['regression_pass_k']}**")
    if previous:
        lines[-1] += f" (previous: {previous['regression_pass_k']}, {previous['at']})"
        if previous["model"] != latest["model"]:
            lines += ["", f"> Model changed from `{previous['model']}`: scores aren't like for like."]
    lines += ["", "| task | suite | previous | latest | |", "|---|---|---|---|---|"]
    task_ids = list(latest["tasks"]) + [t for t in (previous or {}).get("tasks", {}) if t not in latest["tasks"]]
    for task_id in task_ids:
        now = latest["tasks"].get(task_id)
        before = (previous or {}).get("tasks", {}).get(task_id)
        cell = lambda t: f"{t['passed']}/{t['k']}" if t else "-"  # noqa: E731
        flag = ""
        if before and before["pass_k"] and not (now and now["pass_k"]):
            flag = "regressed"
        elif now and now["pass_k"] and before and not before["pass_k"]:
            flag = "fixed"
        suite = (now or before)["suite"]
        lines.append(f"| {task_id} | {suite} | {cell(before)} | {cell(now)} | {flag} |")
    return "\n".join(lines) + "\n"


def newest_results(results_dir: Path) -> Path:
    files = sorted(p for p in results_dir.glob("*.json") if p.name != HISTORY.name)
    if not files:
        sys.exit(f"no results file in {results_dir}: did the eval run (RUN_EVALS=1)?")
    return max(files, key=lambda p: p.stat().st_mtime)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--history", type=Path, default=HISTORY)
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="append the latest results file to the history")
    rec.add_argument("--results", type=Path, help="results file (default: newest in tests/evals/results/)")
    sub.add_parser("compare", help="latest history line vs the previous one; exit 1 on a regression")
    args = parser.parse_args(argv)

    if args.command == "record":
        path = args.results or newest_results(RESULTS_DIR)
        line = history_line(json.loads(path.read_text()), source=path.name)
        args.history.parent.mkdir(parents=True, exist_ok=True)
        with args.history.open("a") as f:
            f.write(json.dumps(line) + "\n")
        print(f"recorded {path.name}: regression pass^k {line['regression_pass_k']} -> {args.history}")
        return 0

    history = read_history(args.history)
    if not history:
        sys.exit(f"{args.history} is empty: run `record` first")
    latest, previous = history[-1], (history[-2] if len(history) > 1 else None)
    print(report(previous, latest))
    if previous is None:
        print("First recorded run: nothing to compare against yet.")
        return 0
    dropped = regressions(previous, latest)
    if dropped:
        print("Regressed since the previous run:\n" + "\n".join(f"- {d}" for d in dropped))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
