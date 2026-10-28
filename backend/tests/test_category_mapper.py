from app.services.category_mapper import map_raw_category


def test_maps_detailed_value_to_its_subcategory_or_primary():
    assert map_raw_category("food_and_drink_groceries", -50.0) == "groceries"
    assert map_raw_category("FOOD_AND_DRINK_COFFEE", -5.0) == "coffee"
    assert map_raw_category("FOOD_AND_DRINK_RESTAURANT", -20.0) == "restaurants"
    assert map_raw_category("FOOD_AND_DRINK_FAST_FOOD", -9.0) == "restaurants"
    assert map_raw_category("rent_and_utilities_rent", -1800.0) == "rent"
    assert map_raw_category("rent_and_utilities_internet_and_cable", -80.0) == "utilities"
    assert map_raw_category("home_improvement_hardware", -40.0) == "home_improvement"
    assert map_raw_category("personal_care_gyms_and_fitness_centers", -30.0) == "personal_care"
    assert map_raw_category("government_and_non_profit_donations", -25.0) == "donations"
    assert map_raw_category("GENERAL_MERCHANDISE_ONLINE_MARKETPLACES", -30.0) == "online_marketplaces"
    assert map_raw_category("GENERAL_SERVICES_INSURANCE", -120.0) == "insurance"
    assert map_raw_category("bank_fees_overdraft_fees", -35.0) == "bank_fees"


def test_falls_back_to_primary_for_unmapped_detailed_value():
    # PFCv2 could add a new FOOD_AND_DRINK subcategory Bankr doesn't know
    # about yet -- it should still land under Food & Drink, not silently miss.
    assert map_raw_category("food_and_drink_some_new_subcategory", -10.0) == "other_food_and_drink"
    assert map_raw_category("FOOD_AND_DRINK_VENDING_MACHINES", -2.0) == "other_food_and_drink"
    assert map_raw_category("entertainment_video_games", -60.0) == "entertainment"
    assert map_raw_category("income_wages", 3000.0) == "income"


def test_unknown_category_falls_back_by_sign():
    assert map_raw_category("some_unrecognized_value", 100.0) == "income"
    assert map_raw_category("some_unrecognized_value", -100.0) == "other_shopping"


def test_missing_category_falls_back_by_sign():
    assert map_raw_category(None, 50.0) == "income"
    assert map_raw_category(None, -50.0) == "other_shopping"


def test_car_gas_and_the_gas_bill_never_collide():
    # "How much did I spend on gas" must not include the heating bill.
    assert map_raw_category("TRANSPORTATION_GAS", -55.0) == "gas"
    assert map_raw_category("RENT_AND_UTILITIES_GAS_AND_ELECTRICITY", -90.0) == "utilities"


def test_credit_card_payment_is_a_transfer_not_spending():
    # The card purchases are the spending; paying the bill is just moving
    # money between the user's own accounts.
    assert map_raw_category("LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", -500.0) == "transfer_out"
    assert map_raw_category("LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", 500.0) == "transfer_in"
    assert map_raw_category("LOAN_PAYMENTS_STUDENT_LOAN_PAYMENT", -300.0) == "student_loans"
    assert map_raw_category("TRANSFER_OUT_SAVINGS", -200.0) == "transfer_out"
    assert map_raw_category("TRANSFER_IN_SAVINGS", 200.0) == "transfer_in"


def test_cash_and_money_sent_to_people_are_spending():
    # Gone from the user's accounts, so spent -- unlike moving money to
    # their own savings or brokerage.
    assert map_raw_category("TRANSFER_OUT_WITHDRAWAL", -200.0, "checking") == "cash_and_atm"
    assert map_raw_category("TRANSFER_OUT_TRANSFER_OUT_FROM_APPS", -1200.0, "checking", "Zelle payment to Sam") == "payments_to_people"
    assert map_raw_category("TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS", -500.0, "checking") == "transfer_out"
    assert map_raw_category("TRANSFER_OUT_ACCOUNT_TRANSFER", -500.0, "checking") == "transfer_out"
    # The same tags on money coming in aren't spending, and a Zelle to a
    # software company's founder is still a Zelle.
    assert map_raw_category("TRANSFER_OUT_WITHDRAWAL", 200.0, "checking") == "transfer_in"
    assert map_raw_category("TRANSFER_OUT_TRANSFER_OUT_FROM_APPS", -40.0, "checking", "Zelle to GitHub") == "payments_to_people"


def test_flights_are_travel_not_transportation():
    assert map_raw_category("TRAVEL_FLIGHTS", -420.0) == "travel"
    assert map_raw_category("TRANSPORTATION_TAXIS_AND_RIDE_SHARES", -18.0) == "rideshare_and_taxis"


def test_every_mapped_key_is_a_seeded_category():
    from app.db.seed_categories import DEFAULT_CATEGORIES
    from app.services.category_mapper import DETAILED_CATEGORY_MAP, PRIMARY_CATEGORY_MAP

    seeded = {key for key, _, _, _ in DEFAULT_CATEGORIES}
    assert set(DETAILED_CATEGORY_MAP.values()) <= seeded
    assert set(PRIMARY_CATEGORY_MAP.values()) <= seeded


