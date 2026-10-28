"""category groups as their own table; budgets by group or by category

Revision ID: b3f8d1a6c742
Revises: a7d2e9c4b318
Create Date: 2026-10-28 15:00:00.000000

A group was a category row with children, so whether a category was a
group depended on the data and every query had to tell the two apart. Now
groups live in category_groups and every category is in exactly one:
- each top-level category with subcategories becomes a group (same name,
  key and owner) and its row goes away; its subcategories join that group;
- each top-level category without any becomes a group of its own, holding
  just that category.
Budgets and budget moves were on top-level categories, so they move to the
group, which a user budgets as one line until they choose a line per
category (category_prefs.budget_mode). A tracker on a group follows it to
goals.group_id. category_prefs also holds a user's own names for built-in
groups and categories.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3f8d1a6c742"
down_revision: Union[str, None] = "a7d2e9c4b318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "category_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("system_key", sa.String(), nullable=True, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_category_groups_user_id", "category_groups", ["user_id"])
    op.create_table(
        "category_prefs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=True),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("category_groups.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("budget_mode", sa.String(), nullable=True),
        sa.UniqueConstraint("user_id", "category_id"),
        sa.UniqueConstraint("user_id", "group_id"),
        sa.CheckConstraint("(category_id IS NULL) <> (group_id IS NULL)", name="category_prefs_one_target"),
    )
    op.create_index("ix_category_prefs_user_id", "category_prefs", ["user_id"])

    # One group per top-level category, then every category into its group.
    op.add_column("categories", sa.Column("group_id", sa.Uuid(), nullable=True))
    op.execute(
        "INSERT INTO category_groups (id, system_key, name, type, user_id) "
        "SELECT gen_random_uuid(), system_key, name, type, user_id FROM categories WHERE parent_category_id IS NULL"
    )
    op.execute(
        "UPDATE categories c SET group_id = g.id FROM category_groups g "
        "WHERE c.parent_category_id IS NULL AND g.name = c.name AND g.user_id IS NOT DISTINCT FROM c.user_id"
    )
    op.execute("UPDATE categories c SET group_id = p.group_id FROM categories p WHERE c.parent_category_id = p.id")

    # Budgets, moves and group trackers move from the top-level row to its group.
    op.add_column("budgets", sa.Column("group_id", sa.Uuid(), sa.ForeignKey("category_groups.id"), nullable=True))
    op.alter_column("budgets", "category_id", nullable=True)
    op.execute("UPDATE budgets b SET group_id = c.group_id, category_id = NULL FROM categories c WHERE c.id = b.category_id")
    op.create_unique_constraint("budgets_user_id_group_id_key", "budgets", ["user_id", "group_id"])
    op.create_check_constraint("budgets_one_target", "budgets", "(category_id IS NULL) <> (group_id IS NULL)")
    for side in ("from", "to"):
        op.add_column(
            "budget_moves", sa.Column(f"{side}_group_id", sa.Uuid(), sa.ForeignKey("category_groups.id"), nullable=True)
        )
        op.execute(
            f"UPDATE budget_moves m SET {side}_group_id = c.group_id, {side}_category_id = NULL "
            f"FROM categories c WHERE c.id = m.{side}_category_id"
        )

    # The rows that were groups, kept aside: their children stop pointing at them below.
    op.execute(
        "CREATE TEMP TABLE old_group_rows ON COMMIT DROP AS "
        "SELECT DISTINCT parent_category_id AS id FROM categories WHERE parent_category_id IS NOT NULL"
    )
    parents = "(SELECT id FROM old_group_rows)"
    op.add_column(
        "goals", sa.Column("group_id", sa.Uuid(), sa.ForeignKey("category_groups.id", ondelete="SET NULL"), nullable=True)
    )
    op.execute(
        f"UPDATE goals g SET group_id = c.group_id, category_id = NULL FROM categories c "
        f"WHERE c.id = g.category_id AND c.id IN {parents}"
    )
    # Nothing else may point at a group's old row (transactions, splits and
    # rules have been on leaves since d9a4b7e2c815); a cached guess or a
    # recurring series that still does has nothing to say about a leaf.
    op.execute(f"DELETE FROM merchant_category_guesses WHERE category_id IN {parents}")
    op.execute(f"UPDATE recurring_series SET category_id = NULL WHERE category_id IN {parents}")
    op.execute("UPDATE categories SET parent_category_id = NULL")
    op.execute(f"DELETE FROM categories WHERE id IN {parents}")

    op.alter_column("categories", "group_id", nullable=False)
    op.create_foreign_key("categories_group_id_fkey", "categories", "category_groups", ["group_id"], ["id"])
    op.create_index("ix_categories_group_id", "categories", ["group_id"])
    op.drop_column("categories", "parent_category_id")


def downgrade() -> None:
    # A group with one category and a category with no parent were the same
    # thing before; a budget split per category had no way to exist.
    raise NotImplementedError("the move to a category_groups table is one-way")
