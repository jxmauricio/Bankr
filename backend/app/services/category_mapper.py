"""Maps a raw aggregator category string to one of Bankr's default categories.

Two-tier lookup against Plaid's PFCv2 taxonomy (verified against
https://plaid.com/documents/transactions-personal-finance-category-taxonomy.csv,
not assumed):

1. Try an exact match on the transaction's `detailed` value -- only needed
   for detailed values that land somewhere other than their primary's
   default: a different top-level category (FOOD_AND_DRINK_GROCERIES ->
   Groceries, LOAN_PAYMENTS_CREDIT_CARD_PAYMENT -> Transfer) or a Bankr
   subcategory (TRANSPORTATION_GAS -> Gas). Anything not listed falls
   through to its primary's category.
2. Fall back to a coarse match on the `primary` value (all 16 taxonomy
   primaries) -- this also catches any `detailed` value PFCv2 adds later
   under a primary we already know how to bucket.
3. Fall back to sign-based Income/Other if nothing matched.

This table is aggregator-specific -- if Plaid is ever replaced, this map
(and plaid_client.py's `raw_category` extraction) is the only thing that
needs to change, per the adapter boundary in app/integrations/bank_aggregator.py.
"""

DETAILED_CATEGORY_MAP: dict[str, str] = {
    "food_and_drink_groceries": "Groceries",
    "food_and_drink_restaurant": "Restaurants",
    "food_and_drink_fast_food": "Fast Food",
    "food_and_drink_coffee": "Coffee",
    "food_and_drink_beer_wine_and_liquor": "Alcohol & Bars",
    # Gas *for the car*. The utility gas bill is
    # rent_and_utilities_gas_and_electricity -> Utilities, and must never
    # land here, or "how much did I spend on gas" includes the heating bill.
    "transportation_gas": "Gas",
    "transportation_taxis_and_ride_shares": "Rideshare & Taxi",
    "transportation_public_transit": "Public Transit",
    "transportation_parking": "Parking & Tolls",
    "transportation_tolls": "Parking & Tolls",
    "general_services_automotive": "Auto Maintenance",
    "rent_and_utilities_rent": "Rent & Housing",
    "rent_and_utilities_gas_and_electricity": "Utilities",
    "rent_and_utilities_internet_and_cable": "Utilities",
    "rent_and_utilities_sewage_and_waste_management": "Utilities",
    "rent_and_utilities_telephone": "Utilities",
    "rent_and_utilities_water": "Utilities",
    "rent_and_utilities_other_utilities": "Utilities",
    # Paying a credit card moves money between the user's own accounts; the
    # spending already happened as the card purchases. Other loan payments
    # (mortgage, car, student) are real outflows and stay under LOAN_PAYMENTS.
    "loan_payments_credit_card_payment": "Transfer",
}

PRIMARY_CATEGORY_MAP: dict[str, str] = {
    "income": "Income",
    "transfer_in": "Transfer",
    "transfer_out": "Transfer",
    "loan_payments": "Loan Payments",
    "bank_fees": "Fees",
    "entertainment": "Entertainment",
    "food_and_drink": "Dining",
    "general_merchandise": "Shopping",
    "home_improvement": "Other",
    "medical": "Health",
    "personal_care": "Health",
    "general_services": "Other",
    "government_and_non_profit": "Other",
    "transportation": "Transportation",
    "travel": "Travel",
    "rent_and_utilities": "Rent & Housing",
}


# Account types whose balance is money owed. See sync_service.LIABILITY_ACCOUNT_TYPES.
_LIABILITY_ACCOUNT_TYPES = {"credit", "loan"}


def map_raw_category(raw_category: str | None, amount: float, account_type: str | None = None) -> str:
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
    spending."""
    if raw_category:
        normalized = raw_category.strip().lower()

        if account_type in _LIABILITY_ACCOUNT_TYPES and normalized.startswith("loan_payments"):
            return "Transfer"

        if normalized in DETAILED_CATEGORY_MAP:
            return DETAILED_CATEGORY_MAP[normalized]

        for primary, category in PRIMARY_CATEGORY_MAP.items():
            if normalized == primary or normalized.startswith(primary + "_"):
                return category

    return "Income" if amount > 0 else "Other"
