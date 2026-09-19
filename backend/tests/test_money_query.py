"""Exact-cent answers to the MVP questions against the golden ledger.

If any of these drift, a user checking their bank would catch us -- which
is the one failure the MVP can't afford."""

from datetime import date, datetime, timezone

import pytest

from app.services import money_query as mq
from app.services.sync_service import sync_user_accounts
from tests.golden_ledger import EXPECTED, FROZEN_NOW, golden_aggregator

TODAY = date(2026, 9, 19)


@pytest.fixture
def ledger(db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: FROZEN_NOW)
    sync_user_accounts(db, user.id, "golden-token", aggregator=golden_aggregator())
    return user


def w(name):
    return mq.resolve_window(TODAY, name)


# --- windows --------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, start, end",
    [
        ("this_week", date(2026, 9, 14), date(2026, 9, 19)),
        ("last_week", date(2026, 9, 7), date(2026, 9, 13)),
        ("this_month", date(2026, 9, 1), date(2026, 9, 19)),
        ("last_month", date(2026, 8, 1), date(2026, 8, 31)),
        ("this_year", date(2026, 1, 1), date(2026, 9, 19)),
        ("last_year", date(2025, 1, 1), date(2025, 12, 31)),
        ("last_7_days", date(2026, 9, 13), date(2026, 9, 19)),
        ("yesterday", date(2026, 9, 18), date(2026, 9, 18)),
        ("month", date(2026, 9, 1), date(2026, 9, 19)),  # legacy dashboard period
    ],
)
def test_named_windows(name, start, end):
    window = mq.resolve_window(TODAY, name)
    assert (window.start, window.end) == (start, end)


def test_last_month_across_a_year_boundary():
    window = mq.resolve_window(date(2026, 1, 10), "last_month")
    assert (window.start, window.end) == (date(2025, 12, 1), date(2025, 12, 31))


def test_explicit_dates_win_and_are_capped_at_today():
    window = mq.resolve_window(TODAY, "last_week", start="2026-09-01", end="2026-12-31")
    assert (window.start, window.end, window.name) == (date(2026, 9, 1), TODAY, "custom")


def test_bad_window_is_a_recoverable_error():
    with pytest.raises(mq.QueryError) as exc:
        mq.resolve_window(TODAY, "last_fortnight")
    assert "last_week" in exc.value.extra["valid_windows"]


def test_labels_read_like_a_person_wrote_them():
    assert w("last_week").label == "Sep 7–13, 2026"
    assert mq.format_range(date(2026, 8, 28), date(2026, 9, 3)) == "Aug 28 – Sep 3, 2026"


def test_today_is_taken_in_the_users_timezone(db, user, monkeypatch):
    # 9:30pm Friday in Los Angeles is already Saturday in UTC.
    monkeypatch.setattr(mq, "_now", lambda: datetime(2026, 9, 19, 4, 30, tzinfo=timezone.utc))
    user.timezone = "America/Los_Angeles"
    db.flush()
    assert mq.today_for_user(db, user.id) == date(2026, 9, 18)
    user.timezone = "Not/AZone"  # garbage from a client falls back, doesn't crash
    db.flush()
    assert mq.today_for_user(db, user.id) == date(2026, 9, 19)  # default America/New_York


# --- categories ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "said, canonical",
    [
        ("eating out", "Dining"),
        ("Dining", "Dining"),
        ("groceries", "Groceries"),
        ("gas", "Gas"),
        ("fuel", "Gas"),
        ("gas bill", "Utilities"),
        ("restaurants", "Restaurants"),
        ("Uber", "Rideshare & Taxi"),
    ],
)
def test_category_resolution(db, said, canonical):
    assert mq.resolve_category(db, said).name == canonical


def test_unknown_category_suggests_instead_of_answering_zero(db):
    with pytest.raises(mq.QueryError) as exc:
        mq.resolve_category(db, "grocries")
    assert "Groceries" in exc.value.extra["did_you_mean"]


def test_transfer_is_not_a_spending_category(db):
    with pytest.raises(mq.QueryError):
        mq.resolve_category(db, "Transfer")


# --- the six MVP questions -------------------------------------------------------------


