"""software subcategory under General Services

Revision ID: f4c8a1d3e726
Revises: e2a7c4b9f150
Create Date: 2026-10-25 17:00:00.000000

No schema change. Seeds Software under General Services, then re-maps
every transaction the user didn't categorize by hand, so charges from
known software merchants (category_mapper.SOFTWARE_MERCHANTS) move to it.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = "f4c8a1d3e726"
down_revision: Union[str, None] = "e2a7c4b9f150"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOFTWARE = "(SELECT id FROM categories WHERE is_system_default AND name = 'Software')"
_PARENT = "(SELECT parent_category_id FROM categories WHERE is_system_default AND name = 'Software')"


def upgrade() -> None:
    # Imported here, not at module top, so `alembic history` etc. don't
    # need the app importable.
    from app.services.category_backfill import remap_with_current_categories

    remap_with_current_categories(Session(bind=op.get_bind()))


def downgrade() -> None:
    # Everything on Software goes back to General Services, then it goes.
    for table, column in (
        ("transactions", "bankr_category_id"),
        ("rules", "set_category_id"),
        ("merchant_category_guesses", "category_id"),
        ("recurring_series", "category_id"),
    ):
        op.execute(f"UPDATE {table} SET {column} = {_PARENT} WHERE {column} = {_SOFTWARE}")
    op.execute("DELETE FROM categories WHERE is_system_default AND name = 'Software'")
