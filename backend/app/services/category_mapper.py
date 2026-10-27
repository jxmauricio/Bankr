"""Maps a raw aggregator category string to one of Bankr's default categories.

Two-tier lookup against Plaid's PFCv2 taxonomy (verified against
https://plaid.com/documents/transactions-personal-finance-category-taxonomy.csv,
not assumed):

Bankr's categories are the taxonomy's 16 primaries, most split into
subcategories (see seed_categories.py); this always returns a leaf.
Spending at a known software merchant (SOFTWARE_MERCHANTS) is Software
whatever the steps below say -- the taxonomy has no software tag.

1. Try an exact match on the transaction's `detailed` value -- only needed
   for detailed values that land somewhere other than their primary's
   default: a Bankr subcategory (TRANSPORTATION_GAS -> Gas) or a different
   category (LOAN_PAYMENTS_CREDIT_CARD_PAYMENT -> Transfer Out). Anything
   not listed falls through to its primary.
2. Fall back to a match on the `primary` value -- this also catches any
   `detailed` value PFCv2 adds later under a primary we already know. A
   primary that's a Bankr group lands on its "Other ..." subcategory.
3. Fall back to sign-based Income / Other Shopping if nothing
   matched -- except that money into a credit card or loan is never
   income, so it falls back to Transfer In. Plaid tags many card payments'
   receiving side LOAN_DISBURSEMENTS_OTHER_DISBURSEMENT, which no map
   entry covers.

This table is aggregator-specific -- if Plaid is ever replaced, this map
(and plaid_client.py's `raw_category` extraction) is the only thing that
needs to change, per the adapter boundary in app/integrations/bank_aggregator.py.
"""

import re

DETAILED_CATEGORY_MAP: dict[str, str] = {
    "food_and_drink_groceries": "Groceries",
    "food_and_drink_restaurant": "Restaurants",
    "food_and_drink_fast_food": "Restaurants",
    "food_and_drink_coffee": "Coffee",
    "food_and_drink_beer_wine_and_liquor": "Alcohol & Bars",
    "general_merchandise_clothing_and_accessories": "Clothing",
    "general_merchandise_electronics": "Electronics",
    "general_merchandise_online_marketplaces": "Online Marketplaces",
    "general_merchandise_superstores": "Superstores",
    "general_merchandise_pet_supplies": "Pets",
    # The vet is the pet's doctor: counting it as Medical inflates what the
    # user spends on their own health.
    "medical_veterinary_services": "Pets",
    "general_services_insurance": "Insurance",
    "general_services_childcare": "Childcare",
    "general_services_education": "Education",
    # Repairs belong with the rest of what the car costs, not with postage.
    "general_services_automotive": "Car Maintenance",
    "government_and_non_profit_tax_payment": "Taxes",
    "government_and_non_profit_donations": "Donations",
    # Gas *for the car*. The utility gas bill is
    # rent_and_utilities_gas_and_electricity -> Utilities, and must never
    # land here, or "how much did I spend on gas" includes the heating bill.
    "transportation_gas": "Gas",
    "transportation_taxis_and_ride_shares": "Rideshare & Taxis",
    "transportation_public_transit": "Public Transit",
    "transportation_parking": "Parking & Tolls",
    "transportation_tolls": "Parking & Tolls",
    "loan_payments_mortgage_payment": "Mortgage",
    "loan_payments_car_payment": "Car Payment",
    "loan_payments_student_loan_payment": "Student Loans",
    "rent_and_utilities_rent": "Rent",
    "rent_and_utilities_gas_and_electricity": "Utilities",
    "rent_and_utilities_internet_and_cable": "Utilities",
    "rent_and_utilities_sewage_and_waste_management": "Utilities",
    "rent_and_utilities_telephone": "Utilities",
    "rent_and_utilities_water": "Utilities",
    "rent_and_utilities_other_utilities": "Utilities",
    # Paying a credit card moves money between the user's own accounts; the
    # spending already happened as the card purchases. Other loan payments
    # (mortgage, car, student) are real outflows and stay under LOAN_PAYMENTS.
    "loan_payments_credit_card_payment": "Transfer Out",
}

# A primary that's a group in seed_categories lands on its "Other ..."
# child: transactions never sit on a group. Every non-rent RENT_AND_UTILITIES
# value is a utility, so that one's catch-all is Utilities.
PRIMARY_CATEGORY_MAP: dict[str, str] = {
    "income": "Income",
    "transfer_in": "Transfer In",
    "transfer_out": "Transfer Out",
    "loan_payments": "Other Loan Payments",
    "bank_fees": "Bank Fees",
    "entertainment": "Entertainment",
    "food_and_drink": "Other Food & Drink",
    "general_merchandise": "Other Shopping",
    "home_improvement": "Home Improvement",
    "medical": "Medical",
    "personal_care": "Personal Care",
    "general_services": "Other Services",
    "government_and_non_profit": "Government Fees",
    "transportation": "Other Transportation",
    "travel": "Travel",
    "rent_and_utilities": "Utilities",
}


# Software subscriptions Plaid has no tag for: it files most of them under
# GENERAL_SERVICES_OTHER or GENERAL_MERCHANDISE_OTHER. Matched on whole
# words of the bank's merchant name, so only names that mean software and
# nothing else belong here ("Apple" or "Google" alone could be anything).
# Not inside an email or web address: a Zelle to name@icloud.com is a person.
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
        return "Software"
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
    known software merchant is Software whatever Plaid tagged it."""
    category = _map_plaid_category(raw_category, amount, account_type)
    # Only where Plaid's answer was spending (a refund nets against it too):
    # a paycheck or card payment from a software company stays what it is.
    if category not in _NOT_SPENDING and (known := merchant_category(merchant_name)):
        return known
    return category


_NOT_SPENDING = {"Income", "Transfer In", "Transfer Out", "Mortgage", "Car Payment", "Student Loans", "Other Loan Payments"}


def _map_plaid_category(raw_category: str | None, amount: float, account_type: str | None) -> str:
    if raw_category:
        normalized = raw_category.strip().lower()

        if account_type in _LIABILITY_ACCOUNT_TYPES and normalized.startswith(("loan_payments", "income")):
            return "Transfer In"

        if normalized in DETAILED_CATEGORY_MAP:
            category = DETAILED_CATEGORY_MAP[normalized]
            # A card payment seen from the side the money lands on.
            return "Transfer In" if category == "Transfer Out" and amount > 0 else category

        for primary, category in PRIMARY_CATEGORY_MAP.items():
            if normalized == primary or normalized.startswith(primary + "_"):
                return category

    if amount > 0:
        return "Transfer In" if account_type in _LIABILITY_ACCOUNT_TYPES else "Income"
    return "Other Shopping"
