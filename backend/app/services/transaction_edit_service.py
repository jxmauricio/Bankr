"""User edits to synced transactions: recategorize, rename, note, exclude,
and split one bank charge across several categories.

Edits set the *_overridden flags that sync_service.py checks, so a later
re-sync of the same row never reverts them.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Category, CategoryGroup, LinkedAccount, Transaction
from app.db.seed_categories import BY_GROUP, budget_modes, category_color, display_names, user_categories, user_groups, visible_to

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
        group = db.get(CategoryGroup, category_id)
        if group is not None and visible_to(group, txn.linked_account.user_id):
            raise TransactionEditError(f"pick one of {group.name}'s categories")
        raise TransactionEditError("unknown category")
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
    """Every group and category the user can see (the built-in ones and
    their own, under their names for them), groups first with their
    categories nested, for pickers. A group holding a single category is
    that category, with no children: there's nothing to pick between.

    `kind` says which a node is (only a category can be picked for a
    transaction). Every node carries `group_id` and the group's
    `budget_mode`; `custom`
    marks the user's own, which they can delete; `key` is a built-in's
    stable id and `color` its chart color, so clients never match on names."""
    names = display_names(db, user_id)
    modes = budget_modes(db, user_id)
    by_group: dict[UUID, list[Category]] = {}
    for c in user_categories(db, user_id).values():
        by_group.setdefault(c.group_id, []).append(c)

    def node(item: Category | CategoryGroup, group: CategoryGroup) -> dict:
        return {
            "id": str(item.id),
            "kind": "group" if isinstance(item, CategoryGroup) else "category",
            "key": item.system_key,
            "name": names.get(item.id, item.name),
            "type": item.type,
            "color": category_color(item),
            "custom": item.user_id is not None,
            "renamed": item.id in names,
            "group_id": str(group.id),
            "budget_mode": modes.get(group.id, BY_GROUP),
        }

    tree = []
    for group in user_groups(db, user_id).values():
        members = sorted(by_group.get(group.id, []), key=lambda c: names.get(c.id, c.name))
        if len(members) == 1:
            tree.append({**node(members[0], group), "children": []})
        else:
            tree.append({**node(group, group), "children": [node(c, group) for c in members]})
    type_order = {"expense": 0, "income": 1, "transfer": 2}
    return sorted(tree, key=lambda c: (type_order.get(c["type"], 3), c["name"]))
