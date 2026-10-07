"""Monthly budgets: available = budgeted + carryover + moves - spent, in
both flex and per-category modes."""

from datetime import date

import pytest

from app.agent import tools
from app.db.models import Category, InsightLog
from app.integrations.bank_aggregator import AggregatorTransaction
from app.jobs import insights_job
from app.services import money_query as mq
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient
from tests.fake_aggregator import FakeAggregatorClient

TODAY = date(2026, 9, 15)  # halfway through September


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    monkeypatch.setattr(mq, "today_for_user", lambda db, user_id: TODAY)


def _t(txn_id, day, amount, merchant, raw):
    return AggregatorTransaction(txn_id, "acc_checking", amount, day, merchant, raw, False)


LEDGER = [
    # July
    _t("jul-rent", date(2026, 7, 1), -1800.0, "Greystar", "RENT_AND_UTILITIES_RENT"),
    _t("jul-food", date(2026, 7, 10), -300.0, "Ramen", "FOOD_AND_DRINK_RESTAURANT"),
    _t("jul-groc", date(2026, 7, 12), -400.0, "Safeway", "FOOD_AND_DRINK_GROCERIES"),
    # August
    _t("aug-rent", date(2026, 8, 1), -1800.0, "Greystar", "RENT_AND_UTILITIES_RENT"),
    _t("aug-food", date(2026, 8, 10), -250.0, "Ramen", "FOOD_AND_DRINK_RESTAURANT"),
    _t("aug-groc", date(2026, 8, 12), -380.0, "Safeway", "FOOD_AND_DRINK_GROCERIES"),
    # September (to the 15th)
    _t("sep-rent", date(2026, 9, 1), -1800.0, "Greystar", "RENT_AND_UTILITIES_RENT"),
    _t("sep-food", date(2026, 9, 10), -260.0, "Ramen", "FOOD_AND_DRINK_RESTAURANT"),
    _t("sep-groc", date(2026, 9, 12), -150.0, "Safeway", "FOOD_AND_DRINK_GROCERIES"),
    _t("sep-pay", date(2026, 9, 1), 4000.0, "Employer", "INCOME_WAGES"),
]


@pytest.fixture
def ledger(db, user):
    fake = FakeAggregatorClient(transactions_by_account={"acc_checking": list(LEDGER)})
    sync_user_accounts(db, user.id, "fake-token", aggregator=fake)


def _id(db, name):
    return str(db.query(Category).filter(Category.name == name).one().id)


def _line(status, name):
    return next(line for line in status["lines"] if line["name"] == name)


def test_no_budget_yet(client, ledger):
    status = client.get("/budgets").json()
    assert status["has_budget"] is False
    assert status["mode"] == "flex"
    assert status["month"] == "2026-09"


def test_suggestion_and_flex_setup(client, db, ledger):
    s = client.get("/budgets/suggestion").json()
    lines = {line["name"]: line for line in s["lines"]}
    # Median of Jun (0), Jul, Aug, rounded up to $10.
    assert lines["Rent & Housing"] == {**lines["Rent & Housing"], "amount": 1800.0, "group": "fixed"}
    assert lines["Dining"]["amount"] == 250.0 and lines["Dining"]["group"] == "flex"
    assert lines["Groceries"]["amount"] == 380.0
    assert s["flex_amount"] == 630.0

    status = client.post("/budgets/setup", json={"mode": "flex", "flex_amount": 600, "lines": s["lines"]}).json()
    rent = _line(status, "Rent & Housing")
    assert rent["spent"] == 1800.0 and rent["available"] == 0.0 and rent["status"] == "ok"
    flex = status["flex"]
    assert flex["budgeted"] == 600.0
    assert flex["spent"] == 410.0  # 260 dining + 150 groceries
    assert flex["available"] == 190.0
    # Halfway through the month at $410 projects to $820 > $600.
    assert flex["projected_spent"] == 820.0 and flex["status"] == "warning"
    assert {c["name"] for c in flex["categories"]} == {"Dining", "Groceries"}
    assert status["income"]["so_far"] == 4000.0
    assert status["totals"]["spent"] == 2210.0


