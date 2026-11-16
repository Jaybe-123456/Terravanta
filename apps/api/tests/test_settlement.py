from datetime import date

from app.settlement import parse_settlement_sources


def sources(*, payout="MEM-1,2026-11-01,480.00,P-1\n", processor="MEM-1,2026-11-01,10,500,20,480,S-1\n"):
    collection = b"member_code,delivery_date,quantity_liters,receipt_reference\nMEM-1,2026-11-01,10,C-1\n"
    processor_bytes = ("member_code,settlement_date,accepted_liters,gross_amount_kes,deductions_kes,net_amount_kes,settlement_reference\n" + processor).encode()
    payout_bytes = ("member_code,payout_date,amount_kes,payout_reference\n" + payout).encode()
    return collection, processor_bytes, payout_bytes


def test_exact_month_end_close_reconciles_and_retains_source_rows():
    collection, processor, payout = sources()
    result = parse_settlement_sources(collection, processor, payout, date(2026, 11, 1), date(2026, 11, 30))
    item = result["items"][0]
    assert item["status"] == "reconciled"
    assert item["collection_liters"] == item["processor_liters"] == 10
    assert item["payout_variance_kes"] == 0
    assert item["collection_rows"] == [2]
    assert result["collection_row_count"] == 1


def test_volume_arithmetic_and_payout_variances_route_to_review():
    collection, processor, payout = sources(processor="MEM-1,2026-11-01,8,400,20,380,S-1\n", payout="MEM-1,2026-11-01,360,P-1\n")
    result = parse_settlement_sources(collection, processor, payout, date(2026, 11, 1), date(2026, 11, 30))
    item = result["items"][0]
    assert item["status"] == "needs_review"
    assert item["volume_variance_liters"] == -2
    assert item["payout_variance_kes"] == -20
    assert "volume_variance" in item["issues"]
    assert item["review_status"] == "pending"


def test_member_missing_in_one_export_is_an_exception_not_dropped():
    collection, processor, payout = sources(payout="MEM-2,2026-11-01,20,P-2\n")
    result = parse_settlement_sources(collection, processor, payout, date(2026, 11, 1), date(2026, 11, 30))
    by_member = {row["member_code"]: row for row in result["items"]}
    assert by_member["MEM-1"]["issues"] == ["missing_payout"]
    assert by_member["MEM-2"]["issues"] == ["missing_collection", "missing_processor_settlement"]


def test_source_parser_rejects_out_of_period_rows_and_missing_headers():
    collection, processor, payout = sources()
    collection = collection.replace(b"2026-11-01", b"2026-10-31")
    import pytest
    with pytest.raises(ValueError, match="within the close period"):
        parse_settlement_sources(collection, processor, payout, date(2026, 11, 1), date(2026, 11, 30))
    with pytest.raises(ValueError, match="requires unique headers"):
        parse_settlement_sources(b"member_code,delivery_date\nMEM-1,2026-11-01\n", processor, payout, date(2026, 11, 1), date(2026, 11, 30))


def test_close_review_approval_and_statement_pack_are_server_gated(client):
    token = client.post("/api/v1/auth/demo-login?role=cooperative_admin").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    collection, processor, payout = sources(processor="MEM-1,2026-11-01,8,400,20,380,S-1\n", payout="MEM-1,2026-11-01,360,P-1\n")
    data = {"period_start": "2026-11-01", "period_end": "2026-11-30"}
    files = {
        "collection_file": ("collection.csv", collection, "text/csv"),
        "processor_file": ("processor.csv", processor, "text/csv"),
        "payout_file": ("payout.csv", payout, "text/csv"),
    }
    created = client.post("/api/v1/cooperative/settlement-closes", headers=headers, data=data, files=files)
    assert created.status_code == 201, created.text
    result = created.json()
    close_id = result["close"]["id"]
    item = result["items"][0]
    assert result["close"]["exception_count"] == 1
    assert result["close"]["unresolved_exception_count"] == 1
    assert result["close"]["issue_counts"] == {"volume_variance": 1, "payout_variance": 1}
    assert client.get(f"/api/v1/cooperative/settlement-closes/{close_id}/statement-pack", headers=headers).status_code == 409
    blocked = client.post(f"/api/v1/cooperative/settlement-closes/{close_id}/approve", headers=headers, json={"note": "Review close"})
    assert blocked.status_code == 409
    follow_up = client.post(
        f"/api/v1/cooperative/settlement-closes/{close_id}/items/{item['id']}/review",
        headers=headers, json={"decision": "follow_up", "note": "Need source voucher"},
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["close"]["unresolved_exception_count"] == 1
    reviewed = client.post(
        f"/api/v1/cooperative/settlement-closes/{close_id}/items/{item['id']}/review",
        headers=headers, json={"decision": "accept_with_note", "note": "Source variance reviewed"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["close"]["unresolved_exception_count"] == 0
    approved = client.post(f"/api/v1/cooperative/settlement-closes/{close_id}/approve", headers=headers, json={"note": "Finance close reviewed"})
    assert approved.status_code == 200
    assert approved.json()["close"]["status"] == "approved"
    report = client.get(f"/api/v1/cooperative/settlement-closes/{close_id}/statement-pack", headers=headers)
    assert report.status_code == 200
    assert "MEM-1" in report.text


def test_farmer_cannot_create_a_cooperative_settlement_close(client):
    token = client.post("/api/v1/auth/demo-login?role=farmer").json()["access_token"]
    response = client.get("/api/v1/cooperative/settlement-closes", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
