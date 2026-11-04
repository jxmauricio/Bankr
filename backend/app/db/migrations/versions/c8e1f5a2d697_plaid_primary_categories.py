"""plaid primary categories: replace Bankr's category tree with PFC's 16 primaries

Revision ID: c8e1f5a2d697
Revises: a7c2e9d4f318
Create Date: 2026-10-25 12:00:00.000000

No schema change. Seeds the Plaid-shaped tree (by name: rows get their keys
in a7d2e9c4b318), moves everything that points at a legacy category
(Dining, Fast Food, Shopping, Subscriptions, ...) to its successor, and
deletes the legacy rows.

This used to call into app/services/category_backfill.py, which has since
moved on to later trees and schemas, so a database still before this
revision couldn't upgrade. It now works in plain SQL against the schema as
it is here. Transactions the user didn't categorize by hand only need to
land somewhere sensible: c9e4a2f7d051 and e8b1d4f2a690 re-map all of them
from their raw Plaid category.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8e1f5a2d697"
down_revision: Union[str, None] = "a7c2e9d4f318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (name, type, parent name or None), parents before children: the tree as
# a7d2e9c4b318 keys it (its KEYS), groups and subcategories included, so
# d9a4b7e2c815 has nothing left to seed.
TREE: list[tuple[str, str, str | None]] = [
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

# Legacy name -> the leaf it becomes. Legacy names that are in TREE
# (Groceries, Gas, Travel, ...) keep their rows. "Transfer" splits by sign
# on transactions; anything else on it (a rule, a series) becomes Transfer Out.
LEGACY_MOVES: dict[str, str] = {
    "Transfer": "Transfer Out",
    "Dining": "Restaurants",
    "Fast Food": "Restaurants",
    "Rideshare & Taxi": "Rideshare & Taxis",
    "Auto Maintenance": "Car Maintenance",
    "Rent & Housing": "Rent",
    "Subscriptions": "Entertainment",
    "Shopping": "Other Shopping",
    "Health": "Medical",
    "Fees": "Bank Fees",
    "Other": "Other Shopping",
}
# Spending trackers kept a category name. Dining was all of eating out
# (Restaurants, Fast Food, Coffee, Alcohol & Bars), which is the Eating Out
# slice a7d2e9c4b318 recognizes, not just Restaurants.
GOAL_MOVES: dict[str, str] = {**LEGACY_MOVES, "Dining": "Eating Out"}


def upgrade() -> None:
    bind = op.get_bind()
    # bankr_category_id until g3d7b1e9a542, on databases built before it.
    txn_column = next(
        c["name"] for c in sa.inspect(bind).get_columns("transactions") if c["name"] in ("bankr_category_id", "category_id")
    )

    def ids() -> dict[str, object]:
        return dict(bind.execute(sa.text("SELECT name, id FROM categories WHERE is_system_default")).all())

    # Seed the tree. A legacy name in it keeps its row, re-typed and
    # re-parented.
    existing = ids()
    for name, type_, _parent in TREE:
        if name in existing:
            bind.execute(sa.text("UPDATE categories SET type = :type WHERE id = :id"), {"type": type_, "id": existing[name]})
        else:
            bind.execute(
                sa.text(
                    "INSERT INTO categories (id, name, type, parent_category_id, is_system_default) "
                    "VALUES (gen_random_uuid(), :name, :type, NULL, true)"
                ),
                {"name": name, "type": type_},
            )
    current = ids()
    for name, _type, parent in TREE:
        bind.execute(
            sa.text("UPDATE categories SET parent_category_id = :parent WHERE id = :id"),
            {"parent": current[parent] if parent else None, "id": current[name]},
        )
    parent_of = {name: parent for name, _type, parent in TREE}

    retired = {name: current[name] for name in LEGACY_MOVES if name in current}
    if not retired:
        return
    for name, old in retired.items():
        new = current[LEGACY_MOVES[name]]
        # Budgets and budget moves go on top-level categories only.
        top = current[parent_of[LEGACY_MOVES[name]] or LEGACY_MOVES[name]]
        params = {"old": old, "new": new, "top": top}
        if name == "Transfer":
            bind.execute(
                sa.text(f"UPDATE transactions SET {txn_column} = :into WHERE {txn_column} = :old AND amount > 0"),
                {"old": old, "into": current["Transfer In"]},
            )
        for table, column in (
            ("transactions", txn_column),
            ("rules", "set_category_id"),
            ("merchant_category_guesses", "category_id"),
            ("recurring_series", "category_id"),
        ):
            bind.execute(sa.text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old"), params)
        for column in ("from_category_id", "to_category_id"):
            bind.execute(sa.text(f"UPDATE budget_moves SET {column} = :top WHERE {column} = :old"), params)
        _merge_budgets(bind, old, top)
        bind.execute(
            sa.text("UPDATE goals SET category = :new WHERE category = :old"), {"old": name, "new": GOAL_MOVES[name]}
        )

    # Nothing points at the legacy rows any more, children included: those
    # were re-parented above or are being deleted with them.
    bind.execute(
        sa.text("UPDATE categories SET parent_category_id = NULL WHERE id = ANY(:ids)"), {"ids": list(retired.values())}
    )
    bind.execute(sa.text("DELETE FROM categories WHERE id = ANY(:ids)"), {"ids": list(retired.values())})


def _merge_budgets(bind, old, new) -> None:
    """Move budgets on `old` to `new`. A user with a line on both gets one
    line: amounts added, the earliest start, rollover if either rolled over,
    fixed if either was."""
    rows = bind.execute(
        sa.text('SELECT user_id, amount, "group", rollover, start_month FROM budgets WHERE category_id = :old'),
        {"old": old},
    ).all()
    for user_id, amount, group, rollover, start_month in rows:
        params = {"user_id": user_id, "old": old, "new": new}
        merged = bind.execute(
            sa.text(
                "UPDATE budgets SET amount = amount + :amount, rollover = rollover OR :rollover, "
                "start_month = LEAST(start_month, :start_month), "
                "\"group\" = CASE WHEN :group = 'fixed' THEN 'fixed' ELSE \"group\" END "
                "WHERE user_id = :user_id AND category_id = :new"
            ),
            {**params, "amount": amount, "rollover": rollover, "start_month": start_month, "group": group},
        ).rowcount
        if merged:
            bind.execute(sa.text("DELETE FROM budgets WHERE user_id = :user_id AND category_id = :old"), params)
        else:
            bind.execute(sa.text("UPDATE budgets SET category_id = :new WHERE user_id = :user_id AND category_id = :old"), params)


def downgrade() -> None:
    # Merged categories (Dining + Fast Food -> Restaurants) can't be split
    # back apart from the data alone.
    raise NotImplementedError("the move to Plaid's primary categories is one-way")
