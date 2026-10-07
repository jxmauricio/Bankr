"""The rules that keep a chat answer checkable, against the golden ledger:
every dollar figure is numbered to its source, every chart carries the rows
behind it, one picture per answer, ask instead of guess, and an empty search
says $0 and what it looked through."""

import pytest

from app.agent import claude_agent, tools
from app.agent.claude_agent import run_agent_turn
from app.api.chat import _answer_parts, _citations
from app.services import money_query as mq
from app.services.dashboard_service import get_itemized_transactions
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient, ScriptedTurn
from tests.golden_ledger import EXPECTED, FROZEN_NOW, golden_aggregator


@pytest.fixture
def ledger(db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: FROZEN_NOW)
    sync_user_accounts(db, user.id, "golden-token", aggregator=golden_aggregator())
    return user


def _turn(db, user, monkeypatch, reply, tool_calls):
    monkeypatch.setattr(
        claude_agent, "_client", FakeAgentClient(turns=[ScriptedTurn(final_text=reply, tool_calls=tool_calls)])
    )
    _, sources = run_agent_turn(db, user.id, [{"role": "user", "content": "?"}])
    return sources


# --- every dollar figure is numbered to its source ---------------------------


def test_figures_are_numbered_to_the_source_that_holds_them(db, ledger, monkeypatch):
    reply = "You've spent $235.80 on groceries (about $236), $45.10 of it pending. Rent was $1,800.00."
    sources = _turn(
        db,
        ledger,
        monkeypatch,
        reply,
        [
            ("get_spending", {"window": "this_month", "category": "groceries"}),
            ("get_spending", {"window": "this_month", "group_by": "category"}),
        ],
    )
    assert _citations(reply, sources) == [
        {"text": "$235.80", "source": 1},
        {"text": "$236", "source": 1},  # rounded, no cents
        {"text": "$45.10", "source": 1},
        {"text": "$1,800.00", "source": 2},  # only the breakdown holds rent
    ]


def test_a_figure_no_tool_returned_stays_uncited(db, ledger, monkeypatch):
    reply = "You spent $235.80, so maybe $240 next month, or $235.85."
    sources = _turn(db, ledger, monkeypatch, reply, [("get_spending", {"window": "this_month", "category": "groceries"})])
    assert _citations(reply, sources) == [{"text": "$235.80", "source": 1}]


def test_counts_never_back_a_dollar_figure(db, ledger, monkeypatch):
    # Dining last week has 5 transactions; "$5" must not cite it.
    reply = "Dining was $86.15 across 5 charges -- not $5."
    sources = _turn(db, ledger, monkeypatch, reply, [("get_spending", {"window": "last_week", "category": "dining"})])
    assert _citations(reply, sources) == [{"text": "$86.15", "source": 1}]


def test_charts_are_sources_but_questions_and_links_are_not(db, ledger, monkeypatch):
    reply = "Rent is $1,800.00 of it; you average $71.60 a month at Shell."
    sources = _turn(
        db,
        ledger,
        monkeypatch,
        reply,
        [
            ("get_spending", {"window": "this_month", "group_by": "category"}),
            ("show_chart", {"kind": "merchant", "merchant": "Shell", "months": 2}),
            ("show_chart", {"kind": "trend"}),  # becomes a link
            ("ask_clarifying_question", {"question": "Which?", "choices": ["a", "b"]}),
        ],
    )
    parts = _answer_parts(reply, sources)
    assert [s["tool"] for s in parts["sources"]] == ["get_spending", "show_chart"]
    assert parts["sources"][1]["label"] == "Chart · Shell by month"
    # The average is only in the chart.
    assert parts["citations"] == [{"text": "$1,800.00", "source": 1}, {"text": "$71.60", "source": 2}]


