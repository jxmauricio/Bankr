"""Re-map already-stored transactions after the category table changes.

Every Transaction keeps its raw aggregator category, so a categorization
fix never needs a re-fetch from Plaid -- run this instead. Used by the
7a3e9c2d4b10 migration; safe to re-run any time category_mapper.py changes.

Reads and writes named columns only, never whole Transaction rows: the
migration that calls this runs against the schema as it was then, before
later columns (category_overridden, ...) existed.
"""

from types import SimpleNamespace

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.models import LinkedAccount, Transaction
from app.db.seed_categories import seed_default_categories
from app.services.category_classifier import merchant_key, needs_second_opinion, trusted
from app.services.category_mapper import map_raw_category
from app.services.rules_service import apply_rules, user_rules


def recategorize_all_transactions(db: Session) -> int:
    categories = seed_default_categories(db)
    columns = {c["name"] for c in inspect(db.get_bind()).get_columns("transactions")}
    rows = db.query(
        Transaction.id,
        Transaction.raw_aggregator_category,
        Transaction.amount,
        Transaction.bankr_category_id,
        Transaction.merchant_name,
        LinkedAccount.account_type,
    ).join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
    if "category_overridden" in columns:
        rows = rows.filter(Transaction.category_overridden.is_(False))  # the user picked these; never re-map

    changed = 0
    for txn_id, raw, amount, current, merchant, account_type in rows.all():
        category_id = categories[map_raw_category(raw, float(amount), account_type, merchant)].id
        if current != category_id:
            db.query(Transaction).filter(Transaction.id == txn_id).update(
                {Transaction.bankr_category_id: category_id}, synchronize_session=False
            )
            changed += 1
    db.flush()
    return changed


def remap_with_current_categories(db: Session) -> None:
    """Seed any categories DEFAULT_CATEGORIES gained (e.g. subcategories)
    and re-map every transaction the user didn't categorize by hand, with
    cached guesses and the user's rules applied on top."""
    _remap_uncategorized_by_hand(db, seed_default_categories(db))


def remap_transactions(db: Session, txn_ids: list) -> None:
    """Re-map these rows from their raw Plaid category, with cached guesses
    and the user's rules on top, whether or not the user had picked theirs:
    for when what they picked is gone (category_service.delete_category)."""
    if txn_ids:
        _remap_uncategorized_by_hand(db, seed_default_categories(db), txn_ids)


def _remap_uncategorized_by_hand(db: Session, categories: dict, txn_ids: list | None = None) -> None:
    rows = db.execute(
        text(
            "SELECT t.id, t.raw_aggregator_category, t.amount, t.bankr_category_id, t.aggregator_category_confidence, "
            "t.merchant_name, t.original_merchant_name, t.merchant_overridden, t.is_split, t.split_parent_id, "
            "t.linked_account_id, a.account_type, a.user_id "
            "FROM transactions t JOIN linked_accounts a ON a.id = t.linked_account_id "
            + ("WHERE t.id = ANY(:ids)" if txn_ids is not None else "WHERE NOT t.category_overridden")
        ),
        {"ids": list(txn_ids)} if txn_ids is not None else {},
    ).mappings().all()
    guesses = _cached_guesses(db)
    rules_by_user: dict = {}
    for row in rows:
        txn = SimpleNamespace(**row, category_overridden=False)
        mapped = categories[map_raw_category(
            txn.raw_aggregator_category, float(txn.amount), txn.account_type, txn.original_merchant_name
        )]
        txn.bankr_category_id = mapped.id
        guess = guesses.get(merchant_key(txn.original_merchant_name)) if needs_second_opinion(txn, mapped) else None
        if guess is not None and trusted(guess):  # as a sync would: an unsure guess keeps Plaid's
            txn.bankr_category_id = guess.category_id
        if txn.user_id not in rules_by_user:
            rules_by_user[txn.user_id] = user_rules(db, txn.user_id)
        apply_rules(txn, rules_by_user[txn.user_id])
        if txn.bankr_category_id != row["bankr_category_id"]:
            db.execute(
                text("UPDATE transactions SET bankr_category_id = :category WHERE id = :id"),
                {"category": txn.bankr_category_id, "id": txn.id},
            )
    db.flush()


def _cached_guesses(db: Session) -> dict[str, SimpleNamespace]:
    """merchant_key -> cached guess, in named columns: confidence came after
    the migrations that call this, and a guess without one is trusted."""
    columns = {c["name"] for c in inspect(db.get_bind()).get_columns("merchant_category_guesses")}
    confidence = "confidence" if "confidence" in columns else "NULL AS confidence"
    rows = db.execute(text(f"SELECT merchant_key, category_id, {confidence} FROM merchant_category_guesses")).mappings()
    return {row["merchant_key"]: SimpleNamespace(**row) for row in rows}
