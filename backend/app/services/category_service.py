"""A user's own categories, on top of the built-in ones (seed_categories).

Only spending categories, and only where they keep the tree's rules:
- a subcategory of a built-in group ("Wedding" under General Merchandise),
  which then counts in that group's totals and budget, or
- a top-level category of its own, which can have a budget of its own.
Never a subcategory of a leaf (that would turn it into a group with
transactions already on it) or of another custom category.

Plaid's mapping never assigns one: a transaction gets there only by the
user's pick, a split or a rule. Deleting one sends those transactions back
through the mapping, as if never picked.
"""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Budget, BudgetMove, Category, Goal, RecurringSeries, Rule, Transaction
from app.db.seed_categories import is_group, user_categories
from app.services.category_backfill import remap_transactions
from app.services.money_query import SLICE_NAMES

MAX_CUSTOM_CATEGORIES = 50
MAX_NAME_LENGTH = 40


class CategoryError(ValueError):
    pass


class CategoryNotFound(LookupError):
    pass


def _owned(db: Session, user_id: UUID, category_id: UUID) -> Category:
    category = db.get(Category, category_id)
    if category is None or category.user_id != user_id:
        raise CategoryNotFound(category_id)
    return category


def _clean_name(db: Session, user_id: UUID, name: str, *, renaming: Category | None = None) -> str:
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise CategoryError("a category needs a name")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise CategoryError(f"keep the name to {MAX_NAME_LENGTH} characters")
    # Names are how the assistant and trackers find a category, so they must
    # be unique among everything this user can see.
    taken = {n.lower() for n, c in user_categories(db, user_id).items() if c is not renaming} | {
        n.lower() for n in SLICE_NAMES
    }
    if cleaned.lower() in taken:
        raise CategoryError(f"there's already a category called {cleaned!r}")
    return cleaned


def create_category(db: Session, user_id: UUID, name: str, parent_id: UUID | None = None) -> Category:
    count = db.query(func.count(Category.id)).filter(Category.user_id == user_id).scalar()
    if count >= MAX_CUSTOM_CATEGORIES:
        raise CategoryError(f"you can have up to {MAX_CUSTOM_CATEGORIES} categories of your own")
    if parent_id is not None:
        parent = db.get(Category, parent_id)
        if parent is None or parent.user_id is not None or parent.type != "expense" or not is_group(db, parent):
            raise CategoryError("a new subcategory goes under one of the spending groups")
    category = Category(
        name=_clean_name(db, user_id, name),
        type="expense",
        parent_category_id=parent_id,
        is_system_default=False,
        user_id=user_id,
    )
    db.add(category)
    db.flush()
    return category


def rename_category(db: Session, user_id: UUID, category_id: UUID, name: str) -> Category:
    category = _owned(db, user_id, category_id)
    category.name = _clean_name(db, user_id, name, renaming=category)
    db.flush()
    return category


def delete_category(db: Session, user_id: UUID, category_id: UUID) -> int:
    """Delete one of the user's categories. Its transactions go back to
    what Plaid, the user's other rules and cached guesses say; rules and
    budgets that only made sense for it go with it. Returns how many
    transactions moved."""
    category = _owned(db, user_id, category_id)
    if db.query(Goal).filter(Goal.user_id == user_id, Goal.category_id == category.id, Goal.status == "active").count():
        raise CategoryError("a spending tracker follows this category: change or delete the tracker first")

    db.query(Rule).filter(Rule.user_id == user_id, Rule.set_category_id == category.id).delete(synchronize_session=False)
    db.query(Budget).filter(Budget.category_id == category.id).delete(synchronize_session=False)
    db.query(BudgetMove).filter(
        (BudgetMove.from_category_id == category.id) | (BudgetMove.to_category_id == category.id)
    ).delete(synchronize_session=False)
    db.query(RecurringSeries).filter(RecurringSeries.category_id == category.id).update(
        {RecurringSeries.category_id: None}, synchronize_session=False
    )

    txn_ids = [row.id for row in db.query(Transaction.id).filter(Transaction.bankr_category_id == category.id)]
    # A split's parts stay hand-picked (the split is); a whole row isn't any more.
    db.query(Transaction).filter(Transaction.id.in_(txn_ids), Transaction.split_parent_id.is_(None)).update(
        {Transaction.category_overridden: False}, synchronize_session=False
    )
    db.flush()
    remap_transactions(db, txn_ids)
    db.delete(category)
    db.flush()
    return len(txn_ids)
