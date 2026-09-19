"""Re-map already-stored transactions after the category table changes.

Every Transaction keeps its raw aggregator category, so a categorization
fix never needs a re-fetch from Plaid -- run this instead. Used by the
7a3e9c2d4b10 migration; safe to re-run any time category_mapper.py changes.
"""

from sqlalchemy.orm import Session

from app.db.models import LinkedAccount, Transaction
from app.db.seed_categories import seed_default_categories
from app.services.category_mapper import map_raw_category


def recategorize_all_transactions(db: Session) -> int:
    categories = seed_default_categories(db)
    changed = 0
    rows = db.query(Transaction, LinkedAccount.account_type).join(
        LinkedAccount, Transaction.linked_account_id == LinkedAccount.id
    )
    for txn, account_type in rows.all():
        raw = txn.raw_aggregator_category
        category_id = categories[map_raw_category(raw, float(txn.amount), account_type)].id
        if txn.bankr_category_id != category_id:
            txn.bankr_category_id = category_id
            changed += 1
    db.flush()
    return changed
