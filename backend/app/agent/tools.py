"""Implementations of every tool the Claude agent is allowed to call.

Most are DB-backed and deliberately narrow: each takes a user_id and returns
a small, already-aggregated JSON-serializable result. The model never sees
raw SQL or a full transaction dump -- this keeps answers grounded, cheap,
and auditable, and structurally prevents the agent from reaching outside
banking/spending data (there is no investment or trade-execution tool to
call). calculate and web_search are the two exceptions -- pure/external
helpers with no user data in scope, kept in this module anyway so
claude_agent.py has one single dispatch surface to reason about.
"""

import ast
import operator
from datetime import date, timedelta
from functools import wraps
from statistics import mean, pstdev
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Category, Goal, LinkedAccount, NetWorthSnapshot, Transaction
from app.integrations.web_search import WebSearchClient
from app.services import budget_service
from app.services import money_query as mq
from app.services.goal_service import (
    DEFAULT_TRACKING_WINDOW,
    MAX_ACTIVE_GOALS,
    SAVE,
    TRACK_SPENDING,
    TRACKING_WINDOW_LABELS,
    TRACKING_WINDOWS,
    GoalValidationError,
    list_active_goals,
    normalize_goal_kind,
    spend_for_tracker,
)
from app.services.recurring_service import merchant_key, recurring_merchant_keys, recurring_overview
from app.services.rules_service import preview_rule
from app.services.sync_service import LIABILITY_ACCOUNT_TYPES


def _grounded(fn):
    """Money tools: turn a bad window/category into an error result the
    model can recover from (it gets the valid options back), and stamp
    every result with how fresh the underlying data is."""

    @wraps(fn)
    def wrapper(db: Session, user_id: UUID, *args, **kwargs) -> dict:
        try:
            result = fn(db, user_id, *args, **kwargs)
        except mq.QueryError as e:
            return {"error": str(e), **e.extra}
        result["data_as_of"] = mq.data_freshness(db, user_id)
        return result

    return wrapper


def _window(db: Session, user_id: UUID, window=None, start=None, end=None) -> mq.Window:
    return mq.resolve_window(mq.today_for_user(db, user_id), window, start, end)


def _category(db: Session, category: str | None) -> mq.ResolvedCategory | None:
    return mq.resolve_category(db, category) if category else None


@_grounded
def get_net_worth(db: Session, user_id: UUID) -> dict:
    """Net worth as the visible sum of every linked account's balance, so
    the user can see exactly which accounts it's made of."""
    accounts = db.query(LinkedAccount).filter(LinkedAccount.user_id == user_id).all()
    if not accounts:
        return {"net_worth": None, "message": "No linked accounts yet."}

    if all(a.current_balance is None for a in accounts):
        # Accounts synced before per-account balances were stored.
        snapshot = (
            db.query(NetWorthSnapshot)
            .filter(NetWorthSnapshot.user_id == user_id)
            .order_by(NetWorthSnapshot.date.desc())
            .first()
        )
        if snapshot is None:
            return {"net_worth": None, "message": "No balances synced yet."}
        return {
            "net_worth": float(snapshot.net_worth),
            "total_assets": float(snapshot.total_assets),
            "total_liabilities": float(snapshot.total_liabilities),
            "message": "Per-account balances aren't available until the next sync.",
        }

    included, excluded = [], []
    total_assets = total_liabilities = 0.0
    for a in sorted(accounts, key=lambda a: (a.institution_name, a.account_type, a.mask or "")):
        is_liability = a.account_type in LIABILITY_ACCOUNT_TYPES
        entry = {
            "institution": a.institution_name,
            "name": a.name,
            "mask": a.mask,
            "type": a.account_type,
            "kind": "liability" if is_liability else "asset",
            "balance": round(float(a.current_balance or 0), 2),
        }
        if a.status != "active":
            excluded.append({**entry, "reason": f"account is {a.status}; reconnect to include it"})
            continue
        included.append(entry)
        if is_liability:
            total_liabilities += entry["balance"]
        else:
            total_assets += entry["balance"]

    result = {
        "net_worth": round(total_assets - total_liabilities, 2),
        "total_assets": round(total_assets, 2),
        "total_liabilities": round(total_liabilities, 2),
        "accounts": included,
    }
    if excluded:
        result["excluded_accounts"] = excluded
    return result


