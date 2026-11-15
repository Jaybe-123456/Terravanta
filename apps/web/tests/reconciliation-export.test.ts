import assert from "node:assert/strict";
import test from "node:test";
import { buildReconciliationCsv } from "../lib/reconciliation-export";

test("reconciled export includes source row, status and provenance path", () => {
  const csv = buildReconciliationCsv([{
    row_number: 2, farm_code: "KBU-1", farm_name: "Greenridge", collection_date: "2026-11-14",
    submitted_quantity: "20.7", receipt_reference: "R-1", status: "matched", review_status: "not_required",
    matched_delivery: { quantity: 20.7, unit: "L", reference: "R-1", lot_code: "LOT-1" },
    trace_graph: [{ label: "Greenridge" }, { label: "production record" }, { label: "LOT-1" }, { label: "R-1" }, { label: "Row 2" }],
  }]);
  assert.match(csv, /"source_row","farm_code"/);
  assert.match(csv, /"2","KBU-1","Greenridge","2026-11-14","20\.7"/);
  assert.match(csv, /"Greenridge > production record > LOT-1 > R-1 > Row 2"/);
});

test("CSV export quotes embedded separators and neutralizes formula-like values", () => {
  const csv = buildReconciliationCsv([{
    row_number: 3, farm_code: "=HYPERLINK(\"https://bad.example\")", farm_name: "Farm, \"One\"",
    status: "invalid_row", review_note: "Line one\nLine two",
  }]);
  assert.match(csv, /"'=HYPERLINK\(""https:\/\/bad\.example""\)"/);
  assert.match(csv, /"Farm, ""One"""/);
  assert.match(csv, /"Line one\nLine two"/);
});