def test_q2_income_vs_spend_this_month(db, ledger):
    flow = mq.cash_flow(db, ledger.id, w("this_month"))
    assert flow["income"] == EXPECTED["this_month_income"]
    assert flow["spending"] == EXPECTED["this_month_spending"]
    assert flow["net"] == EXPECTED["this_month_net"]
    assert (flow["start"], flow["end"]) == ("2026-09-01", "2026-09-19")


def test_q3_groceries_this_month_vs_last(db, ledger):
    result = mq.compare_spend(db, ledger.id, w("this_month"), w("last_month"), mq.resolve_category(db, "groceries"))
    assert result["current"]["total_spent"] == EXPECTED["groceries_this_month"]
    assert result["current"]["pending_amount"] == EXPECTED["groceries_this_month_pending"]
    assert result["previous"]["total_spent"] == EXPECTED["groceries_last_month"]
    assert result["previous_to_same_point"]["total_spent"] == EXPECTED["groceries_last_month_to_date"]
    assert result["previous_to_same_point"]["end"] == "2026-08-19"
    assert result["change"] == {"difference": -39.95, "percent_change": -14.5, "direction": "down"}
    assert result["change_vs_same_point"] == {"difference": 20.05, "percent_change": 9.3, "direction": "up"}


def test_q4_eating_out_last_week(db, ledger):
    result = mq.spend_query(db, ledger.id, w("last_week"), mq.resolve_category(db, "eating out"))
    assert result["total_spent"] == EXPECTED["dining_last_week"]
    assert result["gross_spent"] == EXPECTED["dining_last_week_gross"]
    assert result["refunds"] == 10.00
    assert result["transaction_count"] == EXPECTED["dining_last_week_count"]
    assert "Coffee" in result["includes_subcategories"]


def test_q5_breakdown_by_category(db, ledger):
    result = mq.spend_query(db, ledger.id, w("this_month"), group_by="category")
    assert [(g["name"], g["amount"]) for g in result["groups"]] == EXPECTED["this_month_by_category"]
    assert round(sum(g["amount"] for g in result["groups"]), 2) == result["total_spent"]
    assert result["groups"][0]["share_of_total"] == round(1800 / EXPECTED["this_month_spending"], 4)


def test_q5_breakdown_by_merchant_rolls_up_the_long_tail(db, ledger):
    result = mq.spend_query(db, ledger.id, w("this_month"), group_by="merchant", top_n=3)
    assert [g["name"] for g in result["groups"][:3]] == ["Greystar", "Trader Joe's", "PG&E"]
    assert result["groups"][-1]["name"].endswith("others")
    assert round(sum(g["amount"] for g in result["groups"]), 2) == EXPECTED["this_month_spending"]


def test_q6_gas_last_month_excludes_the_gas_bill(db, ledger):
    gas = mq.spend_query(db, ledger.id, w("last_month"), mq.resolve_category(db, "gas"))
    assert gas["total_spent"] == EXPECTED["gas_last_month"]
    assert gas["transaction_count"] == 3

    transportation = mq.spend_query(db, ledger.id, w("last_month"), mq.resolve_category(db, "Transportation"))
    assert transportation["total_spent"] == EXPECTED["transportation_last_month"]
    travel = mq.spend_query(db, ledger.id, w("last_month"), mq.resolve_category(db, "Travel"))
    assert travel["total_spent"] == EXPECTED["travel_last_month"]


def test_transfers_and_card_payments_never_count(db, ledger):
    found = mq.find_transactions(db, ledger.id, w("this_month"), merchant="payment")
    assert found["transaction_count"] == 0
    spend = mq.spend_query(db, ledger.id, w("this_month"))
    assert spend["refunds"] == 10.00  # only the restaurant refund; the card's payment-received isn't one
    income = mq.income_query(db, ledger.id, w("this_month"))
    assert income["transaction_count"] == 2  # two paychecks; not Venmo, not the savings transfer


def test_find_transactions_backs_up_the_number(db, ledger):
    found = mq.find_transactions(db, ledger.id, w("last_week"), mq.resolve_category(db, "Dining"))
    assert found["total_spent"] == EXPECTED["dining_last_week"]
    assert len(found["transactions"]) == EXPECTED["dining_last_week_count"]
    assert not found["truncated"]


def test_empty_window_reports_zero_transactions_not_just_zero(db, ledger):
    result = mq.spend_query(db, ledger.id, mq.resolve_window(TODAY, start="2025-01-01", end="2025-01-31"))
    assert result["total_spent"] == 0
    assert result["transaction_count"] == 0