def test_citations_come_back_on_the_api_and_with_history(client, db, user, monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: FROZEN_NOW)
    sync_user_accounts(db, user.id, "golden-token", aggregator=golden_aggregator())
    monkeypatch.setattr(
        claude_agent,
        "_client",
        FakeAgentClient(turns=[ScriptedTurn(final_text="Net worth is $13,350.00.", tool_calls=[("get_net_worth", {})])]),
    )
    body = client.post("/chat", json={"message": "net worth?"}).json()
    assert body["citations"] == [{"text": "$13,350.00", "source": 1}]

    history = client.get(f"/chat/conversations/{body['conversation_id']}").json()
    assert history[1]["citations"] == body["citations"]


# --- every chart carries the transactions behind it --------------------------


def test_each_breakdown_bar_opens_exactly_the_rows_it_is_drawn_from(db, ledger):
    chart = tools.show_chart(db, ledger.id, kind="breakdown", window="this_month")["chart"]
    assert chart["query"] == {"start": "2026-09-01", "end": "2026-09-19", "category": None, "merchant": None}
    assert chart["group_by"] == "category"
    for point in chart["points"]:
        q = point["query"]
        rows = get_itemized_transactions(db, ledger.id, "expense", None, start=q["start"], end=q["end"], category=q["category"])
        assert rows["total"] == point["value"], point["label"]


def test_merchant_bars_filter_by_merchant(db, ledger):
    chart = tools.show_chart(db, ledger.id, kind="breakdown", window="this_month", group_by="merchant")["chart"]
    amazon = next(p for p in chart["points"] if p["label"] == "Amazon")
    assert amazon["query"]["merchant"] == "Amazon"
    # Rolled-up "N others" has no single filter.
    assert all(p["query"] is None for p in chart["points"] if p["label"].endswith(" others"))


def test_compare_and_trend_bars_carry_their_own_windows(db, ledger):
    compare = tools.show_chart(db, ledger.id, kind="compare", category="groceries")["chart"]
    assert [(p["query"]["start"], p["query"]["end"]) for p in compare["points"]] == [
        ("2026-08-01", "2026-08-19"),
        ("2026-09-01", "2026-09-19"),
    ]
    assert compare["query"] == compare["points"][-1]["query"]

    trend = tools.show_chart(db, ledger.id, kind="trend", months=2)["chart"]
    assert [(p["query"]["start"], p["query"]["end"]) for p in trend["points"]] == [
        ("2026-08-01", "2026-08-31"),
        ("2026-09-01", "2026-09-19"),
    ]

    income = tools.show_chart(db, ledger.id, kind="trend", metric="income", months=2)["chart"]
    assert income["query"]["kind"] == "income"

    # Net is two lists at once -- that's Cash flow, not a chart's list.
    net = tools.show_chart(db, ledger.id, kind="trend", metric="net", months=2)["chart"]
    assert net["query"] is None


# --- one picture per answer ----------------------------------------------------


def test_a_second_chart_becomes_a_link(db, ledger, monkeypatch):
    sources = _turn(
        db,
        ledger,
        monkeypatch,
        "Rent is most of it; the monthly picture is in Cash flow.",
        [
            ("show_chart", {"kind": "breakdown", "window": "this_month"}),
            ("show_chart", {"kind": "trend"}),
            ("show_chart", {"kind": "compare", "category": "groceries"}),
        ],
    )
    parts = _answer_parts("", sources)
    assert [c["kind"] for c in parts["charts"]] == ["breakdown"]
    assert parts["links"] == [
        {"view": "cash_flow", "label": "Open Cash flow"},
        {
            "view": "transactions",
            "label": "Groceries: then vs now in Transactions",
            "query": {"start": "2026-09-01", "end": "2026-09-19", "category": "Groceries", "merchant": None},
        },
    ]


# --- ask instead of guessing -------------------------------------------------