def test_category_mode_rollover_and_moves(client, db, ledger):
    from app.db.models import Budget

    client.put("/budgets/settings", json={"mode": "category"})
    client.put(f"/budgets/{_id(db, 'Dining')}", json={"amount": 200, "rollover": True})
    client.put(f"/budgets/{_id(db, 'Groceries')}", json={"amount": 400})
    # Pretend the Dining budget started in July so rollover has history.
    db.query(Budget).filter(Budget.category_id == _id(db, "Dining")).update({"start_month": date(2026, 7, 1)})
    db.commit()

    status = client.get("/budgets").json()
    dining = _line(status, "Dining")
    # Jul: 200-300 = -100; Aug: 200-100-250 = -150 carried; Sep: 200-150-260 = -210.
    assert dining["carryover"] == -150.0
    assert dining["available"] == -210.0 and dining["status"] == "over"
    groceries = _line(status, "Groceries")
    assert groceries["carryover"] == 0.0 and groceries["available"] == 250.0
    assert [u["name"] for u in status["unbudgeted"]] == ["Rent & Housing"]

    status = client.post(
        "/budgets/moves",
        json={"from_key": _id(db, "Groceries"), "to_key": _id(db, "Dining"), "amount": 210},
    ).json()
    assert _line(status, "Dining")["available"] == 0.0
    assert _line(status, "Groceries")["available"] == 40.0
    assert _line(status, "Dining")["moved"] == 210.0

    # A past month is fully elapsed: no projection.
    august = client.get("/budgets", params={"month": "2026-08"}).json()
    assert _line(august, "Dining")["projected_spent"] is None


def test_budget_validation(client, db, ledger):
    assert client.put(f"/budgets/{_id(db, 'Coffee')}", json={"amount": 50}).status_code == 422
    assert client.put(f"/budgets/{_id(db, 'Income')}", json={"amount": 50}).status_code == 422
    assert client.post("/budgets/moves", json={"from_key": "flex", "to_key": "flex", "amount": 5}).status_code == 422
    assert client.get("/budgets", params={"month": "nope"}).status_code == 422
    assert client.delete(f"/budgets/{_id(db, 'Dining')}").status_code == 404


def test_excluded_and_split_spending_follow_into_budgets(client, db, ledger):
    from app.db.models import Transaction

    client.put("/budgets/settings", json={"mode": "category"})
    client.put(f"/budgets/{_id(db, 'Dining')}", json={"amount": 300})
    txn = db.query(Transaction).filter(Transaction.aggregator_transaction_id == "sep-food").one()
    client.patch(f"/transactions/{txn.id}", json={"excluded": True})
    assert _line(client.get("/budgets").json(), "Dining")["spent"] == 0.0


def test_agent_tools(client, db, ledger):
    client.put("/budgets/settings", json={"mode": "category"})
    client.put(f"/budgets/{_id(db, 'Dining')}", json={"amount": 200})
    client.put(f"/budgets/{_id(db, 'Groceries')}", json={"amount": 400})

    status = tools.get_budget_status(db, _user_id(db))
    assert _line(status, "Dining")["status"] == "over"

    proposal = tools.propose_budget_move(db, _user_id(db), from_line="groceries", to_line="coffee", amount=60)
    assert proposal["action"] == {
        "kind": "budget_move",
        "month": "2026-09",
        "from_key": _id(db, "Groceries"),
        "from_name": "Groceries",
        "to_key": _id(db, "Dining"),
        "to_name": "Dining",
        "amount": 60.0,
    }
    assert "error" in tools.propose_budget_move(db, _user_id(db), from_line="Travel", to_line="Dining", amount=5)


def _user_id(db):
    from app.db.models import User

    return db.query(User).one().id


def test_overspend_insight_once_per_line_month_and_state(client, db, ledger, monkeypatch):
    monkeypatch.setattr(insights_job, "_client", FakeAgentClient(completions=["Dining is over budget."] * 5))
    client.put("/budgets/settings", json={"mode": "category"})
    client.put(f"/budgets/{_id(db, 'Dining')}", json={"amount": 200})
    insights_job.run_insights_job(db, _user_id(db))
    insights_job.run_insights_job(db, _user_id(db))
    logs = db.query(InsightLog).filter(InsightLog.type == "budget_overspend").all()
    assert len(logs) == 1
    assert logs[0].dedupe_key.endswith(":2026-09:over")
