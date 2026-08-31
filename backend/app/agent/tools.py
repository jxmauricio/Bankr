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
from statistics import mean, pstdev
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Category, Goal, LinkedAccount, NetWorthSnapshot, Transaction
from app.integrations.web_search import WebSearchClient

PERIOD_DAYS = {"week": 7, "month": 30, "year": 365}


def get_net_worth(db: Session, user_id: UUID) -> dict:
    snapshot = (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.user_id == user_id)
        .order_by(NetWorthSnapshot.date.desc())
        .first()
    )
    if snapshot is None:
        return {"net_worth": None, "as_of": None, "message": "No net worth snapshot yet."}
    return {
        "net_worth": float(snapshot.net_worth),
        "total_assets": float(snapshot.total_assets),
        "total_liabilities": float(snapshot.total_liabilities),
        "as_of": snapshot.date.isoformat(),
    }


def get_spending_by_category(db: Session, user_id: UUID, period: str = "month") -> dict:
    """Returns positive amounts (money spent), even though expense
    transactions are stored as negative (money out) internally.

    Only sums outflows (amount < 0). Without that filter, a refund tagged
    under an expense category (e.g. an airline refund under Transportation)
    can net a category positive, and abs() of that net would misreport a
    net *gain* as spending -- confirmed against real Plaid sandbox data."""
    since = date.today() - timedelta(days=PERIOD_DAYS.get(period, 30))
    rows = (
        db.query(Category.name, func.sum(Transaction.amount))
        .join(Transaction, Transaction.bankr_category_id == Category.id)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(
            LinkedAccount.user_id == user_id,
            Category.type == "expense",
            Transaction.amount < 0,
            Transaction.date >= since,
        )
        .group_by(Category.name)
        .all()
    )
    return {"period": period, "by_category": {name: abs(float(total)) for name, total in rows}}


def get_income_by_period(db: Session, user_id: UUID, period: str = "month") -> dict:
    since = date.today() - timedelta(days=PERIOD_DAYS.get(period, 30))
    total = (
        db.query(func.sum(Transaction.amount))
        .join(Category, Transaction.bankr_category_id == Category.id)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(
            LinkedAccount.user_id == user_id,
            Category.type == "income",
            Transaction.date >= since,
        )
        .scalar()
    )
    return {"period": period, "total_income": float(total or 0)}


def get_goal_progress(db: Session, user_id: UUID) -> dict:
    goal = (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active")
        .order_by(Goal.created_at.desc())
        .first()
    )
    if goal is None:
        return {"goal": None, "message": "No active goal set."}

    progress_fraction = float(goal.current_progress_amount) / float(goal.target_amount) if goal.target_amount else 0
    result = {
        "type": goal.type,
        "target_amount": float(goal.target_amount),
        "current_progress_amount": float(goal.current_progress_amount),
        "progress_fraction": round(progress_fraction, 4),
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
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


def get_recent_transactions(db: Session, user_id: UUID, limit: int = 20) -> dict:
    rows = (
        db.query(Transaction, Category.name)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .outerjoin(Category, Transaction.bankr_category_id == Category.id)
        .filter(LinkedAccount.user_id == user_id)
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
    """Flag recent transactions that are outliers vs. the user's typical transaction size."""
    since = date.today() - timedelta(days=90)
    rows = (
        db.query(Transaction)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(LinkedAccount.user_id == user_id, Transaction.date >= since)
        .all()
    )
    amounts = [float(t.amount) for t in rows]
    if len(amounts) < 5:
        return {"unusual_transactions": [], "message": "Not enough history yet."}

    avg, std = mean(amounts), pstdev(amounts) or 1.0
    recent_since = date.today() - timedelta(days=7)
    unusual = [
        t
        for t in rows
        if t.date >= recent_since and abs(float(t.amount) - avg) > stddev_threshold * std
    ]
    return {
        "unusual_transactions": [
            {"date": t.date.isoformat(), "amount": float(t.amount), "merchant_name": t.merchant_name}
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
        return {"query": query, "error": "Web search is not configured (no BRAVE_SEARCH_API_KEY set)."}
    try:
        results = client.search(query, max_results=max_results)
    except Exception as e:
        # A flaky search API/network blip shouldn't fail the whole chat turn.
        return {"query": query, "error": f"Search failed: {e}"}
    return {
        "query": query,
        "results": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results],
    }
