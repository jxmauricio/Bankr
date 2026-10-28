"""stable keys for built-in categories; trackers follow a category by id

Revision ID: a7d2e9c4b318
Revises: e5b8c3a1f907
Create Date: 2026-10-28 12:00:00.000000

Adds categories.system_key, what code now looks a built-in category up by
(see app/db/seed_categories.py), and backfills it from today's names.
Spending trackers stored their category's name, which broke on any rename:
they now store goals.category_id, or goals.category_slice for a slice of a
group such as Eating Out (money_query.CATEGORY_SLICES).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7d2e9c4b318"
down_revision: Union[str, None] = "e5b8c3a1f907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The built-in categories as of this revision. Spelled out, not imported:
# seed_categories will change, this migration must not.
KEYS = {
    "Income": "income",
    "Transfer In": "transfer_in",
    "Transfer Out": "transfer_out",
    "Loan Payments": "loan_payments",
    "Mortgage": "mortgage",
    "Car Payment": "car_payment",
    "Student Loans": "student_loans",
    "Other Loan Payments": "other_loan_payments",
    "Bank Fees": "bank_fees",
    "Entertainment": "entertainment",
    "Food & Drink": "food_and_drink",
    "Groceries": "groceries",
    "Restaurants": "restaurants",
    "Coffee": "coffee",
    "Alcohol & Bars": "alcohol_and_bars",
    "Other Food & Drink": "other_food_and_drink",
    "General Merchandise": "general_merchandise",
    "Clothing": "clothing",
    "Electronics": "electronics",
    "Online Marketplaces": "online_marketplaces",
    "Superstores": "superstores",
    "Pets": "pets",
    "Other Shopping": "other_shopping",
    "Home Improvement": "home_improvement",
    "Medical": "medical",
    "Personal Care": "personal_care",
    "General Services": "general_services",
    "Insurance": "insurance",
    "Childcare": "childcare",
    "Education": "education",
    "Software": "software",
    "Other Services": "other_services",
    "Government & Non-Profit": "government_and_non_profit",
    "Taxes": "taxes",
    "Donations": "donations",
    "Government Fees": "government_fees",
    "Transportation": "transportation",
    "Gas": "gas",
    "Car Maintenance": "car_maintenance",
    "Rideshare & Taxis": "rideshare_and_taxis",
    "Public Transit": "public_transit",
    "Parking & Tolls": "parking_and_tolls",
    "Other Transportation": "other_transportation",
    "Travel": "travel",
    "Cash & ATM": "cash_and_atm",
    "Payments to People": "payments_to_people",
    "Rent & Utilities": "rent_and_utilities",
    "Rent": "rent",
    "Utilities": "utilities",
}
SLICES = {"Eating Out": "eating_out"}


def upgrade() -> None:
    op.add_column("categories", sa.Column("system_key", sa.String(), nullable=True))
    op.create_unique_constraint("uq_categories_system_key", "categories", ["system_key"])
    for name, key in KEYS.items():
        op.execute(
            sa.text("UPDATE categories SET system_key = :key WHERE is_system_default AND user_id IS NULL AND name = :name")
            .bindparams(key=key, name=name)
        )

    op.add_column(
        "goals",
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("goals", sa.Column("category_slice", sa.String(), nullable=True))
    for name, key in SLICES.items():
        op.execute(sa.text("UPDATE goals SET category_slice = :key WHERE category = :name").bindparams(key=key, name=name))
    # A user's own category wins over a built-in of the same name; names
    # were unique among what a user could see, so there's at most one each.
    op.execute(
        "UPDATE goals g SET category_id = c.id FROM categories c "
        "WHERE g.category_slice IS NULL AND c.name = g.category AND c.user_id = g.user_id"
    )
    op.execute(
        "UPDATE goals g SET category_id = c.id FROM categories c "
        "WHERE g.category_slice IS NULL AND g.category_id IS NULL AND c.name = g.category AND c.system_key IS NOT NULL"
    )
    op.drop_column("goals", "category")


def downgrade() -> None:
    op.add_column("goals", sa.Column("category", sa.String(), nullable=True))
    op.execute("UPDATE goals g SET category = c.name FROM categories c WHERE c.id = g.category_id")
    for name, key in SLICES.items():
        op.execute(sa.text("UPDATE goals SET category = :name WHERE category_slice = :key").bindparams(key=key, name=name))
    op.drop_column("goals", "category_slice")
    op.drop_column("goals", "category_id")
    op.drop_constraint("uq_categories_system_key", "categories", type_="unique")
    op.drop_column("categories", "system_key")
