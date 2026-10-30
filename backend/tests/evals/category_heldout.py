"""Held-out categorization eval: label merchants the classifier was never
tuned on, then score Plaid and the pipeline on them.

The classifier (app/services/category_classifier.py) was tuned on the 41
merchants in category_jev_labels.csv, so its 30/30 there says little about a
merchant it hasn't seen. This builds a bigger labeled set, kept apart:

  python -m tests.evals.category_heldout export              # dev DB -> template
  python -m tests.evals.category_heldout export --source csv # from category_low_confidence.csv
  (fill in expected_category by hand)
  python -m tests.evals.category_heldout score [--db] [--misses]
  python -m tests.evals.category_heldout score --historical  # the frozen tuning-run CSV

The template has a row per low-confidence (Plaid LOW/UNKNOWN) spending
merchant: split=tuning for the 41, split=heldout for the rest. Labels are
today's category names or keys ("Coffee Shops" or "coffee_shops"; "a|b" when
both are right; "?" when you can't tell). The tuning rows show their old label
(from before the Monarch category rename) for reference, but need relabeling
in today's names to count.

The pipeline's answer is the classifier's cached guess when it's trusted
(MerchantCategoryGuess, >= JEV_MIN_CONFIDENCE), else Plaid's mapping: what
categorization_service would pick before any of the user's own picks, rules
or corrections. Never the transaction's current category: a merchant you've
corrected would then score its own label.

Offline: nothing here calls a model. Export from the dev DB reads it; --db
on score re-reads the cached guesses (after you've re-run the classifier) so
one labeled file can score each classifier version.
"""

import argparse
import csv
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.db.seed_categories import DEFAULT_CATEGORIES, DEFAULT_GROUPS
from app.services.category_classifier import LOW_CONFIDENCE, merchant_key
from app.services.category_mapper import map_raw_category

HERE = Path(__file__).parent
TUNING_LABELS = HERE / "category_jev_labels.csv"
TUNING_RUN = HERE / "category_jev_pipeline_v2.csv"
LOW_CONFIDENCE_CSV = HERE / "category_low_confidence.csv"
TEMPLATE = HERE / "category_heldout.csv"

COLUMNS = [
    "split",
    "merchant",
    "merchant_key",
    "count",
    "example_amount",
    "payment_channel",
    "plaid_category",
    "plaid_confidence",
    "plaid_bankr",
    "pipeline_bankr",
    "pipeline_confidence",
    "previous_label",
    "expected_category",
    "notes",
]
LABEL_COLUMNS = ("expected_category", "notes")  # the user's; kept across re-exports
UNSURE = {"", "?"}

_NAMES = {key: name for key, name, *_ in DEFAULT_CATEGORIES}
_GROUP_NAMES = {key: name for key, name, _ in DEFAULT_GROUPS}
# Every way a label may name a category -> its key: key, name, "Group > Name".
_LOOKUP = {}
for _key, _name, _, _group, _ in DEFAULT_CATEGORIES:
    for alias in (_key, _name, f"{_GROUP_NAMES[_group]} > {_name}"):
        _LOOKUP[alias.strip().lower()] = _key


def category_key(label: str) -> str | None:
    """A category name, key or "Group > Name" -> its key; None if unknown."""
    return _LOOKUP.get(label.strip().lower())


def parse_expected(label: str) -> set[str] | None:
    """"a|b" -> {key_a, key_b}; None for "?"/blank. Raises on an unknown name."""
    if label.strip() in UNSURE:
        return None
    keys = set()
    for part in label.split("|"):
        key = category_key(part)
        if key is None:
            raise ValueError(f"unknown category {part.strip()!r}")
        keys.add(key)
    return keys


def tuning_keys() -> dict[str, str]:
    """merchant_key -> its old label, for the 41 merchants the classifier was tuned on."""
    with TUNING_LABELS.open() as f:
        return {merchant_key(r["merchant"]): r["expected"] for r in csv.DictReader(f)}


def plaid_key(row: dict) -> str:
    amount = -abs(float(row.get("example_amount") or 1))
    return map_raw_category(row.get("plaid_category"), amount, merchant_name=row.get("merchant"))


# --- export -----------------------------------------------------------------


