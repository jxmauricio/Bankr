"""Spending health: average category spend as a share of income, scored
against widely cited rules of thumb (HUD housing, 50/30/20, common budget
shares). These are guidelines, not advice — Bankr is not a financial advisor.

Income is money that hit linked accounts (closer to take-home than gross),
so a 30% housing bar here is tighter than HUD’s original gross-income
threshold. Saved is income minus spending, so a brokerage send counts as
saved rather than spent.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import LinkedAccount
from app.db.seed_categories import DEFAULT_GROUPS
from app.services import money_query as mq

# Needs vs wants for the 50/30/20 snapshot (Elizabeth Warren, All Your Worth),
# by group, with a category on the other side of its group's line where it
# belongs there: Groceries are a need though eating out is a want, and Cash &
# ATM is a want (what it paid for is unknown) though Financial is a need.
# Every other group is a want, including Other (a Zelle to a person lands in
# Miscellaneous) and any a user made themselves.
NEEDS = frozenset(
    {
        "housing",
        "bills_and_utilities",
        "auto_and_transport",
        "health_and_wellness",
        "financial",
        "children",
        "education",
    }
)
NEED_CATEGORIES = frozenset({"groceries"})
WANT_CATEGORIES = frozenset({"cash_and_atm"})
# Debt payments for debt-to-income. The mortgage is housing's.
DEBT_CATEGORIES = frozenset({"auto_payment", "student_loans", "loan_repayment"})


@dataclass(frozen=True)
class Guideline:
    pct: float
    source: str
    why: str


# Recommended *maximum* share of take-home, except Savings which is a minimum.
SAVINGS_GUIDELINE = Guideline(
    20,
    "50/30/20",
    "Elizabeth Warren’s 50/30/20 split puts at least 20% of after-tax income toward savings and extra debt payments.",
)
NEEDS_GUIDELINE = Guideline(
    50,
    "50/30/20",
    "The same split keeps necessities (housing, groceries, transport, bills) around half of take-home.",
)
WANTS_GUIDELINE = Guideline(
    30,
    "50/30/20",
    "The remaining 30% is wants: dining out, shopping, entertainment, travel.",
)

CATEGORY_GUIDELINES: dict[str, Guideline] = {
    "housing": Guideline(
        30,
        "HUD / CFPB",
        "Households spending over 30% of income on housing are considered cost-burdened.",
    ),
    "bills_and_utilities": Guideline(
        10,
        "Common budget share",
        "Budget templates often keep utilities, internet, and phone around 5–10% of take-home.",
    ),
    "food_and_dining": Guideline(
        15,
        "Common budget share",
        "Budget templates often put groceries around 10% of take-home and eating out around 5%.",
    ),
    "auto_and_transport": Guideline(
        15,
        "Common budget share",
        "Budget templates often keep gas, transit, and car costs around 10–15% of take-home.",
    ),
    "health_and_wellness": Guideline(
        10,
        "Common budget share",
        "Out-of-pocket medical and fitness costs are often budgeted around 5–10% of take-home.",
    ),
    "travel_and_lifestyle": Guideline(
        15,
        "50/30/20 wants",
        "Travel, entertainment, and personal care are wants; about 5% each is a common cap.",
    ),
    "shopping": Guideline(
        5,
        "50/30/20 wants",
        "Non-essential shopping is a want; a common cap is about 5% of take-home.",
    ),
}
DEBT_GUIDELINE = Guideline(
    15,
    "Common budget share",
    "Non-mortgage debt payments are often kept under 10–15% of take-home (the mortgage lives in housing).",
)


# Months of average spending that checking and savings would cover. A minimum, like savings.
EMERGENCY_FUND_GUIDELINE = Guideline(
    3,
    "Common rule of thumb",
    "Three to six months of expenses in cash is the usual emergency-fund advice.",
)
CASH_ACCOUNT_TYPES = frozenset({"checking", "savings"})


_EXPENSE_GROUPS = tuple(key for key, _, type_ in DEFAULT_GROUPS if type_ == "expense")


def _pct(amount: float, income: float) -> float | None:
    if income <= 0:
        return None
    return round(amount / income * 100, 1)


# Spend at or under the recommended max is healthy. A modest overage is a
# warning; beyond ~15% over the guideline is high.
_SPEND_HIGH_RATIO = 1.15
# 50/30/20 is 20% saved. Within 25% of that target (15%+) is a reasonable range.
_SAVE_HEALTHY_RATIO = 0.75
_SAVE_LOW_RATIO = 0.5


def _spend_tone(pct: float | None, rec: float | None) -> str:
    if pct is None or rec is None:
        return "neutral"
    if pct > rec * _SPEND_HIGH_RATIO:
        return "high"
    if pct > rec:
        return "ok"
    return "good"


def _save_tone(pct: float | None, rec: float) -> str:
    if pct is None:
        return "neutral"
    if pct >= rec * _SAVE_HEALTHY_RATIO:
        return "good"
    if pct >= rec * _SAVE_LOW_RATIO:
        return "ok"
    return "high"


def _spend_verdict(pct: float | None, rec: float | None) -> str:
    if pct is None:
        return "Need income in linked accounts to score this."
    if rec is None:
        return "No widely cited share for this category — shown as a percent of income only."
    if pct > rec * _SPEND_HIGH_RATIO:
        return f"Above the {rec:g}% guideline."
    if pct > rec:
        return f"A bit above the {rec:g}% guideline."
    return f"Healthy — at or under the {rec:g}% guideline."


def _save_verdict(pct: float | None, rec: float) -> str:
    if pct is None:
        return "Need income in linked accounts to score this."
    if pct >= rec:
        return f"Healthy — at or above the {rec:g}% 50/30/20 target."
    if pct >= rec * _SAVE_HEALTHY_RATIO:
        return f"Healthy — around the {rec:g}% 50/30/20 target."
    if pct >= rec * _SAVE_LOW_RATIO:
        return f"Below the {rec:g}% 50/30/20 target."
    return f"Well below the {rec:g}% 50/30/20 target."


def _line(
    *,
    id: str,
    name: str,
    amount: float,
    income: float,
    guideline: Guideline | None,
    this_month_amount: float,
    this_month_income: float,
    higher_is_better: bool = False,
) -> dict:
    rec = guideline.pct if guideline else None
    pct = _pct(amount, income)
    this_pct = _pct(this_month_amount, this_month_income)
    tone = _save_tone(pct, rec) if higher_is_better and rec is not None else _spend_tone(pct, rec)
    verdict = (
        _save_verdict(pct, rec)
        if higher_is_better and rec is not None
        else _spend_verdict(pct, rec)
    )
    recommended_amount = mq._money(income * rec / 100) if rec is not None and income > 0 else None
    return {
        "id": id,
        "name": name,
        "amount": mq._money(amount),
        "pct": pct,
        "recommended_pct": rec,
        "recommended_amount": recommended_amount,
        "tone": tone,
        "verdict": verdict,
        "source": guideline.source if guideline else None,
        "why": guideline.why if guideline else None,
        "this_month_amount": mq._money(this_month_amount),
        "this_month_pct": this_pct,
        "higher_is_better": higher_is_better,
    }


def _points(value: float | None, rec: float, higher_is_better: bool) -> float | None:
    """0–100 for one metric: full marks at the guideline, falling off past it.
    A minimum (savings, emergency fund) scores its share of the target; a
    maximum loses 2 points per 1% of the guideline it's over, so 15% over
    is 70 and 50% over is 0."""
    if value is None:
        return None
    if higher_is_better:
        return max(0.0, min(100.0, value / rec * 100))
    ratio = value / rec if rec else 0
    return max(0.0, min(100.0, 100 - (ratio - 1) * 200)) if ratio > 1 else 100.0


def _metric(*, id: str, name: str, value: float | None, unit: str, tone: str, rec: float, higher_is_better: bool) -> dict:
    points = _points(value, rec, higher_is_better)
    return {
        "id": id,
        "name": name,
        "value": value,
        "unit": unit,
        "tone": tone,
        "recommended": rec,
        "higher_is_better": higher_is_better,
        "points": round(points) if points is not None else None,
    }


def _emergency_tone(months: float | None, rec: float) -> str:
    if months is None:
        return "neutral"
    if months >= rec:
        return "good"
    if months >= 1:
        return "ok"
    return "high"


def _cash_on_hand(db: Session, user_id: UUID) -> float | None:
    """Checking and savings balances on active accounts; None before any balance has synced."""
    balances = [
        float(a.current_balance)
        for a in db.query(LinkedAccount).filter(LinkedAccount.user_id == user_id, LinkedAccount.status == "active")
        if a.account_type in CASH_ACCOUNT_TYPES and a.current_balance is not None
    ]
    return sum(balances) if balances else None


def _score(metrics: list[dict]) -> int | None:
    scored = [m["points"] for m in metrics if m["points"] is not None]
    return round(sum(scored) / len(scored)) if scored else None


def spending_health(db: Session, user_id: UUID) -> dict:
    """Average monthly spending by category vs recommended shares of income."""
    months, partial, n = mq.average_month_windows(db, user_id)
    today = mq.today_for_user(db, user_id)
    this_month = mq.resolve_window(today, "this_month")

    income = sum(mq.income_query(db, user_id, w)["total_income"] for w in months) / n
    spending = sum(mq.spend_query(db, user_id, w)["total_spent"] for w in months) / n
    saved = income - spending

    # By group key; a user's own group (no key) by its name.
    names = {key: name for key, name, _ in DEFAULT_GROUPS}
    by_cat: dict[str, float] = {key: 0.0 for key in _EXPENSE_GROUPS}
    for w in months:
        for g in mq.spend_query(db, user_id, w, group_by="category").get("groups", []):
            cid = g.get("key", g["name"])
            names[cid] = g["name"]  # the user's name for it, if they renamed it
            by_cat[cid] = by_cat.get(cid, 0.0) + g["amount"]
    for name in by_cat:
        by_cat[name] /= n

    this_income = mq.income_query(db, user_id, this_month)["total_income"]
    this_spend = mq.spend_query(db, user_id, this_month)
    this_by_cat = {g.get("key", g["name"]): g["amount"] for g in this_spend.get("groups", [])}
    this_saved = this_income - this_spend["total_spent"]

    start = min(w.start for w in months)
    end = max(w.end for w in months)

    categories = [
        _line(
            id=cid,
            name=names[cid],
            amount=amount,
            income=income,
            guideline=CATEGORY_GUIDELINES.get(cid),
            this_month_amount=this_by_cat.get(cid, 0.0),
            this_month_income=this_income,
        )
        for cid, amount in sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)
        if amount > 0 or cid in ("housing", "food_and_dining")
    ]

    # By category key, for the categories that sit on the other side of
    # their group's needs/wants line, and for debt.
    by_key: dict[str, float] = {}
    for w in months:
        for g in mq.spend_query(db, user_id, w, group_by="subcategory").get("groups", []):
            if "key" in g:
                by_key[g["key"]] = by_key.get(g["key"], 0.0) + g["amount"] / n
    this_by_key = {
        g["key"]: g["amount"] for g in mq.spend_query(db, user_id, this_month, group_by="subcategory").get("groups", []) if "key" in g
    }

    def needs(groups: dict[str, float], categories: dict[str, float]) -> float:
        return (
            sum(groups.get(key, 0.0) for key in NEEDS)
            + sum(categories.get(key, 0.0) for key in NEED_CATEGORIES)
            - sum(categories.get(key, 0.0) for key in WANT_CATEGORIES)
        )

    needs_amount = needs(by_cat, by_key)
    wants_amount = sum(by_cat.values()) - needs_amount
    this_needs = needs(this_by_cat, this_by_key)
    this_wants = sum(this_by_cat.values()) - this_needs

    buckets = [
        _line(
            id="needs",
            name="Needs",
            amount=needs_amount,
            income=income,
            guideline=NEEDS_GUIDELINE,
            this_month_amount=this_needs,
            this_month_income=this_income,
        ),
        _line(
            id="wants",
            name="Wants",
            amount=wants_amount,
            income=income,
            guideline=WANTS_GUIDELINE,
            this_month_amount=this_wants,
            this_month_income=this_income,
        ),
        _line(
            id="saved",
            name="Saved",
            amount=saved,
            income=income,
            guideline=SAVINGS_GUIDELINE,
            this_month_amount=this_saved,
            this_month_income=this_income,
            higher_is_better=True,
        ),
    ]

    by_id = {c["id"]: c for c in categories}

    def snapshot(key: str) -> dict:
        return by_id.get(key) or _line(
            id=key,
            name=names[key],
            amount=0,
            income=income,
            guideline=CATEGORY_GUIDELINES[key],
            this_month_amount=0,
            this_month_income=this_income,
        )

    snapshots = [buckets[2], snapshot("housing"), snapshot("food_and_dining")]  # saved first

    cash = _cash_on_hand(db, user_id)
    months_covered = round(cash / spending, 1) if cash is not None and spending > 0 else None
    debt_pct = _pct(sum(by_key.get(key, 0.0) for key in DEBT_CATEGORIES), income)
    # What HUD counts: the home and the bills that come with it.
    housing_pct = _pct(by_cat.get("housing", 0.0) + by_cat.get("bills_and_utilities", 0.0), income)
    housing_guideline = CATEGORY_GUIDELINES["housing"]
    metrics = [
        _metric(
            id="saved",
            name="Savings rate",
            value=buckets[2]["pct"],
            unit="pct",
            tone=buckets[2]["tone"],
            rec=SAVINGS_GUIDELINE.pct,
            higher_is_better=True,
        ),
        _metric(
            id="emergency_fund",
            name="Emergency fund",
            value=months_covered,
            unit="months",
            tone=_emergency_tone(months_covered, EMERGENCY_FUND_GUIDELINE.pct),
            rec=EMERGENCY_FUND_GUIDELINE.pct,
            higher_is_better=True,
        ),
        _metric(
            id="debt",
            name="Debt to income",
            value=debt_pct,
            unit="pct",
            tone=_spend_tone(debt_pct, DEBT_GUIDELINE.pct),
            rec=DEBT_GUIDELINE.pct,
            higher_is_better=False,
        ),
        _metric(
            id="housing",
            name="Housing",
            value=housing_pct,
            unit="pct",
            tone=_spend_tone(housing_pct, housing_guideline.pct),
            rec=housing_guideline.pct,
            higher_is_better=False,
        ),
    ]

    return {
        "income": mq._money(income),
        "spending": mq._money(spending),
        "saved": mq._money(saved),
        "saved_pct": _pct(saved, income),
        "months_used": round(n, 1) if partial else int(n),
        "partial": partial,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "label": mq.format_range(start, end),
        "as_of": mq.data_freshness(db, user_id),
        "note": (
            "Income is pay that hit linked accounts (take-home, not gross). "
            "Saved is income minus spending, so a transfer to Fidelity counts as saved. "
            "Guidelines are widely cited rules of thumb, not personalized advice. "
            "The score averages the four metrics: full marks at a guideline, less the further past it."
        ),
        "score": _score(metrics),
        "metrics": metrics,
        "snapshots": snapshots,
        "buckets": buckets,
        "categories": categories,
    }
