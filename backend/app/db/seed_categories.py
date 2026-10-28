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
  money is gone from the user's accounts, so Cash & ATM, and Zelle or Venmo
  to a person (Miscellaneous), are spending, as in Mint and Monarch.

Two levels, as in Monarch and YNAB: groups (CategoryGroup) over categories,
so a question can be answered at either level: "how much on gas" -> Gas;
"on getting around" -> Auto & Transport, which includes Gas. See
app/services/money_query.py. Transactions, splits and rules always point at
a category, never a group, so a group's total is exactly the sum of its
categories. A transaction nothing else places lands in Uncategorized.

Code finds a built-in group or category by its key (system_key), never by
its name: names are for people and may change, keys never do. The Plaid
mapping, the classifier, budgets, health and the clients' colors all go by
key, so renaming "Restaurants & Bars" moves nothing.
"""

from sqlalchemy.orm import Session

from app.db.models import Category, CategoryGroup, CategoryPref

# (key, name, type), in display order. Monarch's default groups, so a user
# coming from Monarch, Mint or Copilot finds the tree they know.
DEFAULT_GROUPS: list[tuple[str, str, str]] = [
    ("income", "Income", "income"),
    ("gifts_and_donations", "Gifts & Donations", "expense"),
    ("auto_and_transport", "Auto & Transport", "expense"),
    ("housing", "Housing", "expense"),
    ("bills_and_utilities", "Bills & Utilities", "expense"),
    ("food_and_dining", "Food & Dining", "expense"),
    ("travel_and_lifestyle", "Travel & Lifestyle", "expense"),
    ("shopping", "Shopping", "expense"),
    ("children", "Children", "expense"),
    ("education", "Education", "expense"),
    ("health_and_wellness", "Health & Wellness", "expense"),
    ("financial", "Financial", "expense"),
    ("other", "Other", "expense"),
    ("business", "Business", "expense"),
    ("transfers", "Transfers", "transfer"),
]

# (key, name, type, group key, emoji): Monarch's default categories. Plaid's
# categories map onto these in category_mapper.py.
DEFAULT_CATEGORIES: list[tuple[str, str, str, str, str]] = [
    ("paychecks", "Paychecks", "income", "income", "💵"),
    ("interest", "Interest", "income", "income", "💸"),
    ("business_income", "Business Income", "income", "income", "💰"),
    ("dividends_and_capital_gains", "Dividends & Capital Gains", "income", "income", "📈"),
    ("other_income", "Other Income", "income", "income", "💰"),
    ("charity", "Charity", "expense", "gifts_and_donations", "🎗️"),
    ("gifts", "Gifts", "expense", "gifts_and_donations", "🎁"),
    ("auto_payment", "Auto Payment", "expense", "auto_and_transport", "🚗"),
    ("public_transit", "Public Transit", "expense", "auto_and_transport", "🚃"),
    ("gas", "Gas", "expense", "auto_and_transport", "⛽️"),
    ("auto_maintenance", "Auto Maintenance", "expense", "auto_and_transport", "🔧"),
    ("parking_and_tolls", "Parking & Tolls", "expense", "auto_and_transport", "🏢"),
    ("taxi_and_ride_shares", "Taxi & Ride Shares", "expense", "auto_and_transport", "🚕"),
    ("mortgage", "Mortgage", "expense", "housing", "🏠"),
    ("rent", "Rent", "expense", "housing", "🏠"),
    ("home_improvement", "Home Improvement", "expense", "housing", "🔨"),
    ("garbage", "Garbage", "expense", "bills_and_utilities", "🗑️"),
    ("water", "Water", "expense", "bills_and_utilities", "💧"),
    ("gas_and_electric", "Gas & Electric", "expense", "bills_and_utilities", "⚡️"),
    ("internet_and_cable", "Internet & Cable", "expense", "bills_and_utilities", "🌐"),
    ("phone", "Phone", "expense", "bills_and_utilities", "📱"),
    ("groceries", "Groceries", "expense", "food_and_dining", "🍏"),
    ("restaurants_and_bars", "Restaurants & Bars", "expense", "food_and_dining", "🍽️"),
    ("coffee_shops", "Coffee Shops", "expense", "food_and_dining", "☕️"),
    ("travel_and_vacation", "Travel & Vacation", "expense", "travel_and_lifestyle", "🏝️"),
    ("entertainment_and_recreation", "Entertainment & Recreation", "expense", "travel_and_lifestyle", "🎥"),
    ("personal", "Personal", "expense", "travel_and_lifestyle", "👑"),
    ("pets", "Pets", "expense", "travel_and_lifestyle", "🐶"),
    ("fun_money", "Fun Money", "expense", "travel_and_lifestyle", "😜"),
    ("general_shopping", "Shopping", "expense", "shopping", "🛍️"),
    ("clothing", "Clothing", "expense", "shopping", "👕"),
    ("furniture_and_housewares", "Furniture & Housewares", "expense", "shopping", "🪑"),
    ("electronics", "Electronics", "expense", "shopping", "🖥️"),
    ("child_care", "Child Care", "expense", "children", "👶"),
    ("child_activities", "Child Activities", "expense", "children", "⚽️"),
    ("student_loans", "Student Loans", "expense", "education", "🎓"),
    ("school_and_tuition", "Education", "expense", "education", "🏫"),
    ("medical", "Medical", "expense", "health_and_wellness", "💊"),
    ("dentist", "Dentist", "expense", "health_and_wellness", "🦷"),
    ("fitness", "Fitness", "expense", "health_and_wellness", "💪"),
    ("loan_repayment", "Loan Repayment", "expense", "financial", "💰"),
    ("financial_and_legal_services", "Financial & Legal Services", "expense", "financial", "🗄️"),
    ("financial_fees", "Financial Fees", "expense", "financial", "🏦"),
    ("cash_and_atm", "Cash & ATM", "expense", "financial", "🏧"),
    ("insurance", "Insurance", "expense", "financial", "☂️"),
    ("taxes", "Taxes", "expense", "financial", "🏛️"),
    ("uncategorized", "Uncategorized", "expense", "other", "❓"),
    ("check", "Check", "expense", "other", "💸"),
    ("miscellaneous", "Miscellaneous", "expense", "other", "💲"),
    ("advertising_and_promotion", "Advertising & Promotion", "expense", "business", "📣"),
    ("business_utilities_and_communication", "Business Utilities & Communication", "expense", "business", "📞"),
    ("employee_wages_and_contract_labor", "Employee Wages & Contract Labor", "expense", "business", "💵"),
    ("business_travel_and_meals", "Business Travel & Meals", "expense", "business", "🍴"),
    ("business_auto_expenses", "Business Auto Expenses", "expense", "business", "🚖"),
    ("business_insurance", "Business Insurance", "expense", "business", "📁"),
    ("office_supplies_and_expenses", "Office Supplies & Expenses", "expense", "business", "📎"),
    ("office_rent", "Office Rent", "expense", "business", "🏢"),
    ("postage_and_shipping", "Postage & Shipping", "expense", "business", "📦"),
    ("transfer", "Transfer", "transfer", "transfers", "🔁"),
    ("credit_card_payment", "Credit Card Payment", "transfer", "transfers", "💳"),
    ("balance_adjustments", "Balance Adjustments", "transfer", "transfers", "⚖️"),
    ("buy", "Buy", "transfer", "transfers", "➡️"),
    ("sell", "Sell", "transfer", "transfers", "⬅️"),
]
_EMOJI = {key: emoji for key, _, _, _, emoji in DEFAULT_CATEGORIES}

# Built-in group or category -> color slot, most-seen spending first so those
# get distinct hues. Fixed (not cycled per render) so a category's color is
# the same on every screen and every visit: "color follows the entity". The
# palette is the validated dark-mode categorical set (8 hues, checked
# against the app's #10131C surface). A user's own are grey.
_COLOR_ORDER = [
    # Groups first, so the donut's slices are told apart.
    "food_and_dining",
    "auto_and_transport",
    "housing",
    "shopping",
    "bills_and_utilities",
    "travel_and_lifestyle",
    "health_and_wellness",
    "financial",
    "income",
    "transfers",
    "gifts_and_donations",
    "children",
    "education",
    "other",
    "business",
    *(key for key, *_ in DEFAULT_CATEGORIES),
]
CATEGORY_PALETTE = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767")
UNCOLORED = "#565D72"
_COLORS = {}
for _i, _key in enumerate(_COLOR_ORDER):
    _COLORS.setdefault(_key, CATEGORY_PALETTE[_i % len(CATEGORY_PALETTE)])


def category_emoji(item: Category | CategoryGroup) -> str | None:
    return _EMOJI.get(item.system_key) if isinstance(item, Category) else None


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
    for key, name, type_, group_key, _ in DEFAULT_CATEGORIES:
        category = existing.get(key)
        if category is None:
            category = existing[key] = Category(system_key=key, is_system_default=True)
            db.add(category)
        category.name, category.type, category.group_id = name, type_, groups[group_key].id
    db.flush()
    return existing
