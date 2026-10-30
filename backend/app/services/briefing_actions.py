"""One-tap fixes for daily briefing items, always in two steps: a preview
that says exactly what will change, then the same call with confirm=True.

Every fix goes through the service the rest of the app uses for it: a
recategorize is transaction_edit_service's (so it counts toward learning the
merchant), a rule is rules_service's. "Mark as expected" and "dismiss" only
record what the user said, by the item's key, so it doesn't come back.
"""

from datetime import date
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import BriefingItemState, Category, DailyBriefing
from app.db.seed_categories import display_names, visible_to
from app.integrations.web_search import WebSearchClient
from app.jobs import daily_briefing_job as job
from app.services import subscription_help as help_
from app.services.rules_service import RuleError, apply_rule_to_existing, create_rule, preview_rule
from app.services.transaction_edit_service import (
    TransactionEditError,
    TransactionNotFound,
    get_owned_transaction,
    update_transaction,
)


class BriefingActionError(ValueError):
    pass


class ItemNotFound(LookupError):
    pass


def find_item(db: Session, user_id: UUID, item_key: str) -> dict:
    """The item from the user's latest briefing (today's, or the last one made)."""
    briefing = (
        db.query(DailyBriefing)
        .filter(DailyBriefing.user_id == user_id)
        .order_by(DailyBriefing.day.desc())
        .first()
    )
    item = next((i for i in (briefing.items if briefing else []) if i["key"] == item_key), None)
    if item is None:
        raise ItemNotFound(item_key)
    return item


def _record(db: Session, user_id: UUID, item_key: str, status: str) -> None:
    state = (
        db.query(BriefingItemState)
        .filter(BriefingItemState.user_id == user_id, BriefingItemState.item_key == item_key)
        .one_or_none()
    )
    if state is None:
        db.add(BriefingItemState(user_id=user_id, item_key=item_key, status=status))
    else:
        state.status = status
    try:
        db.flush()
    except IntegrityError:
        db.rollback()


def _category(db: Session, user_id: UUID, item: dict, category_id: UUID | None) -> Category:
    if category_id is None and item.get("suggestion"):
        category_id = UUID(item["suggestion"]["category_id"])
    if category_id is None:
        raise BriefingActionError("pick a category")
    category = db.get(Category, category_id)
    if category is None or not visible_to(category, user_id):
        raise BriefingActionError("unknown category")
    return category


def _category_name(db: Session, user_id: UUID, category: Category) -> str:
    return display_names(db, user_id).get(category.id, category.name)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def run_action(
    db: Session,
    user_id: UUID,
    item_key: str,
    action: str,
    category_id: UUID | None = None,
    confirm: bool = False,
) -> dict:
    """{"summary": what this does / did, "applied": confirm, ...}. Nothing
    changes unless confirm is True. The caller commits."""
    item = find_item(db, user_id, item_key)
    if action not in item["actions"]:
        raise BriefingActionError(f"can't {action.replace('_', ' ')} a {item['type'].replace('_', ' ')} item")

    if action == "recategorize":
        category = _category(db, user_id, item, category_id)
        name = _category_name(db, user_id, category)
        txns = []
        for tid in item["transaction_ids"]:
            try:
                txns.append(get_owned_transaction(db, user_id, UUID(tid)))
            except TransactionNotFound:
                continue  # removed by the bank since
        summary = f"Move {_plural(len(txns), 'charge')} from {item['merchant']} to {name}."
        if confirm:
            try:
                for txn in txns:
                    update_transaction(db, txn, category_id=category.id)
            except TransactionEditError as e:
                db.rollback()
                raise BriefingActionError(str(e))
            _record(db, user_id, item_key, "done")
            summary = f"Moved {_plural(len(txns), 'charge')} from {item['merchant']} to {name}."
        return {"summary": summary, "applied": confirm, "category": name}

    if action == "create_rule":
        category = _category(db, user_id, item, category_id)
        name = _category_name(db, user_id, category)
        merchant = item["merchant"]
        would_change = preview_rule(db, user_id, merchant, category.id)
        summary = (
            f"Always put {merchant} in {name}. "
            f"{_plural(would_change, 'past transaction')} would move there too."
        )
        if confirm:
            try:
                rule = create_rule(db, user_id, merchant_contains=merchant, set_category_id=category.id)
            except RuleError as e:
                db.rollback()
                raise BriefingActionError(str(e))
            changed = apply_rule_to_existing(db, user_id, rule)
            _record(db, user_id, item_key, "done")
            summary = f"Added a rule: {merchant} goes in {name}. Moved {_plural(changed, 'past transaction')}."
            return {"summary": summary, "applied": True, "category": name, "rule_id": str(rule.id), "applied_to": changed}
        return {"summary": summary, "applied": False, "category": name, "would_change": would_change}

    if action == "mark_expected":
        summary = {
            "unusual": f"Mark the {item['merchant']} charge as expected. Bankr won't flag it again.",
            "duplicate": f"Mark both {item['merchant']} charges as expected: not a duplicate.",
            "price_change": f"Accept {item['merchant']}'s new price. Bankr won't flag this change again.",
        }[item["type"]]
        if confirm:
            _record(db, user_id, item_key, "expected")
            summary = "Marked as expected."
        return {"summary": summary, "applied": confirm}

    # dismiss
    summary = "Hide this from your briefing."
    if confirm:
        _record(db, user_id, item_key, "dismissed")
        summary = "Dismissed."
    return {"summary": summary, "applied": confirm}


def item_help(db: Session, user_id: UUID, item_key: str, search: WebSearchClient | None) -> dict:
    """Where to cancel and an email the user can copy, for an item that has
    them. Bankr never sends the email or cancels anything."""
    item = find_item(db, user_id, item_key)
    if not item["has_help"]:
        raise BriefingActionError("nothing to help with for this item")
    merchant = item["merchant"]
    out: dict = {"merchant": merchant, "cancel": None, "emails": []}
    if item["type"] in ("renewal", "price_change", "trial"):
        out["cancel"] = help_.cancel_link(db, merchant, search)
        next_date = date.fromisoformat(item["date"]) if item["type"] == "renewal" else None
        out["emails"].append(help_.cancellation_email(merchant, item["amount"] if next_date else None, next_date))
    if item["type"] == "price_change":
        out["emails"].append(help_.refund_email(merchant, [{"amount": item["amount"], "date": item["date"]}], "price_change"))
    elif item["type"] == "duplicate":
        out["emails"].append(help_.refund_email(merchant, item["charges"], "duplicate"))
    elif item["type"] == "unusual":
        out["emails"].append(help_.refund_email(merchant, [{"amount": item["amount"], "date": item["date"]}], "unrecognized"))
    return out


def summarize_for_agent(db: Session, user_id: UUID) -> dict:
    """Today's briefing for the chat agent: the open items and how many the
    user has already handled. Same items the app shows."""
    briefing = job.get_or_create_briefing(db, user_id)
    data = job.briefing_dict(db, briefing)
    keep = ("type", "title", "detail", "merchant", "amount", "date", "suggestion")
    return {
        "day": data["day"],
        "open_items": [{k: i.get(k) for k in keep} for i in data["items"] if i["status"] == "open"],
        "handled_count": len(data["items"]) - data["open_count"],
        "note": "The user can fix each item with one tap from the briefing card on Home; you can't change anything from chat.",
    }