def rows_from_db(db) -> list[dict]:
    """One row per low-confidence spending merchant across the DB's transactions."""
    from app.db.models import Transaction

    txns = (
        db.query(Transaction)
        .filter(Transaction.amount < 0, Transaction.split_parent_id.is_(None))
        .filter(Transaction.aggregator_category_confidence.in_(sorted(LOW_CONFIDENCE)))
        .all()
    )
    by_key: dict[str, list] = defaultdict(list)
    for t in txns:
        if (t.raw_aggregator_category or "").lower().startswith(("transfer_", "loan_")):
            continue  # cash, Zelle, loan payments: no merchant to look up
        key = merchant_key(t.original_merchant_name or t.merchant_name)
        if key:
            by_key[key].append(t)
    rows = []
    for key, group in by_key.items():
        common = lambda attr: Counter(getattr(t, attr) for t in group if getattr(t, attr)).most_common(1)  # noqa: E731
        rows.append(
            {
                "merchant": (common("original_merchant_name") or common("merchant_name"))[0][0],
                "merchant_key": key,
                "count": len(group),
                "example_amount": round(statistics.median(-float(t.amount) for t in group), 2),
                "payment_channel": "",
                "plaid_category": (common("raw_aggregator_category") or [("",)])[0][0],
                "plaid_confidence": (common("aggregator_category_confidence") or [("",)])[0][0],
            }
        )
    return rows


def rows_from_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return [
            {
                "merchant": r["merchant"],
                "merchant_key": merchant_key(r["merchant"]),
                "count": r.get("count", ""),
                "example_amount": r.get("example_amount", ""),
                "payment_channel": r.get("payment_channel", ""),
                "plaid_category": r.get("plaid_category", ""),
                "plaid_confidence": r.get("plaid_confidence", ""),
            }
            for r in csv.DictReader(f)
            if merchant_key(r["merchant"])
        ]


def pipeline_answers(db, keys: set[str]) -> dict[str, tuple[str, float | None]]:
    """merchant_key -> (category key or name, Jev's confidence), for trusted cached guesses."""
    from app.db.models import Category
    from app.services.category_classifier import cached_guesses, trusted

    out = {}
    for key, guess in cached_guesses(db, keys).items():
        if trusted(guess):
            category = db.get(Category, guess.category_id)
            out[key] = (category.system_key or category.name, guess.confidence)
    return out


def fill_predictions(rows: list[dict], answers: dict[str, tuple[str, float | None]] | None) -> None:
    """Plaid's mapping and, when the DB was read, the pipeline's answer."""
    for row in rows:
        plaid = plaid_key(row)
        row["plaid_bankr"] = _NAMES.get(plaid, plaid)
        if answers is None:
            continue
        pipeline, confidence = answers.get(row["merchant_key"], (plaid, None))
        row["pipeline_bankr"] = _NAMES.get(pipeline, pipeline)
        row["pipeline_confidence"] = "" if confidence is None else confidence


def build_template(rows: list[dict], existing: list[dict], limit: int | None) -> list[dict]:
    tuning = tuning_keys()
    kept = {r["merchant_key"]: r for r in existing}
    seen, tuning_rows, heldout_rows = set(), [], []
    for row in sorted(rows, key=lambda r: -int(r["count"] or 0)):
        if row["merchant_key"] in seen:
            continue
        seen.add(row["merchant_key"])
        row = {c: row.get(c, "") for c in COLUMNS}
        row["split"] = "tuning" if row["merchant_key"] in tuning else "heldout"
        row["previous_label"] = tuning.get(row["merchant_key"], "")
        for c in LABEL_COLUMNS:
            row[c] = kept.get(row["merchant_key"], {}).get(c, "")
        (tuning_rows if row["split"] == "tuning" else heldout_rows).append(row)
    if limit is not None:
        # Never drop a row someone already labeled.
        labeled = [r for r in heldout_rows if r["expected_category"]]
        rest = [r for r in heldout_rows if not r["expected_category"]]
        heldout_rows = labeled + rest[: max(0, limit - len(labeled))]
    # Already-labeled merchants that this export didn't see stay too.
    gone = [r for k, r in kept.items() if k not in seen and r.get("expected_category")]
    return tuning_rows + heldout_rows + gone


