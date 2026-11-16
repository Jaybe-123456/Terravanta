"""Deterministic, auditable settlement-close parsing and reconciliation.

No generative model is used to make or approve a financial match.
"""

import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MAX_SETTLEMENT_ROWS = 20_000
MAX_SETTLEMENT_FILE_BYTES = 5_000_000
CENT = Decimal("0.01")
TENTH_LITRE = Decimal("0.1")


def _read_rows(content: bytes, required: set[str], label: str) -> list[dict]:
    if not content or len(content) > MAX_SETTLEMENT_FILE_BYTES:
        raise ValueError(f"{label} file must be between 1 byte and 5 MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} file must use UTF-8 encoding") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = [str(name or "").strip().lower() for name in (reader.fieldnames or [])]
    if len(headers) != len(set(headers)) or not required.issubset(set(headers)):
        expected = ", ".join(sorted(required))
        raise ValueError(f"{label} CSV requires unique headers including: {expected}")
    rows = []
    for row_number, raw in enumerate(reader, start=2):
        if row_number > MAX_SETTLEMENT_ROWS + 1:
            raise ValueError(f"{label} CSV may contain at most {MAX_SETTLEMENT_ROWS} rows")
        if not any(str(value or "").strip() for value in raw.values()):
            continue
        normalized = {str(key or "").strip().lower(): str(value or "").strip() for key, value in raw.items()}
        if None in raw:
            raise ValueError(f"{label} CSV row {row_number} has more values than headers")
        rows.append({"row_number": row_number, **normalized})
    if not rows:
        raise ValueError(f"{label} CSV contains no data rows")
    return rows


def _member_code(row: dict, label: str) -> str:
    value = row.get("member_code", "").strip().upper()
    if not value or len(value) > 80:
        raise ValueError(f"{label} row {row['row_number']}: member_code is required (max 80 characters)")
    return value


def _event_date(row: dict, field: str, label: str, start: date, end: date) -> date:
    try:
        parsed = date.fromisoformat(row.get(field, ""))
    except ValueError as exc:
        raise ValueError(f"{label} row {row['row_number']}: {field} must use YYYY-MM-DD") from exc
    if parsed < start or parsed > end:
        raise ValueError(f"{label} row {row['row_number']}: {field} must be within the close period")
    return parsed