@_grounded
def get_spending(
    db: Session,
    user_id: UUID,
    window: str | None = None,
    start: str | None = None,
    end: str | None = None,
    category: str | None = None,
    group_by: str | None = None,
    top_n: int | None = None,
    **_extra,
) -> dict:
    return mq.spend_query(
        db, user_id, _window(db, user_id, window, start, end), _category(db, category), group_by, top_n
    )


@_grounded
def compare_spending(
    db: Session,
    user_id: UUID,
    current_window: str = "this_month",
    previous_window: str | None = None,
    category: str | None = None,
    current_start: str | None = None,
    current_end: str | None = None,
    previous_start: str | None = None,
    previous_end: str | None = None,
    **_extra,
) -> dict:
    """previous_window defaults to the period before a this_* window
    (this_month -> last_month)."""
    if previous_window is None and not previous_start:
        previous_window = {"this_week": "last_week", "this_month": "last_month", "this_year": "last_year"}.get(
            current_window
        )
        if previous_window is None:
            raise mq.QueryError("give previous_window (or previous_start/previous_end) to compare against")
    return mq.compare_spend(
        db,
        user_id,
        _window(db, user_id, current_window, current_start, current_end),
        _window(db, user_id, previous_window, previous_start, previous_end),
        _category(db, category),
    )


@_grounded
def get_cash_flow(
    db: Session, user_id: UUID, window: str | None = None, start: str | None = None, end: str | None = None, **_extra
) -> dict:
    return mq.cash_flow(db, user_id, _window(db, user_id, window, start, end))


@_grounded
def find_transactions(
    db: Session,
    user_id: UUID,
    window: str | None = None,
    start: str | None = None,
    end: str | None = None,
    category: str | None = None,
    merchant: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    limit: int = 50,
    **_extra,
) -> dict:
    return mq.find_transactions(
        db,
        user_id,
        _window(db, user_id, window, start, end),
        _category(db, category),
        merchant,
        min_amount,
        max_amount,
        limit,
    )


CHART_KINDS = ("breakdown", "compare", "trend")
_CHART_BREAKDOWN_TOP_N = 6


def _short_range(result: dict) -> str:
    """"Sep 1–14" -- the chart header already sits under a dated reply."""
    return mq.format_range(date.fromisoformat(result["start"]), date.fromisoformat(result["end"])).rsplit(", ", 1)[0]


def _chart_query(window: dict, category: str | None, kind: str | None = None, merchant: str | None = None) -> dict:
    """The transaction filter behind a chart or one of its bars -- the same
    shape as a source chip's query (claude_agent._source_query), so the chat
    can list exactly the rows a bar is drawn from."""
    query = {"start": window["start"], "end": window["end"], "category": category, "merchant": merchant}
    if kind:
        query["kind"] = kind
    return query


def _group_query(result: dict, name: str) -> dict | None:
    """One breakdown bar's rows. The rolled-up "N others" bar has no single filter."""
    if name.endswith(" others") and name.split(" ", 1)[0].isdigit():
        return None
    if result["group_by"] == "merchant" and name == "Unknown merchant":
        return None  # rows with no merchant name; a name filter can't select them
    if result["group_by"] == "merchant":
        return _chart_query(result, result["category"], merchant=name)
    return _chart_query(result, name)


