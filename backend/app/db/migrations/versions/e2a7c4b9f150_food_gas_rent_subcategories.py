"""subcategories: Groceries and Coffee, Gas, Rent and Utilities

Revision ID: e2a7c4b9f150
Revises: c8e1f5a2d697
Create Date: 2026-10-25 15:00:00.000000

No schema change. Seeds the new subcategories under Food & Drink,
Transportation and Rent & Utilities, then re-maps every transaction the
user didn't categorize by hand from its stored Plaid category. See
app/services/category_backfill.py.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = "e2a7c4b9f150"
down_revision: Union[str, None] = "c8e1f5a2d697"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SUBCATEGORIES = ["Groceries", "Coffee", "Gas", "Rent", "Utilities"]


def upgrade() -> None:
    # Imported here, not at module top, so `alembic history` etc. don't
    # need the app importable.
    from app.services.category_backfill import remap_with_current_categories

    remap_with_current_categories(Session(bind=op.get_bind()))


def downgrade() -> None:
    # Everything on a subcategory goes back to its parent, then the
    # subcategories go.
    op.execute(
        f"""
        WITH sub AS (
            SELECT id, parent_category_id FROM categories
            WHERE is_system_default AND name IN ({", ".join(f"'{n}'" for n in _SUBCATEGORIES)})
              AND parent_category_id IS NOT NULL
        )
        UPDATE transactions t SET bankr_category_id = sub.parent_category_id
        FROM sub WHERE t.bankr_category_id = sub.id
        """
    )
    for table, column in (
        ("rules", "set_category_id"),
        ("merchant_category_guesses", "category_id"),
        ("recurring_series", "category_id"),
    ):
        op.execute(
            f"""
            UPDATE {table} x SET {column} = c.parent_category_id
            FROM categories c
            WHERE x.{column} = c.id AND c.is_system_default AND c.parent_category_id IS NOT NULL
              AND c.name IN ({", ".join(f"'{n}'" for n in _SUBCATEGORIES)})
            """
        )
    op.execute(
        f"""
        DELETE FROM categories WHERE is_system_default AND parent_category_id IS NOT NULL
          AND name IN ({", ".join(f"'{n}'" for n in _SUBCATEGORIES)})
        """
    )
