"use client";

import { useState } from "react";
import { CheckCircle2, FileUp, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";

type Row = Record<string, any>;
type ImportPreview = {
  evidence_artifact_id: string;
  filename: string;
  sha256: string;
  schema_fingerprint: string;
  headers: string[];
  row_count: number;
  max_rows: number;
};
type MappingProfile = {
  id: string;
  source_system: string;
  version: number;
  status: string;
  schema_fingerprint: string;
  mapping_definition: { columns?: Record<string, string>; defaults?: Record<string, string> };
};

const mappingFields = [
  ["amount", "Amount"],
  ["line_type", "Line type"],
  ["direction", "Direction"],
  ["source_reference", "Source reference"],
  ["occurred_on", "Date (ISO YYYY-MM-DD)"],
  ["quantity", "Quantity"],
  ["unit", "Unit"],
] as const;

const lineTypes = ["accepted_supply", "quality_adjustment", "deduction", "credit_note", "other"];
const directions = ["increase", "decrease", "informational"];

export function ReceivableSourceImport({ caseRecord, token, onImported }: {
  caseRecord: Row;
  token: string;
  onImported: () => Promise<unknown>;
}) {
  const csvFiles = (caseRecord.evidence || []).filter((file: Row) => file.filename?.toLowerCase().endsWith(".csv") && file.media_type === "text/csv");
  const [artifactId, setArtifactId] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [profiles, setProfiles] = useState<MappingProfile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [sourceSystem, setSourceSystem] = useState("Processor CSV export");
  const [columns, setColumns] = useState<Record<string, string>>({});
  const [defaults, setDefaults] = useState<Record<string, string>>({ line_type: "accepted_supply", direction: "increase" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  if (!csvFiles.length || caseRecord.status !== "draft" || caseRecord.lines?.length) return null;

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); setNotice(success); }
    catch (e) { setError(e instanceof Error ? e.message : "Source mapping action failed"); }
    finally { setBusy(false); }
  }

  async function previewFile() {
    if (!artifactId) { setError("Select a CSV already attached to this claim."); return; }
    await run(async () => {
      const result = await api<ImportPreview>(`/api/v1/cooperative/receivables/cases/${caseRecord.id}/source-import/preview`, token, {
        method: "POST", body: JSON.stringify({ evidence_artifact_id: artifactId }),
      });
      setPreview(result); setProfileId(""); setColumns({});
      setDefaults({ line_type: "accepted_supply", direction: "increase" });
      setSourceSystem("Processor CSV export");
      const saved = await api<MappingProfile[]>(`/api/v1/cooperative/receivables/source-mappings?schema_fingerprint=${result.schema_fingerprint}`, token);
      setProfiles(saved);
    }, "CSV structure loaded. Values remain private in your cooperative workspace.");
  }

  function selectProfile(profile: MappingProfile, headers = preview?.headers || []) {
    setProfileId(profile.id);
    setSourceSystem(profile.source_system);
    setColumns(profile.mapping_definition?.columns || {});
    setDefaults(profile.mapping_definition?.defaults || {});
    if (!headers.length) setPreview(null);
  }

  function buildMapping() {
    const mappedColumns = Object.fromEntries(Object.entries(columns).filter(([, header]) => Boolean(header)));
    const mappedDefaults: Record<string, string> = {};
    for (const field of ["line_type", "direction"]) {
      if (!mappedColumns[field] && defaults[field]) mappedDefaults[field] = defaults[field];
    }
    return { columns: mappedColumns, defaults: mappedDefaults };
  }

  async function saveMapping() {
    if (!preview) { setError("Preview the CSV columns before saving a mapping."); return; }
    await run(async () => {
      const saved = await api<MappingProfile>("/api/v1/cooperative/receivables/source-mappings", token, {
        method: "POST", body: JSON.stringify({
          source_system: sourceSystem, record_type: "receivable_lines",
          schema_fingerprint: preview.schema_fingerprint, mapping_definition: buildMapping(),
        }),
      });
      setProfiles((current) => [saved, ...current]);
      setProfileId(saved.id);
    }, "Mapping saved as a draft. Review the target fields, then approve it for this file schema.");
  }

  async function approveMapping() {
    if (!profileId) return;
    await run(async () => {
      const approved = await api<MappingProfile>(`/api/v1/cooperative/receivables/source-mappings/${profileId}/approve`, token, { method: "POST" });
      setProfiles((current) => current.map((item) => item.id === approved.id ? approved : item));
    }, "Mapping approved. You can now import the rows into this draft claim.");
  }

  async function applyMapping() {
    if (!preview || !profileId) return;
    await run(async () => {
      const result = await api<{ rows_imported: number; signed_total: string; currency: string }>(
        `/api/v1/cooperative/receivables/cases/${caseRecord.id}/source-import/apply`, token, {
          method: "POST", body: JSON.stringify({ evidence_artifact_id: preview.evidence_artifact_id, mapping_profile_id: profileId }),
        },
      );
      setNotice(`Imported ${result.rows_imported} rows totaling ${result.signed_total} ${result.currency}.`);
      await onImported();
    }, "Source rows imported.");
  }

  function columnSelect(field: string, label: string) {
    return <label className="field" key={field}><span>{label}</span><select value={columns[field] || ""} onChange={(event) => setColumns({ ...columns, [field]: event.target.value })}>
      <option value="">{field === "amount" ? "Choose source column…" : "Not mapped"}</option>
      {preview?.headers.map((header) => <option key={header} value={header}>{header}</option>)}
    </select></label>;
  }

  const selectedProfile = profiles.find((profile) => profile.id === profileId);
  const selectedColumns = selectedProfile?.mapping_definition?.columns || {};
  const selectedDefaults = selectedProfile?.mapping_definition?.defaults || {};

  return <section className="receivable-subsection" aria-label="CSV source mapping">
    <h3>Map a source export <small>repeatable, reviewable import</small></h3>
    <p className="receivable-help">Terravanta fingerprints the CSV headers and stores each imported line with its source file and row locator. It does not guess columns or match debt automatically. Import is limited to an empty draft claim, and the mapped signed total must equal the claim amount.</p>
    {error ? <div role="alert" className="workspace-load-error"><p>{error}</p></div> : null}
    {notice ? <div role="status" className="receivable-notice"><CheckCircle2 size={14} /><span>{notice}</span></div> : null}
    <div className="receivable-form-grid">
      <label className="field receivable-span"><span>Attached CSV source</span><select value={artifactId} onChange={(event) => { setArtifactId(event.target.value); setPreview(null); setProfiles([]); setProfileId(""); }}>
        <option value="">Choose a CSV file…</option>{csvFiles.map((file: Row) => <option key={file.id} value={file.id}>{file.filename} · {file.sha256?.slice(0, 12)}…</option>)}
      </select></label>
      <button type="button" className="button button-outline receivable-span" disabled={busy || !artifactId} onClick={() => void previewFile()}><RefreshCw size={13} />Preview headers and row count</button>
    </div>
    {preview ? <>
      <div className="receivable-response-row"><span><strong>{preview.row_count} rows · {preview.filename}</strong><small>Schema fingerprint {preview.schema_fingerprint}</small><small>File SHA-256 {preview.sha256}</small></span></div>
      <p className="receivable-help">Columns: {preview.headers.join(" · ")}</p>
      {profiles.length ? <label className="field"><span>Reuse only if this is the same source and field meaning</span><select value={profileId} onChange={(event) => { const chosen = profiles.find((profile) => profile.id === event.target.value); if (chosen) selectProfile(chosen); else { setProfileId(""); setColumns({}); setDefaults({ line_type: "accepted_supply", direction: "increase" }); setSourceSystem("Processor CSV export"); } }}>
        <option value="">Create a new mapping version…</option>{profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.source_system} · v{profile.version} · {profile.status}</option>)}
      </select></label> : null}
      {!selectedProfile ? <>
        <label className="field"><span>Source export label</span><input value={sourceSystem} maxLength={120} onChange={(event) => setSourceSystem(event.target.value)} /></label>
        <div className="receivable-form-grid">
          {columnSelect("amount", "Amount · required")}
          {columnSelect("source_reference", "Source reference · optional")}
          {columnSelect("occurred_on", "Date in ISO format · optional")}
          {columnSelect("quantity", "Quantity · optional")}
          {columnSelect("unit", "Unit · optional")}
          {columnSelect("line_type", "Line type column · optional")}
          {!columns.line_type ? <label className="field"><span>Fixed line type</span><select value={defaults.line_type || "accepted_supply"} onChange={(event) => setDefaults({ ...defaults, line_type: event.target.value })}>{lineTypes.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label> : null}
          {columnSelect("direction", "Direction column · optional")}
          {!columns.direction ? <label className="field"><span>Fixed direction</span><select value={defaults.direction || "increase"} onChange={(event) => setDefaults({ ...defaults, direction: event.target.value })}>{directions.map((value) => <option key={value} value={value}>{value}</option>)}</select></label> : null}
        </div>
        <button type="button" className="button button-outline" disabled={busy || !columns.amount || sourceSystem.trim().length < 2} onClick={() => void saveMapping()}>Save mapping draft</button>
      </> : <>
        <p className="receivable-help">Selected mapping: {selectedProfile.source_system} v{selectedProfile.version}. Only this exact schema fingerprint can reuse it.</p>
        <div className="receivable-line-list" aria-label="Saved source field assignments">
          {mappingFields.map(([field, label]) => <div key={field}><span>{label}</span><strong>{selectedColumns[field] ? `CSV column “${selectedColumns[field]}”` : selectedDefaults[field] ? `Fixed value “${selectedDefaults[field]}”` : "Not mapped"}</strong></div>)}
        </div>
        {selectedProfile.status === "draft" ? <button type="button" className="button button-outline" disabled={busy} onClick={() => void approveMapping()}>I reviewed and approve this mapping</button> : null}
        {selectedProfile.status === "approved" ? <button type="button" className="button button-primary" disabled={busy} onClick={() => void applyMapping()}><FileUp size={13} />Import mapped rows into draft claim</button> : null}
      </>}
    </> : null}
    <small className="receivable-help">Amounts, dates, and directions are parsed deterministically. A new header layout needs a new profile version; imported lines stay cooperative-attested until the processor responds.</small>
  </section>;
}