@_grounded
def show_chart(
    db: Session,
    user_id: UUID,
    kind: str,
    window: str | None = None,
    start: str | None = None,
    end: str | None = None,
    category: str | None = None,
    group_by: str | None = None,
    current_window: str = "this_month",
    previous_window: str | None = None,
    current_start: str | None = None,
    current_end: str | None = None,
    previous_start: str | None = None,
    previous_end: str | None = None,
    metric: str = "spending",
    months: int = 6,
    **_extra,
) -> dict:
    """Builds a small chart from a fresh query -- the model only says *what*
    to chart, never the numbers, so a chart can't show anything the data
    doesn't. The spec rides along on the source entry (see run_agent_turn)."""
    cat = _category(db, category)
    query = None
    if kind == "breakdown":
        result = mq.spend_query(
            db, user_id, _window(db, user_id, window, start, end), cat, group_by or "category", _CHART_BREAKDOWN_TOP_N
        )
        query = _chart_query(result, result["category"])
        points = [
            {
                "label": g["name"],
                "value": g["amount"],
                "share": g["share_of_total"],
                "query": _group_query(result, g["name"]),
            }
            for g in result["groups"]
        ]
        title = f"{result['category']} by {result['group_by']}" if cat else f"Spending by {result['group_by']}"
        period = _short_range(result)
        change = None
    elif kind == "compare":
        result = compare_spending.__wrapped__(
            db, user_id, current_window, previous_window, category, current_start, current_end, previous_start, previous_end
        )
        previous = result.get("previous_to_same_point") or result["previous"]
        change = result.get("change_vs_same_point") or result["change"]
        points = [
            {"label": _short_range(w), "value": w["total_spent"], "query": _chart_query(w, result["category"])}
            for w in (previous, result["current"])
        ]
        query = points[-1]["query"]
        title = f"{result['category'] or 'Spending'}: then vs now"
        period = None
    elif kind == "trend":
        result = mq.monthly_series(db, user_id, metric, months, cat)
        # Net is income minus spending: two lists, which is Cash flow's job, not a chart's.
        list_kind = {"spending": None, "income": "income"}.get(metric, "none")
        points = [
            {
                "label": p["label"],
                "value": p["value"],
                "partial": p["partial"],
                "query": None if list_kind == "none" else _chart_query(p, result["category"], list_kind),
            }
            for p in result["points"]
        ]
        if list_kind != "none":
            query = _chart_query(result, result["category"], list_kind)
        what = result["category"] or {"spending": "Spending", "income": "Income", "net": "Income minus spending"}[metric]
        title = f"{what} by month"
        period = _short_range(result)
        change = None
    else:
        raise mq.QueryError(f"kind must be one of: {', '.join(CHART_KINDS)}")

    # A trend needs at least two months with something in them, or it's just one bar.
    if sum(1 for p in points if p["value"]) < (2 if kind == "trend" else 1):
        return {"shown": False, "message": "Nothing to chart in that window -- answer in text instead."}
    chart = {
        "kind": kind,
        "title": title,
        "period": period,
        "unit": "usd",
        "points": points,
        "query": query,
    }
    if kind == "breakdown":
        chart["group_by"] = result["group_by"]
    if change:
        chart["change"] = change
    return {
        "shown": True,
        "chart": chart,
        "message": "The chart is shown under your reply. Give the takeaway in 1-3 lines; don't list every bar.",
    }


MAX_CLARIFY_CHOICES = 4


def ask_clarifying_question(db: Session, user_id: UUID, question: str = "", choices=None, **_extra) -> dict:
    """Ask instead of guessing when a question could mean more than one
    thing. Each choice can carry a window or start/end; the resolved dates
    are added to its label here ("Last weekend · Sep 19–20"), so a choice
    never shows dates the model worked out itself. The choices ride along
    on the source entry (see run_agent_turn) and render as buttons; tapping
    one sends its label as the user's next message."""
    question = (question or "").strip()
    if not question:
        return {"error": "question is required"}
    if not isinstance(choices, list) or not 2 <= len(choices) <= MAX_CLARIFY_CHOICES:
        return {"error": f"give 2-{MAX_CLARIFY_CHOICES} choices"}
    resolved = []
    for choice in choices:
        if isinstance(choice, str):
            choice = {"label": choice}
        label = str((choice or {}).get("label") or "").strip()
        if not label:
            return {"error": "every choice needs a label"}
        if choice.get("window") or choice.get("start"):
            try:
                w = _window(db, user_id, choice.get("window"), choice.get("start"), choice.get("end"))
            except mq.QueryError as e:
                return {"error": str(e), **e.extra}
            label = f"{label} · {_short_range(w.as_dict())}"
        resolved.append({"label": label})
    return {
        "asked": True,
        "clarify": {"question": question, "choices": resolved},
        "message": "The choices are shown as buttons under your reply. Reply with just the question in one "
        "short line; don't list the choices or answer yet.",
    }


