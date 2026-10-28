"""Maps a raw aggregator category string to one of Bankr's default
categories, by key (seed_categories.DEFAULT_CATEGORIES: "restaurants_and_bars",
"credit_card_payment"), so renaming a category never changes where anything lands.

Two-tier lookup against Plaid's PFC taxonomy (verified against
https://plaid.com/documents/transactions-personal-finance-category-taxonomy.csv,
not assumed, plus the v2 values seen in Plaid's sandbox):

Bankr's categories are Monarch's (see seed_categories.py), which cut across
Plaid's primaries -- GENERAL_SERVICES alone lands in Auto Maintenance, Child
Care, Education, Insurance and more -- so most detailed values are spelled
out. Spending at a known software merchant (SOFTWARE_MERCHANTS) is Shopping
whatever the steps below say, rather than a service it isn't.

1. Try an exact match on the transaction's `detailed` value.
2. Fall back to a match on the `primary` value -- this also catches any
   `detailed` value PFC adds later under a primary we already know.
3. Fall back by sign: money in is Other Income, money out Uncategorized --
   except that money into a credit card or loan is never income, so it is a
   transfer. Plaid tags many card payments' receiving side
   LOAN_DISBURSEMENTS_OTHER_DISBURSEMENT, which no map entry covers.

This table is aggregator-specific -- if Plaid is ever replaced, this map
(and plaid_client.py's `raw_category` extraction) is the only thing that
needs to change, per the adapter boundary in app/integrations/bank_aggregator.py.
"""

import re

DETAILED_CATEGORY_MAP: dict[str, str] = {
    "income_dividends": "dividends_and_capital_gains",
    "income_interest_earned": "interest",
    "income_wages": "paychecks",
    "income_salary": "paychecks",  # PFCv2
    # Paying a credit card moves money between the user's own accounts; the
    # spending already happened as the card purchases. Both sides are the
    # payment. Other loan payments (mortgage, car, student) are real outflows.
    "loan_payments_credit_card_payment": "credit_card_payment",
    "loan_payments_car_payment": "auto_payment",
    "loan_payments_mortgage_payment": "mortgage",
    "loan_payments_student_loan_payment": "student_loans",
    # Cash out of an ATM or over the counter, and money sent to someone
    # through Zelle, Venmo, Cash App: it has left the user's accounts, so it's
    # spending, not a transfer -- otherwise rent paid to a roommate over Zelle
    # never shows up anywhere. What it paid for is unknown, so Miscellaneous.
    # Money to the user's own savings or brokerage has its own tags
    # (TRANSFER_OUT_SAVINGS, ..._INVESTMENT_...) and stays a transfer; a user
    # can mark any of these as one by hand.
    "transfer_out_withdrawal": "cash_and_atm",
    "transfer_out_transfer_out_from_apps": "miscellaneous",  # PFCv2
    "food_and_drink_groceries": "groceries",
    "food_and_drink_coffee": "coffee_shops",
    "general_merchandise_clothing_and_accessories": "clothing",
    "general_merchandise_electronics": "electronics",
    "general_merchandise_gifts_and_novelties": "gifts",
    "general_merchandise_pet_supplies": "pets",
    "home_improvement_furniture": "furniture_and_housewares",
    "medical_dental_care": "dentist",
    # The vet is the pet's doctor: counting it as Medical inflates what the
    # user spends on their own health.
    "medical_veterinary_services": "pets",
    "personal_care_gyms_and_fitness_centers": "fitness",
    "general_services_accounting_and_financial_planning": "financial_and_legal_services",
    "general_services_consulting_and_legal": "financial_and_legal_services",
    # Repairs belong with the rest of what the car costs, not with postage.
    "general_services_automotive": "auto_maintenance",
    "general_services_childcare": "child_care",
    "general_services_education": "school_and_tuition",
    "general_services_insurance": "insurance",
    "general_services_postage_and_shipping": "postage_and_shipping",
    "government_and_non_profit_donations": "charity",
    "government_and_non_profit_tax_payment": "taxes",
    # Gas *for the car*. The utility gas bill is
    # rent_and_utilities_gas_and_electricity -> Gas & Electric, and must never
    # land here, or "how much did I spend on gas" includes the heating bill.
    "transportation_gas": "gas",
    "transportation_parking": "parking_and_tolls",
    "transportation_tolls": "parking_and_tolls",
    "transportation_taxis_and_ride_shares": "taxi_and_ride_shares",
    "rent_and_utilities_rent": "rent",
    "rent_and_utilities_internet_and_cable": "internet_and_cable",
    "rent_and_utilities_sewage_and_waste_management": "garbage",
    "rent_and_utilities_telephone": "phone",
    "rent_and_utilities_water": "water",
}

# Detailed values that only describe money going out: the same tag on money
# coming in (a deposit, a Zelle received) is a transfer.
_OUTFLOW_ONLY = {"cash_and_atm", "miscellaneous"}

