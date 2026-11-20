"""onboarding financial profile on users

Revision ID: m6f1a2b3c4d5
Revises: l5e2a9c4b173
Create Date: 2026-11-18 13:20:00.000000

Answers from onboarding (or a free-text story) live on the user as JSON plus
the markdown Centsio reads at the start of every chat turn.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "m6f1a2b3c4d5"
down_revision: Union[str, None] = "l5e2a9c4b173"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("financial_profile", JSONB(), nullable=True))
    op.add_column("users", sa.Column("financial_profile_md", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
    op.drop_column("users", "financial_profile_md")
    op.drop_column("users", "financial_profile")
