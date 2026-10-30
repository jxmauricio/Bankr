"""Proposals from MCP clients with the write scope (app/mcp_server.py).

An external client never changes the user's data. Its write tools draft a
change with the same validation the in-app agent's propose_* tools use
(app/agent/tools.py), and this module stores it as a pending McpProposal.
The change happens only when the user confirms it in Bankr, which runs the
same service call the in-app confirm cards do.
"""

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent import tools
from app.db.models import McpProposal
from app.services import budget_service, money_query as mq
from app.services.goal_service import GoalLimitReached, GoalValidationError, create_goal
from app.services.rules_service import RuleError, apply_rule_to_existing, create_rule
from app.services.sync_service import refresh_net_worth
from app.services.transaction_edit_service import (
    TransactionEditError,
    TransactionNotFound,
    get_owned_transaction,
    update_transaction,
)

PENDING = "pending"
MAX_PENDING = 25

CONFIRM_MESSAGE = (
    "Saved in Bankr as a proposal. Nothing has changed yet: the user has to open Bankr and confirm it. "
    "Tell them that, and don't say it's done."
)


class ProposalError(ValueError):
    pass


class ProposalNotFound(LookupError):
    pass


def _money(amount: float) -> str:
    return f"${amount:,.2f}"


def _goal_summary(p: dict) -> str:
    if p["type"] == "track_spending":
        target = f" under {_money(p['target_amount'])}" if p["target_amount"] else ""
        return f"Track {p.get('category') or 'all'} spending{target} ({p['window'].replace('_', ' ')})"
    by = f" by {p['target_date']}" if p.get("target_date") else ""
    return f"Save {_money(p['target_amount'])} for {p['name']}{by}"


def draft_recategorization(db: Session, user_id: UUID, transaction_id: str, category: str) -> dict:
    """Like the agent's propose_* tools: validate, return an action or an
    error the client can recover from, write nothing."""
    try:
        txn = get_owned_transaction(db, user_id, UUID(str(transaction_id)))
    except (TransactionNotFound, ValueError):
        return {"error": "no transaction with that id; get ids from find_transactions"}
    if txn.is_split:
        return {"error": "a split transaction is categorized by its splits; the user can edit them in Bankr"}
    try:
        target = tools._any_category(db, user_id, category)
    except mq.QueryError as e:
        return {"error": str(e), **e.extra}
    return {
        "status": "proposed",
        "action": {
            "kind": "recategorize",
            "transaction_id": str(txn.id),
            "date": txn.date.isoformat(),
            "merchant_name": txn.merchant_name,
            "amount": float(txn.amount),
            "category_id": str(target.id),
            "category": target.name,
        },
    }


def _summary(kind: str, p: dict) -> str:
    if kind == "goal":
        return _goal_summary(p)
    if kind == "rule":
        return f"Always put “{p['merchant_contains']}” in {p['category']}"
    if kind == "budget_move":
        return f"Move {_money(p['amount'])} from {p['from_name']} to {p['to_name']} ({p['month']})"
    return f"Put {p['merchant_name'] or 'this transaction'} ({_money(abs(p['amount']))}, {p['date']}) in {p['category']}"


def save(db: Session, user_id: UUID, kind: str, payload: dict, grant_id: UUID | None, source: str) -> dict:
    """Store a validated draft as pending and tell the client what happens
    next. The same pending draft twice is stored once."""
    existing = (
        db.query(McpProposal)
        .filter(McpProposal.user_id == user_id, McpProposal.status == PENDING, McpProposal.kind == kind)
        .all()
    )
    proposal = next((p for p in existing if p.payload == payload), None)
    if proposal is None:
        if db.query(McpProposal).filter(McpProposal.user_id == user_id, McpProposal.status == PENDING).count() >= MAX_PENDING:
            return {
                "error": f"The user already has {MAX_PENDING} proposals waiting in Bankr. "
                "Ask them to confirm or dismiss those first."
            }
        proposal = McpProposal(
            user_id=user_id, grant_id=grant_id, source=source, kind=kind, payload=payload, summary=_summary(kind, payload)
        )
        db.add(proposal)
        db.commit()
    return {
        "status": "pending_user_confirmation",
        "proposal_id": str(proposal.id),
        "summary": proposal.summary,
        "message": CONFIRM_MESSAGE,
    }


def as_dict(p: McpProposal) -> dict:
    return {
        "id": str(p.id),
        "kind": p.kind,
        "summary": p.summary,
        "source": p.source,
        "status": p.status,
        "payload": p.payload,
        "error": p.error,
        "created_at": p.created_at.isoformat(),
        "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None,
    }


def list_pending(db: Session, user_id: UUID) -> list[McpProposal]:
    return (
        db.query(McpProposal)
        .filter(McpProposal.user_id == user_id, McpProposal.status == PENDING)
        .order_by(McpProposal.created_at.desc())
        .all()
    )


def _get_pending(db: Session, user_id: UUID, proposal_id: UUID) -> McpProposal:
    p = db.get(McpProposal, proposal_id)
    if p is None or p.user_id != user_id or p.status != PENDING:
        raise ProposalNotFound(proposal_id)
    return p


def _apply(db: Session, user_id: UUID, kind: str, p: dict) -> None:
    if kind == "goal":
        create_goal(
            db,
            user_id,
            p["type"],
            p["target_amount"],
            date.fromisoformat(p["target_date"]) if p.get("target_date") else None,
            category=p.get("category"),
            window=p.get("window"),
            name=p.get("name"),
        )
    elif kind == "rule":
        rule = create_rule(
            db,
            user_id,
            merchant_contains=p["merchant_contains"],
            set_category_id=UUID(p["category_id"]),
            **({"set_merchant_name": p["set_merchant_name"]} if p.get("set_merchant_name") else {}),
        )
        apply_rule_to_existing(db, user_id, rule)
        refresh_net_worth(db, user_id)
    elif kind == "budget_move":
        month = budget_service.parse_month(p["month"], mq.today_for_user(db, user_id))
        budget_service.move_money(db, user_id, month, p["from_key"], p["to_key"], p["amount"])
        db.commit()
    elif kind == "recategorize":
        txn = get_owned_transaction(db, user_id, UUID(p["transaction_id"]))
        update_transaction(db, txn, category_id=UUID(p["category_id"]))
        refresh_net_worth(db, user_id)
    else:
        raise ProposalError(f"unknown proposal kind {kind!r}")


def confirm(db: Session, user_id: UUID, proposal_id: UUID) -> McpProposal:
    """Make the change. A change that no longer applies (a deleted
    transaction, a full goal list) raises ProposalError and stays pending,
    so the user can see why and dismiss it."""
    proposal = _get_pending(db, user_id, proposal_id)
    try:
        _apply(db, user_id, proposal.kind, proposal.payload)
    except (
        GoalLimitReached,
        GoalValidationError,
        RuleError,
        budget_service.BudgetError,
        TransactionEditError,
        TransactionNotFound,
    ) as e:
        db.rollback()
        message = str(e) if not isinstance(e, TransactionNotFound) else "that transaction no longer exists"
        raise ProposalError(message) from e
    proposal.status = "confirmed"
    proposal.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return proposal


def dismiss(db: Session, user_id: UUID, proposal_id: UUID) -> McpProposal:
    proposal = _get_pending(db, user_id, proposal_id)
    proposal.status = "dismissed"
    proposal.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return proposal
