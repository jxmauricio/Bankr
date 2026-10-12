"""Eval tasks against the golden ledger (tests/golden_ledger.py).

Expected figures come from EXPECTED -- added up by hand, never taken from
the agent. Most tasks also pin the "trap" total a naive answer would give
(a transfer counted as income, the gas bill counted as car gas, ...), since
those are the bugs users actually catch.

suite="regression": should pass every trial; a failure fails the run.
suite="capability": a target we're still climbing toward; reported, xfails.
"""

from dataclasses import dataclass, field

from tests.evals.graders import (
    Grader,
    all_of,
    any_of,
    called_no_tools,
    called_tool,
    figures_cited,
    matches,
    never_called_tool,
    never_matches,
    never_says_amount,
    no_amounts,
    only_zero_amounts,
    says_amount,
)
from tests.golden_ledger import EXPECTED as E


@dataclass
class Task:
    id: str
    prompt: str
    checks: list[Grader]
    suite: str = "regression"
    note: str = ""
    tags: list[str] = field(default_factory=list)


TASKS: list[Task] = [
    Task(
        "net_worth",
        "What's my net worth?",
        [says_amount(E["net_worth"]), figures_cited()],
    ),
    Task(
        "income_this_month",
        "How much income did I get this month?",
        [
            says_amount(E["this_month_income"]),
            never_says_amount(E["this_month_income"] + 40, "Venmo payback counted as income"),
            never_says_amount(E["this_month_income"] + 640, "card payment counted as income"),
        ],
    ),
    Task(
        "spending_this_month",
        "How much have I spent this month?",
        [
            says_amount(E["this_month_spending"]),
            never_says_amount(E["this_month_spending"] + 640, "card payment counted as spending"),
            never_says_amount(E["this_month_spending"] + 500, "savings transfer counted as spending"),
        ],
    ),
    Task(
        "groceries_this_month",
        "How much have I spent on groceries this month?",
        [says_amount(E["groceries_this_month"]), figures_cited()],
    ),
    Task(
        "groceries_last_month",
        "How much did I spend on groceries last month?",
        [says_amount(E["groceries_last_month"])],
    ),
    Task(
        "dining_last_week",
        "How much did I spend eating out last week?",
        [
            says_amount(E["dining_last_week"]),
            never_says_amount(E["dining_last_week_gross"], "refund not netted"),
        ],
    ),
    Task(
        "car_gas_last_month",
        "How much did I spend on gas for my car last month?",
        [
            says_amount(E["gas_last_month"]),
            never_says_amount(E["gas_last_month"] + 85, "PG&E gas bill counted as car gas"),
        ],
    ),
    Task(
        "travel_last_month",
        "What did travel cost me last month?",
        [says_amount(E["travel_last_month"])],
        note="No trap check on $420: a correct reply may cite it as the pre-refund gross.",
    ),
    Task(
        "transportation_last_month",
        "How much did I spend on transportation last month?",
        [
            says_amount(E["transportation_last_month"]),
            never_says_amount(E["transportation_last_month"] + 300, "flight counted as transportation"),
        ],
    ),
    Task(
        "top_category",
        "What's my biggest spending category this month?",
        [matches(r"\brent\b|housing"), called_tool("get_spending")],
        note="The figure may live in the chart rather than the text, so don't require $1,800 in the reply.",
    ),
    Task(
        "no_data_pets",
        "How much did I spend on pets last month?",
        [only_zero_amounts()],
        note="Nothing in the ledger is pet spending; any non-zero figure is invented.",
    ),
    Task(
        "small_talk",
        "Thanks!",
        [called_no_tools(), no_amounts()],
    ),
    Task(
        "advice_decline",
        "Should I put my savings into Tesla stock?",
        [
            never_matches(r"\byou should (buy|invest|put)\b|\bI('d| would)? recommend (buying|investing)\b"),
            never_called_tool("propose_goal"),
        ],
        suite="capability",
        note="System prompt forbids specific investment recommendations. Code check is a weak proxy; "
        "a calibrated LLM judge would grade this better.",
    ),
    Task(
        "ambiguous_gas",
        "How much did I spend on gas last month?",
        [
            any_of(
                called_tool("ask_clarifying_question"),
                all_of(says_amount(E["gas_last_month"]), matches(r"PG&E|gas bill|utilit")),
            )
        ],
        suite="capability",
        note="Car gas vs. the PG&E gas bill -- the prompt says ask instead of guess.",
    ),
]
