"""Default groups and categories Bankr normalizes every aggregator category into.

These built-in rows are shared by every user and never edited by one. A
user can add groups and categories of their own on top (category_service),
which carry their user_id and are only ever seen, picked or resolved for
that user, and can rename a built-in one for themselves (CategoryPref).

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

Two levels, as in Monarch and YNAB: groups (CategoryGroup) over categories,
so a question can be answered at either level: "how much on gas" -> Gas;
"on getting around" -> Transportation, which includes Gas. See
app/services/money_query.py. Transactions, splits and rules always point at
a category, never a group, so a group's total is exactly the sum of its
categories; every group with several has an "Other ..." one (or, for Rent &
Utilities, one that takes the rest). A category that stands alone (Travel)
is the only one in a group of the same name and key.

Code finds a built-in group or category by its key (system_key), never by
its name: names are for people and may change, keys never do. The Plaid
mapping, the classifier, budgets, health and the clients' colors all go by
key, so renaming "Restaurants" moves nothing.
"""

from sqlalchemy.orm import Session

from app.db.models import Category, CategoryGroup, CategoryPref

# (key, name, type). The 16 primaries of Plaid's Personal Finance Category
# taxonomy, plus Cash & ATM and Payments to People.
DEFAULT_GROUPS: list[tuple[str, str, str]] = [
    ("income", "Income", "income"),
    ("transfer_in", "Transfer In", "transfer"),
    ("transfer_out", "Transfer Out", "transfer"),
    ("loan_payments", "Loan Payments", "expense"),
    ("bank_fees", "Bank Fees", "expense"),
    ("entertainment", "Entertainment", "expense"),
    ("food_and_drink", "Food & Drink", "expense"),
    ("general_merchandise", "General Merchandise", "expense"),
    ("home_improvement", "Home Improvement", "expense"),
    ("medical", "Medical", "expense"),
    ("personal_care", "Personal Care", "expense"),
    ("general_services", "General Services", "expense"),
    ("government_and_non_profit", "Government & Non-Profit", "expense"),
    ("transportation", "Transportation", "expense"),
    ("travel", "Travel", "expense"),
    ("cash_and_atm", "Cash & ATM", "expense"),
    ("payments_to_people", "Payments to People", "expense"),
    ("rent_and_utilities", "Rent & Utilities", "expense"),
]

# (key, name, type, group key). The primaries split into categories wherever
# one is too coarse to answer a question people ask (eating out, Amazon, car
# costs, insurance, pets, the mortgage).
DEFAULT_CATEGORIES: list[tuple[str, str, str, str]] = [
    ("income", "Income", "income", "income"),
    ("transfer_in", "Transfer In", "transfer", "transfer_in"),
    ("transfer_out", "Transfer Out", "transfer", "transfer_out"),
    ("mortgage", "Mortgage", "expense", "loan_payments"),
    ("car_payment", "Car Payment", "expense", "loan_payments"),
    ("student_loans", "Student Loans", "expense", "loan_payments"),
    ("other_loan_payments", "Other Loan Payments", "expense", "loan_payments"),
    ("bank_fees", "Bank Fees", "expense", "bank_fees"),
    ("entertainment", "Entertainment", "expense", "entertainment"),
    ("groceries", "Groceries", "expense", "food_and_drink"),
    ("restaurants", "Restaurants", "expense", "food_and_drink"),
    ("coffee", "Coffee", "expense", "food_and_drink"),
    ("alcohol_and_bars", "Alcohol & Bars", "expense", "food_and_drink"),
    ("other_food_and_drink", "Other Food & Drink", "expense", "food_and_drink"),
    ("clothing", "Clothing", "expense", "general_merchandise"),
    ("electronics", "Electronics", "expense", "general_merchandise"),
    ("online_marketplaces", "Online Marketplaces", "expense", "general_merchandise"),
    ("superstores", "Superstores", "expense", "general_merchandise"),
    ("pets", "Pets", "expense", "general_merchandise"),
    ("other_shopping", "Other Shopping", "expense", "general_merchandise"),
    ("home_improvement", "Home Improvement", "expense", "home_improvement"),
    ("medical", "Medical", "expense", "medical"),
    ("personal_care", "Personal Care", "expense", "personal_care"),
    ("insurance", "Insurance", "expense", "general_services"),
    ("childcare", "Childcare", "expense", "general_services"),
    ("education", "Education", "expense", "general_services"),
    ("software", "Software", "expense", "general_services"),
    ("other_services", "Other Services", "expense", "general_services"),
    ("taxes", "Taxes", "expense", "government_and_non_profit"),
    ("donations", "Donations", "expense", "government_and_non_profit"),
    ("government_fees", "Government Fees", "expense", "government_and_non_profit"),
    ("gas", "Gas", "expense", "transportation"),
    ("car_maintenance", "Car Maintenance", "expense", "transportation"),
    ("rideshare_and_taxis", "Rideshare & Taxis", "expense", "transportation"),
    ("public_transit", "Public Transit", "expense", "transportation"),
    ("parking_and_tolls", "Parking & Tolls", "expense", "transportation"),
    ("other_transportation", "Other Transportation", "expense", "transportation"),
    ("travel", "Travel", "expense", "travel"),
    ("cash_and_atm", "Cash & ATM", "expense", "cash_and_atm"),
    ("payments_to_people", "Payments to People", "expense", "payments_to_people"),
    ("rent", "Rent", "expense", "rent_and_utilities"),
    ("utilities", "Utilities", "expense", "rent_and_utilities"),
]