def test_clarifying_choices_get_their_resolved_dates(db, ledger):
    result = tools.ask_clarifying_question(
        db,
        ledger.id,
        question="Which weekend do you mean?",
        choices=[
            {"label": "Last weekend", "start": "2026-09-12", "end": "2026-09-13"},
            {"label": "This week", "window": "this_week"},
            {"label": "Every weekend this month"},
        ],
    )
    assert result["clarify"] == {
        "question": "Which weekend do you mean?",
        "choices": [
            {"label": "Last weekend · Sep 12–13"},
            {"label": "This week · Sep 14–19"},
            {"label": "Every weekend this month"},
        ],
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"question": "", "choices": ["a", "b"]},
        {"question": "Which?", "choices": ["only one"]},
        {"question": "Which?", "choices": ["a", "b", "c", "d", "e"]},
        {"question": "Which?", "choices": ["a", {"label": "b", "window": "next_decade"}]},
    ],
)
def test_bad_clarifying_questions_come_back_as_errors(db, ledger, kwargs):
    assert "error" in tools.ask_clarifying_question(db, ledger.id, **kwargs)


def test_clarify_rides_on_the_answer_not_the_sources(db, ledger, monkeypatch):
    sources = _turn(
        db,
        ledger,
        monkeypatch,
        "Which weekend do you mean?",
        [("ask_clarifying_question", {"question": "Which weekend do you mean?", "choices": ["Last weekend", "This one"]})],
    )
    parts = _answer_parts("Which weekend do you mean?", sources)
    assert parts["sources"] == []
    assert parts["clarify"]["choices"] == [{"label": "Last weekend"}, {"label": "This one"}]


# --- nothing found says $0 and what it searched --------------------------------


def test_an_empty_search_says_what_it_looked_through(db, ledger, monkeypatch):
    reply = "$0 — I didn't find any Target purchases in your 3 linked accounts this year."
    sources = _turn(db, ledger, monkeypatch, reply, [("find_transactions", {"window": "this_year", "merchant": "Target"})])
    parts = _answer_parts(reply, sources)
    assert parts["sources"][0]["searched"] == {
        "what": "“Target”",
        "range": "Jan 1 – Sep 19, 2026",
        "accounts": ["Total Checking •••• 1111", "Savings •••• 2222", "Sapphire •••• 3333"],
    }
    assert parts["citations"] == [{"text": "$0", "source": 1}]


def test_the_model_sees_what_was_searched_too(db, ledger, monkeypatch):
    """The searched box is also in the result the model gets back, so its
    "$0" line can say how many accounts it looked through."""
    seen = []

    class Client(FakeAgentClient):
        def run_turn(self, system, tools, history, call_tool):
            seen.append(call_tool("get_spending", {"window": "last_year", "category": "dining"}))
            return "$0"

    monkeypatch.setattr(claude_agent, "_client", Client())
    run_agent_turn(db, ledger.id, [{"role": "user", "content": "?"}])
    assert seen[0]["transaction_count"] == 0
    assert seen[0]["searched"]["what"] == "Dining" and len(seen[0]["searched"]["accounts"]) == 3


def test_a_search_that_found_rows_has_no_searched_box(db, ledger, monkeypatch):
    sources = _turn(db, ledger, monkeypatch, "x", [("get_spending", {"window": "this_month", "category": "groceries"})])
    assert "searched" not in sources[0]


# --- the answer-shaped charts ------------------------------------------------------


def test_breakdown_has_a_headline_and_a_vs_last_month_column(db, ledger):
    chart = tools.show_chart(db, ledger.id, kind="breakdown", window="this_month")["chart"]
    assert chart["headline"] == {
        "eyebrow": "THIS MONTH · SEP 1–19",
        "value": EXPECTED["this_month_spending"],
        "detail": "across 6 categories",
        "tone": None,
    }
    assert chart["previous_label"] == "vs Aug 1–19"
    previous = {p["label"]: p["previous"] for p in chart["points"]}
    # Aug 1–19 groceries (same point last month) -- the like-for-like number.
    assert previous["Groceries"] == EXPECTED["groceries_last_month_to_date"]
    assert previous["Shopping"] == 0.0  # nothing on Amazon by Aug 19


