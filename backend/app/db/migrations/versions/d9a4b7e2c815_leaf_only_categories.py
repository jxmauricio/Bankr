"""leaf-only categories: split every coarse primary into subcategories

Revision ID: d9a4b7e2c815
Revises: b8d3f6a2c419
Create Date: 2026-10-27 12:00:00.000000

No schema change. Seeds the new subcategories (Restaurants, Clothing,
Insurance, Mortgage, ...), moves everything that points straight at a group
(Food & Drink, General Merchandise, ...) to one of its subcategories, and
re-maps every transaction the user didn't categorize by hand.

This used to call into app/services/category_backfill.py, which has since
moved on, so a database still before this revision couldn't upgrade. It now
works in plain SQL, by name (keys come in a7d2e9c4b318). c8e1f5a2d697 seeds
the subcategories; transactions the user didn't categorize by hand are
re-mapped by c9e4a2f7d051 and e8b1d4f2a690.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d9a4b7e2c815"
down_revision: Union[str, None] = "b8d3f6a2c419"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Where things that point straight at a group go: mostly its "Other ..."
# child. A pick of Food & Drink, made when Groceries and Coffee were already
# their own choices, meant eating out; Rent & Utilities' description was
# "housing costs that fit neither subcategory", closer to Rent. Budgets,
# budget moves and trackers stay on the group: they cover all of it.
GROUP_MOVES: dict[str, str] = {
    "Loan Payments": "Other Loan Payments",
    "Food & Drink": "Restaurants",
    "General Merchandise": "Other Shopping",
    "General Services": "Other Services",
    "Government & Non-Profit": "Government Fees",
    "Transportation": "Other Transportation",
    "Rent & Utilities": "Rent",
}


def upgrade() -> None:
    bind = op.get_bind()
    # bankr_category_id until g3d7b1e9a542, on databases built before it.
    txn_column = next(
        c["name"] for c in sa.inspect(bind).get_columns("transactions") if c["name"] in ("bankr_category_id", "category_id")
    )
    ids = dict(bind.execute(sa.text("SELECT name, id FROM categories WHERE is_system_default")).all())
    for group, leaf in GROUP_MOVES.items():
        if group not in ids or leaf not in ids:
            continue
        for table, column in (
            ("transactions", txn_column),
            ("rules", "set_category_id"),
            ("merchant_category_guesses", "category_id"),
            ("recurring_series", "category_id"),
        ):
            bind.execute(
                sa.text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old"), {"old": ids[group], "new": ids[leaf]}
            )


def downgrade() -> None:
    # A user's pick or rule moved off a group (Food & Drink -> Restaurants)
    # can't be told apart from one made on the subcategory afterwards.
    raise NotImplementedError("the move to leaf-only categories is one-way")
