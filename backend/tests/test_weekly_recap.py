"""Weekly recap: hand-checked numbers from the golden ledger, and the API's
make-once / read-state behaviour.

Frozen "today" is Saturday 2026-09-19, so the latest finished week is
Mon Sep 7 – Sun Sep 13. Added up by hand from tests/golden_ledger.py:
  spending  = Food & Drink (groceries 102.30 + dining 86.15) + gas 50.00 = 238.45
  money in  = Venmo +40 (a transfer in; no paycheck that week)
  kept      = 40 - 238.45 = -198.45
"""

from datetime import date, datetime, timezone

import pytest

from app.db.models import InsightLog, NetWorthSnapshot, WeeklyRecap
from app.jobs import weekly_recap_job as job
from app.services import money_query as mq
from app.services.goal_service import create_goal
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient
from app.integrations.bank_aggregator import AggregatorTransaction
from tests.golden_ledger import FROZEN_NOW, golden_aggregator


@pytest.fixture
def ledger(db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: FROZEN_NOW)
    sync_user_accounts(db, user.id, "golden-token", aggregator=golden_aggregator())
    monkeypatch.setattr(job, "_client", FakeAgentClient(completions=["A quiet week."] * 5))
    return user


def test_latest_week_is_last_week_until_sunday_evening(db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: FROZEN_NOW)
    assert job.latest_week(db, user.id).start == date(2026, 9, 7)

    # Sunday Sep 20, 5pm in New York: this week isn't ready yet.
    monkeypatch.setattr(mq, "_now", lambda: datetime(2026, 9, 20, 21, tzinfo=timezone.utc))
    assert job.latest_week(db, user.id).start == date(2026, 9, 7)

    # 7pm: it is.
    monkeypatch.setattr(mq, "_now", lambda: datetime(2026, 9, 20, 23, tzinfo=timezone.utc))
    week = job.latest_week(db, user.id)
    assert (week.start, week.end) == (date(2026, 9, 14), date(2026, 9, 20))


def test_recap_numbers_match_the_ledger(db, ledger):
    facts = job.compute_recap_facts(db, ledger.id, job.week_starting(date(2026, 9, 7)))

    assert facts["spending"] == 238.45
    assert facts["money_in"] == 40.00
    assert facts["money_out"] == 238.45
    assert facts["kept"] == -198.45
    assert [(c["name"], c["amount"]) for c in facts["categories"]] == [
        ("Food & Dining", 188.45),
        ("Auto & Transport", 50.00),
    ]
    # Usual = Aug 10 – Sep 6 food: groceries (95.25 + 60 + 88.40) and
    # dining (60 + 25), over 4 weeks.
    assert facts["categories"][0]["usual"] == 82.16
    assert [(p["merchant"], p["amount"]) for p in facts["biggest_purchases"]] == [
        ("Trader Joe's", 102.30),
        ("Shell", 50.00),
        ("Ramen Spot", 42.00),
    ]
    assert [(m["merchant"], m["amount"]) for m in facts["money_in_items"]] == [("Venmo", 40.00)]
    # August (the only complete month) spent 2701.75; per week = x 12 / 52.
    assert facts["typical_week_spending"] == 623.48


def _august_categories(db, user, *extra):
    """August of the golden ledger (Housing, Food & Dining, Travel &
    Lifestyle, Auto & Transport, Bills & Utilities) plus extra August
    charges on the checking account."""
    aggregator = golden_aggregator()
    aggregator.transactions_by_account["chk"] += [
        AggregatorTransaction(f"extra-{raw}", "chk", amount, date(2026, 8, 14), merchant, raw, False)
        for merchant, amount, raw in extra
    ]
    sync_user_accounts(db, user.id, "golden-token", aggregator=aggregator)
    facts = job.compute_recap_facts(db, user.id, mq.Window(date(2026, 8, 1), date(2026, 8, 31), "custom"))
    return [(c["name"], c["amount"]) for c in facts["categories"]]


_PHARMACY = ("Walgreens", -40.00, "MEDICAL_PHARMACIES_AND_SUPPLEMENTS")
_GYM = ("Equinox", -30.00, "PERSONAL_CARE_GYMS_AND_FITNESS_CENTERS")
_GIFT = ("Paper Source", -25.00, "GENERAL_MERCHANDISE_GIFTS_AND_NOVELTIES")


def test_one_category_past_the_top_five_keeps_its_name(db, ledger):
    # Rent 1800; PG&E 85; flight 420 - 120 refund; gas 146 + Uber 35;
    # pharmacy 40 + gym 30.
    assert _august_categories(db, ledger, _PHARMACY, _GYM) == [
        ("Housing", 1800.00),
        ("Food & Dining", 335.75),
        ("Travel & Lifestyle", 300.00),
        ("Auto & Transport", 181.00),
        ("Bills & Utilities", 85.00),
        ("Health & Wellness", 70.00),
    ]


