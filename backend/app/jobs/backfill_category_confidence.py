"""Fill in Plaid's category confidence on transactions synced before it was
stored, then give the LOW/UNKNOWN ones the same second opinion a fresh sync
would (see app/services/category_classifier.py).

Re-reads full history with a cursor-less /transactions/sync and never saves
the cursor it ends on, so the next real sync carries on where it was.

    python -m app.jobs.backfill_category_confidence <user_id> [<user_id> ...]
"""

import sys
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import LinkedAccount, Transaction
from app.db.seed_categories import seed_default_categories
from app.integrations.bank_aggregator import AggregatorTransaction, BankAggregatorClient
from app.services.category_classifier import (
    build_profile,
    cached_guesses,
    classify_merchants,
    get_classifier,
    merchant_key,
    needs_second_opinion,
    trusted,
)
from app.services.category_mapper import map_raw_category
from app.services.crypto import decrypt_token
from app.services.rules_service import apply_rules, user_rules


def backfill_category_confidence(
    db: Session, user_id: UUID, aggregator: BankAggregatorClient, limit: int | None = None
) -> dict[str, int]:
    """`limit` caps how many merchants are sent to the classifier; None
    sends them all (about $0.003 each), unlike a sync's per-run cap."""
    categories = seed_default_categories(db)
    rules = user_rules(db, user_id)
    linked_accounts = db.query(LinkedAccount).filter(LinkedAccount.user_id == user_id).all()

    from_plaid = {}
    for token in {decrypt_token(la.access_token_ref) for la in linked_accounts}:
        changes = aggregator.sync_transactions(token, None)
        for t in [*changes.added, *changes.modified]:
            from_plaid[t.aggregator_transaction_id] = t

    account_types = {la.id: la.account_type for la in linked_accounts}
    rows = (
        db.query(Transaction)
        .filter(Transaction.linked_account_id.in_(account_types))
        .filter(Transaction.aggregator_transaction_id.in_(from_plaid))
        .all()
    )
    guesses = cached_guesses(db, {k for row in rows if (k := merchant_key(row.original_merchant_name))})
    unclassified: dict[str, tuple[list[AggregatorTransaction], list[Transaction]]] = {}
    from_cache = 0
    for row in rows:
        t = from_plaid[row.aggregator_transaction_id]
        row.aggregator_category_confidence = t.category_confidence
        if row.category_overridden:
            continue
        mapped = categories[map_raw_category(
            row.raw_aggregator_category,
            float(row.amount),
            account_types[row.linked_account_id],
            row.original_merchant_name,
        )]
        if not needs_second_opinion(row, mapped) or apply_rules(row, rules) is not None:
            continue
        key = merchant_key(row.original_merchant_name)
        if key in guesses:
            if trusted(guesses[key]):
                row.bankr_category_id = guesses[key].category_id
                from_cache += 1
            continue
        sent, merchant_rows = unclassified.setdefault(key, ([], []))
        sent.append(t)
        merchant_rows.append(row)

    classified = 0
    classifier = get_classifier()
    if classifier is not None and unclassified:
        pending = {key: (build_profile(key, sent), merchant_rows) for key, (sent, merchant_rows) in unclassified.items()}
        classified = classify_merchants(db, pending, categories, classifier, limit or len(pending))
    db.commit()
    return {
        "rows_updated": len(rows),
        "low_confidence_merchants": len(unclassified),
        "recategorized_from_cache": from_cache,
        "recategorized_by_classifier": classified,
    }


if __name__ == "__main__":
    from app.api.deps import get_aggregator
    from app.db.base import get_session_factory

    db = get_session_factory()()
    try:
        for arg in sys.argv[1:]:
            print(arg, backfill_category_confidence(db, UUID(arg), get_aggregator()))
    finally:
        db.close()
