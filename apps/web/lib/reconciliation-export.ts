type ExportRow = {
  row_number?: number;
  farm_code?: string;
  farm_name?: string | null;
  collection_date?: string | null;
  submitted_quantity?: string | null;
  quantity_liters?: number | null;
  receipt_reference?: string | null;
  status?: string;
  review_status?: string;
  review_note?: string | null;
  discrepancies?: string[];
  matched_delivery?: { quantity?: number; unit?: string; reference?: string; lot_code?: string } | null;
  trace_graph?: Array<{ label?: string }>;
};

const columns = [
  "source_row", "farm_code", "consented_farm_name", "collection_date", "submitted_litres",
  "receipt_reference", "recorded_delivery_litres", "recorded_delivery_reference", "product_lot",
  "match_status", "review_status", "review_note", "exception_reasons", "trace_path",
];

function csvCell(value: unknown): string {
  const raw = String(value ?? "");
  // Prefix spreadsheet formula-like strings so opening the output cannot run them.
  const neutralized = /^[\t\r ]*[=+\-@]/.test(raw) ? `'${raw}` : raw;
  return `"${neutralized.replaceAll('"', '""')}"`;
}

export function buildReconciliationCsv(items: ExportRow[]): string {
  const rows = items.map((item) => [
    item.row_number,
    item.farm_code,
    item.farm_name,
    item.collection_date,
    item.submitted_quantity,
    item.receipt_reference,
    item.matched_delivery ? `${item.matched_delivery.quantity ?? ""} ${item.matched_delivery.unit ?? ""}`.trim() : "",
    item.matched_delivery?.reference,
    item.matched_delivery?.lot_code,
    item.status,
    item.review_status,
    item.review_note,
    item.discrepancies?.join("; "),
    item.trace_graph?.map((node) => node.label).join(" > "),
  ]);
  return `\uFEFF${[columns, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
}
