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
from app.db.seed_categories import DEFAULT_CATEGORIES, seed_default_categories
from app.services.category_classifier import cached_guesses, merchant_key, needs_second_opinion
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


# Where each category of the pre-PFC tree went when Bankr moved to Plaid's
# 16 primaries. "Transfer" is split by sign on transactions; anything else
# that pointed at it (a rule, a budget line) becomes Transfer Out.
LEGACY_CATEGORY_MOVES: dict[str, str] = {
    "Transfer": "Transfer Out",
    "Groceries": "Food & Drink",
    "Dining": "Food & Drink",
    "Restaurants": "Food & Drink",
    "Fast Food": "Food & Drink",
    "Coffee": "Food & Drink",
    "Alcohol & Bars": "Food & Drink",
    "Gas": "Transportation",
    "Rideshare & Taxi": "Transportation",
    "Public Transit": "Transportation",
    "Parking & Tolls": "Transportation",
    "Auto Maintenance": "General Services",
    "Rent & Housing": "Rent & Utilities",
    "Utilities": "Rent & Utilities",
    "Subscriptions": "Entertainment",
    "Shopping": "General Merchandise",
    "Health": "Medical",
    "Fees": "Bank Fees",
    "Other": "General Merchandise",
}


def move_to_plaid_primaries(db: Session) -> None:
    """Retire the legacy categories in LEGACY_CATEGORY_MOVES. Everything
    that points at one moves to its new category first: the user's own
    picks, rules, budgets (merged when two land on one line), budget moves,
    recurring series, cached merchant guesses and spending trackers. Then
    every row the user didn't categorize by hand is re-mapped from its raw
    Plaid category, with the cached guesses and the user's rules applied
    on top, as a sync would.

    Like recategorize_all_transactions, it works in named columns and SQL
    so the migration that calls it keeps running as the schema grows."""
    categories = seed_default_categories(db)
    new_ids = {name: categories[name].id for name in {*LEGACY_CATEGORY_MOVES.values(), "Transfer In"}}
    # A legacy name that's a category again today (Groceries, now under
    # Food & Drink) keeps its row: the seed above already re-parented it.
    retired = [name for name in LEGACY_CATEGORY_MOVES if name not in {n for n, _, _ in DEFAULT_CATEGORIES}]
    old = dict(
        db.execute(
            text("SELECT name, id FROM categories WHERE is_system_default AND name = ANY(:names)"),
            {"names": retired},
        ).all()
    )
    if not old:
        return

    for name, old_id in old.items():
        new_id = new_ids[LEGACY_CATEGORY_MOVES[name]]
        params = {"old": old_id, "new": new_id}
        if name == "Transfer":
            db.execute(
                text("UPDATE transactions SET bankr_category_id = :into WHERE bankr_category_id = :old AND amount > 0"),
                {"old": old_id, "into": new_ids["Transfer In"]},
            )
        for table, column in (
            ("transactions", "bankr_category_id"),
            ("rules", "set_category_id"),
            ("merchant_category_guesses", "category_id"),
            ("recurring_series", "category_id"),
            ("budget_moves", "from_category_id"),
            ("budget_moves", "to_category_id"),
        ):
            db.execute(text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old"), params)
        db.execute(
            text("UPDATE goals SET category = :new_name WHERE category = :old_name"),
            {"old_name": name, "new_name": LEGACY_CATEGORY_MOVES[name]},
        )
        _merge_budgets(db, old_id, new_id)

    db.execute(text("UPDATE categories SET parent_category_id = NULL WHERE id = ANY(:ids)"), {"ids": list(old.values())})
    db.execute(text("DELETE FROM categories WHERE id = ANY(:ids)"), {"ids": list(old.values())})
    db.flush()
    _remap_uncategorized_by_hand(db, categories)


def remap_with_current_categories(db: Session) -> None:
    """Seed any categories DEFAULT_CATEGORIES gained (e.g. subcategories)
    and re-map every transaction the user didn't categorize by hand, with
    cached guesses and the user's rules applied on top."""
    _remap_uncategorized_by_hand(db, seed_default_categories(db))


def _merge_budgets(db: Session, old_id, new_id) -> None:
    """Move budgets on old_id to new_id. A user with a line on both (Groceries
    and Dining, both now Food & Drink) gets one line: amounts added, the
    earliest start, rollover if either rolled over, fixed if either was."""
    for user_id, amount, group, rollover, start_month in db.execute(
        text('SELECT user_id, amount, "group", rollover, start_month FROM budgets WHERE category_id = :old'),
        {"old": old_id},
    ).all():
        merged = db.execute(
            text(
                'UPDATE budgets SET amount = amount + :amount, rollover = rollover OR :rollover, '
                "start_month = LEAST(start_month, :start_month), "
                "\"group\" = CASE WHEN :group = 'fixed' THEN 'fixed' ELSE \"group\" END "
                "WHERE user_id = :user_id AND category_id = :new"
            ),
            {"amount": amount, "rollover": rollover, "start_month": start_month, "group": group, "user_id": user_id, "new": new_id},
        ).rowcount
        if merged:
            db.execute(text("DELETE FROM budgets WHERE user_id = :user_id AND category_id = :old"), {"user_id": user_id, "old": old_id})
        else:
            db.execute(text("UPDATE budgets SET category_id = :new WHERE user_id = :user_id AND category_id = :old"), {"user_id": user_id, "old": old_id, "new": new_id})


def _remap_uncategorized_by_hand(db: Session, categories: dict) -> None:
    rows = db.execute(
        text(
            "SELECT t.id, t.raw_aggregator_category, t.amount, t.bankr_category_id, t.aggregator_category_confidence, "
            "t.merchant_name, t.original_merchant_name, t.merchant_overridden, t.is_split, t.split_parent_id, "
            "t.linked_account_id, a.account_type, a.user_id "
            "FROM transactions t JOIN linked_accounts a ON a.id = t.linked_account_id "
            "WHERE NOT t.category_overridden"
        )
    ).mappings().all()
    guesses = cached_guesses(db, {k for row in rows if (k := merchant_key(row["original_merchant_name"]))})
    rules_by_user: dict = {}
    for row in rows:
        txn = SimpleNamespace(**row, category_overridden=False)
        mapped = categories[map_raw_category(
            txn.raw_aggregator_category, float(txn.amount), txn.account_type, txn.original_merchant_name
        )]
        txn.bankr_category_id = mapped.id
        guess = guesses.get(merchant_key(txn.original_merchant_name)) if needs_second_opinion(txn, mapped) else None
        if guess is not None:
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