def read_template(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def write_template(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# --- score ------------------------------------------------------------------


@dataclass
class Tally:
    rows: int = 0
    labeled: int = 0
    plaid: int = 0
    pipeline: int = 0
    no_pipeline: int = 0  # labeled rows with no pipeline answer to score
    changed: int = 0  # pipeline overrode Plaid
    changed_right: int = 0


def score(rows: list[dict]) -> tuple[dict[str, Tally], list[str]]:
    """Accuracy per split against Plaid's mapping and the pipeline's answer.
    Splits come from the tuning label file, not the row's split column."""
    tuning = tuning_keys()
    tallies: dict[str, Tally] = defaultdict(Tally)
    misses, bad = [], []
    for row in rows:
        key = row.get("merchant_key") or merchant_key(row["merchant"])
        split = "tuning" if key in tuning else "heldout"
        t = tallies[split]
        t.rows += 1
        try:
            expected = parse_expected(row.get("expected_category", ""))
        except ValueError as exc:
            bad.append(f"{row['merchant']}: {exc}")
            continue
        if expected is None:
            continue
        t.labeled += 1
        plaid = plaid_key(row)
        t.plaid += plaid in expected
        pipeline = category_key(row.get("pipeline_bankr") or "") or (row.get("pipeline_bankr") or None)
        if pipeline is None:
            t.no_pipeline += 1
        else:
            t.pipeline += pipeline in expected
            if pipeline != plaid:
                t.changed += 1
                t.changed_right += pipeline in expected
        if plaid not in expected or (pipeline and pipeline not in expected):
            misses.append(
                f"[{split}] {row['merchant']}: expected {row['expected_category']}; "
                f"plaid {_NAMES.get(plaid, plaid)}, pipeline {_NAMES.get(pipeline, pipeline) if pipeline else '-'}"
            )
    if bad:
        raise SystemExit("unknown labels (use today's category names or keys):\n" + "\n".join(f"  {b}" for b in bad))
    return dict(tallies), misses


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} {n / d:.0%}" if d else "-"


def format_scores(tallies: dict[str, Tally]) -> str:
    lines = [f"{'split':8} {'labeled':>9}  {'plaid':>12}  {'pipeline':>12}  pipeline changed plaid (right)"]
    for split in ("tuning", "heldout"):
        t = tallies.get(split, Tally())
        scored = t.labeled - t.no_pipeline
        lines.append(
            f"{split:8} {f'{t.labeled}/{t.rows}':>9}  {_pct(t.plaid, t.labeled):>12}  "
            f"{_pct(t.pipeline, scored):>12}  {t.changed} ({t.changed_right})"
        )
        if t.no_pipeline:
            lines.append(f"         {t.no_pipeline} labeled rows have no pipeline answer: export from the DB, or score --db")
    return "\n".join(lines)


def score_historical() -> str:
    """The frozen tuning run, in the old category names: Plaid vs final answer."""
    with TUNING_RUN.open() as f:
        rows = [r for r in csv.DictReader(f) if r["expected"].strip() not in UNSURE]
    right = lambda col: sum(r[col] in r["expected"].split("|") for r in rows)  # noqa: E731
    return (
        f"{TUNING_RUN.name} (tuning set, old category names): {len(rows)} labeled; "
        f"plaid {_pct(right('plaid'), len(rows))}, pipeline {_pct(right('final_after_gate'), len(rows))}"
    )


# --- cli --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="write the label template (keeps labels already in it)")
    exp.add_argument("--source", choices=["db", "csv"], default="db")
    exp.add_argument("--csv", type=Path, default=LOW_CONFIDENCE_CSV, help="with --source csv")
    exp.add_argument("--out", type=Path, default=TEMPLATE)
    exp.add_argument("--limit", type=int, default=150, help="max held-out merchants, most visits first")
    sc = sub.add_parser("score", help="accuracy per split, Plaid vs pipeline")
    sc.add_argument("--labels", type=Path, default=TEMPLATE)
    sc.add_argument("--db", action="store_true", help="re-read the pipeline's cached guesses from the DB")
    sc.add_argument("--misses", action="store_true", help="list every labeled row either one got wrong")
    sc.add_argument("--historical", action="store_true", help="also score the frozen tuning run")
    args = parser.parse_args(argv)

    if args.command == "export":
        existing = read_template(args.out)
        if args.source == "db":
            from app.db.base import SessionLocal

            with SessionLocal() as db:
                rows = rows_from_db(db)
                answers = pipeline_answers(db, {r["merchant_key"] for r in rows})
        else:
            rows, answers = rows_from_csv(args.csv), None
        fill_predictions(rows, answers)
        out = build_template(rows, existing, args.limit)
        write_template(args.out, out)
        split = Counter(r["split"] for r in out)
        print(f"wrote {args.out}: {split['tuning']} tuning, {split['heldout']} held-out merchants")
        return 0

    rows = read_template(args.labels)
    if not rows:
        sys.exit(f"{args.labels} is missing or empty: run `export` first")
    if args.db:
        from app.db.base import SessionLocal

        with SessionLocal() as db:
            for row in rows:
                row["merchant_key"] = row.get("merchant_key") or merchant_key(row["merchant"])
            fill_predictions(rows, pipeline_answers(db, {r["merchant_key"] for r in rows}))
    tallies, misses = score(rows)
    print(format_scores(tallies))
    if args.historical:
        print(score_historical())
    if args.misses and misses:
        print("\n".join(["", *misses]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