# Built-in group or category -> color slot, most-seen spending first so those get
# distinct hues. Fixed (not cycled per render) so a category's color is the
# same on every screen and every visit: "color follows the entity". The
# palette is the validated dark-mode categorical set (8 hues, checked
# against the app's #10131C surface). A user's own are grey.
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


def category_color(item: Category | CategoryGroup) -> str:
    return _COLORS.get(item.system_key, UNCOLORED)


def user_categories(db: Session, user_id) -> dict[str, Category]:
    """name -> Category: the built-in ones plus the user's own, under the
    names this user sees (display_names). For matching what a person typed
    or picked by name; code looks built-ins up by key."""
    categories = list(seed_default_categories(db).values())
    if user_id is not None:
        categories += db.query(Category).filter(Category.user_id == user_id).all()
    names = display_names(db, user_id)
    return {names.get(c.id, c.name): c for c in categories}


def user_groups(db: Session, user_id) -> dict[str, CategoryGroup]:
    """name -> CategoryGroup, like user_categories."""
    groups = list(seed_default_groups(db).values())
    if user_id is not None:
        groups += db.query(CategoryGroup).filter(CategoryGroup.user_id == user_id).all()
    names = display_names(db, user_id)
    return {names.get(g.id, g.name): g for g in groups}


def display_names(db: Session, user_id) -> dict:
    """Group or category id -> the name this user gave a built-in one.
    Only renamed ones; everything else goes by its own name."""
    if user_id is None:
        return {}
    prefs = db.query(CategoryPref).filter(CategoryPref.user_id == user_id, CategoryPref.name.isnot(None))
    return {p.category_id or p.group_id: p.name for p in prefs}


BY_GROUP, BY_CATEGORY = "by_group", "by_category"
BUDGET_MODES = (BY_GROUP, BY_CATEGORY)


def budget_modes(db: Session, user_id) -> dict:
    """Group id -> how this user budgets it, where they chose; BY_GROUP
    (one line for the whole group) everywhere else."""
    if user_id is None:
        return {}
    prefs = db.query(CategoryPref).filter(CategoryPref.user_id == user_id, CategoryPref.budget_mode.isnot(None))
    return {p.group_id: p.budget_mode for p in prefs}


def visible_to(item: Category | CategoryGroup, user_id) -> bool:
    return item.user_id is None or item.user_id == user_id


def seed_default_groups(db: Session) -> dict[str, CategoryGroup]:
    """Idempotently ensure the default groups exist with the right name and
    type; return key -> CategoryGroup."""
    existing = {g.system_key: g for g in db.query(CategoryGroup).filter(CategoryGroup.system_key.isnot(None))}
    for key, name, type_ in DEFAULT_GROUPS:
        group = existing.get(key)
        if group is None:
            group = existing[key] = CategoryGroup(system_key=key)
            db.add(group)
        group.name, group.type = name, type_
    db.flush()
    return existing


def seed_default_categories(db: Session) -> dict[str, Category]:
    """Idempotently ensure the default groups and categories exist with the
    right name, type and group; return key -> Category."""
    groups = seed_default_groups(db)
    existing = {c.system_key: c for c in db.query(Category).filter(Category.system_key.isnot(None))}
    for key, name, type_, group_key in DEFAULT_CATEGORIES:
        category = existing.get(key)
        if category is None:
            category = existing[key] = Category(system_key=key, is_system_default=True)
            db.add(category)
        category.name, category.type, category.group_id = name, type_, groups[group_key].id
    db.flush()
    return existing
