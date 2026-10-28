"""Monarch's default groups and categories

Revision ID: c9e4a2f7d051
Revises: b3f8d1a6c742
Create Date: 2026-10-28 18:00:00.000000

No schema change. Replaces the Plaid-shaped default tree (Food & Drink,
General Merchandise, General Services, ...) with Monarch's (Food & Dining,
Shopping, Bills & Utilities, ..., Business, Transfers): see
app/db/seed_categories.py. Everything that pointed at a retired category or
group moves to its successor (category_backfill.MONARCH_*_MOVES), then every
row the user didn't categorize by hand is re-mapped from its Plaid category.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = "c9e4a2f7d051"
down_revision: Union[str, None] = "b3f8d1a6c742"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Imported here, not at module top, so `alembic history` etc. don't
    # need the app importable.
    from app.services.category_backfill import move_to_monarch

    move_to_monarch(Session(bind=op.get_bind()))


def downgrade() -> None:
    # Restaurants and Alcohol & Bars are one category now, as are Transfer In
    # and Transfer Out: a pick of either can't be told apart afterwards.
    raise NotImplementedError("the move to Monarch's categories is one-way")
