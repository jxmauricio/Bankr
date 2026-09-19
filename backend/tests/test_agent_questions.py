"""The MVP questions end to end through the agent's real tool dispatch:
the tool call a model should make for each question returns the golden
answer, a source chip that states the exact window, and a drill-down query
whose rows add up to the same number. Also checks the model is told today's
date, since it must never work dates out on its own."""

import pytest

from app.agent import claude_agent
from app.agent.claude_agent import run_agent_turn
from app.services import money_query as mq
from app.services.dashboard_service import get_itemized_transactions
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient
from tests.golden_ledger import EXPECTED, FROZEN_NOW, golden_aggregator


class RecordingAgentClient(FakeAgentClient):
    def __init__(self, tool_calls):
        super().__init__()
        self.tool_calls = tool_calls
        self.results: list[dict] = []
        self.system = ""

    def run_turn(self, system, tools, history, call_tool):
        self.system = system
        for name, tool_input in self.tool_calls:
            self.results.append(call_tool(name, tool_input))
        return "ok"


@pytest.fixture
def ledger(db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: FROZEN_NOW)
    sync_user_accounts(db, user.id, "golden-token", aggregator=golden_aggregator())
    return user


def ask(db, user, monkeypatch, name, tool_input):
    client = RecordingAgentClient([(name, tool_input)])
    monkeypatch.setattr(claude_agent, "_client", client)
    _, sources = run_agent_turn(db, user.id, [{"role": "user", "content": "?"}])
    return client, client.results[0], sources[0]


def test_model_is_told_todays_date_in_the_users_timezone(db, ledger, monkeypatch):
    client, _, _ = ask(db, ledger, monkeypatch, "get_net_worth", {})
    assert "Today is Saturday, September 19, 2026" in client.system


def test_q1_how_much_am_i_worth(db, ledger, monkeypatch):
    _, result, source = ask(db, ledger, monkeypatch, "get_net_worth", {})
    assert result["net_worth"] == EXPECTED["net_worth"]
    assert result["total_assets"] == EXPECTED["total_assets"]
    assert result["total_liabilities"] == EXPECTED["total_liabilities"]
    # The number is visibly the sum of its parts.
    assert round(sum(a["balance"] * (1 if a["kind"] == "asset" else -1) for a in result["accounts"]), 2) == result["net_worth"]
    assert {a["mask"] for a in result["accounts"]} == {"1111", "2222", "3333"}
    assert result["data_as_of"] is not None
    assert source["label"] == "Net worth · 3 accounts"


def test_q2_income_vs_spend(db, ledger, monkeypatch):
    _, result, source = ask(db, ledger, monkeypatch, "get_cash_flow", {"window": "this_month"})
    assert (result["income"], result["spending"], result["net"]) == (
        EXPECTED["this_month_income"],
        EXPECTED["this_month_spending"],
        EXPECTED["this_month_net"],
    )
    assert source["label"] == "Income vs spending · Sep 1–19, 2026"


def test_q3_groceries_this_month_vs_last(db, ledger, monkeypatch):
    _, result, source = ask(db, ledger, monkeypatch, "compare_spending", {"category": "groceries"})
    assert result["current"]["total_spent"] == EXPECTED["groceries_this_month"]
    assert result["previous"]["total_spent"] == EXPECTED["groceries_last_month"]
    assert result["previous_to_same_point"]["total_spent"] == EXPECTED["groceries_last_month_to_date"]
    assert source["label"] == "Groceries · Sep 1–19, 2026 vs Aug 1–19, 2026"
    assert source["query"] == {"start": "2026-09-01", "end": "2026-09-19", "category": "Groceries", "merchant": None}


def test_q4_eating_out_last_week_and_the_drilldown_adds_up(db, ledger, monkeypatch):
    _, result, source = ask(db, ledger, monkeypatch, "get_spending", {"window": "last_week", "category": "eating out"})
    assert result["total_spent"] == EXPECTED["dining_last_week"]
    assert source["label"] == "Dining · Sep 7–13, 2026 · 5 transactions"

    # Tapping the chip lists exactly the rows behind the number.
    rows = get_itemized_transactions(db, ledger.id, "expense", **{k: v for k, v in source["query"].items() if v})
    assert rows["total"] == EXPECTED["dining_last_week"]
    assert round(-sum(i["amount"] for i in rows["items"]), 2) == EXPECTED["dining_last_week"]


def test_q5_what_am_i_spending_a_lot_on(db, ledger, monkeypatch):
    _, result, _ = ask(db, ledger, monkeypatch, "get_spending", {"window": "this_month", "group_by": "category"})
    assert [(g["name"], g["amount"]) for g in result["groups"]] == EXPECTED["this_month_by_category"]


def test_q6_gas_last_month(db, ledger, monkeypatch):
    _, result, source = ask(db, ledger, monkeypatch, "get_spending", {"window": "last_month", "category": "gas"})
    assert result["total_spent"] == EXPECTED["gas_last_month"]
    assert source["label"] == "Gas · Aug 1–31, 2026 · 3 transactions"


def test_a_bad_category_comes_back_as_a_recoverable_error(db, ledger, monkeypatch):
    _, result, source = ask(db, ledger, monkeypatch, "get_spending", {"category": "grocries"})
    assert "Groceries" in result["did_you_mean"]
    assert "query" not in source  # no drill-down for a figure that doesn't exist
