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

from app.db.seed_categories import DEFAULT_CATEGORIES
from app.services import money_query as mq

# Needs vs wants for the 50/30/20 snapshot (Elizabeth Warren, All Your Worth).
NEEDS = frozenset(
    {"Rent & Housing", "Groceries", "Utilities", "Transportation", "Health", "Loan Payments", "Fees"}
)
WANTS = frozenset({"Dining", "Entertainment", "Shopping", "Travel", "Subscriptions", "Other"})


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
    "Rent & Housing": Guideline(
        30,
        "HUD / CFPB",
        "Households spending over 30% of income on housing are considered rent-burdened.",
    ),
    "Groceries": Guideline(
        10,
        "Common budget share",
        "Many budget templates cap groceries around 10% of take-home; BLS food-at-home is often closer to 5–8%.",
    ),
    "Dining": Guideline(
        5,
        "50/30/20 wants",
        "Eating out sits in the 30% wants bucket; about 5% of take-home is a common dining cap.",
    ),
    "Transportation": Guideline(
        15,
        "Common budget share",
        "Budget templates often keep gas, transit, and car costs around 10–15% of take-home.",
    ),
    "Utilities": Guideline(
        8,
        "Common budget share",
        "Power, water, and internet are commonly budgeted around 5–10% of take-home, beside rent.",
    ),
    "Health": Guideline(
        10,
        "Common budget share",
        "Out-of-pocket medical and personal-care costs are often budgeted around 5–10% of take-home.",
    ),
    "Entertainment": Guideline(
        5,
        "50/30/20 wants",
        "Entertainment is a want; a common cap is about 5% of take-home.",
    ),
    "Shopping": Guideline(
        5,
        "50/30/20 wants",
        "Non-essential shopping is a want; a common cap is about 5% of take-home.",
    ),
    "Travel": Guideline(
        5,
        "50/30/20 wants",
        "Travel is lumpy, but averaged monthly it still sits in wants — about 5% is a common ceiling.",
    ),
    "Subscriptions": Guideline(
        5,
        "50/30/20 wants",
        "Streaming and similar subscriptions are wants; a common cap is about 5% of take-home.",
    ),
    "Loan Payments": Guideline(
        15,
        "Common budget share",
        "Non-mortgage debt payments are often kept under 10–15% of take-home (mortgage lives in housing).",
    ),
}


_EXPENSE_PARENTS = tuple(name for name, type_, parent in DEFAULT_CATEGORIES if type_ == "expense" and parent is None)


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


def spending_health(db: Session, user_id: UUID) -> dict:
    """Average monthly spending by category vs recommended shares of income."""
    months, partial, n = mq.average_month_windows(db, user_id)
    today = mq.today_for_user(db, user_id)
    this_month = mq.resolve_window(today, "this_month")

    income = sum(mq.income_query(db, user_id, w)["total_income"] for w in months) / n
    spending = sum(mq.spend_query(db, user_id, w)["total_spent"] for w in months) / n
    saved = income - spending

    by_cat: dict[str, float] = {name: 0.0 for name in _EXPENSE_PARENTS}
    for w in months:
        for g in mq.spend_query(db, user_id, w, group_by="category").get("groups", []):
            by_cat[g["name"]] = by_cat.get(g["name"], 0.0) + g["amount"]
    for name in by_cat:
        by_cat[name] /= n

    this_income = mq.income_query(db, user_id, this_month)["total_income"]
    this_spend = mq.spend_query(db, user_id, this_month)
    this_by_cat = {g["name"]: g["amount"] for g in this_spend.get("groups", [])}
    this_saved = this_income - this_spend["total_spent"]

    start = min(w.start for w in months)
    end = max(w.end for w in months)

    categories = [
        _line(
            id=name,
            name=name,
            amount=amount,
            income=income,
            guideline=CATEGORY_GUIDELINES.get(name),
            this_month_amount=this_by_cat.get(name, 0.0),
            this_month_income=this_income,
        )
        for name, amount in sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)
        if amount > 0 or name in ("Rent & Housing", "Groceries")
    ]

    needs_amount = sum(by_cat.get(name, 0.0) for name in NEEDS)
    wants_amount = sum(by_cat.get(name, 0.0) for name in WANTS)
    this_needs = sum(this_by_cat.get(name, 0.0) for name in NEEDS)
    this_wants = sum(this_by_cat.get(name, 0.0) for name in WANTS)

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
    snapshots = [
        buckets[2],  # saved
        by_id.get("Rent & Housing")
        or _line(
            id="Rent & Housing",
            name="Rent & Housing",
            amount=0,
            income=income,
            guideline=CATEGORY_GUIDELINES["Rent & Housing"],
            this_month_amount=0,
            this_month_income=this_income,
        ),
        by_id.get("Groceries")
        or _line(
            id="Groceries",
            name="Groceries",
            amount=0,
            income=income,
            guideline=CATEGORY_GUIDELINES["Groceries"],
            this_month_amount=0,
            this_month_income=this_income,
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
            "Guidelines are widely cited rules of thumb, not personalized advice."
        ),
        "snapshots": snapshots,
        "buckets": buckets,
        "categories": categories,
    }
