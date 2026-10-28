"""Re-map already-stored transactions after the category table changes.

Every Transaction keeps its raw aggregator category, so a categorization
fix never needs a re-fetch from Plaid -- run this instead. Used by the
7a3e9c2d4b10 migration; safe to re-run any time category_mapper.py changes.

Reads and writes named columns only, never whole Transaction rows: the
migration that calls this runs against the schema as it was then, before
later columns (category_source, ...) existed.
"""

from types import SimpleNamespace

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.models import LinkedAccount, Transaction
from app.db.seed_categories import seed_default_categories, seed_default_groups
from app.services.category_mapper import map_raw_category
from app.services import categorization_service as categorization


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
    if "category_source" in columns:
        rows = rows.filter(Transaction.category_source != "manual")  # the user picked these; never re-map
    elif "category_overridden" in columns:  # before e8b1d4f2a690
        rows = rows.filter(text("NOT transactions.category_overridden"))

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


# Where each category and group of the Plaid-shaped tree went in Monarch's
# (b3f8d1a6c742 -> c9e4a2f7d051). Manual picks, rules, cached guesses,
# recurring series, trackers and budgets follow these; rows nobody picked
# are re-mapped from Plaid afterwards, which is finer (Utilities splits into
# Gas & Electric, Internet & Cable, Phone, ...). A key kept as-is (gas,
# groceries) keeps its row: the seed just moves it to its new group.
MONARCH_CATEGORY_MOVES: dict[str, str] = {
    "income": "other_income",
    "transfer_in": "transfer",
    "transfer_out": "transfer",
    "car_payment": "auto_payment",
    "other_loan_payments": "loan_repayment",
    "bank_fees": "financial_fees",
    "entertainment": "entertainment_and_recreation",
    "restaurants": "restaurants_and_bars",
    "coffee": "coffee_shops",
    "alcohol_and_bars": "restaurants_and_bars",
    "other_food_and_drink": "restaurants_and_bars",
    "online_marketplaces": "general_shopping",
    "superstores": "general_shopping",
    "other_shopping": "general_shopping",
    "software": "general_shopping",
    "personal_care": "personal",
    "childcare": "child_care",
    "education": "school_and_tuition",
    "other_services": "miscellaneous",
    "donations": "charity",
    "government_fees": "miscellaneous",
    "car_maintenance": "auto_maintenance",
    "rideshare_and_taxis": "taxi_and_ride_shares",
    "other_transportation": "public_transit",
    "travel": "travel_and_vacation",
    "payments_to_people": "miscellaneous",
    "utilities": "gas_and_electric",
}
MONARCH_GROUP_MOVES: dict[str, str] = {
    "transfer_in": "transfers",
    "transfer_out": "transfers",
    "loan_payments": "financial",
    "bank_fees": "financial",
    "entertainment": "travel_and_lifestyle",
    "food_and_drink": "food_and_dining",
    "general_merchandise": "shopping",
    "home_improvement": "housing",
    "medical": "health_and_wellness",
    "personal_care": "travel_and_lifestyle",
    "general_services": "other",
    "government_and_non_profit": "financial",
    "transportation": "auto_and_transport",
    "travel": "travel_and_lifestyle",
    "cash_and_atm": "financial",
    "payments_to_people": "other",
    "rent_and_utilities": "housing",
}


