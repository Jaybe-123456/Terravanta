import pytest

from app.reconciliation import classify_collection_entry, parse_collection_csv


def entry(quantity=20.7, reference="R-1"):
    return {"errors": [], "quantity_liters": quantity, "receipt_reference": reference}


def test_csv_parser_accepts_expected_headers_and_preserves_row_number():
    rows = parse_collection_csv(b"farm_code,collection_date,milk_litres,receipt_reference\nF-1,2026-11-14,20.7,R-1\n")
    assert rows[0]["row_number"] == 2
    assert rows[0]["farm_code"] == "F-1"
    assert rows[0]["quantity_liters"] == 20.7
    assert rows[0]["collection_date"].isoformat() == "2026-11-14"


@pytest.mark.parametrize("content", [
    b"",
    b"farm,date,litres,reference\nF-1,2026-11-14,20,R-1\n",
    b"farm_code,farm_code,collection_date,milk_litres,receipt_reference\nF-1,F-1,2026-11-14,20,R-1\n",
    b"farm_code,collection_date,milk_litres,receipt_reference\nF-1,20261114,20,R-1\n",
    b"farm_code,collection_date,milk_litres,receipt_reference\nF-1,not-a-date,0,R-1\n",
])
def test_csv_parser_rejects_empty_or_invalid_structure(content):
    with pytest.raises(ValueError):
        parse_collection_csv(content)


def test_csv_parser_keeps_bad_rows_as_reviewable_exceptions():
    rows = parse_collection_csv(b"farm_code,collection_date,milk_litres,receipt_reference\nF-1,bad-date,0,R-1\n")
    assert rows[0]["errors"]
    assert classify_collection_entry(rows[0], []) == (
        "invalid_row", None,
        ["Collection date must use YYYY-MM-DD", "Milk litres must be a number greater than zero"],
    )


def test_exact_delivery_reference_and_quantity_match():
    result = classify_collection_entry(entry(), [{"id": "d1", "quantity": 20.7, "reference": "R-1"}])
    assert result == ("matched", "d1", [])


def test_reference_and_quantity_discrepancies_are_explicit():
    delivery = {"id": "d1", "quantity": 18.4, "reference": "R-1"}
    assert classify_collection_entry(entry(), [delivery])[0] == "quantity_mismatch"
    assert classify_collection_entry(entry(reference="OTHER"), [{"id": "d1", "quantity": 20.7, "reference": "R-1"}])[0] == "reference_mismatch"


def test_missing_and_ambiguous_delivery_matches_are_not_auto_confirmed():
    assert classify_collection_entry(entry(), [])[0] == "missing_delivery"
    candidates = [
        {"id": "d1", "quantity": 20.7, "reference": "R-1"},
        {"id": "d2", "quantity": 20.7, "reference": "R-1"},
    ]
    assert classify_collection_entry(entry(), candidates)[0] == "ambiguous"
    assert classify_collection_entry(entry(reference=""), candidates)[0] == "ambiguous"
