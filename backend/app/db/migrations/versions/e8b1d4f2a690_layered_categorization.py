"""where each category came from, learned merchants, hidden and excluded categories

Revision ID: e8b1d4f2a690
Revises: c9e4a2f7d051
Create Date: 2026-10-28 21:00:00.000000

transactions.category_overridden becomes transactions.category_source
(manual | rule | learned | classifier | aggregator | fallback; see
app/services/categorization_service.py): a hand-picked row is "manual".
Adds learned_categories, seeded from the picks users already made, rules.
match_exact and category_prefs.hidden; a category's type may now be
"excluded". Then every row the user didn't pick is re-run through the
pipeline, so each one says where its category came from.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = "e8b1d4f2a690"
down_revision: Union[str, None] = "c9e4a2f7d051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions", sa.Column("category_source", sa.String(), nullable=False, server_default="aggregator")
    )
    op.execute("UPDATE transactions SET category_source = 'manual' WHERE category_overridden")
    op.drop_column("transactions", "category_overridden")

    op.add_column("rules", sa.Column("match_exact", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("category_prefs", sa.Column("hidden", sa.Boolean(), nullable=False, server_default="false"))
    op.create_table(
        "learned_categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_key", sa.String(), nullable=False),
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "merchant_key"),
    )
    op.create_index("ix_learned_categories_user_id", "learned_categories", ["user_id"])

    # Imported here, not at module top, so `alembic history` etc. don't
    # need the app importable.
    from app.services.category_backfill import learn_from_history, remap_with_current_categories

    db = Session(bind=op.get_bind())
    learn_from_history(db)
    remap_with_current_categories(db)


def downgrade() -> None:
    op.drop_index("ix_learned_categories_user_id", "learned_categories")
    op.drop_table("learned_categories")
    op.drop_column("category_prefs", "hidden")
    op.drop_column("rules", "match_exact")
    op.add_column(
        "transactions", sa.Column("category_overridden", sa.Boolean(), nullable=False, server_default="false")
    )
    op.execute("UPDATE transactions SET category_overridden = category_source = 'manual'")
    op.drop_column("transactions", "category_source")