def _progress_for(db: Session, user_id: UUID, goal: Goal) -> dict:
    if goal.type == TRACK_SPENDING:
        return _tracker_progress(db, user_id, goal)

    progress_fraction = float(goal.current_progress_amount) / float(goal.target_amount) if goal.target_amount else 0
    result = {
        "id": str(goal.id),
        "type": goal.type,
        "name": goal.name or "Savings",
        "target_amount": float(goal.target_amount),
        "current_progress_amount": float(goal.current_progress_amount),
        "progress_fraction": round(progress_fraction, 4),
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "category": None,
        "window": None,
    }

    if goal.target_date:
        # days_elapsed is NOT floored to 1 here: a goal created moments ago
        # has 0 days elapsed and should look on-pace, not instantly "behind".
        days_elapsed = max((date.today() - goal.created_at.date()).days, 0)
        days_total = max((goal.target_date - goal.created_at.date()).days, 1)
        expected_fraction = min(days_elapsed / days_total, 1.0)
        result["expected_progress_fraction"] = round(expected_fraction, 4)
        result["on_pace"] = progress_fraction >= expected_fraction

    return result


def _tracker_progress(db: Session, user_id: UUID, goal: Goal) -> dict:
    spent = float(goal.current_progress_amount)
    spend: dict = {}
    if goal.category and goal.window:
        try:
            spend = spend_for_tracker(db, user_id, goal.category, goal.window)
            spent = float(spend["total_spent"])
        except mq.QueryError:
            pass

    budget = float(goal.target_amount) if goal.target_amount and float(goal.target_amount) > 0 else None
    over_budget = bool(budget is not None and spent > budget)
    remaining = round(budget - spent, 2) if budget is not None else None
    expected = mq.calendar_elapsed_fraction(goal.window, mq.today_for_user(db, user_id)) if goal.window else None
    spent_fraction = (spent / budget) if budget else None
    # Spending "on pace" means you haven't used more than the even share of
    # the cap for this point in the window -- the inverse of a savings goal.
    on_pace = None
    if budget is not None and expected is not None:
        on_pace = (spent_fraction or 0) <= expected

    result = {
        "id": str(goal.id),
        "type": goal.type,
        "name": goal.name or goal.category or "Spending",
        "category": goal.category,
        "window": goal.window,
        "window_label": TRACKING_WINDOW_LABELS.get(goal.window or "", goal.window),
        "window_start": spend.get("start"),
        "window_end": spend.get("end"),
        "label": spend.get("label"),
        "target_amount": budget or 0.0,
        "current_progress_amount": spent,
        "progress_fraction": round(spent_fraction, 4) if spent_fraction is not None else None,
        "remaining_amount": remaining,
        "target_date": None,
        "transaction_count": spend.get("transaction_count", 0),
        "over_budget": over_budget,
    }
    if expected is not None:
        result["expected_progress_fraction"] = round(expected, 4)
    if on_pace is not None:
        result["on_pace"] = on_pace
    return result


def get_goal_progress(db: Session, user_id: UUID) -> dict:
    goals = list_active_goals(db, user_id)
    payloads = [_progress_for(db, user_id, goal) for goal in goals]
    result: dict = {
        "goals": payloads,
        "active_count": len(payloads),
        "max_goals": MAX_ACTIVE_GOALS,
    }
    if not payloads:
        result["message"] = "No active goal set."
    return result


def _parse_goal_proposal(
    db: Session,
    goal_type: str | None,
    target_amount,
    target_date: str | None,
    category: str | None = None,
    window: str | None = None,
    name: str | None = None,
) -> dict:
    """Shared validation for propose_goal. Returns either {"error": ...} or
    a clean dict the UI can POST to /goals."""
    try:
        kind, title = normalize_goal_kind(goal_type, name, category)
    except GoalValidationError as e:
        return {"error": str(e)}

    if kind == TRACK_SPENDING:
        parsed = _parse_spending_tracker_proposal(db, target_amount, category, window)
        if "error" in parsed:
            return parsed
        parsed["name"] = (name or "").strip() or parsed.get("category") or title or "Spending"
        return parsed

    try:
        amount = float(target_amount)
    except (TypeError, ValueError):
        return {"error": "target_amount must be a number"}
    if amount <= 0:
        return {"error": "target_amount must be positive"}

    parsed_date = None
    if target_date:
        try:
            parsed_date = date.fromisoformat(str(target_date))
        except ValueError:
            return {"error": "target_date must be YYYY-MM-DD"}

    return {
        "type": SAVE,
        "name": title,
        "target_amount": amount,
        "target_date": parsed_date.isoformat() if parsed_date else None,
        "category": None,
        "window": None,
    }


