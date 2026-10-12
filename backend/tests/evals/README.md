# Agent evals

Runs the **real configured model** (same `AGENT_PROVIDER` / model as the app)
against the hand-verified golden ledger (`tests/golden_ledger.py`) and grades
the answers with deterministic code graders. Skipped by default, so normal
`pytest` and CI stay free and offline.

```bash
cd backend
RUN_EVALS=1 pytest tests/evals -q -s                       # everything, 3 trials each
RUN_EVALS=1 EVAL_TRIALS=5 EVAL_TASKS=net_worth pytest tests/evals -q -s
```

Needs the same Postgres `bankr_test` database as the rest of the tests, and an
API key for the configured provider. To compare models, override the env vars
(e.g. `AGENT_PROVIDER=anthropic ANTHROPIC_MODEL=...`).

## Reading results

The summary prints, per task, passes out of k trials plus **pass^k** (all k
passed -- the bar for a user-facing answer) and **pass@k** (any passed). Every
trial's reply and tool-call transcript is written to `results/*.json`
(gitignored). **Read the transcripts of failures** before trusting a score: a
failure is either an agent bug or a task/grader bug, and only the transcript
tells you which.

## Suites

- `regression`: should pass every trial. A failure fails the run.
- `capability`: a target we're still climbing toward. Reported, never fails the run.
  Graduate a task to `regression` once it passes reliably.

## Adding a task

Add a `Task` to `tasks.py`. Take the expected figure from `golden_ledger.EXPECTED`
(hand-computed, never from the agent), and add a `never_says_amount` for the
wrong total a naive answer would give. Grade the outcome, not the tool order.
Every bug you fix in the agent should become a task here.
