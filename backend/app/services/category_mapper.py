"""Maps a raw aggregator category string to one of Bankr's default categories.

Two-tier lookup against Plaid's PFCv2 taxonomy (verified against
https://plaid.com/documents/transactions-personal-finance-category-taxonomy.csv,
not assumed):

1. Try an exact match on the transaction's `detailed` value -- only needed
   for the two primaries that split across more than one Bankr category
   (FOOD_AND_DRINK -> Groceries vs. Dining; RENT_AND_UTILITIES -> Rent &
   Housing vs. Utilities). Every other primary maps wholesale to one Bankr
   category, so its subcategories don't need individual entries.
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
    "food_and_drink_restaurant": "Dining",
    "food_and_drink_fast_food": "Dining",
    "food_and_drink_coffee": "Dining",
    "food_and_drink_beer_wine_and_liquor": "Dining",
    "food_and_drink_vending_machines": "Dining",
    "food_and_drink_other_food_and_drink": "Dining",
    "rent_and_utilities_rent": "Rent & Housing",
    "rent_and_utilities_gas_and_electricity": "Utilities",
    "rent_and_utilities_internet_and_cable": "Utilities",
    "rent_and_utilities_sewage_and_waste_management": "Utilities",
    "rent_and_utilities_telephone": "Utilities",
    "rent_and_utilities_water": "Utilities",
    "rent_and_utilities_other_utilities": "Utilities",
    "general_services_automotive": "Transportation",
}

PRIMARY_CATEGORY_MAP: dict[str, str] = {
    "income": "Income",
    "transfer_in": "Transfer",
    "transfer_out": "Transfer",
    "loan_payments": "Other",
    "bank_fees": "Other",
    "entertainment": "Entertainment",
    "food_and_drink": "Dining",
    "general_merchandise": "Shopping",
    "home_improvement": "Other",
    "medical": "Health",
    "personal_care": "Health",
    "general_services": "Other",
    "government_and_non_profit": "Other",
    "transportation": "Transportation",
    "travel": "Transportation",
    "rent_and_utilities": "Rent & Housing",
}


def map_raw_category(raw_category: str | None, amount: float) -> str:
    """`amount` follows Bankr's internal convention: positive = money in.
    `raw_category` is expected to be a Plaid `detailed` PFC value (e.g.
    "FOOD_AND_DRINK_GROCERIES"), but a bare `primary` value works too --
    both resolve through the same two-tier lookup."""
    if raw_category:
        normalized = raw_category.strip().lower()

        if normalized in DETAILED_CATEGORY_MAP:
            return DETAILED_CATEGORY_MAP[normalized]

        for primary, category in PRIMARY_CATEGORY_MAP.items():
            if normalized == primary or normalized.startswith(primary + "_"):
                return category

    return "Income" if amount > 0 else "Other"