def _parse_spending_tracker_proposal(db: Session, target_amount, category: str | None, window: str | None) -> dict:
    canonical = None
    if category and str(category).strip():
        try:
            canonical = mq.resolve_category(db, category).name
        except mq.QueryError as e:
            return {"error": str(e), **e.extra}

    window_name = window or DEFAULT_TRACKING_WINDOW
    if window_name not in TRACKING_WINDOWS:
        return {"error": f"window must be one of {list(TRACKING_WINDOWS)}"}

    amount = 0.0
    if target_amount not in (None, ""):
        try:
            amount = float(target_amount)
        except (TypeError, ValueError):
            return {"error": "target_amount must be a number"}
        if amount < 0:
            return {"error": "target_amount must be zero or positive"}

    return {
        "type": TRACK_SPENDING,
        "target_amount": amount,
        "target_date": None,
        "category": canonical,
        "window": window_name,
    }


def propose_goal(
    db: Session,
    user_id: UUID,
    type: str | None = None,
    target_amount=None,
    target_date: str | None = None,
    goal_type: str | None = None,
    category: str | None = None,
    window: str | None = None,
    name: str | None = None,
    **_extra,
) -> dict:
    """Draft a goal for the user to confirm in the chat UI.

    Does not write -- Bankr only creates a Goal row after the user taps
    Set goal on the card (POST /goals). Bankr tracks up to MAX_ACTIVE_GOALS
    active goals; this tool reports remaining slots so the UI can add
    another card on the left instead of replacing.
    """
    parsed = _parse_goal_proposal(
        db,
        type or goal_type,
        target_amount,
        target_date,
        category=category,
        window=window,
        name=name,
    )
    if "error" in parsed:
        return parsed

    existing = list_active_goals(db, user_id)
    at_limit = len(existing) >= MAX_ACTIVE_GOALS
    proposal = {
        **parsed,
        "replaces_existing": False,
        "at_limit": at_limit,
        "active_count": len(existing),
        "slots_remaining": max(MAX_ACTIVE_GOALS - len(existing), 0),
    }
    if at_limit:
        return {
            "status": "at_limit",
            "proposal": proposal,
            "message": (
                f"The user already has {MAX_ACTIVE_GOALS} active goals, the maximum. "
                "Do not tell them to confirm a new one."
            ),
        }
    return {
        "status": "proposed",
        "proposal": proposal,
        "message": (
            "Drafted a goal for the user to confirm in the app. "
            "Do not claim it is already created."
        ),
    }


def _any_category(db: Session, name: str):
    """A category of any type (income and transfers too) by name or alias."""
    categories = mq.seed_default_categories(db)
    by_lower = {c.lower(): c for c in categories}
    query = name.strip().lower()
    canonical = by_lower.get(query) or mq.CATEGORY_ALIASES.get(query)
    if canonical is None:
        raise mq.QueryError(f"no category called {name!r}", valid_categories=sorted(categories))
    return categories[canonical]


def propose_rule(
    db: Session, user_id: UUID, merchant: str, category: str, rename_to: str | None = None
) -> dict:
    """Draft "always categorize <merchant> as <category>" for the user to
    confirm. Doesn't create anything -- the confirm card does."""
    merchant = (merchant or "").strip()
    if len(merchant) < 2:
        return {"error": "merchant needs at least 2 characters"}
    try:
        target = _any_category(db, category)
    except mq.QueryError as e:
        return {"error": str(e), **e.extra}
    would_change = preview_rule(db, user_id, merchant, target.id)
    return {
        "status": "proposed",
        "action": {
            "kind": "rule",
            "merchant_contains": merchant,
            "category_id": str(target.id),
            "category": target.name,
            "set_merchant_name": (rename_to or "").strip() or None,
            "would_change": would_change,
        },
        "message": (
            f"Drafted a rule for the user to confirm; it would recategorize {would_change} past "
            "transactions. Do not claim it is already created."
        ),
    }