def test_two_or_more_past_the_top_five_are_summed(db, ledger):
    assert _august_categories(db, ledger, _PHARMACY, _GYM, _GIFT) == [
        ("Housing", 1800.00),
        ("Food & Dining", 335.75),
        ("Travel & Lifestyle", 300.00),
        ("Auto & Transport", 181.00),
        ("Bills & Utilities", 85.00),
        ("2 others", 95.00),  # Health & Wellness 70 + Gifts & Donations 25
    ]


def test_headline_and_teaser(db, ledger):
    facts = job.compute_recap_facts(db, ledger.id, job.week_starting(date(2026, 9, 7)))

    assert job.headline_for(facts) == "$198.45 more went out than came in"
    # (238.45 - 623.48) / 623.48 = -62%.
    assert job.teaser_for(facts) == "Spent $238.45, 62% under usual."


def test_goal_impact(db, ledger):
    db.add_all(
        [
            NetWorthSnapshot(user_id=ledger.id, date=date(2026, 9, 6), total_assets=14000, total_liabilities=0, net_worth=14000),
            NetWorthSnapshot(user_id=ledger.id, date=date(2026, 9, 13), total_assets=14300, total_liabilities=0, net_worth=14300),
        ]
    )
    db.commit()
    # Starts from the latest snapshot (Sep 19 sync: 14200 in assets).
    create_goal(db, ledger.id, "save", target_amount=5000.0, target_date=date(2027, 9, 1), name="Emergency fund")
    create_goal(db, ledger.id, "track_spending", target_amount=400.0, target_date=None, category="Food & Dining", window="this_month")

    goals = job.compute_recap_facts(db, ledger.id, job.week_starting(date(2026, 9, 7)))["goals"]
    save, dining = goals

    assert save["name"] == "Emergency fund"
    assert save["change"] == 300.00  # 14300 - 14000 across the week
    assert save["saved"] == 100.00  # 14300 at week end - 14200 start
    assert dining["spent"] == 364.95  # Food & Drink Sep 1–19
    assert dining["remaining"] == 35.05
    assert dining["week_spent"] == 188.45


def test_latest_recap_is_made_once_and_logged_as_unread(client, db, ledger):
    first = client.get("/recaps/latest").json()["recap"]
    again = client.get("/recaps/latest").json()["recap"]

    assert first["week_start"] == "2026-09-07"
    assert first["label"] == "Sep 7–13, 2026"
    assert first["summary"] == "A quiet week."
    assert first["read"] is False
    assert again["created_at"] == first["created_at"]
    assert db.query(WeeklyRecap).count() == 1

    insights = client.get("/insights").json()
    assert insights["unread_count"] == 1
    assert insights["insights"][0]["type"] == "weekly_recap"
    assert insights["insights"][0]["subject_id"] == "2026-09-07"
    assert insights["insights"][0]["message"] == (
        "Sep 7–13: $198.45 more went out than came in. Spent $238.45, 62% under usual."
    )


def test_reading_the_recap_clears_its_notification(client, db, ledger):
    client.get("/recaps/latest")

    assert client.post("/recaps/2026-09-07/read").status_code == 204
    assert client.get("/recaps/latest").json()["recap"]["read"] is True
    assert client.get("/insights").json()["unread_count"] == 0


def test_a_past_week_is_made_without_a_notification(client, db, ledger):
    recap = client.get("/recaps/2026-08-31").json()["recap"]

    assert recap["week_start"] == "2026-08-31"
    assert recap["read"] is True
    assert recap["next_week_start"] == "2026-09-07"
    assert recap["previous_week_start"] == "2026-08-24"
    assert db.query(InsightLog).filter(InsightLog.type == "weekly_recap").count() == 0


def test_no_earlier_week_than_the_first_transaction(client, ledger):
    # The ledger starts Aug 1, inside the week of Jul 27.
    recap = client.get("/recaps/2026-07-27").json()["recap"]
    assert recap["previous_week_start"] is None
    assert client.get("/recaps/2026-07-20").status_code == 404


def test_week_must_be_a_finished_monday(client, ledger):
    assert client.get("/recaps/2026-09-08").status_code == 400
    assert client.get("/recaps/2026-09-14").status_code == 404


def test_recap_without_the_model_still_has_its_numbers(client, ledger, monkeypatch):
    monkeypatch.setattr(job, "_client", FakeAgentClient(completions=[]))

    recap = client.get("/recaps/latest").json()["recap"]

    assert recap["summary"] is None
    assert recap["facts"]["spending"] == 238.45


def test_no_recap_before_any_history(client):
    assert client.get("/recaps/latest").json() == {"recap": None}
