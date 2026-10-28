"""Monthly budgets: how much is left in each line this month.

A line is a spending group as a whole, or, in a group the user budgets by
category (CategoryPref.budget_mode), one of its categories; either way it's
keyed by that group's or category's id. Spending is net of refunds per
line, over the same rows as money_query.spend_query, so a group's "spent"
matches the number on the dashboard and in chat.

For each line, every month:
    available = budgeted + carryover + moved in - moved out - spent
carryover is the previous month's available (possibly negative) when the
line rolls over, back as far as the line's start month. Flex mode gives
each fixed bill its own line and pools every other line into one Flexible
line.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal
from statistics import median
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.models import Budget, BudgetMove, BudgetSettings, Category, CategoryGroup, LinkedAccount, RecurringSeries, Transaction
from app.db.seed_categories import BUDGET_MODES, BY_CATEGORY, BY_GROUP, budget_modes, display_names, user_categories, user_groups
from app.services import money_query as mq
from app.services.category_service import CategoryNotFound, group_pref

FLEX = "flex"
MODES = ("flex", "category")
GROUPS = ("fixed", "flex")
MAX_ROLLOVER_MONTHS = 12
# Usually fixed: suggest these groups as their own lines in flex mode.
FIXED_BY_DEFAULT = {"housing", "bills_and_utilities"}
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


@dataclass(frozen=True)
class Target:
    """What one budget line covers: a group, or one category of a group
    budgeted by category."""

    id: UUID
    kind: str  # group | category
    name: str
    category_ids: tuple[UUID, ...]
    group: CategoryGroup


def targets(db: Session, user_id: UUID) -> dict[UUID, Target]:
    """Every line this user's spending groups can have, by id: one per group,
    or one per category in a group they budget by category."""
    names, modes = display_names(db, user_id), budget_modes(db, user_id)
    members: dict[UUID, list[Category]] = {}
    for c in user_categories(db, user_id).values():
        members.setdefault(c.group_id, []).append(c)
    out = {}
    for group in user_groups(db, user_id).values():
        if group.type != "expense":
            continue
        if modes.get(group.id, BY_GROUP) == BY_CATEGORY:
            for c in members.get(group.id, []):
                out[c.id] = Target(c.id, "category", names.get(c.id, c.name), (c.id,), group)
        else:
            ids = tuple(c.id for c in members.get(group.id, []))
            out[group.id] = Target(group.id, "group", names.get(group.id, group.name), ids, group)
    return out


@dataclass
class _Ledger:
    """Everything budget_status reads, loaded once and cached per month."""

    db: Session
    user_id: UUID
    settings: BudgetSettings
    targets: dict[UUID, Target]
    budgets: dict[UUID, Budget]  # only lines this user's budget modes still have
    spend_cache: dict[date, dict[UUID, float]] = field(default_factory=dict)
    moves_cache: dict[date, list[BudgetMove]] = field(default_factory=dict)

    def spend(self, month: date) -> dict[UUID, float]:
        """Net spent per line in `month`; lines that net to a refund are left out."""
        if month not in self.spend_cache:
            window = mq.Window(month, month_end(month), "custom")
            q = mq._base_query(self.db, self.user_id, window, "expense")
            by_category = dict(
                q.with_entities(Transaction.bankr_category_id, func.sum(-Transaction.amount))
                .group_by(Transaction.bankr_category_id)
                .all()
            )
            spend = {}
            for tid, target in self.targets.items():
                amount = sum(float(by_category.get(cid) or 0) for cid in target.category_ids)
                if amount > 0:
                    spend[tid] = amount
            self.spend_cache[month] = spend
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
        return {tid for tid, b in self.budgets.items() if b.group == "fixed"} if self.flex_mode() else set()

    # --- one line ----------------------------------------------------------

    def budgeted(self, key) -> float:
        if key == FLEX:
            return float(self.settings.flex_amount or 0)
        return float(self.budgets[key].amount)

    def spent(self, key, month: date) -> float:
        spend = self.spend(month)
        if key == FLEX:
            fixed = self.fixed_ids()
            return sum(v for tid, v in spend.items() if tid not in fixed)
        return spend.get(key, 0.0)

    def moved(self, key, month: date) -> float:
        tid = None if key == FLEX else key
        total = 0.0
        for m in self.moves(month):
            if (m.to_group_id or m.to_category_id) == tid:
                total += float(m.amount)
            if (m.from_group_id or m.from_category_id) == tid:
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
    lines = targets(db, user_id)
    budgets = {
        tid: b
        for b in db.query(Budget).filter(Budget.user_id == user_id)
        if (tid := b.group_id or b.category_id) in lines
    }
    return _Ledger(db, user_id, settings, lines, budgets)


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
        # The group's or category's id: what PUT /budgets/{id} takes.
        "category_id": None if key == FLEX else str(key),
        "kind": "flex" if key == FLEX else ledger.targets[key].kind,
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
    for tid, budget in sorted(ledger.budgets.items(), key=lambda kv: ledger.targets[kv[0]].name):
        if month < budget.start_month or (flex_mode and budget.group != "fixed"):
            continue
        lines.append(
            _line(
                ledger, tid, month, elapsed,
                name=ledger.targets[tid].name,
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
                {"category_id": str(tid), "name": ledger.targets[tid].name, "spent": mq._money(v)}
                for tid, v in spend.items()
                if tid not in fixed and v > 0
            ),
            key=lambda c: c["spent"],
            reverse=True,
        )
    else:
        unbudgeted = sorted(
            (
                {"category_id": str(tid), "name": ledger.targets[tid].name, "spent": mq._money(v)}
                for tid, v in spend.items()
                if tid not in ledger.budgets and v > 0
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


def set_budget_mode(db: Session, user_id: UUID, group_id: UUID, mode: str) -> None:
    """Budget a spending group as one line (by_group) or a line per category
    (by_category). The other mode's lines stay, unused, for switching back."""
    if mode not in BUDGET_MODES:
        raise BudgetError(f"mode must be one of {BUDGET_MODES}")
    group = db.get(CategoryGroup, group_id)
    if group is not None and group.type != "expense":
        raise BudgetError("budgets are for spending groups")
    try:
        pref = group_pref(db, user_id, group_id)
    except CategoryNotFound:
        raise BudgetError("unknown group")
    pref.budget_mode = None if mode == BY_GROUP else mode
    db.flush()


