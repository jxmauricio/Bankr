from app.services.category_mapper import map_raw_category


def test_maps_detailed_category():
    assert map_raw_category("food_and_drink_groceries", -50.0) == "Groceries"
    assert map_raw_category("FOOD_AND_DRINK_RESTAURANT", -20.0) == "Dining"
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