def test_daily_bars_add_up_to_the_range(db, ledger):
    chart = tools.show_chart(db, ledger.id, kind="daily", start="2026-09-07", end="2026-09-13", category="dining")["chart"]
    assert [p["label"] for p in chart["points"]][:2] == ["Sep 7", "Sep 8"]
    assert chart["points"][0]["weekday"] == "Mon"
    assert round(sum(p["value"] for p in chart["points"]), 2) == EXPECTED["dining_last_week"]
    assert chart["headline"]["value"] == EXPECTED["dining_last_week"]
    assert chart["headline"]["detail"] == f"spent across {EXPECTED['dining_last_week_count']} transactions"
    assert chart["points"][0]["query"] == {"start": "2026-09-07", "end": "2026-09-07", "category": "Dining", "merchant": None}


def test_daily_refuses_a_range_that_is_too_long(db, ledger):
    assert "error" in tools.show_chart(db, ledger.id, kind="daily", window="this_year")


def test_merchant_chart_has_monthly_bars_and_stats(db, ledger):
    chart = tools.show_chart(db, ledger.id, kind="merchant", merchant="Shell", months=2)["chart"]
    # Aug: 48.20 + 45.00; Sep: 50.00
    assert [(p["label"], p["value"]) for p in chart["points"]] == [("Aug", 93.2), ("Sep", 50.0)]
    assert chart["points"][-1]["partial"] is True
    assert chart["headline"]["value"] == 143.2 and chart["headline"]["detail"] == "over 3 orders"
    assert chart["average"] == 71.6
    assert chart["stats"] == [
        {"label": "Orders", "value": 3, "unit": "count"},
        {"label": "Average order", "value": 47.73, "unit": "usd"},
        {"label": "Largest", "value": 50.0, "unit": "usd", "date": "2026-09-08"},
    ]
    assert chart["points"][0]["query"]["merchant"] == "Shell"


def test_merchant_with_no_orders_falls_back_to_text(db, ledger):
    assert tools.show_chart(db, ledger.id, kind="merchant", merchant="Target")["shown"] is False


def test_net_worth_moves_are_each_accounts_transactions(db, ledger):
    chart = tools.show_chart(db, ledger.id, kind="net_worth", start="2026-09-01", end="2026-09-19")["chart"]
    moves = {p["label"]: p["value"] for p in chart["points"]}
    # Checking: +3000 +3000 -500 -640 +40 -1800 -90; savings +500; card:
    # -88.40 -102.30 -45.10 +640 -25 -42 -5.75 -12.40 +10 -36 -18 -50 -64.99.
    assert moves == {"Total Checking •••• 1111": 3010.0, "Savings •••• 2222": 500.0, "Sapphire •••• 3333": 160.06}
    assert chart["headline"]["value"] == 3670.06 and chart["headline"]["tone"] == "pos"
    # No balance saved before Sep 1, so it says so instead of inventing a start.
    assert "no balance saved" in chart["headline"]["detail"]
    assert chart["points"][0]["query"]["kind"] == "all"


def test_records_show_for_a_short_lookup(db, ledger, monkeypatch):
    sources = _turn(
        db,
        ledger,
        monkeypatch,
        "Yes -- $3,000.00 landed Sep 15.",
        [("find_transactions", {"start": "2026-09-15", "end": "2026-09-15", "kind": "income"})],
    )
    parts = _answer_parts("Yes -- $3,000.00 landed Sep 15.", sources)
    assert parts["records"] == [
        {
            "date": "2026-09-15",
            "amount": 3000.0,
            "merchant_name": "Employer Inc",
            "category": parts["records"][0]["category"],
            "is_pending": False,
            "account": "Total Checking •••• 1111",
            "kind": "income",
        }
    ]
    assert parts["sources"][0]["query"]["kind"] == "income"
    assert parts["citations"] == [{"text": "$3,000.00", "source": 1}]


def test_a_long_lookup_has_no_record_cards(db, ledger, monkeypatch):
    sources = _turn(db, ledger, monkeypatch, "x", [("find_transactions", {"window": "this_month"})])
    assert _answer_parts("x", sources)["records"] == []