def move_to_monarch(db: Session) -> None:
    """Retire the Plaid-shaped categories and groups for Monarch's: seed the
    new tree, move everything that points at a retired category or group to
    its new one (budgets merged where two land on one line), drop the user's
    names for retired ones, then re-map every row the user didn't
    categorize by hand.

    Works in SQL, like the rest of this module, so the migration that calls
    it keeps running as the schema grows."""
    old_categories = _keyed(db, "categories", MONARCH_CATEGORY_MOVES)
    old_groups = _keyed(db, "category_groups", MONARCH_GROUP_MOVES)
    categories = seed_default_categories(db)
    groups = seed_default_groups(db)

    for key, old in old_categories.items():
        new = categories[MONARCH_CATEGORY_MOVES[key]].id
        for table, column in (
            ("transactions", "bankr_category_id"),
            ("rules", "set_category_id"),
            ("merchant_category_guesses", "category_id"),
            ("recurring_series", "category_id"),
            ("goals", "category_id"),
            ("budget_moves", "from_category_id"),
            ("budget_moves", "to_category_id"),
        ):
            db.execute(text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old"), {"old": old, "new": new})
        _merge_budgets(db, "category_id", old, new)
        db.execute(text("DELETE FROM category_prefs WHERE category_id = :old"), {"old": old})
        db.execute(text("DELETE FROM categories WHERE id = :old"), {"old": old})

    for key, old in old_groups.items():
        new = groups[MONARCH_GROUP_MOVES[key]].id
        for table, column in (
            ("categories", "group_id"),  # the user's own categories in it
            ("goals", "group_id"),
            ("budget_moves", "from_group_id"),
            ("budget_moves", "to_group_id"),
        ):
            db.execute(text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old"), {"old": old, "new": new})
        _merge_budgets(db, "group_id", old, new)
        # A group budgeted by category stays so where it lands; its name was for the old group.
        db.execute(
            text(
                "UPDATE category_prefs n SET budget_mode = COALESCE(n.budget_mode, o.budget_mode) "
                "FROM category_prefs o WHERE o.group_id = :old AND n.group_id = :new AND n.user_id = o.user_id"
            ),
            {"old": old, "new": new},
        )
        db.execute(
            text(
                "UPDATE category_prefs o SET group_id = :new, name = NULL WHERE o.group_id = :old AND NOT EXISTS "
                "(SELECT 1 FROM category_prefs n WHERE n.group_id = :new AND n.user_id = o.user_id)"
            ),
            {"old": old, "new": new},
        )
        db.execute(text("DELETE FROM category_prefs WHERE group_id = :old"), {"old": old})
        db.execute(text("DELETE FROM category_groups WHERE id = :old"), {"old": old})

    db.flush()
    _remap_uncategorized_by_hand(db, categories)


def _keyed(db: Session, table: str, moves: dict) -> dict:
    """key -> id of the built-in rows in `table` that `moves` retires (a key
    moving to itself is kept, not retired)."""
    retired = [key for key, new in moves.items() if key != new]
    return dict(
        db.execute(text(f"SELECT system_key, id FROM {table} WHERE system_key = ANY(:keys)"), {"keys": retired}).all()
    )


def _merge_budgets(db: Session, column: str, old, new) -> None:
    """Move budgets on `old` to `new` (both in `column`). A user with a line
    on both gets one line: amounts added, the earliest start, rollover if
    either rolled over, fixed if either was."""
    rows = db.execute(
        text(f'SELECT user_id, amount, "group", rollover, start_month FROM budgets WHERE {column} = :old'), {"old": old}
    ).all()
    for user_id, amount, group, rollover, start_month in rows:
        params = {"user_id": user_id, "old": old, "new": new}
        merged = db.execute(
            text(
                'UPDATE budgets SET amount = amount + :amount, rollover = rollover OR :rollover, '
                "start_month = LEAST(start_month, :start_month), "
                "\"group\" = CASE WHEN :group = 'fixed' THEN 'fixed' ELSE \"group\" END "
                f"WHERE user_id = :user_id AND {column} = :new"
            ),
            {**params, "amount": amount, "rollover": rollover, "start_month": start_month, "group": group},
        ).rowcount
        if merged:
            db.execute(text(f"DELETE FROM budgets WHERE user_id = :user_id AND {column} = :old"), params)
        else:
            db.execute(text(f"UPDATE budgets SET {column} = :new WHERE user_id = :user_id AND {column} = :old"), params)


def remap_transactions(db: Session, txn_ids: list) -> None:
    """Re-map these rows from their raw Plaid category, with cached guesses
    and the user's rules on top, whether or not the user had picked theirs:
    for when what they picked is gone (category_service.delete_category)."""
    if txn_ids:
        _remap_uncategorized_by_hand(db, seed_default_categories(db), txn_ids)


def _remap_uncategorized_by_hand(db: Session, categories: dict, txn_ids: list | None = None) -> None:
    """Run categorization_service's pipeline again over every row the user
    didn't categorize by hand (or just `txn_ids`, whoever picked them)."""
    rows = db.execute(
        text(
            "SELECT t.id, t.raw_aggregator_category, t.amount, t.bankr_category_id, t.aggregator_category_confidence, "
            "t.merchant_name, t.original_merchant_name, t.merchant_overridden, t.is_split, t.split_parent_id, "
            "t.linked_account_id, t.category_source, a.account_type, a.user_id "
            "FROM transactions t JOIN linked_accounts a ON a.id = t.linked_account_id "
            + ("WHERE t.id = ANY(:ids)" if txn_ids is not None else "WHERE t.category_source <> 'manual'")
        ),
        {"ids": list(txn_ids)} if txn_ids is not None else {},
    ).mappings().all()
    guesses = _cached_guesses(db)
    contexts: dict = {}
    for row in rows:
        txn = SimpleNamespace(**{**row, "category_source": categorization.AGGREGATOR})
        if txn.user_id not in contexts:
            contexts[txn.user_id] = categorization.context(db, txn.user_id, categories, guesses)
        categorization.categorize(txn, txn.account_type, contexts[txn.user_id])
        if (txn.bankr_category_id, txn.category_source) != (row["bankr_category_id"], row["category_source"]):
            db.execute(
                text("UPDATE transactions SET bankr_category_id = :category, category_source = :source WHERE id = :id"),
                {"category": txn.bankr_category_id, "source": txn.category_source, "id": txn.id},
            )
    db.flush()


def learn_from_history(db: Session) -> None:
    """Seed LearnedCategory from the picks users already made by hand: a
    merchant whose manual picks all agree counts one hit per pick, so two
    or more are learned at once (categorization_service.LEARN_AFTER)."""
    from app.services.category_classifier import merchant_key

    rows = db.execute(
        text(
            "SELECT a.user_id, t.original_merchant_name, t.bankr_category_id FROM transactions t "
            "JOIN linked_accounts a ON a.id = t.linked_account_id "
            "WHERE t.category_source = 'manual' AND NOT t.is_split AND t.split_parent_id IS NULL "
            "AND t.bankr_category_id IS NOT NULL"
        )
    ).all()
    picks: dict = {}
    for user_id, name, category_id in rows:
        if key := merchant_key(name):
            picks.setdefault((user_id, key), []).append(category_id)
    for (user_id, key), categories in picks.items():
        if len(set(categories)) == 1:
            db.execute(
                text(
                    "INSERT INTO learned_categories (id, user_id, merchant_key, category_id, hits, updated_at) "
                    "VALUES (gen_random_uuid(), :user_id, :key, :category, :hits, now()) "
                    "ON CONFLICT (user_id, merchant_key) DO NOTHING"
                ),
                {"user_id": user_id, "key": key, "category": categories[0], "hits": len(categories)},
            )
    db.flush()


def _cached_guesses(db: Session) -> dict[str, SimpleNamespace]:
    """merchant_key -> cached guess, in named columns: confidence came after
    the migrations that call this, and a guess without one is trusted."""
    columns = {c["name"] for c in inspect(db.get_bind()).get_columns("merchant_category_guesses")}
    confidence = "confidence" if "confidence" in columns else "NULL AS confidence"
    rows = db.execute(text(f"SELECT merchant_key, category_id, {confidence} FROM merchant_category_guesses")).mappings()
    return {row["merchant_key"]: SimpleNamespace(**row) for row in rows}