def test_a_transaction_never_lands_on_a_group():
    # Every group's total must be exactly the sum of its subcategories.
    from app.db.seed_categories import GROUPS
    from app.services.category_mapper import DETAILED_CATEGORY_MAP, PRIMARY_CATEGORY_MAP

    assert GROUPS == {
        "loan_payments",
        "food_and_drink",
        "general_merchandise",
        "general_services",
        "government_and_non_profit",
        "transportation",
        "rent_and_utilities",
    }
    assert not (set(DETAILED_CATEGORY_MAP.values()) | set(PRIMARY_CATEGORY_MAP.values())) & GROUPS


def test_new_subcategories_answer_the_questions_a_primary_cannot():
    # The vet is the pet's, not the user's, medical bill.
    assert map_raw_category("MEDICAL_VETERINARY_SERVICES", -180.0) == "pets"
    assert map_raw_category("GENERAL_MERCHANDISE_PET_SUPPLIES", -40.0) == "pets"
    # What the car costs sits together under Transportation.
    assert map_raw_category("GENERAL_SERVICES_AUTOMOTIVE", -300.0) == "car_maintenance"
    assert map_raw_category("TRANSPORTATION_TOLLS", -6.0) == "parking_and_tolls"
    assert map_raw_category("GOVERNMENT_AND_NON_PROFIT_TAX_PAYMENT", -800.0) == "taxes"
    assert map_raw_category("LOAN_PAYMENTS_PERSONAL_LOAN_PAYMENT", -150.0) == "other_loan_payments"


def test_software_is_known_by_merchant_whatever_plaid_tagged_it():
    other = "GENERAL_SERVICES_OTHER_GENERAL_SERVICES"
    assert map_raw_category(other, -5.0, "credit", "Obsidian") == "software"
    assert map_raw_category("GENERAL_MERCHANDISE_OTHER_GENERAL_MERCHANDISE", -9.84, "credit", "GitHub") == "software"
    assert map_raw_category(other, -15.99, "credit", "ZOOM.US 888-799-9666") == "software"
    # A refund nets against it.
    assert map_raw_category(other, 34.49, "credit", "Adobe") == "software"
    # Whole words only, and never income or a transfer.
    assert map_raw_category(other, -12.0, "credit", "Notionally Fine Bakery") == "other_services"
    assert map_raw_category("INCOME_WAGES", 5000.0, "checking", "Anthropic") == "income"
    assert map_raw_category("TRANSFER_OUT_ACCOUNT_TRANSFER", -20.0, "checking", "GitHub") == "transfer_out"
    assert map_raw_category(other, -10.0, "credit", "Apple iTunes") == "other_services"
    # A payment to someone's iCloud address is a person, not iCloud.
    assert map_raw_category(other, -43.55, "checking", "ISSOUFKINDA@ICLOUD.CO") == "other_services"
    assert map_raw_category(other, -2.99, "credit", "Apple iCloud Storage") == "software"


def test_every_plaid_primary_has_its_own_category():
    from app.services.category_mapper import PRIMARY_CATEGORY_MAP

    assert len(PRIMARY_CATEGORY_MAP) == 16
    assert len(set(PRIMARY_CATEGORY_MAP.values())) == 16


def test_loan_payment_on_the_card_or_loan_itself_is_a_transfer():
    # The receiving side of a payment, whatever detailed value Plaid picked.
    assert map_raw_category("LOAN_PAYMENTS_OTHER_PAYMENT", -2078.50, "credit") == "transfer_in"
    assert map_raw_category("LOAN_PAYMENTS_MORTGAGE_PAYMENT", 1500.0, "loan") == "transfer_in"
    # The paying side, from checking, is real money out.
    assert map_raw_category("LOAN_PAYMENTS_MORTGAGE_PAYMENT", -1500.0, "checking") == "mortgage"


def test_uncategorized_money_into_a_card_or_loan_is_a_transfer_not_income():
    # A card payment with a category the map doesn't know must not show up
    # as income. LOAN_DISBURSEMENTS_OTHER_DISBURSEMENT is what Plaid sends
    # for the card's "Payment Thank You" credit.
    assert map_raw_category("LOAN_DISBURSEMENTS_OTHER_DISBURSEMENT", 1883.17, "credit") == "transfer_in"
    assert map_raw_category(None, 500.0, "credit") == "transfer_in"
    assert map_raw_category("some_unrecognized_value", 500.0, "loan") == "transfer_in"
    assert map_raw_category(None, -40.0, "credit") == "other_shopping"
    assert map_raw_category(None, 500.0, "checking") == "income"


def test_income_category_on_a_card_or_loan_is_a_transfer():
    # Plaid sandbox tags card "AUTOMATIC PAYMENT - THANK YOU" rows INCOME_SALARY.
    assert map_raw_category("INCOME_SALARY", 2835.80, "credit") == "transfer_in"
    assert map_raw_category("INCOME_CONTRACTOR", 297.04, "loan") == "transfer_in"
    assert map_raw_category("INCOME_SALARY", 2835.80, "checking") == "income"