# Each primary's catch-all: what its other detailed values, and new ones,
# land on.
PRIMARY_CATEGORY_MAP: dict[str, str] = {
    "income": "other_income",
    "transfer_in": "transfer",
    "transfer_out": "transfer",
    "loan_disbursements": "transfer",
    "loan_payments": "loan_repayment",
    "bank_fees": "financial_fees",
    "entertainment": "entertainment_and_recreation",
    "food_and_drink": "restaurants_and_bars",
    "general_merchandise": "general_shopping",
    "home_improvement": "home_improvement",
    "medical": "medical",
    "personal_care": "personal",
    "general_services": "miscellaneous",
    "government_and_non_profit": "miscellaneous",
    "transportation": "public_transit",
    "travel": "travel_and_vacation",
    # Every non-rent RENT_AND_UTILITIES value not listed above is energy.
    "rent_and_utilities": "gas_and_electric",
}


# Software subscriptions Plaid has no tag for: it files most of them under
# GENERAL_SERVICES_OTHER (Miscellaneous) or GENERAL_MERCHANDISE_OTHER. Matched
# on whole words of the bank's merchant name, so only names that mean
# software and nothing else belong here ("Apple" or "Google" alone could be
# anything). Not inside an email or web address: a Zelle to name@icloud.com
# is a person.
SOFTWARE_MERCHANTS = (
    "1password",
    "adobe",
    "anthropic",
    "canva",
    "chatgpt",
    "claude.ai",
    "digitalocean",
    "dropbox",
    "evernote",
    "figma",
    "github",
    "google one",
    "google workspace",
    "grammarly",
    "heroku",
    "icloud",
    "jetbrains",
    "lastpass",
    "leetcode",
    "linear.app",
    "linkedin",
    "microsoft 365",
    "notion",
    "obsidian",
    "openai",
    "slack",
    "todoist",
    "vercel",
    "zoom.us",
)
_SOFTWARE = re.compile(r"(?<![@.])\b(" + "|".join(re.escape(m) for m in SOFTWARE_MERCHANTS) + r")\b")


def merchant_category(merchant_name: str | None) -> str | None:
    """A category known from the merchant alone, whatever Plaid tagged it."""
    if merchant_name and _SOFTWARE.search(merchant_name.lower()):
        return "general_shopping"
    return None


# Account types whose balance is money owed. See sync_service.LIABILITY_ACCOUNT_TYPES.
_LIABILITY_ACCOUNT_TYPES = {"credit", "loan"}


def map_raw_category(
    raw_category: str | None, amount: float, account_type: str | None = None, merchant_name: str | None = None
) -> str:
    """`amount` follows Bankr's internal convention: positive = money in.
    `raw_category` is expected to be a Plaid `detailed` PFC value (e.g.
    "FOOD_AND_DRINK_GROCERIES"), but a bare `primary` value works too --
    both resolve through the same two-tier lookup.

    `account_type` matters for loan payments: on a credit card or loan
    account, a LOAN_PAYMENTS_* row is the *receiving* side of a payment
    (the matching outflow sits on the checking account), so it's a transfer
    no matter which detailed value Plaid picked -- found in Plaid sandbox
    data, where a card's "AUTOMATIC PAYMENT - THANK YOU" is tagged
    LOAN_PAYMENTS_OTHER_PAYMENT and would otherwise count as $2k/month of
    spending.

    The same goes for INCOME_*: nobody earns a paycheck on a credit card or
    loan, so Plaid tagging a card payment's receiving side INCOME_SALARY /
    INCOME_CONTRACTOR (also seen in sandbox) is a payment, not income.

    `merchant_name` is the bank's name for the merchant: spending at a
    known software merchant is Shopping whatever Plaid tagged it.

    Returns a category key."""
    normalized = (raw_category or "").strip().lower()
    category = _map_plaid_category(normalized, amount, account_type)
    # Only where Plaid's answer was a purchase (a refund nets against it too):
    # a paycheck, card payment, loan, cash or Zelle from a software company
    # stays what it is.
    purchase = not normalized.startswith(("income", "transfer", "loan_")) and category not in _NOT_PURCHASES
    if purchase and (known := merchant_category(merchant_name)):
        return known
    return category


_NOT_PURCHASES = {"mortgage", "auto_payment", "student_loans", "loan_repayment", "cash_and_atm"}


def _map_plaid_category(normalized: str, amount: float, account_type: str | None) -> str:
    liability = account_type in _LIABILITY_ACCOUNT_TYPES
    if normalized:
        if liability and normalized.startswith(("loan_payments", "income")):
            return "credit_card_payment" if account_type == "credit" else "transfer"

        if normalized in DETAILED_CATEGORY_MAP:
            category = DETAILED_CATEGORY_MAP[normalized]
            # e.g. cash deposited, or a Zelle received.
            return "transfer" if category in _OUTFLOW_ONLY and amount > 0 else category

        for primary, category in PRIMARY_CATEGORY_MAP.items():
            if normalized == primary or normalized.startswith(primary + "_"):
                return category

    if amount > 0:
        return "transfer" if liability else "other_income"
    return "uncategorized"
