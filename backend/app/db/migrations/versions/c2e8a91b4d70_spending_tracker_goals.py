"""spending tracker goals: category + rolling window

Revision ID: c2e8a91b4d70
Revises: 9b1f4d7c6e2a
Create Date: 2026-09-20 15:20:00.000000

track_spending goals watch one expense category over a named window
(this_month, this_week, ...). Savings/debt goals leave both columns null.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2e8a91b4d70"
down_revision: Union[str, None] = "9b1f4d7c6e2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("goals", sa.Column("category", sa.String(), nullable=True))
    op.add_column("goals", sa.Column("window", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("goals", "window")
    op.drop_column("goals", "category")
