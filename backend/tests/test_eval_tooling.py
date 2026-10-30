"""The offline eval tooling: the nightly run's history/compare script and the
held-out categorization export and scorer. Lives outside tests/evals, whose
conftest skips everything unless RUN_EVALS=1; nothing here calls a model."""

import json

import pytest

from app.db.models import Transaction
from app.services import sync_service
from tests.evals import category_heldout as ch
from tests.evals import regression_history as rh
from tests.test_category_classifier import FakeClassifier, _sync, _txn


def _results(**passed_by_task) -> dict:
    """{"net_worth": [True, True, False]} -> a conftest-shaped results file."""
    rows = [
        {"task_id": task, "suite": "regression", "trial": i + 1, "passed": ok}
        for task, trials in passed_by_task.items()
        for i, ok in enumerate(trials)
    ]
    return {"model": "openrouter:pinned", "trials": 3, "results": rows}


def _record(tmp_path, history, results):
    path = tmp_path / f"run{len(rh.read_history(history))}.json"
    path.write_text(json.dumps(results))
    assert rh.main(["--history", str(history), "record", "--results", str(path)]) == 0


def test_history_records_pass_k_per_task(tmp_path):
    history = tmp_path / "history.jsonl"
    _record(tmp_path, history, _results(net_worth=[True] * 3, income=[True, False, True]))

    (line,) = rh.read_history(history)
    assert line["regression_pass_k"] == "1/2"
    assert line["tasks"]["income"] == {"suite": "regression", "passed": 2, "k": 3, "pass_k": 0}


def test_compare_fails_when_a_passing_task_drops(tmp_path, capsys):
    history = tmp_path / "history.jsonl"
    _record(tmp_path, history, _results(net_worth=[True] * 3, income=[True, False, True]))
    _record(tmp_path, history, _results(net_worth=[True, True, False], income=[True] * 3))

    assert rh.main(["--history", str(history), "compare"]) == 1
    out = capsys.readouterr().out
    assert "| net_worth | regression | 3/3 | 2/3 | regressed |" in out
    assert "| income | regression | 2/3 | 3/3 | fixed |" in out


def test_compare_passes_when_nothing_dropped_or_on_the_first_run(tmp_path):
    history = tmp_path / "history.jsonl"
    _record(tmp_path, history, _results(net_worth=[True] * 3, income=[False] * 3))
    assert rh.main(["--history", str(history), "compare"]) == 0  # first run
    _record(tmp_path, history, _results(net_worth=[True] * 3, income=[True, False, False]))
    assert rh.main(["--history", str(history), "compare"]) == 0  # income was already failing


def test_a_task_missing_from_the_latest_run_is_a_regression(tmp_path):
    history = tmp_path / "history.jsonl"
    _record(tmp_path, history, _results(net_worth=[True] * 3, income=[True] * 3))
    _record(tmp_path, history, _results(net_worth=[True] * 3))
    assert rh.regressions(*rh.read_history(history)) == ["income: missing from the latest run"]


def test_labels_take_names_keys_group_labels_and_alternatives():
    assert ch.parse_expected("Coffee Shops") == {"coffee_shops"}
    assert ch.parse_expected("coffee_shops") == {"coffee_shops"}
    assert ch.parse_expected("Food & Dining > Coffee Shops") == {"coffee_shops"}
    assert ch.parse_expected("Restaurants & Bars | coffee shops") == {"restaurants_and_bars", "coffee_shops"}
    assert ch.parse_expected("?") is None and ch.parse_expected("") is None
    with pytest.raises(ValueError, match="'Coffee'"):
        ch.parse_expected("Coffee")  # an old name


def _row(merchant, expected, plaid="FOOD_AND_DRINK_RESTAURANT", pipeline=""):
    return {"merchant": merchant, "example_amount": "6", "plaid_category": plaid,
            "pipeline_bankr": pipeline, "expected_category": expected}


def test_score_splits_tuning_from_held_out_and_scores_both_answers():
    rows = [
        _row("Hangar", "Fitness", pipeline="Fitness"),  # tuning: Plaid wrong, pipeline right
        _row("Moongoat Greenhouse", "Coffee Shops", plaid="FOOD_AND_DRINK_COFFEE", pipeline="Coffee Shops"),
        _row("Brand New Diner", "Restaurants & Bars", pipeline="Coffee Shops"),  # held-out: pipeline broke it
        _row("Mystery Co", "?"),
    ]
    tallies, misses = ch.score(rows)

    assert (tallies["tuning"].labeled, tallies["tuning"].plaid, tallies["tuning"].pipeline) == (2, 1, 2)
    held = tallies["heldout"]
    assert (held.rows, held.labeled, held.plaid, held.pipeline, held.changed, held.changed_right) == (2, 1, 1, 0, 1, 0)
    assert len(misses) == 2


def test_score_rejects_a_label_it_cant_map():
    with pytest.raises(SystemExit, match="Mystery Co: unknown category 'Dining'"):
        ch.score([_row("Mystery Co", "Dining")])


def test_historical_score_reproduces_the_tuning_run():
    assert "plaid 25/30 83%, pipeline 30/30 100%" in ch.score_historical()


def test_re_export_keeps_labels_and_never_drops_a_labeled_merchant():
    existing = [
        {"merchant_key": "brand new diner", "expected_category": "Restaurants & Bars", "notes": "mine"},
        {"merchant_key": "gone cafe", "merchant": "Gone Cafe", "expected_category": "Coffee Shops"},
    ]
    rows = [
        {"merchant": "Busy Place", "merchant_key": "busy place", "count": 9},
        {"merchant": "Brand New Diner", "merchant_key": "brand new diner", "count": 1},
        {"merchant": "Hangar", "merchant_key": "hangar", "count": 31},
    ]
    out = ch.build_template(rows, existing, limit=1)

    by_key = {r["merchant_key"]: r for r in out}
    assert by_key["hangar"]["split"] == "tuning" and by_key["hangar"]["previous_label"] == "Health"
    assert by_key["brand new diner"]["notes"] == "mine"
    assert "busy place" not in by_key  # over the limit, unlabeled
    assert "gone cafe" in by_key


@pytest.fixture
def classifier(monkeypatch):
    fake = FakeClassifier(answer="Food & Dining > Coffee Shops", confidence=0.95)
    monkeypatch.setattr(sync_service, "get_classifier", lambda: fake)
    return fake


def test_export_from_db_uses_the_cached_guess_not_the_users_correction(db, user, classifier):
    _sync(db, user, _txn("t1"), _txn("t2"), _txn("t3", merchant="Sure Thing", confidence="HIGH"))
    # The user corrects the row: the pipeline's answer must still be Jev's.
    row = db.query(Transaction).filter(Transaction.aggregator_transaction_id == "t1").one()
    row.category_source = "manual"
    db.commit()

    rows = ch.rows_from_db(db)
    ch.fill_predictions(rows, ch.pipeline_answers(db, {r["merchant_key"] for r in rows}))

    (only,) = rows  # the HIGH-confidence merchant isn't a candidate
    assert (only["merchant_key"], only["count"], only["example_amount"]) == ("moongoat greenhouse", 2, 6.0)
    assert (only["plaid_bankr"], only["pipeline_bankr"], only["pipeline_confidence"]) == (
        "Home Improvement", "Coffee Shops", 0.95)
