"""User edits to synced transactions: recategorize, rename, note, exclude,
and split one bank charge across several categories.

Edits set the *_overridden flags that sync_service.py checks, so a later
re-sync of the same row never reverts them.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Category, LinkedAccount, Transaction
from app.db.seed_categories import category_color, is_group, user_categories, visible_to

MAX_SPLITS = 10


class TransactionNotFound(LookupError):
    pass


class TransactionEditError(ValueError):
    pass


def get_owned_transaction(db: Session, user_id: UUID, transaction_id: UUID) -> Transaction:
    txn = (
        db.query(Transaction)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(Transaction.id == transaction_id, LinkedAccount.user_id == user_id)
        .one_or_none()
    )
    if txn is None:
        raise TransactionNotFound(transaction_id)
    return txn


def _category(db: Session, txn: Transaction, category_id: UUID) -> Category:
    category = db.get(Category, category_id)
    if category is None or not visible_to(category, txn.linked_account.user_id):
        raise TransactionEditError("unknown category")
    if is_group(db, category):
        raise TransactionEditError(f"pick one of {category.name}'s subcategories")
    return category


def update_transaction(
    db: Session,
    txn: Transaction,
    *,
    category_id: UUID | None = None,
    merchant_name: str | None = None,
    notes: str | None = None,
    excluded: bool | None = None,
) -> Transaction:
    """Only the fields passed (not None) change. An empty merchant name
    restores the bank's own name; an empty note clears it."""
    if category_id is not None:
        if txn.is_split:
            raise TransactionEditError("a split transaction is categorized by its splits")
        txn.bankr_category_id = _category(db, txn, category_id).id
        txn.category_overridden = True
    if merchant_name is not None:
        cleaned = merchant_name.strip()
        txn.merchant_name = cleaned or txn.original_merchant_name
        txn.merchant_overridden = bool(cleaned)
    if notes is not None:
        txn.notes = notes.strip() or None
    if excluded is not None:
        txn.is_excluded = excluded
    db.flush()
    return txn


def set_splits(db: Session, txn: Transaction, parts: list[dict]) -> list[Transaction]:
    """Replace txn's splits with `parts` ({amount, category_id, note}).
    Amounts use the transaction's sign convention and must sum exactly to
    it; an empty list removes the split."""
    if txn.split_parent_id is not None:
        raise TransactionEditError("can't split a split")
    if len(parts) == 1 or len(parts) > MAX_SPLITS:
        raise TransactionEditError(f"a split needs 2 to {MAX_SPLITS} parts")

    db.query(Transaction).filter(Transaction.split_parent_id == txn.id).delete(synchronize_session=False)
    txn.is_split = bool(parts)
    if not parts:
        db.flush()
        return []

    total = sum(Decimal(str(p["amount"])) for p in parts)
    if total != Decimal(str(txn.amount)).quantize(Decimal("0.01")):
        raise TransactionEditError(f"splits add up to {total}, but the transaction is {txn.amount}")
    if any(Decimal(str(p["amount"])) == 0 for p in parts):
        raise TransactionEditError("each split needs an amount")

    children = []
    for n, part in enumerate(parts, start=1):
        child = Transaction(
            linked_account_id=txn.linked_account_id,
            aggregator_transaction_id=f"{txn.aggregator_transaction_id}:split:{n}",
            amount=part["amount"],
            date=txn.date,
            merchant_name=txn.merchant_name,
            original_merchant_name=txn.original_merchant_name,
            raw_aggregator_category=txn.raw_aggregator_category,
            bankr_category_id=_category(db, txn, part["category_id"]).id,
            category_overridden=True,
            is_pending=txn.is_pending,
            notes=(part.get("note") or "").strip() or None,
            split_parent_id=txn.id,
        )
        db.add(child)
        children.append(child)
    db.flush()
    return children


def category_tree(db: Session, user_id: UUID) -> list[dict]:
    """Every category the user can see (the built-in ones and their own),
    parents first with their children nested, for pickers. `custom` marks
    the user's own, which they can rename or delete; `key` is a built-in's
    stable id and `color` its chart color, so clients never match on names."""
    rows = sorted(user_categories(db, user_id).values(), key=lambda c: c.name)

    def node(c: Category) -> dict:
        return {
            "id": str(c.id),
            "key": c.system_key,
            "name": c.name,
            "type": c.type,
            "color": category_color(c),
            "custom": c.user_id is not None,
        }

    children: dict[UUID, list[dict]] = {}
    for c in rows:
        if c.parent_category_id:
            children.setdefault(c.parent_category_id, []).append(node(c))
    type_order = {"expense": 0, "income": 1, "transfer": 2}
    return sorted(
        ({**node(c), "children": children.get(c.id, [])} for c in rows if c.parent_category_id is None),
        key=lambda c: (type_order.get(c["type"], 3), c["name"]),
    )
