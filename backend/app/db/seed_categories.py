"""Default Category rows Bankr normalizes every aggregator category into.

Not user-editable in MVP (see backend/README.md) -- this is a small,
backend-maintained mapping, not a full categorization engine.

Three types, and the third one is load-bearing for correct totals:
- income / expense: what "income" and "spending" sum over.
- transfer: money moving between the user's *own* accounts (checking ->
  savings, paying off a credit card, sending to a brokerage). Never
  counted as spending or income -- otherwise a $500 card payment is
  "spent" on top of the $500 of card purchases it pays for. Cash flow
  still reports the ones that leave or enter the linked accounts
  (brokerage, Venmo) separately from spending.

Subcategories hang off a parent via parent_category_id so a question can be
answered at either level: "how much on gas" -> Gas; "on getting around" ->
Transportation, which includes Gas. See app/services/money_query.py.
"""

from sqlalchemy.orm import Session

from app.db.models import Category

# (name, type, parent name or None). Parents must appear before children.
# The 16 primaries of Plaid's Personal Finance Category taxonomy, plus a few
# subcategories for the questions a primary is too coarse to answer
# (groceries vs eating out, car gas, rent vs the bills, software).
DEFAULT_CATEGORIES: list[tuple[str, str, str | None]] = [
    ("Income", "income", None),
    ("Transfer In", "transfer", None),
    ("Transfer Out", "transfer", None),
    ("Loan Payments", "expense", None),
    ("Bank Fees", "expense", None),
    ("Entertainment", "expense", None),
    ("Food & Drink", "expense", None),
    ("Groceries", "expense", "Food & Drink"),
    ("Coffee", "expense", "Food & Drink"),
    ("General Merchandise", "expense", None),
    ("Home Improvement", "expense", None),
    ("Medical", "expense", None),
    ("Personal Care", "expense", None),
    ("General Services", "expense", None),
    ("Software", "expense", "General Services"),
    ("Government & Non-Profit", "expense", None),
    ("Transportation", "expense", None),
    ("Gas", "expense", "Transportation"),
    ("Travel", "expense", None),
    ("Rent & Utilities", "expense", None),
    ("Rent", "expense", "Rent & Utilities"),
    ("Utilities", "expense", "Rent & Utilities"),
]


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