def get_recurring(db: Session, user_id: UUID, days_ahead: int = 30) -> dict:
    """Recurring bills, subscriptions and paychecks: what's coming up, monthly
    totals, and any price changes. Suggested series aren't confirmed by the
    user yet -- say so when mentioning them."""
    overview = recurring_overview(db, user_id, days_ahead=max(1, min(days_ahead, 90)))
    return {
        "today": overview["today"],
        "monthly_totals_confirmed": overview["monthly"],
        "upcoming": overview["upcoming"][:25],
        "series": [
            {k: s[k] for k in ("name", "kind", "cadence", "status", "last_amount", "typical_amount",
                               "next_expected_date", "monthly_amount", "price_changed", "is_active")}
            for s in overview["series"]
        ],
        "suggested_count": overview["suggested_count"],
    }


def get_budget_status(db: Session, user_id: UUID, month: str | None = None) -> dict:
    """This month's budget (or another, YYYY-MM): each line's budgeted,
    spent, carryover and what's left, plus whether it's over or on pace to go over."""
    try:
        status = budget_service.budget_status(
            db, user_id, budget_service.parse_month(month, mq.today_for_user(db, user_id))
        )
    except budget_service.BudgetError as e:
        return {"error": str(e)}
    if not status["has_budget"]:
        return {**status, "message": "The user hasn't set up a budget yet; they can start one in the Plan view."}
    return status


def _budget_line_key(db: Session, user_id: UUID, name: str) -> tuple[str, str]:
    """(key, display name) for a budget line named in chat: "Flexible" or a category."""
    if name.strip().lower() in {"flex", "flexible", "flexible spending"}:
        return budget_service.FLEX, "Flexible"
    category = mq.resolve_category(db, name)
    parent = mq.seed_default_categories(db)[category.name]
    if parent.parent_category_id is not None:  # "Coffee" -> its parent's budget
        parent = db.get(Category, parent.parent_category_id)
    return str(parent.id), parent.name


def propose_budget_move(
    db: Session, user_id: UUID, from_line: str, to_line: str, amount: float, month: str | None = None
) -> dict:
    """Draft moving money between two budget lines (to cover overspending)
    for the user to confirm on a card."""
    if not amount or amount <= 0:
        return {"error": "amount must be positive"}
    try:
        from_key, from_name = _budget_line_key(db, user_id, from_line)
        to_key, to_name = _budget_line_key(db, user_id, to_line)
        target = budget_service.parse_month(month, mq.today_for_user(db, user_id))
    except (mq.QueryError, budget_service.BudgetError) as e:
        return {"error": str(e)}
    status = budget_service.budget_status(db, user_id, target)
    keys = {line["key"] for line in status["lines"]} | ({"flex"} if status["flex"] else set())
    missing = [n for k, n in ((from_key, from_name), (to_key, to_name)) if k not in keys]
    if missing:
        return {"error": f"no budget line for {', '.join(missing)} this month", "budget_lines": sorted(keys)}
    return {
        "status": "proposed",
        "action": {
            "kind": "budget_move",
            "month": status["month"],
            "from_key": from_key,
            "from_name": from_name,
            "to_key": to_key,
            "to_name": to_name,
            "amount": round(float(amount), 2),
        },
        "message": "Drafted a budget move for the user to confirm. Do not claim it is already done.",
    }


def get_recent_transactions(db: Session, user_id: UUID, limit: int = 20) -> dict:
    rows = (
        db.query(Transaction, Category.name)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .outerjoin(Category, Transaction.bankr_category_id == Category.id)
        .filter(LinkedAccount.user_id == user_id, Transaction.is_split.is_(False))
        .order_by(Transaction.date.desc())
        .limit(limit)
        .all()
    )
    return {
        "transactions": [
            {
                "date": txn.date.isoformat(),
                "amount": float(txn.amount),
                "merchant_name": txn.merchant_name,
                "category": category_name,
                "is_pending": txn.is_pending,
            }
            for txn, category_name in rows
        ]
    }


