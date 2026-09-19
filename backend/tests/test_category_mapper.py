from app.services.category_mapper import map_raw_category


def test_maps_detailed_category():
    assert map_raw_category("food_and_drink_groceries", -50.0) == "Groceries"
    assert map_raw_category("FOOD_AND_DRINK_RESTAURANT", -20.0) == "Restaurants"
    assert map_raw_category("rent_and_utilities_rent", -1800.0) == "Rent & Housing"
    assert map_raw_category("rent_and_utilities_internet_and_cable", -80.0) == "Utilities"


def test_falls_back_to_primary_for_unmapped_detailed_value():
    # PFCv2 could add a new FOOD_AND_DRINK subcategory Bankr doesn't know
    # about yet -- it should still land on Dining via the primary fallback,
    # not silently miss.
    assert map_raw_category("food_and_drink_some_new_subcategory", -10.0) == "Dining"
    assert map_raw_category("entertainment_video_games", -60.0) == "Entertainment"
    assert map_raw_category("income_wages", 3000.0) == "Income"


def test_unknown_category_falls_back_by_sign():
    assert map_raw_category("some_unrecognized_value", 100.0) == "Income"
    assert map_raw_category("some_unrecognized_value", -100.0) == "Other"


def test_missing_category_falls_back_by_sign():
    assert map_raw_category(None, 50.0) == "Income"
    assert map_raw_category(None, -50.0) == "Other"


def test_car_gas_and_the_gas_bill_never_collide():
    # "How much did I spend on gas" must not include the heating bill.
    assert map_raw_category("TRANSPORTATION_GAS", -55.0) == "Gas"
    assert map_raw_category("RENT_AND_UTILITIES_GAS_AND_ELECTRICITY", -90.0) == "Utilities"


def test_credit_card_payment_is_a_transfer_not_spending():
    # The card purchases are the spending; paying the bill is just moving
    # money between the user's own accounts.
    assert map_raw_category("LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", -500.0) == "Transfer"
    assert map_raw_category("LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", 500.0) == "Transfer"
    assert map_raw_category("LOAN_PAYMENTS_STUDENT_LOAN_PAYMENT", -300.0) == "Loan Payments"
    assert map_raw_category("TRANSFER_OUT_SAVINGS", -200.0) == "Transfer"


def test_flights_are_travel_not_transportation():
    assert map_raw_category("TRAVEL_FLIGHTS", -420.0) == "Travel"
    assert map_raw_category("TRANSPORTATION_TAXIS_AND_RIDE_SHARES", -18.0) == "Rideshare & Taxi"


def test_every_mapped_name_is_a_seeded_category():
    from app.db.seed_categories import DEFAULT_CATEGORIES
    from app.services.category_mapper import DETAILED_CATEGORY_MAP, PRIMARY_CATEGORY_MAP

    seeded = {name for name, _, _ in DEFAULT_CATEGORIES}
    assert set(DETAILED_CATEGORY_MAP.values()) <= seeded
    assert set(PRIMARY_CATEGORY_MAP.values()) <= seeded


def test_loan_payment_on_the_card_or_loan_itself_is_a_transfer():
    # The receiving side of a payment, whatever detailed value Plaid picked.
    assert map_raw_category("LOAN_PAYMENTS_OTHER_PAYMENT", -2078.50, "credit") == "Transfer"
    assert map_raw_category("LOAN_PAYMENTS_MORTGAGE_PAYMENT", 1500.0, "loan") == "Transfer"
    # The paying side, from checking, is real money out.
    assert map_raw_category("LOAN_PAYMENTS_MORTGAGE_PAYMENT", -1500.0, "checking") == "Loan Payments"