def _target(db: Session, user_id: UUID, target_id: UUID) -> Target:
    """A line by its id; a category alone in its group (Travel) also stands
    for the group's line, since pickers show the two as one."""
    lines = targets(db, user_id)
    target = lines.get(target_id) or next((t for t in lines.values() if t.category_ids == (target_id,)), None)
    if target is None:
        raise BudgetError(
            "budgets are for spending groups, or the categories of a group budgeted by category"
        )
    return target


def _column(target: Target):
    return Budget.group_id if target.kind == "group" else Budget.category_id


def upsert_budget(
    db: Session,
    user_id: UUID,
    target_id: UUID,
    *,
    amount: float | None = None,
    group: str | None = None,
    rollover: bool | None = None,
) -> Budget:
    target = _target(db, user_id, target_id)
    budget = db.query(Budget).filter(Budget.user_id == user_id, _column(target) == target.id).one_or_none()
    if budget is None:
        if amount is None:
            raise BudgetError("amount is required for a new budget")
        budget = Budget(
            user_id=user_id,
            amount=0,
            group="flex",
            rollover=False,
            start_month=month_start(mq.today_for_user(db, user_id)),
            **{"group_id" if target.kind == "group" else "category_id": target.id},
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


def delete_budget(db: Session, user_id: UUID, target_id: UUID) -> bool:
    try:
        target_id = _target(db, user_id, target_id).id
    except BudgetError:
        pass  # a line the user's budget modes no longer have can still go
    deleted = (
        db.query(Budget)
        .filter(Budget.user_id == user_id, or_(Budget.group_id == target_id, Budget.category_id == target_id))
        .delete(synchronize_session=False)
    )
    db.flush()
    return bool(deleted)


def move_money(
    db: Session, user_id: UUID, month: date, from_key: str, to_key: str, amount: float
) -> BudgetMove:
    """Move `amount` between two lines for `month`. Keys are a line's group
    or category id, or "flex" for the Flexible bucket."""
    if amount <= 0:
        raise BudgetError("amount must be positive")
    if from_key == to_key:
        raise BudgetError("pick two different budget lines")
    ledger = _ledger(db, user_id, mq.today_for_user(db, user_id))

    def side(key: str) -> dict:
        if key == FLEX:
            return {}
        try:
            tid = UUID(key)
        except ValueError:
            raise BudgetError("unknown budget line")
        if tid not in ledger.budgets:
            raise BudgetError("that line has no budget")
        return {"group": tid} if ledger.targets[tid].kind == "group" else {"category": tid}

    source, dest = side(from_key), side(to_key)
    move = BudgetMove(
        user_id=user_id,
        month=month_start(month),
        from_group_id=source.get("group"),
        from_category_id=source.get("category"),
        to_group_id=dest.get("group"),
        to_category_id=dest.get("category"),
        amount=amount,
    )
    db.add(move)
    db.flush()
    return move


def line_for(db: Session, user_id: UUID, resolved: mq.ResolvedCategory) -> Target:
    """The budget line a group, category or slice counts against: the
    category's own line in a group budgeted by category, else its group's."""
    lines = targets(db, user_id)
    if resolved.category_id in lines:
        return lines[resolved.category_id]
    group_ids = {t.group.id for t in lines.values() if set(resolved.ids) & set(t.category_ids)}
    for target in lines.values():
        if target.id in group_ids:
            return target
    raise BudgetError(f"{resolved.name} has no budget line")


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
    bills (and rent, utilities, loans) are proposed as fixed.

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
        per_month = [{tid: v / elapsed for tid, v in ledger.spend(this_month).items()}]

    recurring_categories = set()
    for series in db.query(RecurringSeries).filter(
        RecurringSeries.user_id == user_id,
        RecurringSeries.status == "confirmed",
        RecurringSeries.direction == "out",
        RecurringSeries.category_id.isnot(None),
    ):
        recurring_categories.add(series.category_id)

    lines = []
    for tid, target in ledger.targets.items():
        typical = median([m.get(tid, 0.0) for m in per_month]) if per_month else 0.0
        if typical <= 0:
            continue
        fixed = bool(recurring_categories & set(target.category_ids)) or target.group.system_key in FIXED_BY_DEFAULT
        lines.append(
            {
                "category_id": str(tid),
                "name": target.name,
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
    3 months" button). Each line's "category_id" is its group's or
    category's id, as suggest_budget gives it."""
    update_settings(db, user_id, mode=mode, flex_amount=flex_amount)
    keep = set()
    for line in lines:
        tid = UUID(str(line["category_id"]))
        keep.add(
            upsert_budget(
                db, user_id, tid, amount=float(line["amount"]), group=line.get("group", "flex"), rollover=line.get("rollover")
            ).id
        )
    stale = db.query(Budget).filter(Budget.user_id == user_id)
    if keep:
        stale = stale.filter(Budget.id.notin_(keep))
    stale.delete(synchronize_session=False)
    db.flush()
