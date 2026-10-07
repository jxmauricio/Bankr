"""show_chart builds its numbers from a fresh query against the golden ledger,
never from the model -- so every bar must match the exact-cent answers."""

import pytest

from app.agent import claude_agent, tools
from app.agent.claude_agent import run_agent_turn
from app.api.chat import _charts, _public_sources
from app.services import money_query as mq
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient, ScriptedTurn
from tests.golden_ledger import EXPECTED, FROZEN_NOW, golden_aggregator


@pytest.fixture
def ledger(db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: FROZEN_NOW)
    sync_user_accounts(db, user.id, "golden-token", aggregator=golden_aggregator())
    return user


def test_breakdown_matches_the_category_totals(db, ledger):
    result = tools.show_chart(db, ledger.id, kind="breakdown", window="this_month")
    chart = result["chart"]
    assert (chart["kind"], chart["title"], chart["period"]) == ("breakdown", "Spending by category", "Sep 1–19")
    assert [(p["label"], p["value"]) for p in chart["points"]] == EXPECTED["this_month_by_category"]
    assert sum(p["share"] for p in chart["points"]) == pytest.approx(1, abs=0.001)


def test_compare_uses_the_like_for_like_window_mid_month(db, ledger):
    chart = tools.show_chart(db, ledger.id, kind="compare", category="groceries")["chart"]
    assert [(p["label"], p["value"]) for p in chart["points"]] == [
        ("Aug 1–19", EXPECTED["groceries_last_month_to_date"]),
        ("Sep 1–19", EXPECTED["groceries_this_month"]),
    ]
    assert chart["change"]["direction"] == "up"
    assert chart["title"] == "Groceries: then vs now"


def test_trend_is_oldest_first_and_stops_at_the_first_transaction(db, ledger):
    chart = tools.show_chart(db, ledger.id, kind="trend", months=6)["chart"]
    labels = [p["label"] for p in chart["points"]]
    assert labels[-1] == "Sep" and len(labels) <= 6
    last = chart["points"][-1]
    assert last["value"] == EXPECTED["this_month_spending"] and last["partial"] is True


def test_bad_kind_and_empty_windows_fall_back_to_text(db, ledger):
    assert "error" in tools.show_chart(db, ledger.id, kind="pie")
    empty = tools.show_chart(db, ledger.id, kind="breakdown", window="last_year")
    assert empty["shown"] is False and "chart" not in empty
    # One month isn't a trend.
    assert tools.show_chart(db, ledger.id, kind="trend", months=1)["shown"] is False


def test_a_drawn_chart_is_a_numbered_source(db, ledger, monkeypatch):
    monkeypatch.setattr(
        claude_agent,
        "_client",
        FakeAgentClient(
            turns=[
                ScriptedTurn(
                    final_text="Rent is most of it.",
                    tool_calls=[
                        ("get_spending", {"window": "this_month", "group_by": "category"}),
                        ("show_chart", {"kind": "breakdown", "window": "this_month"}),
                    ],
                )
            ]
        ),
    )
    _, sources = run_agent_turn(db, ledger.id, [{"role": "user", "content": "where did it go?"}])

    # Its figures can back the text, so it's numbered like any source.
    assert [s["tool"] for s in _public_sources(sources)] == ["get_spending", "show_chart"]
    charts = _charts(sources)
    assert len(charts) == 1 and charts[0]["kind"] == "breakdown"


def test_monthly_series_rejects_a_category_on_income(db, ledger):
    with pytest.raises(mq.QueryError):
        mq.monthly_series(db, ledger.id, "income", 6, mq.resolve_category(db, "Dining"))



def test_compare_takes_explicit_months(db, ledger):
    chart = tools.show_chart(
        db,
        ledger.id,
        kind="compare",
        category="groceries",
        current_start="2026-09-01",
        current_end="2026-09-19",
        previous_start="2026-08-01",
        previous_end="2026-08-31",
    )["chart"]
    assert [p["value"] for p in chart["points"]] == [EXPECTED["groceries_last_month"], EXPECTED["groceries_this_month"]]
