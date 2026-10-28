"""A user's own groups and categories, on top of the built-in ones
(seed_categories), and their own names for the built-in ones.

A user's own categories are spending categories, in any spending group:
- a built-in one ("Wedding" in Shopping), where it counts in
  that group's totals and budget, or
- one of their own, made with it ("Hobbies" alone in a Hobbies group) or
  on its own first, to fill later.

Plaid's mapping never assigns one: a transaction gets there only by the
user's pick, a split or a rule. Deleting one sends those transactions back
through the mapping, as if never picked.

A built-in group or category can't be changed for everyone, so renaming one
stores the user's name for it in a CategoryPref; clearing that name brings
the built-in one back. Hiding a built-in category is stored there too: what
would land in it lands in Uncategorized instead.

A category of the user's own can also be *excluded* ("Work Expenses",
"Reimbursable"), in a group of excluded ones: what's in it stays in the
Transactions list but never counts as spending, income or a transfer, since
every total sums one of those types.
"""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    Budget,
    BudgetMove,
    Category,
    CategoryGroup,
    CategoryPref,
    Goal,
    LinkedAccount,
    RecurringSeries,
    Rule,
    Transaction,
)
from app.db.seed_categories import display_names, user_categories, user_groups, visible_to
from app.services.category_backfill import remap_transactions
from app.services.money_query import SLICE_NAMES

MAX_CUSTOM_CATEGORIES = 50
MAX_NAME_LENGTH = 40


class CategoryError(ValueError):
    pass


class CategoryNotFound(LookupError):
    pass


def _visible(db: Session, user_id: UUID, item_id: UUID) -> Category | CategoryGroup:
    item = db.get(Category, item_id) or db.get(CategoryGroup, item_id)
    if item is None or not visible_to(item, user_id):
        raise CategoryNotFound(item_id)
    return item


def _owned(db: Session, user_id: UUID, item_id: UUID) -> Category | CategoryGroup:
    item = _visible(db, user_id, item_id)
    if item.user_id != user_id:
        raise CategoryNotFound(item_id)
    return item


def _members(db: Session, user_id: UUID, group: CategoryGroup) -> list[Category]:
    return [c for c in user_categories(db, user_id).values() if c.group_id == group.id]


def _partner(db: Session, user_id: UUID, item: Category | CategoryGroup) -> Category | CategoryGroup | None:
    """A category alone in its group of the same name, and that group, are
    one thing to the user (one row, one name): each is the other's partner."""
    names = display_names(db, user_id)
    group = item if isinstance(item, CategoryGroup) else item.group
    members = _members(db, user_id, group)
    if len(members) != 1 or names.get(group.id, group.name) != names.get(members[0].id, members[0].name):
        return None
    return members[0] if item is group else group


def _clean_name(db: Session, user_id: UUID, name: str, *, renaming: list | None = None) -> str:
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise CategoryError("a category needs a name")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise CategoryError(f"keep the name to {MAX_NAME_LENGTH} characters")
    # Names are how the assistant and trackers find a category, so they must
    # be unique among everything this user can see.
    skip = {id(item) for item in renaming or []}
    taken = {n.lower() for n, c in user_categories(db, user_id).items() if id(c) not in skip}
    taken |= {n.lower() for n, g in user_groups(db, user_id).items() if id(g) not in skip}
    taken |= {n.lower() for n in SLICE_NAMES}
    if cleaned.lower() in taken:
        raise CategoryError(f"there's already a category called {cleaned!r}")
    return cleaned


def create_group(db: Session, user_id: UUID, name: str) -> CategoryGroup:
    """An empty spending group of the user's own, to put categories in."""
    group = CategoryGroup(name=_clean_name(db, user_id, name), type="expense", user_id=user_id)
    db.add(group)
    db.flush()
    return group


KINDS = ("expense", "excluded")


def create_category(db: Session, user_id: UUID, name: str, group_id: UUID | None = None, kind: str = "expense") -> Category:
    """In group_id, a group of that kind they can see (spending, or one of
    their excluded groups); without one, alone in a new group of the same
    name."""
    if kind not in KINDS:
        raise CategoryError(f"kind must be one of {KINDS}")
    count = db.query(func.count(Category.id)).filter(Category.user_id == user_id).scalar()
    if count >= MAX_CUSTOM_CATEGORIES:
        raise CategoryError(f"you can have up to {MAX_CUSTOM_CATEGORIES} categories of your own")
    cleaned = _clean_name(db, user_id, name)
    if group_id is not None:
        group = db.get(CategoryGroup, group_id)
        if group is None or not visible_to(group, user_id) or group.type != kind:
            raise CategoryError(
                "a new category goes in one of the spending groups" if kind == "expense" else "pick one of your excluded groups"
            )
    else:
        group = CategoryGroup(name=cleaned, type=kind, user_id=user_id)
        db.add(group)
        db.flush()
    category = Category(name=cleaned, type=kind, group_id=group.id, is_system_default=False, user_id=user_id)
    db.add(category)
    db.flush()
    return category


