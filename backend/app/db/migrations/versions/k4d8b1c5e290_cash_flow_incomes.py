"""pay the user expects, for money left

Revision ID: k4d8b1c5e290
Revises: j3c9e5f2a184
Create Date: 2026-11-13 16:50:00.000000

Detected paychecks are a starting guess. This table is the user's version:
adjust an amount, skip a source, or add income the bank never saw.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "k4d8b1c5e290"
down_revision: Union[str, None] = "j3c9e5f2a184"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cash_flow_incomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("cadence", sa.String(), nullable=False, server_default="monthly"),
        sa.Column("included", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("series_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recurring_series.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payer", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cash_flow_incomes_user_id", "cash_flow_incomes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_cash_flow_incomes_user_id", "cash_flow_incomes")
    op.drop_table("cash_flow_incomes")
