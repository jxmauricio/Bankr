"""institution logo on linked_accounts

Revision ID: a1c3e5f7b902
Revises: d0f7a2b5c468
Create Date: 2026-10-12 12:00:00.000000

Nullable: banks linked before this have no logo until their next sync.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1c3e5f7b902"
down_revision: Union[str, None] = "d0f7a2b5c468"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("linked_accounts", sa.Column("institution_logo", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("linked_accounts", "institution_logo")
