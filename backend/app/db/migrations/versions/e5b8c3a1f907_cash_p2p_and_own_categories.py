"""cash and payments to people as spending; categories of a user's own

Revision ID: e5b8c3a1f907
Revises: d9a4b7e2c815
Create Date: 2026-10-27 16:00:00.000000

Adds categories.user_id for the categories a user makes themselves (see
app/services/category_service.py). Seeds Cash & ATM and Payments to People,
then re-maps every transaction the user didn't categorize by hand, so cash
withdrawals and Zelle/Venmo payments move out of Transfer Out.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = "e5b8c3a1f907"
down_revision: Union[str, None] = "d9a4b7e2c815"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"])

    # Imported here, not at module top, so `alembic history` etc. don't
    # need the app importable.
    from app.services.category_backfill import remap_with_current_categories

    remap_with_current_categories(Session(bind=op.get_bind()))


def downgrade() -> None:
    # Users' own categories carry their picks, rules and budgets, which
    # have nowhere to go without them.
    raise NotImplementedError("categories of a user's own can't be removed by a downgrade")
