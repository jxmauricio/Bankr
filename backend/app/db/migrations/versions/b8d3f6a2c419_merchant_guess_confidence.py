"""the classifier's confidence on each cached merchant guess

Revision ID: b8d3f6a2c419
Revises: f4c8a1d3e726
Create Date: 2026-10-25 15:00:00.000000

Nullable: a guess cached before this has no confidence and is trusted as
before (none exist outside development: the classifier was off by default).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8d3f6a2c419"
down_revision: Union[str, None] = "f4c8a1d3e726"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("merchant_category_guesses", sa.Column("confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("merchant_category_guesses", "confidence")
