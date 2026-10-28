"""Default Category rows Bankr normalizes every aggregator category into.

These built-in rows are shared by every user and never edited. A user can
add categories of their own on top (category_service): those carry their
user_id and are only ever seen, picked or resolved for that user.

Three types, and the third one is load-bearing for correct totals:
- income / expense: what "income" and "spending" sum over.
- transfer: money moving between the user's *own* accounts (checking ->
  savings, paying off a credit card, sending to a brokerage). Never
  counted as spending or income -- otherwise a $500 card payment is
  "spent" on top of the $500 of card purchases it pays for. Cash flow
  still reports the ones that leave or enter the linked accounts
  (brokerage, savings elsewhere) separately from spending.
  Cash taken out and money sent to other people are *not* transfers: the
  money is gone from the user's accounts, so Cash & ATM and Payments to
  People are spending, as in Mint and Monarch.

Two levels, as in Monarch and YNAB. Subcategories hang off a parent via
parent_category_id so a question can be answered at either level: "how much
on gas" -> Gas; "on getting around" -> Transportation, which includes Gas.
See app/services/money_query.py.

A parent with subcategories is a *group*: transactions, splits and rules
always point at one of its subcategories, never at the group itself, so a
group's total is exactly the sum of its children and every group has an
"Other ..." child (or, for Rent & Utilities, a child that takes the rest).
Budgets are the opposite: they go on top-level categories only (see
budget_service). A top-level category with no children is its own leaf.
"""

from sqlalchemy.orm import Session

from app.db.models import Category

# (name, type, parent name or None). Parents must appear before children.
# The 16 primaries of Plaid's Personal Finance Category taxonomy, split into
# subcategories wherever a primary is too coarse to answer a question people
# ask (eating out, Amazon, car costs, insurance, pets, the mortgage).
DEFAULT_CATEGORIES: list[tuple[str, str, str | None]] = [
    ("Income", "income", None),
    ("Transfer In", "transfer", None),
    ("Transfer Out", "transfer", None),
    ("Loan Payments", "expense", None),
    ("Mortgage", "expense", "Loan Payments"),
    ("Car Payment", "expense", "Loan Payments"),
    ("Student Loans", "expense", "Loan Payments"),
    ("Other Loan Payments", "expense", "Loan Payments"),
    ("Bank Fees", "expense", None),
    ("Entertainment", "expense", None),
    ("Food & Drink", "expense", None),
    ("Groceries", "expense", "Food & Drink"),
    ("Restaurants", "expense", "Food & Drink"),
    ("Coffee", "expense", "Food & Drink"),
    ("Alcohol & Bars", "expense", "Food & Drink"),
    ("Other Food & Drink", "expense", "Food & Drink"),
    ("General Merchandise", "expense", None),
    ("Clothing", "expense", "General Merchandise"),
    ("Electronics", "expense", "General Merchandise"),
    ("Online Marketplaces", "expense", "General Merchandise"),
    ("Superstores", "expense", "General Merchandise"),
    ("Pets", "expense", "General Merchandise"),
    ("Other Shopping", "expense", "General Merchandise"),
    ("Home Improvement", "expense", None),
    ("Medical", "expense", None),
    ("Personal Care", "expense", None),
    ("General Services", "expense", None),
    ("Insurance", "expense", "General Services"),
    ("Childcare", "expense", "General Services"),
    ("Education", "expense", "General Services"),
    ("Software", "expense", "General Services"),
    ("Other Services", "expense", "General Services"),
    ("Government & Non-Profit", "expense", None),
    ("Taxes", "expense", "Government & Non-Profit"),
    ("Donations", "expense", "Government & Non-Profit"),
    ("Government Fees", "expense", "Government & Non-Profit"),
    ("Transportation", "expense", None),
    ("Gas", "expense", "Transportation"),
    ("Car Maintenance", "expense", "Transportation"),
    ("Rideshare & Taxis", "expense", "Transportation"),
    ("Public Transit", "expense", "Transportation"),
    ("Parking & Tolls", "expense", "Transportation"),
    ("Other Transportation", "expense", "Transportation"),
    ("Travel", "expense", None),
    ("Cash & ATM", "expense", None),
    ("Payments to People", "expense", None),
    ("Rent & Utilities", "expense", None),
    ("Rent", "expense", "Rent & Utilities"),
    ("Utilities", "expense", "Rent & Utilities"),
]

# Parents with subcategories: never a transaction's own category.
GROUPS = frozenset(parent for _, _, parent in DEFAULT_CATEGORIES if parent)


def is_group(db: Session, category: Category) -> bool:
    return db.query(Category.id).filter(Category.parent_category_id == category.id).first() is not None


def user_categories(db: Session, user_id) -> dict[str, Category]:
    """name -> Category: the built-in ones plus the user's own."""
    categories = seed_default_categories(db)
    if user_id is not None:
        categories.update({c.name: c for c in db.query(Category).filter(Category.user_id == user_id)})
    return categories


def visible_to(category: Category, user_id) -> bool:
    return category.user_id is None or category.user_id == user_id


def seed_default_categories(db: Session) -> dict[str, Category]:
    """Idempotently ensure the default categories exist with the right type
    and parent; return name -> Category. Also corrects rows seeded by an
    older version of this table (e.g. Transfer used to be type "expense")."""
    existing = {c.name: c for c in db.query(Category).filter(Category.is_system_default.is_(True))}

    for name, type_, parent_name in DEFAULT_CATEGORIES:
        category = existing.get(name)
        if category is None:
            category = Category(name=name, type=type_, is_system_default=True)
            db.add(category)
            existing[name] = category
        category.type = type_
        if parent_name is None:
            category.parent_category_id = None
        else:
            db.flush()  # parent needs an id before children can point at it
            category.parent_category_id = existing[parent_name].id

    db.flush()
    return existing