def _amount(row: dict, field: str, label: str, *, positive: bool = False) -> Decimal:
    try:
        value = Decimal(row.get(field, ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} row {row['row_number']}: {field} must be a number") from exc
    if not value.is_finite() or value < 0 or (positive and value <= 0) or value > Decimal("1000000000000"):
        qualifier = "greater than zero" if positive else "zero or greater"
        raise ValueError(f"{label} row {row['row_number']}: {field} must be {qualifier}")
    return value


def _reference(row: dict, field: str, label: str) -> str:
    value = row.get(field, "").strip()
    if len(value) > 120:
        raise ValueError(f"{label} row {row['row_number']}: {field} exceeds 120 characters")
    return value


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_settlement_sources(collection: bytes, processor: bytes, payouts: bytes, period_start: date, period_end: date) -> dict:
    if period_end < period_start:
        raise ValueError("Period end cannot precede period start")
    collection_rows = _read_rows(collection, {"member_code", "delivery_date", "quantity_liters", "receipt_reference"}, "Collection")
    processor_rows = _read_rows(processor, {"member_code", "settlement_date", "accepted_liters", "gross_amount_kes", "deductions_kes", "net_amount_kes", "settlement_reference"}, "Processor settlement")
    payout_rows = _read_rows(payouts, {"member_code", "payout_date", "amount_kes", "payout_reference"}, "Payout")

    accounts: dict[str, dict] = defaultdict(lambda: {
        "collection_liters": Decimal(0), "processor_liters": Decimal(0),
        "gross_amount_kes": Decimal(0), "deductions_kes": Decimal(0),
        "net_amount_kes": Decimal(0), "payout_amount_kes": Decimal(0),
        "collection_rows": [], "processor_rows": [], "payout_rows": [],
        "collection_references": [], "processor_references": [], "payout_references": [],
    })

    for row in collection_rows:
        member = _member_code(row, "Collection")
        _event_date(row, "delivery_date", "Collection", period_start, period_end)
        quantity = _amount(row, "quantity_liters", "Collection", positive=True)
        reference = _reference(row, "receipt_reference", "Collection")
        account = accounts[member]
        account["collection_liters"] += quantity
        account["collection_rows"].append(row["row_number"])
        if reference:
            account["collection_references"].append(reference)

    for row in processor_rows:
        member = _member_code(row, "Processor settlement")
        _event_date(row, "settlement_date", "Processor settlement", period_start, period_end)
        liters = _amount(row, "accepted_liters", "Processor settlement", positive=True)
        gross = _amount(row, "gross_amount_kes", "Processor settlement")
        deductions = _amount(row, "deductions_kes", "Processor settlement")
        net = _amount(row, "net_amount_kes", "Processor settlement")
        reference = _reference(row, "settlement_reference", "Processor settlement")
        account = accounts[member]
        account["processor_liters"] += liters
        account["gross_amount_kes"] += gross
        account["deductions_kes"] += deductions
        account["net_amount_kes"] += net
        account["processor_rows"].append(row["row_number"])
        if reference:
            account["processor_references"].append(reference)

    for row in payout_rows:
        member = _member_code(row, "Payout")
        _event_date(row, "payout_date", "Payout", period_start, period_end)
        amount = _amount(row, "amount_kes", "Payout")
        reference = _reference(row, "payout_reference", "Payout")
        account = accounts[member]
        account["payout_amount_kes"] += amount
        account["payout_rows"].append(row["row_number"])
        if reference:
            account["payout_references"].append(reference)

    output = []
    for member in sorted(accounts):
        account = accounts[member]
        collection_liters = account["collection_liters"].quantize(TENTH_LITRE)
        processor_liters = account["processor_liters"].quantize(TENTH_LITRE)
        gross = _money(account["gross_amount_kes"])
        deductions = _money(account["deductions_kes"])
        net = _money(account["net_amount_kes"])
        payout = _money(account["payout_amount_kes"])
        volume_variance = (processor_liters - collection_liters).quantize(TENTH_LITRE)
        arithmetic_variance = _money(gross - deductions - net)
        payout_variance = _money(payout - net)
        issues = []
        if not account["collection_rows"]:
            issues.append("missing_collection")
        if not account["processor_rows"]:
            issues.append("missing_processor_settlement")
        if not account["payout_rows"]:
            issues.append("missing_payout")
        if account["collection_rows"] and account["processor_rows"] and volume_variance != 0:
            issues.append("volume_variance")
        if account["processor_rows"] and arithmetic_variance != 0:
            issues.append("processor_amount_variance")
        if account["processor_rows"] and account["payout_rows"] and payout_variance != 0:
            issues.append("payout_variance")
        output.append({
            "member_code": member,
            "collection_liters": collection_liters, "processor_liters": processor_liters,
            "volume_variance_liters": volume_variance, "gross_amount_kes": gross,
            "deductions_kes": deductions, "net_amount_kes": net,
            "payout_amount_kes": payout, "processor_arithmetic_variance_kes": arithmetic_variance,
            "payout_variance_kes": payout_variance, "status": "reconciled" if not issues else "needs_review",
            "issues": issues, "review_status": "not_required" if not issues else "pending",
            "collection_rows": account["collection_rows"], "processor_rows": account["processor_rows"], "payout_rows": account["payout_rows"],
            "collection_references": account["collection_references"], "processor_references": account["processor_references"], "payout_references": account["payout_references"],
        })
    return {"items": output, "collection_row_count": len(collection_rows), "processor_row_count": len(processor_rows), "payout_row_count": len(payout_rows)}
