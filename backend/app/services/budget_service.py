"""Monthly budgets: how much is left in each line this month.

Spending comes from money_query.spend_query, so a budget's "spent" always
matches the number on the dashboard and in chat.

For each line, every month:
    available = budgeted + carryover + moved in - moved out - spent
carryover is the previous month's available (possibly negative) when the
line rolls over, back as far as the line's start month. Flex mode gives
each fixed bill its own line and pools every other expense category into
one Flexible line.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal
from statistics import median
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Budget, BudgetMove, BudgetSettings, Category, LinkedAccount, RecurringSeries, Transaction
from app.services import money_query as mq

FLEX = "flex"
MODES = ("flex", "category")
GROUPS = ("fixed", "flex")
MAX_ROLLOVER_MONTHS = 12
# Usually fixed: suggest these as their own lines in flex mode.
FIXED_BY_DEFAULT = {"Rent & Housing", "Utilities", "Loan Payments", "Subscriptions"}
# Don't call a line "on pace to go over" from the first few days of spending.
MIN_ELAPSED_FOR_PACE = 0.2


class BudgetError(ValueError):
    pass


def month_start(d: date) -> date:
    return d.replace(day=1)


def previous_month(m: date) -> date:
    return month_start(m - timedelta(days=1))


def month_end(m: date) -> date:
    return month_start(m + timedelta(days=32)) - timedelta(days=1)


def parse_month(value: str | None, today: date) -> date:
    if not value:
        return month_start(today)
    try:
        year, month = (int(p) for p in value.split("-")[:2])
        return date(year, month, 1)
    except (TypeError, ValueError):
        raise BudgetError("month must look like YYYY-MM")


def get_settings(db: Session, user_id: UUID, today: date | None = None) -> BudgetSettings:
    settings = db.get(BudgetSettings, user_id)
    if settings is None:
        today = today or mq.today_for_user(db, user_id)
        settings = BudgetSettings(user_id=user_id, mode="flex", flex_amount=0, flex_rollover=False, start_month=month_start(today))
        db.add(settings)
        db.flush()
    return settings


def _top_level_expense(db: Session, category_id: UUID) -> Category:
    category = db.get(Category, category_id)
    if category is None or category.type != "expense":
        raise BudgetError("budgets are for spending categories")
    if category.parent_category_id is not None:
        raise BudgetError("budget the parent category (e.g. Dining, not Coffee)")
    return category


@dataclass
class _Ledger:
    """Everything budget_status reads, loaded once and cached per month."""

    db: Session
    user_id: UUID
    settings: BudgetSettings
    budgets: dict[UUID, Budget]
    categories: dict[UUID, Category]
    spend_cache: dict[date, dict[UUID, float]] = field(default_factory=dict)
    moves_cache: dict[date, list[BudgetMove]] = field(default_factory=dict)

    def spend(self, month: date) -> dict[UUID, float]:
        """Net spent per top-level expense category in `month`."""
        if month not in self.spend_cache:
            window = mq.Window(month, month_end(month), "custom")
            groups = mq.spend_query(self.db, self.user_id, window, group_by="category")["groups"]
            by_name = {c.name: c.id for c in self.categories.values()}
            self.spend_cache[month] = {by_name[g["name"]]: g["amount"] for g in groups if g["name"] in by_name}
        return self.spend_cache[month]

    def moves(self, month: date) -> list[BudgetMove]:
        if month not in self.moves_cache:
            self.moves_cache[month] = (
                self.db.query(BudgetMove)
                .filter(BudgetMove.user_id == self.user_id, BudgetMove.month == month)
                .all()
            )
        return self.moves_cache[month]

    def flex_mode(self) -> bool:
        return self.settings.mode == "flex"

    def fixed_ids(self) -> set[UUID]:
        return {cid for cid, b in self.budgets.items() if b.group == "fixed"} if self.flex_mode() else set()

    # --- one line ----------------------------------------------------------

    def budgeted(self, key) -> float:
        if key == FLEX:
            return float(self.settings.flex_amount or 0)
        return float(self.budgets[key].amount)

    def spent(self, key, month: date) -> float:
        spend = self.spend(month)
        if key == FLEX:
            fixed = self.fixed_ids()
            return sum(v for cid, v in spend.items() if cid not in fixed)
        return spend.get(key, 0.0)

    def moved(self, key, month: date) -> float:
        cid = None if key == FLEX else key
        total = 0.0
        for m in self.moves(month):
            if m.to_category_id == cid:
                total += float(m.amount)
            if m.from_category_id == cid:
                total -= float(m.amount)
        return total

    def rolls_over(self, key) -> bool:
        return bool(self.settings.flex_rollover if key == FLEX else self.budgets[key].rollover)

    def start(self, key) -> date:
        return self.settings.start_month if key == FLEX else self.budgets[key].start_month

    def carryover(self, key, month: date, depth: int = 0) -> float:
        prev = previous_month(month)
        if not self.rolls_over(key) or prev < self.start(key) or depth >= MAX_ROLLOVER_MONTHS:
            return 0.0
        return self.available(key, prev, depth + 1)

    def available(self, key, month: date, depth: int = 0) -> float:
        return (
            self.budgeted(key)
            + self.carryover(key, month, depth)
            + self.moved(key, month)
            - self.spent(key, month)
        )


def _ledger(db: Session, user_id: UUID, today: date) -> _Ledger:
    settings = get_settings(db, user_id, today)
    budgets = {b.category_id: b for b in db.query(Budget).filter(Budget.user_id == user_id)}
    mq.seed_default_categories(db)
    categories = {
        c.id: c for c in db.query(Category).filter(Category.type == "expense", Category.parent_category_id.is_(None))
    }
    return _Ledger(db, user_id, settings, budgets, categories)


def _elapsed(month: date, today: date) -> float:
    if month > today:
        return 0.0
    if month_end(month) < today:
        return 1.0
    return today.day / month_end(month).day


def _line(ledger: _Ledger, key, month: date, elapsed: float, *, name: str, group: str, paced: bool) -> dict:
    budgeted = ledger.budgeted(key)
    carry = ledger.carryover(key, month)
    moved = ledger.moved(key, month)
    spent = ledger.spent(key, month)
    available = budgeted + carry + moved - spent
    room = budgeted + carry + moved
    projected = spent / elapsed if paced and 0 < elapsed < 1 else None
    if available < -0.005:
        state = "over"
    elif projected is not None and elapsed >= MIN_ELAPSED_FOR_PACE and projected > room + 0.005:
        state = "warning"
    else:
        state = "ok"
    return {
        "key": "flex" if key == FLEX else str(key),
        "category_id": None if key == FLEX else str(key),
        "name": name,
        "group": group,
        "budgeted": mq._money(budgeted),
        "carryover": mq._money(carry),
        "moved": mq._money(moved),
        "spent": mq._money(spent),
        "available": mq._money(available),
        "rollover": ledger.rolls_over(key),
        "projected_spent": mq._money(projected) if projected is not None else None,
        "status": state,
    }


def budget_status(db: Session, user_id: UUID, month: date | None = None) -> dict:
    today = mq.today_for_user(db, user_id)
    month = month_start(month or today)
    ledger = _ledger(db, user_id, today)
    elapsed = _elapsed(month, today)
    flex_mode = ledger.flex_mode()

    lines = []
    for cid, budget in sorted(ledger.budgets.items(), key=lambda kv: ledger.categories[kv[0]].name):
        if month < budget.start_month or (flex_mode and budget.group != "fixed"):
            continue
        lines.append(
            _line(
                ledger, cid, month, elapsed,
                name=ledger.categories[cid].name,
                group=budget.group if flex_mode else "category",
                # A fixed bill lands once; "on pace" means nothing for it.
                paced=not (flex_mode and budget.group == "fixed"),
            )
        )

    spend = ledger.spend(month)
    flex = None
    unbudgeted = []
    if flex_mode:
        fixed = ledger.fixed_ids()
        flex = _line(ledger, FLEX, month, elapsed, name="Flexible", group="flex", paced=True)
        flex["categories"] = sorted(
            (
                {"category_id": str(cid), "name": ledger.categories[cid].name, "spent": mq._money(v)}
                for cid, v in spend.items()
                if cid not in fixed and v > 0
            ),
            key=lambda c: c["spent"],
            reverse=True,
        )
    else:
        unbudgeted = sorted(
            (
                {"category_id": str(cid), "name": ledger.categories[cid].name, "spent": mq._money(v)}
                for cid, v in spend.items()
                if cid not in ledger.budgets and v > 0
            ),
            key=lambda c: c["spent"],
            reverse=True,
        )

    all_lines = lines + ([flex] if flex else [])
    window = mq.Window(month, month_end(month), "custom")
    last = previous_month(month)
    return {
        "month": f"{month:%Y-%m}",
        "label": f"{month:%B %Y}",
        "start": month.isoformat(),
        "end": month_end(month).isoformat(),
        "today": today.isoformat(),
        "elapsed_fraction": round(elapsed, 4),
        "mode": ledger.settings.mode,
        "has_budget": bool(ledger.budgets) or float(ledger.settings.flex_amount or 0) > 0,
        "lines": lines,
        "flex": flex,
        "unbudgeted": unbudgeted,
        "income": {
            "so_far": mq.income_query(db, user_id, window)["total_income"],
            "last_month": mq.income_query(db, user_id, mq.Window(last, month_end(last), "custom"))["total_income"],
        },
        "totals": {
            "budgeted": mq._money(sum(line["budgeted"] for line in all_lines)),
            "spent": mq._money(sum(spend.values())),
            "available": mq._money(sum(line["available"] for line in all_lines)),
        },
    }


# --- changes ------------------------------------------------------------------


def update_settings(
    db: Session, user_id: UUID, *, mode: str | None = None, flex_amount: float | None = None, flex_rollover: bool | None = None
) -> BudgetSettings:
    settings = get_settings(db, user_id)
    if mode is not None:
        if mode not in MODES:
            raise BudgetError(f"mode must be one of {MODES}")
        settings.mode = mode
    if flex_amount is not None:
        if flex_amount < 0:
            raise BudgetError("flex_amount can't be negative")
        settings.flex_amount = flex_amount
    if flex_rollover is not None:
        settings.flex_rollover = flex_rollover
    db.flush()
    return settings


def upsert_budget(
    db: Session,
    user_id: UUID,
    category_id: UUID,
    *,
    amount: float | None = None,
    group: str | None = None,
    rollover: bool | None = None,
) -> Budget:
    _top_level_expense(db, category_id)
    budget = db.query(Budget).filter(Budget.user_id == user_id, Budget.category_id == category_id).one_or_none()
    if budget is None:
        if amount is None:
            raise BudgetError("amount is required for a new budget")
        budget = Budget(
            user_id=user_id,
            category_id=category_id,
            amount=0,
            group="flex",
            rollover=False,
            start_month=month_start(mq.today_for_user(db, user_id)),
        )
        db.add(budget)
    if amount is not None:
        if amount < 0:
            raise BudgetError("amount can't be negative")
        budget.amount = amount
    if group is not None:
        if group not in GROUPS:
            raise BudgetError(f"group must be one of {GROUPS}")
        budget.group = group
    if rollover is not None:
        budget.rollover = rollover
    db.flush()
    return budget


def delete_budget(db: Session, user_id: UUID, category_id: UUID) -> bool:
    deleted = (
        db.query(Budget).filter(Budget.user_id == user_id, Budget.category_id == category_id).delete()
    )
    db.flush()
    return bool(deleted)


def move_money(
    db: Session, user_id: UUID, month: date, from_key: str, to_key: str, amount: float
) -> BudgetMove:
    """Move `amount` between two lines for `month`. Keys are a category id
    or "flex" for the Flexible bucket."""
    if amount <= 0:
        raise BudgetError("amount must be positive")
    if from_key == to_key:
        raise BudgetError("pick two different budget lines")

    def resolve(key: str) -> UUID | None:
        if key == FLEX:
            return None
        try:
            cid = UUID(key)
        except ValueError:
            raise BudgetError("unknown budget line")
        if not db.query(Budget).filter(Budget.user_id == user_id, Budget.category_id == cid).count():
            raise BudgetError("that category has no budget")
        return cid

    move = BudgetMove(
        user_id=user_id,
        month=month_start(month),
        from_category_id=resolve(from_key),
        to_category_id=resolve(to_key),
        amount=amount,
    )
    db.add(move)
    db.flush()
    return move


def _round_up(value: float, step: int = 10) -> float:
    return float((Decimal(str(value)) / step).to_integral_value(ROUND_CEILING) * step)


def _first_spend_month(db: Session, user_id: UUID) -> date | None:
    first = (
        db.query(func.min(Transaction.date))
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .join(Category, Transaction.bankr_category_id == Category.id)
        .filter(LinkedAccount.user_id == user_id, Category.type == "expense", *mq.counted_filters())
        .scalar()
    )
    return month_start(first) if first else None


def suggest_budget(db: Session, user_id: UUID) -> dict:
    """A starting budget from the last three full months: each category's
    median spend, rounded up to $10. Categories with confirmed recurring
    bills (and rent, utilities, loans, subscriptions) are proposed as fixed.

    Only months since spending history begins count -- a card linked in
    September would otherwise have its September median-ed against two
    empty months into $0. With no full month yet, this month's spending so
    far is projected to a full month."""
    today = mq.today_for_user(db, user_id)
    ledger = _ledger(db, user_id, today)
    first = _first_spend_month(db, user_id)
    months = []
    candidate = previous_month(month_start(today))
    while first is not None and candidate >= first and len(months) < 3:
        months.append(candidate)
        candidate = previous_month(candidate)
    per_month = [ledger.spend(m) for m in months]
    if not months and first is not None:
        this_month = month_start(today)
        elapsed = _elapsed(this_month, today) or 1.0
        months = [this_month]
        per_month = [{cid: v / elapsed for cid, v in ledger.spend(this_month).items()}]

    recurring_categories = set()
    for series in db.query(RecurringSeries).filter(
        RecurringSeries.user_id == user_id,
        RecurringSeries.status == "confirmed",
        RecurringSeries.direction == "out",
        RecurringSeries.category_id.isnot(None),
    ):
        category = db.get(Category, series.category_id)
        if category is not None:
            recurring_categories.add(category.parent_category_id or category.id)

    lines = []
    for cid, category in ledger.categories.items():
        typical = median([m.get(cid, 0.0) for m in per_month]) if per_month else 0.0
        if typical <= 0:
            continue
        fixed = cid in recurring_categories or category.name in FIXED_BY_DEFAULT
        lines.append(
            {
                "category_id": str(cid),
                "name": category.name,
                "amount": _round_up(typical),
                "group": "fixed" if fixed else "flex",
                "typical_spent": mq._money(typical),
            }
        )
    lines.sort(key=lambda line: (line["group"] != "fixed", -line["amount"]))
    return {
        "months": [f"{m:%Y-%m}" for m in months],
        "mode": "flex",
        "flex_amount": mq._money(sum(line["amount"] for line in lines if line["group"] == "flex")),
        "lines": lines,
    }


def setup_budget(db: Session, user_id: UUID, *, mode: str, flex_amount: float, lines: list[dict]) -> None:
    """Replace the user's whole budget in one go (the "start from your last
    3 months" button)."""
    update_settings(db, user_id, mode=mode, flex_amount=flex_amount)
    keep = set()
    for line in lines:
        cid = UUID(str(line["category_id"]))
        upsert_budget(
            db, user_id, cid, amount=float(line["amount"]), group=line.get("group", "flex"), rollover=line.get("rollover")
        )
        keep.add(cid)
    stale = db.query(Budget).filter(Budget.user_id == user_id)
    if keep:
        stale = stale.filter(Budget.category_id.notin_(keep))
    stale.delete(synchronize_session=False)
    db.flush()
