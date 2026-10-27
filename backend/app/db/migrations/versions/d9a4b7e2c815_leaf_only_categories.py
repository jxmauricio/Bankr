"""leaf-only categories: split every coarse primary into subcategories

Revision ID: d9a4b7e2c815
Revises: b8d3f6a2c419
Create Date: 2026-10-27 12:00:00.000000

No schema change. Seeds the new subcategories (Restaurants, Clothing,
Insurance, Mortgage, ...), moves everything that points straight at a group
(Food & Drink, General Merchandise, ...) to one of its subcategories, and
re-maps every transaction the user didn't categorize by hand. See
app/services/category_backfill.py.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = "d9a4b7e2c815"
down_revision: Union[str, None] = "b8d3f6a2c419"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Imported here, not at module top, so `alembic history` etc. don't
    # need the app importable.
    from app.services.category_backfill import move_off_groups

    move_off_groups(Session(bind=op.get_bind()))


def downgrade() -> None:
    # A user's pick or rule moved off a group (Food & Drink -> Restaurants)
    # can't be told apart from one made on the subcategory afterwards.
    raise NotImplementedError("the move to leaf-only categories is one-way")
