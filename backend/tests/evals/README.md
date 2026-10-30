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

## Nightly regression run

`.github/workflows/nightly-evals.yml` runs only the `regression` suite
(`EVAL_SUITE=regression`), 3 trials, against a pinned model
(`OPENROUTER_MODEL` in the workflow; bump it on purpose, in its own commit).
It's manual-only for now. To turn it on:

1. Add the repository secret **`OPENROUTER_API_KEY`** (Settings > Secrets and
   variables > Actions). The job fails straight away without it.
2. Run it once from Actions > Nightly evals > Run workflow.
3. Uncomment the `schedule:` block in the workflow.

Each run uploads its transcripts, appends one line per run to
`results/history.jsonl` (carried from run to run as the `eval-history`
artifact), and writes a previous-vs-latest table to the job summary. It fails
if a regression task passed all k trials last run and doesn't now. The same
script works after a hand run:

```bash
python -m tests.evals.regression_history record    # newest results/*.json -> history
python -m tests.evals.regression_history compare   # exit 1 on a regression
```

## Categorization: tuning vs held-out

The category classifier (`app/services/category_classifier.py`) was tuned on
the 41 merchants in `category_jev_labels.csv`; its 30/30 there is a training
score. `category_heldout.csv` is the bigger set to measure it on: one row per
low-confidence (Plaid `LOW`/`UNKNOWN`) spending merchant, `split=tuning` for
the 41 and `split=heldout` for the rest. No model is called by any of this.

```bash
python -m tests.evals.category_heldout export               # from the dev DB (.env DATABASE_URL)
python -m tests.evals.category_heldout export --source csv  # from category_low_confidence.csv
python -m tests.evals.category_heldout score --misses       # accuracy per split
python -m tests.evals.category_heldout score --db           # re-read the pipeline's answers first
python -m tests.evals.category_heldout score --historical   # + the frozen tuning run (old names)
```

The committed file was exported from `category_low_confidence.csv`, so it has
Plaid's answer but not the pipeline's. Re-export from the dev DB, or score
with `--db`, to fill `pipeline_bankr` from the classifier's cached guesses.
Re-exporting keeps every label already in the file.

**Labeling.** Fill in `expected_category` by hand; nothing fills it for you:

- Use today's category names or keys: `Coffee Shops` or `coffee_shops`
  (`Food & Dining > Coffee Shops` works too). Unknown names fail the scorer,
  so a typo can't silently count as wrong.
- `a|b` when both are right (a bakery cafe: `Coffee Shops|Restaurants & Bars`).
- `?` or blank when you can't tell what the business is; it isn't scored.
- Label what the business *is*, from what you know or can look up, not from
  `plaid_bankr` / `pipeline_bankr`. Use `notes` for why.
- The tuning rows show their old label in `previous_label` (from before the
  Monarch rename, e.g. `Health`, `Fast Food`). Relabel them in today's names;
  they don't count until you do.

**Reading it.** `score` prints, per split, labeled rows, Plaid's accuracy, the
pipeline's accuracy and how often the pipeline overrode Plaid (and was right).
The held-out pipeline number is the one to quote; a big gap to the tuning
number means the classifier was fit to its tuning set. The pipeline's answer
is the trusted cached guess, else Plaid's mapping, never the transaction's
current category, which would include your own corrections. Don't tune
prompts or thresholds against the held-out rows: once you do, they're tuning
rows, and you'll need a new held-out set.
