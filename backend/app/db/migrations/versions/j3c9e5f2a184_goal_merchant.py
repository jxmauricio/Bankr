"""merchant on spending trackers

Revision ID: j3c9e5f2a184
Revises: i2b8d4c1e073
Create Date: 2026-11-13 16:00:00.000000

A tracker can watch a vendor (Starbucks) when the bank's category is wrong
or too coarse, not only a category.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j3c9e5f2a184"
down_revision: Union[str, None] = "i2b8d4c1e073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("goals", sa.Column("merchant", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("goals", "merchant")
