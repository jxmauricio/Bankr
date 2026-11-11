"""available_balance and credit_limit on linked_accounts

Revision ID: h1a4c8e2d960
Revises: g3d7b1e9a542
Create Date: 2026-11-11 15:15:00.000000

Credit cards show utilization on Home; both land on the next bank sync.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h1a4c8e2d960"
down_revision: Union[str, None] = "g3d7b1e9a542"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("linked_accounts", sa.Column("available_balance", sa.Numeric(14, 2), nullable=True))
    op.add_column("linked_accounts", sa.Column("credit_limit", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("linked_accounts", "credit_limit")
    op.drop_column("linked_accounts", "available_balance")
