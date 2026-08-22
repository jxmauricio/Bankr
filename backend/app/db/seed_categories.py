"""Default Category rows Bankr normalizes every aggregator category into.

Not user-editable in MVP (see backend/README.md) -- this is a small,
backend-maintained mapping, not a full categorization engine.
"""

from sqlalchemy.orm import Session

from app.db.models import Category

DEFAULT_CATEGORIES: list[tuple[str, str]] = [
    ("Income", "income"),
    ("Groceries", "expense"),
    ("Dining", "expense"),
    ("Transportation", "expense"),
    ("Rent & Housing", "expense"),
    ("Utilities", "expense"),
    ("Subscriptions", "expense"),
    ("Entertainment", "expense"),
    ("Shopping", "expense"),
    ("Health", "expense"),
    ("Transfer", "expense"),
    ("Other", "expense"),
]


def seed_default_categories(db: Session) -> dict[str, Category]:
    """Idempotently ensure the default categories exist; return name -> Category."""
    existing = {c.name: c for c in db.query(Category).filter(Category.is_system_default.is_(True))}

    for name, type_ in DEFAULT_CATEGORIES:
        if name not in existing:
            category = Category(name=name, type=type_, is_system_default=True)
            db.add(category)
            existing[name] = category

    db.flush()
    return existing
