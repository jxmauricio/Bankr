"""Default Category rows Bankr normalizes every aggregator category into.

These built-in rows are shared by every user and never edited. A user can
add categories of their own on top (category_service): those carry their
user_id and are only ever seen, picked or resolved for that user.

Three types, and the third one is load-bearing for correct totals:
- income / expense: what "income" and "spending" sum over.
- transfer: money moving between the user's *own* accounts (checking ->
  savings, paying off a credit card, sending to a brokerage). Never
  counted as spending or income -- otherwise a $500 card payment is
  "spent" on top of the $500 of card purchases it pays for. Cash flow
  still reports the ones that leave or enter the linked accounts
  (brokerage, savings elsewhere) separately from spending.
  Cash taken out and money sent to other people are *not* transfers: the
  money is gone from the user's accounts, so Cash & ATM and Payments to
  People are spending, as in Mint and Monarch.

Two levels, as in Monarch and YNAB. Subcategories hang off a parent via
parent_category_id so a question can be answered at either level: "how much
on gas" -> Gas; "on getting around" -> Transportation, which includes Gas.
See app/services/money_query.py.

A parent with subcategories is a *group*: transactions, splits and rules
always point at one of its subcategories, never at the group itself, so a
group's total is exactly the sum of its children and every group has an
"Other ..." child (or, for Rent & Utilities, a child that takes the rest).
Budgets are the opposite: they go on top-level categories only (see
budget_service). A top-level category with no children is its own leaf.

Code finds a built-in category by its key (Category.system_key), never by
its name: names are for people and may change, keys never do. The Plaid
mapping, the classifier, budgets, health and the clients' colors all go by
key, so renaming "Restaurants" moves nothing. A user's own categories have
no key.
"""

from sqlalchemy.orm import Session

from app.db.models import Category

# (key, name, type, parent key or None). Parents must appear before children.
# The 16 primaries of Plaid's Personal Finance Category taxonomy, split into
# subcategories wherever a primary is too coarse to answer a question people
# ask (eating out, Amazon, car costs, insurance, pets, the mortgage).
DEFAULT_CATEGORIES: list[tuple[str, str, str, str | None]] = [
    ("income", "Income", "income", None),
    ("transfer_in", "Transfer In", "transfer", None),
    ("transfer_out", "Transfer Out", "transfer", None),
    ("loan_payments", "Loan Payments", "expense", None),
    ("mortgage", "Mortgage", "expense", "loan_payments"),
    ("car_payment", "Car Payment", "expense", "loan_payments"),
    ("student_loans", "Student Loans", "expense", "loan_payments"),
    ("other_loan_payments", "Other Loan Payments", "expense", "loan_payments"),
    ("bank_fees", "Bank Fees", "expense", None),
    ("entertainment", "Entertainment", "expense", None),
    ("food_and_drink", "Food & Drink", "expense", None),
    ("groceries", "Groceries", "expense", "food_and_drink"),
    ("restaurants", "Restaurants", "expense", "food_and_drink"),
    ("coffee", "Coffee", "expense", "food_and_drink"),
    ("alcohol_and_bars", "Alcohol & Bars", "expense", "food_and_drink"),
    ("other_food_and_drink", "Other Food & Drink", "expense", "food_and_drink"),
    ("general_merchandise", "General Merchandise", "expense", None),
    ("clothing", "Clothing", "expense", "general_merchandise"),
    ("electronics", "Electronics", "expense", "general_merchandise"),
    ("online_marketplaces", "Online Marketplaces", "expense", "general_merchandise"),
    ("superstores", "Superstores", "expense", "general_merchandise"),
    ("pets", "Pets", "expense", "general_merchandise"),
    ("other_shopping", "Other Shopping", "expense", "general_merchandise"),
    ("home_improvement", "Home Improvement", "expense", None),
    ("medical", "Medical", "expense", None),
    ("personal_care", "Personal Care", "expense", None),
    ("general_services", "General Services", "expense", None),
    ("insurance", "Insurance", "expense", "general_services"),
    ("childcare", "Childcare", "expense", "general_services"),
    ("education", "Education", "expense", "general_services"),
    ("software", "Software", "expense", "general_services"),
    ("other_services", "Other Services", "expense", "general_services"),
    ("government_and_non_profit", "Government & Non-Profit", "expense", None),
    ("taxes", "Taxes", "expense", "government_and_non_profit"),
    ("donations", "Donations", "expense", "government_and_non_profit"),
    ("government_fees", "Government Fees", "expense", "government_and_non_profit"),
    ("transportation", "Transportation", "expense", None),
    ("gas", "Gas", "expense", "transportation"),
    ("car_maintenance", "Car Maintenance", "expense", "transportation"),
    ("rideshare_and_taxis", "Rideshare & Taxis", "expense", "transportation"),
    ("public_transit", "Public Transit", "expense", "transportation"),
    ("parking_and_tolls", "Parking & Tolls", "expense", "transportation"),
    ("other_transportation", "Other Transportation", "expense", "transportation"),
    ("travel", "Travel", "expense", None),
    ("cash_and_atm", "Cash & ATM", "expense", None),
    ("payments_to_people", "Payments to People", "expense", None),
    ("rent_and_utilities", "Rent & Utilities", "expense", None),
    ("rent", "Rent", "expense", "rent_and_utilities"),
    ("utilities", "Utilities", "expense", "rent_and_utilities"),
]

