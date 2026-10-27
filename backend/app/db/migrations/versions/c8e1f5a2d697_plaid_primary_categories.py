"""plaid primary categories: replace Bankr's category tree with PFC's 16 primaries

Revision ID: c8e1f5a2d697
Revises: a7c2e9d4f318
Create Date: 2026-10-25 12:00:00.000000

No schema change. Moves everything that points at a legacy category
(Groceries, Dining, Gas, Subscriptions, ...) to its new one, deletes the
legacy rows, and re-maps every transaction the user didn't categorize by
hand. See app/services/category_backfill.py.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = "c8e1f5a2d697"
down_revision: Union[str, None] = "a7c2e9d4f318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Imported here, not at module top, so `alembic history` etc. don't
    # need the app importable.
    from app.services.category_backfill import move_to_plaid_primaries

    move_to_plaid_primaries(Session(bind=op.get_bind()))


def downgrade() -> None:
    # Merged categories (Groceries + Dining -> Food & Drink) can't be split
    # back apart from the data alone.
    raise NotImplementedError("the move to Plaid's primary categories is one-way")
