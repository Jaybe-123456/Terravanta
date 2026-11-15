"""Deterministic rules for cooperative milk-intake reconciliation.

No model-generated facts are used to create a match. Quantities are compared at
the input precision (0.1 L); uncertain or non-consented rows stay exceptions.
"""

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation


REQUIRED_HEADERS = ("farm_code", "collection_date", "milk_litres", "receipt_reference")
MAX_RECONCILIATION_ROWS = 2_000
QUANTITY_TOLERANCE_LITRES = Decimal("0.1")


def parse_collection_csv(content: bytes) -> list[dict]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        headers = [header.strip().lower() for header in next(reader)]
    except StopIteration as exc:
        raise ValueError("CSV is empty") from exc
    if len(headers) != len(set(headers)) or set(headers) != set(REQUIRED_HEADERS):
        raise ValueError("CSV headers must be farm_code, collection_date, milk_litres, receipt_reference")

    entries = []
    for row_number, values in enumerate(reader, start=2):
        if not values or not any(value.strip() for value in values):
            continue
        errors = []
        if len(values) != len(headers):
            errors.append("Row has a different number of columns than the header")
        values = (values + [""] * len(headers))[:len(headers)]
        raw = {header: value.strip() for header, value in zip(headers, values)}

        farm_code = raw["farm_code"][:40]
        submitted_date = raw["collection_date"][:32]
        submitted_quantity = raw["milk_litres"][:32]
        receipt_reference = raw["receipt_reference"][:80]
        if len(raw["farm_code"]) > 40:
            errors.append("Farm code exceeds 40 characters")
        if len(raw["receipt_reference"]) > 80:
            errors.append("Receipt reference exceeds 80 characters")

        collection_date = None
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", submitted_date):
                raise ValueError("not an extended ISO calendar date")
            collection_date = date.fromisoformat(submitted_date)
        except ValueError:
            errors.append("Collection date must use YYYY-MM-DD")

        quantity = None
        try:
            parsed_quantity = Decimal(submitted_quantity)
            if not parsed_quantity.is_finite() or parsed_quantity <= 0 or parsed_quantity > Decimal("1000000"):
                raise InvalidOperation
            quantity = float(parsed_quantity)
        except (InvalidOperation, ValueError):
            errors.append("Milk litres must be a number greater than zero")

        if not farm_code:
            errors.append("Farm code is required")
        entries.append({
            "row_number": row_number,
            "farm_code": farm_code,
            "submitted_date": submitted_date,
            "collection_date": collection_date,
            "submitted_quantity": submitted_quantity,
            "quantity_liters": quantity,
            "receipt_reference": receipt_reference,
            "errors": errors,
        })
        if len(entries) > MAX_RECONCILIATION_ROWS:
            raise ValueError(f"CSV may contain at most {MAX_RECONCILIATION_ROWS} data rows")
    if not entries:
        raise ValueError("CSV contains no data rows")
    return entries


def classify_collection_entry(entry: dict, deliveries: list[dict]) -> tuple[str, str | None, list[str]]:
    """Return a transparent status, optional delivery ID, and reasons."""
    if entry["errors"]:
        return "invalid_row", None, entry["errors"]
    if not deliveries:
        return "missing_delivery", None, ["No consented milk delivery was recorded for this farm and date"]

    expected = Decimal(str(entry["quantity_liters"])).quantize(Decimal("0.1"))
    quantity_matches = [
        row for row in deliveries
        if abs(Decimal(str(row["quantity"])).quantize(Decimal("0.1")) - expected) <= QUANTITY_TOLERANCE_LITRES
    ]
    reference = entry["receipt_reference"].strip().casefold()

    if reference:
        reference_matches = [row for row in deliveries if str(row["reference"]).strip().casefold() == reference]
        if len(reference_matches) > 1:
            return "ambiguous", None, ["More than one delivery uses this receipt reference"]
        if len(reference_matches) == 1:
            candidate = reference_matches[0]
            if candidate in quantity_matches:
                return "matched", candidate["id"], []
            return "quantity_mismatch", candidate["id"], [
                f"Collection sheet has {expected:g} L; delivery record has {candidate['quantity']:g} L",
            ]
        if len(quantity_matches) == 1:
            return "reference_mismatch", quantity_matches[0]["id"], ["Quantity matches a delivery, but the receipt reference differs"]
        if len(quantity_matches) > 1:
            return "ambiguous", None, ["Several deliveries match the quantity; receipt reference did not match"]
        return "reference_mismatch", None, ["Receipt reference did not match a delivery on this date"]

    if len(quantity_matches) == 1:
        return "missing_reference", quantity_matches[0]["id"], ["Quantity matches, but the collection sheet has no receipt reference"]
    if len(quantity_matches) > 1:
        return "ambiguous", None, ["Several deliveries match the quantity and no receipt reference was supplied"]
    if len(deliveries) == 1:
        return "quantity_mismatch", deliveries[0]["id"], [
            f"Collection sheet has {expected:g} L; delivery record has {deliveries[0]['quantity']:g} L",
        ]
    return "ambiguous", None, ["Several same-day deliveries exist and none matches the submitted quantity"]