# Parents with subcategories: never a transaction's own category.
GROUPS = frozenset(parent for _, _, _, parent in DEFAULT_CATEGORIES if parent)

# Built-in category -> color slot, most-seen spending first so those get
# distinct hues. Fixed (not cycled per render) so a category's color is the
# same on every screen and every visit: "color follows the entity". The
# palette is the validated dark-mode categorical set (8 hues, checked
# against the app's #10131C surface). The user's own categories are grey.
_COLOR_ORDER = [
    "food_and_drink",
    "transportation",
    "rent_and_utilities",
    "general_merchandise",
    "entertainment",
    "travel",
    "medical",
    "personal_care",
    "income",
    "transfer_in",
    "transfer_out",
    "loan_payments",
    "bank_fees",
    "home_improvement",
    "general_services",
    "government_and_non_profit",
    "groceries",
    "coffee",
    "gas",
    "rent",
    "utilities",
    "software",
    "restaurants",
    "clothing",
    "online_marketplaces",
    "superstores",
    "insurance",
    "mortgage",
    "rideshare_and_taxis",
    "car_maintenance",
    "pets",
    "alcohol_and_bars",
    "electronics",
    "childcare",
    "education",
    "taxes",
    "donations",
    "public_transit",
    "parking_and_tolls",
    "car_payment",
    "student_loans",
    "other_food_and_drink",
    "other_shopping",
    "other_services",
    "other_transportation",
    "government_fees",
    "other_loan_payments",
    "cash_and_atm",
    "payments_to_people",
    "3987e5",
    "d95926",
    "199e70",
    "c98500",
    "d55181",
    "008300",
    "9085e9",
    "e66767",
]
CATEGORY_PALETTE = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767")
UNCOLORED = "#565D72"
_COLORS = {key: CATEGORY_PALETTE[i % len(CATEGORY_PALETTE)] for i, key in enumerate(_COLOR_ORDER)}


def category_color(category: Category) -> str:
    return _COLORS.get(category.system_key, UNCOLORED)


def is_group(db: Session, category: Category) -> bool:
    return db.query(Category.id).filter(Category.parent_category_id == category.id).first() is not None


def user_categories(db: Session, user_id) -> dict[str, Category]:
    """name -> Category: the built-in ones plus the user's own. For matching
    what a person typed or picked by name; code looks built-ins up by key."""
    categories = {c.name: c for c in seed_default_categories(db).values()}
    if user_id is not None:
        categories.update({c.name: c for c in db.query(Category).filter(Category.user_id == user_id)})
    return categories


def visible_to(category: Category, user_id) -> bool:
    return category.user_id is None or category.user_id == user_id


def seed_default_categories(db: Session) -> dict[str, Category]:
    """Idempotently ensure the default categories exist with the right name,
    type and parent; return key -> Category. Also corrects rows seeded by an
    older version of this table (e.g. Transfer used to be type "expense")."""
    existing = {c.system_key: c for c in db.query(Category).filter(Category.system_key.isnot(None))}

    for key, name, type_, parent_key in DEFAULT_CATEGORIES:
        category = existing.get(key)
        if category is None:
            category = Category(system_key=key, is_system_default=True)
            db.add(category)
            existing[key] = category
        category.name = name
        category.type = type_
        if parent_key is None:
            category.parent_category_id = None
        else:
            db.flush()  # parent needs an id before children can point at it
            category.parent_category_id = existing[parent_key].id

    db.flush()
    return existing
