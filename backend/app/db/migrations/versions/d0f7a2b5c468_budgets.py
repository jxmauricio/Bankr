"""monthly budgets with rollover and moves

Revision ID: d0f7a2b5c468
Revises: c9e6f1a4b357
Create Date: 2026-10-07 11:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d0f7a2b5c468"
down_revision: Union[str, None] = "c9e6f1a4b357"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "budget_settings",
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mode", sa.String(), nullable=False, server_default="flex"),
        sa.Column("flex_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("flex_rollover", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("start_month", sa.Date(), nullable=False),
    )
    op.create_table(
        "budgets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", UUID, sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("group", sa.String(), nullable=False, server_default="flex"),
        sa.Column("rollover", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("start_month", sa.Date(), nullable=False),
        sa.UniqueConstraint("user_id", "category_id"),
    )
    op.create_index("ix_budgets_user_id", "budgets", ["user_id"])
    op.create_table(
        "budget_moves",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("from_category_id", UUID, sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("to_category_id", UUID, sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_budget_moves_user_id", "budget_moves", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_budget_moves_user_id", "budget_moves")
    op.drop_table("budget_moves")
    op.drop_index("ix_budgets_user_id", "budgets")
    op.drop_table("budgets")
    op.drop_table("budget_settings")
