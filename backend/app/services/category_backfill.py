"""Re-map already-stored transactions after the category table changes.

Every Transaction keeps its raw aggregator category, so a categorization
fix never needs a re-fetch from Plaid -- run this instead. Used by the
7a3e9c2d4b10 migration; safe to re-run any time category_mapper.py changes.

Reads and writes named columns only, never whole Transaction rows: the
migration that calls this runs against the schema as it was then, before
later columns (category_overridden, ...) existed.
"""

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.db.models import LinkedAccount, Transaction
from app.db.seed_categories import seed_default_categories
from app.services.category_mapper import map_raw_category


def recategorize_all_transactions(db: Session) -> int:
    categories = seed_default_categories(db)
    columns = {c["name"] for c in inspect(db.get_bind()).get_columns("transactions")}
    rows = db.query(
        Transaction.id,
        Transaction.raw_aggregator_category,
        Transaction.amount,
        Transaction.bankr_category_id,
        LinkedAccount.account_type,
    ).join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
    if "category_overridden" in columns:
        rows = rows.filter(Transaction.category_overridden.is_(False))  # the user picked these; never re-map

    changed = 0
    for txn_id, raw, amount, current, account_type in rows.all():
        category_id = categories[map_raw_category(raw, float(amount), account_type)].id
        if current != category_id:
            db.query(Transaction).filter(Transaction.id == txn_id).update(
                {Transaction.bankr_category_id: category_id}, synchronize_session=False
            )
            changed += 1
    db.flush()
    return changed