def get_unusual_transactions(db: Session, user_id: UUID, stddev_threshold: float = 2.5) -> dict:
    """Flag recent charges that are outliers vs. the user's typical charge.

    Baseline is spending outflows only -- paychecks, rent-sized transfers
    and card payments would otherwise inflate the spread so much that no
    ordinary purchase could ever look unusual."""
    since = date.today() - timedelta(days=90)
    rows = (
        db.query(Transaction)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .join(Category, Transaction.bankr_category_id == Category.id)
        .filter(
            LinkedAccount.user_id == user_id,
            Category.type == "expense",
            Transaction.amount < 0,
            Transaction.date >= since,
            *mq.counted_filters(),
        )
        .all()
    )
    amounts = [float(t.amount) for t in rows]
    if len(amounts) < 5:
        return {"unusual_transactions": [], "message": "Not enough history yet."}

    avg, std = mean(amounts), pstdev(amounts) or 1.0
    recent_since = date.today() - timedelta(days=7)
    # Rent and other known bills are big but expected -- never "unusual".
    expected = recurring_merchant_keys(db, user_id)
    unusual = [
        t
        for t in rows
        if t.date >= recent_since
        and abs(float(t.amount) - avg) > stddev_threshold * std
        and merchant_key(t.merchant_name) not in expected
    ]
    return {
        "unusual_transactions": [
            {
                "transaction_id": str(t.id),
                "date": t.date.isoformat(),
                "amount": float(t.amount),
                "merchant_name": t.merchant_name,
            }
            for t in unusual
        ]
    }


# ---------------------------------------------------------------------------
# Calculator: precise arithmetic for projections (compound interest, loan
# payoff timelines, percentage changes, ...) that the model would otherwise
# have to compute by hand. Evaluated via an AST whitelist rather than
# eval()/exec() -- only numeric literals, +-*/%**, parens, and a handful of
# safe builtins are reachable, so there is no name/attribute/import surface
# to escape the sandbox with, unlike a real code-execution tool.
# ---------------------------------------------------------------------------

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"round": round, "abs": abs, "min": min, "max": max, "pow": pow}
_MAX_POW_EXPONENT = 1000  # guards against a DoS-sized computation like 9**9**9


class _UnsafeExpression(ValueError):
    pass


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise _UnsafeExpression(f"unsupported constant {node.value!r}")
        return node.value
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise _UnsafeExpression(f"unsupported operator {type(node.op).__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POW_EXPONENT:
            raise _UnsafeExpression("exponent too large")
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARYOPS.get(type(node.op))
        if op is None:
            raise _UnsafeExpression(f"unsupported operator {type(node.op).__name__}")
        return op(_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS or node.keywords:
            raise _UnsafeExpression("only round/abs/min/max/pow may be called, with no keyword args")
        return _FUNCS[node.func.id](*(_eval_node(arg) for arg in node.args))
    raise _UnsafeExpression(f"unsupported expression: {type(node).__name__}")


def calculate(expression: str) -> dict:
    """Evaluate a precise arithmetic expression, e.g. for compound interest
    (1000 * (1 + 0.05/12) ** (12*5)) or a savings timeline
    ((10000-2500) / 400). Numbers, + - * / % **, parentheses, and
    round/abs/min/max/pow only -- no variables or other function calls."""
    try:
        result = _eval_node(ast.parse(expression, mode="eval"))
    except _UnsafeExpression as e:
        return {"expression": expression, "error": f"unsupported expression ({e})"}
    except ZeroDivisionError:
        return {"expression": expression, "error": "division by zero"}
    except (SyntaxError, TypeError, ValueError, OverflowError) as e:
        return {"expression": expression, "error": f"could not evaluate ({e})"}
    return {"expression": expression, "result": result}


def web_search(query: str, max_results: int = 5, *, client: WebSearchClient | None) -> dict:
    """Look up current information the model wasn't trained on or that
    changes over time (interest rates, inflation, general cost-of-living
    context, ...). `client` is injected by claude_agent.py rather than
    built here, so tests can swap in a fake without a real API key -- same
    reason app/api/deps.py injects the bank aggregator instead of
    constructing PlaidClient() inline."""
    if client is None:
        return {"query": query, "error": "Web search is not configured (set OPENROUTER_API_KEY with AGENT_PROVIDER=openrouter, or BRAVE_SEARCH_API_KEY)."}
    try:
        results = client.search(query, max_results=max_results)
    except Exception as e:
        # A flaky search API/network blip shouldn't fail the whole chat turn.
        return {"query": query, "error": f"Search failed: {e}"}
    return {
        "query": query,
        "results": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results],
    }
