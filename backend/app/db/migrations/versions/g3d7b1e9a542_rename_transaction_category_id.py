"""Rename transactions.bankr_category_id to category_id (the Centsio rebrand)

Revision ID: g3d7b1e9a542
Revises: f2a9c6e1b754
Create Date: 2026-11-01 12:00:00.000000

Earlier migrations were edited to create the column as category_id from the
start, so a fresh database never has the old name: rename only when it's there.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g3d7b1e9a542"
down_revision: Union[str, None] = "f2a9c6e1b754"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("transactions")}


def upgrade() -> None:
    if "bankr_category_id" in _columns():
        op.alter_column("transactions", "bankr_category_id", new_column_name="category_id")


def downgrade() -> None:
    if "category_id" in _columns():
        op.alter_column("transactions", "category_id", new_column_name="bankr_category_id")