def rename(db: Session, user_id: UUID, item_id: UUID, name: str) -> Category | CategoryGroup:
    """Rename a group or category: the user's own outright; a built-in one
    for this user only. An empty name puts a built-in one's name back. A
    category alone in its group of the same name takes the group along."""
    item = _visible(db, user_id, item_id)
    partner = _partner(db, user_id, item)
    together = [i for i in (item, partner) if i is not None]
    if item.user_id is None and not " ".join((name or "").split()):
        cleaned = None
    else:
        cleaned = _clean_name(db, user_id, name, renaming=together)
    for target in together:
        if target.user_id is not None:
            if cleaned is not None:
                target.name = cleaned
            continue
        _pref(db, user_id, target).name = None if cleaned == target.name else cleaned
    db.flush()
    return item


def _pref(db: Session, user_id: UUID, item: Category | CategoryGroup) -> CategoryPref:
    is_group = isinstance(item, CategoryGroup)
    column = CategoryPref.group_id if is_group else CategoryPref.category_id
    pref = db.query(CategoryPref).filter(CategoryPref.user_id == user_id, column == item.id).one_or_none()
    if pref is None:
        pref = CategoryPref(user_id=user_id, group_id=item.id if is_group else None, category_id=None if is_group else item.id)
        db.add(pref)
    return pref


def set_hidden(db: Session, user_id: UUID, category_id: UUID, hidden: bool) -> int:
    """Hide a built-in category for this user, or show it again. Rows the
    pipeline put there move (to Uncategorized, or back); their own picks
    stay. Returns how many moved."""
    from app.db.seed_categories import seed_default_categories
    from app.services import categorization_service as categorization

    category = _visible(db, user_id, category_id)
    if not isinstance(category, Category) or category.user_id is not None:
        raise CategoryError("only a built-in category can be hidden; delete one of your own instead")
    if category.system_key == categorization.UNCATEGORIZED:
        raise CategoryError("Uncategorized is where everything nothing else places goes; it can't be hidden")
    _pref(db, user_id, category).hidden = hidden
    db.flush()
    moving = (
        db.query(Transaction)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(LinkedAccount.user_id == user_id, Transaction.category_source != categorization.MANUAL)
        .filter(
            Transaction.bankr_category_id == category.id
            if hidden
            else Transaction.category_source == categorization.FALLBACK
        )
        .all()
    )
    return categorization.recategorize(db, user_id, moving, seed_default_categories(db))


def group_pref(db: Session, user_id: UUID, group_id: UUID) -> CategoryPref:
    """This user's settings for a group they can see, made if missing."""
    group = db.get(CategoryGroup, group_id)
    if group is None or not visible_to(group, user_id):
        raise CategoryNotFound(group_id)
    return _pref(db, user_id, group)


def delete(db: Session, user_id: UUID, item_id: UUID) -> int:
    """Delete one of the user's own categories or groups (a group with its
    categories). Their transactions go back to what Plaid, the user's
    other rules and cached guesses say; rules and budgets that only made
    sense for them go with them. Returns how many transactions moved."""
    item = _owned(db, user_id, item_id)
    if isinstance(item, CategoryGroup):
        moved = sum(_delete_category(db, user_id, c) for c in _members(db, user_id, item))
        _delete_group(db, user_id, item)
        return moved
    group = item.group
    moved = _delete_category(db, user_id, item)
    # A group of the user's own goes with its last category when it was only
    # that category's (same name); one they made to fill stays.
    if group.user_id == user_id and not _members(db, user_id, group) and group.name == item.name:
        _delete_group(db, user_id, group)
    return moved


def _active_tracker(db: Session, user_id: UUID, column, item_id: UUID) -> bool:
    return bool(db.query(Goal).filter(Goal.user_id == user_id, column == item_id, Goal.status == "active").count())


def _delete_category(db: Session, user_id: UUID, category: Category) -> int:
    if _active_tracker(db, user_id, Goal.category_id, category.id):
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
        {Transaction.category_source: "aggregator"}, synchronize_session=False
    )
    db.flush()
    remap_transactions(db, txn_ids)
    db.delete(category)
    db.flush()
    return len(txn_ids)


def _delete_group(db: Session, user_id: UUID, group: CategoryGroup) -> None:
    if _active_tracker(db, user_id, Goal.group_id, group.id):
        raise CategoryError("a spending tracker follows this group: change or delete the tracker first")
    db.query(Budget).filter(Budget.group_id == group.id).delete(synchronize_session=False)
    db.query(BudgetMove).filter(
        (BudgetMove.from_group_id == group.id) | (BudgetMove.to_group_id == group.id)
    ).delete(synchronize_session=False)
    db.delete(group)
    db.flush()
