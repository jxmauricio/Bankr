"""insight dedupe key on insight_logs

Revision ID: e5a2b7c9d013
Revises: d4f1c0a8e912
Create Date: 2026-10-03 12:00:00.000000

Nullable: insights logged before this have no key, so at most one more
duplicate of each can appear after deploy before keys take over.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5a2b7c9d013"
down_revision: Union[str, None] = "d4f1c0a8e912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("insight_logs", sa.Column("dedupe_key", sa.String(), nullable=True))
    op.create_index(op.f("ix_insight_logs_dedupe_key"), "insight_logs", ["dedupe_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_insight_logs_dedupe_key"), table_name="insight_logs")
    op.drop_column("insight_logs", "dedupe_key")
