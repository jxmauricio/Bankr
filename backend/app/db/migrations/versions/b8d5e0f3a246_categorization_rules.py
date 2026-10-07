"""categorization rules

Revision ID: b8d5e0f3a246
Revises: a7c4d9e2f135
Create Date: 2026-10-07 09:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b8d5e0f3a246"
down_revision: Union[str, None] = "a7c4d9e2f135"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_contains", sa.String(), nullable=False),
        sa.Column("amount_min", sa.Numeric(12, 2), nullable=True),
        sa.Column("amount_max", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "linked_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("linked_accounts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("set_category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("set_merchant_name", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rules_user_id", "rules", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_rules_user_id", "rules")
    op.drop_table("rules")
