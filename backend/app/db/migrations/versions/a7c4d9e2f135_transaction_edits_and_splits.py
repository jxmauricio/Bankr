"""let users edit, exclude and split transactions

Revision ID: a7c4d9e2f135
Revises: f6b3c8d1e024
Create Date: 2026-10-07 08:00:00.000000

Adds the user-edit columns to transactions. original_merchant_name is
backfilled from merchant_name so rules can match the bank's name later.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a7c4d9e2f135"
down_revision: Union[str, None] = "f6b3c8d1e024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FLAGS = ("merchant_overridden", "category_overridden", "is_excluded", "is_split")


def upgrade() -> None:
    op.add_column("transactions", sa.Column("original_merchant_name", sa.String(), nullable=True))
    for flag in _FLAGS:
        op.add_column("transactions", sa.Column(flag, sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("transactions", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("transactions", sa.Column("split_parent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "transactions_split_parent_id_fkey", "transactions", "transactions", ["split_parent_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_transactions_split_parent_id", "transactions", ["split_parent_id"])
    op.execute("UPDATE transactions SET original_merchant_name = merchant_name")


def downgrade() -> None:
    op.drop_index("ix_transactions_split_parent_id", "transactions")
    op.drop_constraint("transactions_split_parent_id_fkey", "transactions", type_="foreignkey")
    op.drop_column("transactions", "split_parent_id")
    op.drop_column("transactions", "notes")
    for flag in _FLAGS:
        op.drop_column("transactions", flag)
    op.drop_column("transactions", "original_merchant_name")
