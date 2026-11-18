"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowDownToLine, CheckCircle2, Clock3, FileUp, Inbox, RefreshCw, Send, ShieldCheck } from "lucide-react";
import { API_URL, api } from "@/lib/api";

type Row = Record<string, any>;

function amount(value: unknown, currency = "KES") {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? new Intl.NumberFormat("en-KE", { style: "currency", currency, maximumFractionDigits: 2 }).format(numeric) : String(value);
}

function Label({ children }: { children: React.ReactNode }) { return <span className="receivable-label">{children}</span>; }

export function ReceivablesDesk({ role, token }: { role: string; token: string }) {
  const processorMode = role === "processor_admin";
  const [cases, setCases] = useState<Row[]>([]);
  const [relationships, setRelationships] = useState<Row[]>([]);
  const [summary, setSummary] = useState<Row | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<Row | null>(null);
  const [claimLines, setClaimLines] = useState<Row[]>([]);
  const [lineDraft, setLineDraft] = useState<Row>({ line_type: "accepted_supply", direction: "increase", source_reference: "", occurred_on: "", amount: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const list = await api<Row[]>(processorMode ? "/api/v1/processor/receivables/cases" : "/api/v1/cooperative/receivables/cases", token);
      setCases(list);
      if (!processorMode) {
        const [relationList, totals] = await Promise.all([
          api<Row[]>("/api/v1/cooperative/receivables/relationships", token),
          api<Row>("/api/v1/cooperative/receivables/summary", token),
        ]);
        setRelationships(relationList); setSummary(totals);
      }
      const nextId = selectedId && list.some((item) => item.id === selectedId) ? selectedId : list[0]?.id || "";
      setSelectedId(nextId);
      setSelected(nextId ? await api<Row>(`${processorMode ? "/api/v1/processor" : "/api/v1/cooperative"}/receivables/cases/${nextId}`, token) : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load receivables workspace");
    }
  }, [processorMode, selectedId, token]);

  useEffect(() => { void load(); }, [load]);

  async function run(action: () => Promise<unknown>, message: string): Promise<boolean> {
    setBusy(true); setError(""); setNotice("");
    try { await action(); setNotice(message); await load(); return true; }
    catch (e) { setError(e instanceof Error ? e.message : "The action could not be completed"); return false; }
    finally { setBusy(false); }
  }

  async function createRelationship(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const success = await run(() => api("/api/v1/cooperative/receivables/relationships", token, {
      method: "POST", body: JSON.stringify({ counterparty_name: values.counterparty_name, relationship_type: "processor", external_reference: values.external_reference, counterparty_organization_id: values.counterparty_organization_id || null }),
    }), "Processor relationship saved. You can now open a claim register.");
    if (success) form.reset();
  }

  async function createCase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const body = {
      relationship_id: values.relationship_id,
      source_document_type: values.source_document_type,
      source_reference: values.source_reference,
      period_start: values.period_start || null, period_end: values.period_end || null,
      invoice_date: values.invoice_date || null, due_date: values.due_date || null,
      due_date_basis: values.due_date ? values.due_date_basis : "unknown",
      currency: values.currency, asserted_amount: values.asserted_amount,
      description: values.description || "",
      lines: claimLines.map((line) => ({ ...line, occurred_on: line.occurred_on || null, amount: String(line.amount) })),
    };
    const success = await run(async () => {
      const created = await api<Row>("/api/v1/cooperative/receivables/cases", token, { method: "POST", body: JSON.stringify(body) });
      setSelectedId(created.id);
      setSelected(created);
    }, "Claim draft created. Attach the source documents before asserting and submitting it.");
    if (success) { form.reset(); setClaimLines([]); }
  }

  async function uploadEvidence(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const file = form.get("file");
    if (!(file instanceof File) || !file.size) { setError("Choose a PDF or CSV file first."); return; }
    const success = await run(async () => {
      const upload = new FormData(); upload.append("file", file);
      upload.append("artifact_type", String(form.get("artifact_type") || "processor_statement"));
      upload.append("source_reference", String(form.get("source_reference") || ""));
      await api(`/api/v1/cooperative/receivables/cases/${selected.id}/evidence`, token, { method: "POST", body: upload });
    }, "Private evidence attached to the claim.");
    if (success) formElement.reset();
  }

  async function download(path: string, filename: string) {
    try {
      const response = await fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" });
      if (!response.ok) { const result = await response.json().catch(() => ({})); throw new Error(result.detail || "Download failed"); }
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : "Download failed"); }
  }

  async function respond(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected) return;
    const form = event.currentTarget; const v = Object.fromEntries(new FormData(form));
    const body = { response_status: v.response_status, confirmed_amount: v.confirmed_amount || null, disputed_amount: v.disputed_amount || null, response_reference: v.response_reference || "", response_note: v.response_note };
    const success = await run(() => api(`/api/v1/processor/receivables/cases/${selected.id}/responses`, token, { method: "POST", body: JSON.stringify(body) }), "Processor response recorded in the claim history.");
    if (success) form.reset();
  }

  async function recordDecision(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected) return;
    const form = event.currentTarget; const v = Object.fromEntries(new FormData(form));
    const body = { ...v, price_amount: v.price_amount || null, evidence_artifact_id: v.evidence_artifact_id || null };
    const success = await run(() => api(`/api/v1/cooperative/receivables/cases/${selected.id}/pilot-decisions`, token, { method: "POST", body: JSON.stringify(body) }), "Budget-owner decision recorded. This is an account attestation; retain source evidence for validation.");
    if (success) form.reset();
  }

  async function recordAndAllocate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected) return;
    const form = event.currentTarget; const v = Object.fromEntries(new FormData(form));
    const received = Number(v.amount);
    const remaining = Number(selected.amounts?.seller_asserted_less_reported_receipts ?? selected.asserted_amount ?? 0);
    const defaultAllocation = remaining > 0 ? String(Math.min(received, remaining)) : null;
    const success = await run(() => api<Row>(`/api/v1/cooperative/receivables/cases/${selected.id}/receipts`, token, { method: "POST", body: JSON.stringify({ source_reference: v.source_reference, received_on: v.received_on, amount: v.amount, currency: selected.currency, payment_rail: v.payment_rail, verification_status: v.verification_status, evidence_artifact_id: v.evidence_artifact_id || null, allocate_amount: v.allocate_amount || defaultAllocation }) }), "Receipt recorded; any allocation is limited to the remaining asserted claim balance.");
    if (success) form.reset();
  }

  const selectedCase = selected;
  return <section className="receivables-desk">
    <div className="receivables-toolbar">
      <div><p className="eyebrow">{processorMode ? "PROCESSOR ACCOUNTS PAYABLE" : "COOPERATIVE ACCOUNTS RECEIVABLE"}</p>
        <h2>{processorMode ? "Supplier claim inbox" : "Processor receivables register"}</h2>
        <p>{processorMode ? "Review the cooperative’s source-linked claim and record your organization’s response." : "Turn processor statements and delivery records into a claim with evidence, a clear age, and a recorded response."}</p></div>
      <button type="button" className="button button-outline" onClick={() => void load()} disabled={busy}><RefreshCw size={14} />Refresh</button>
    </div>
    {error ? <div role="alert" className="workspace-load-error"><div><strong>Receivables request failed</strong><p>{error}</p></div></div> : null}
    {notice ? <div role="status" className="receivable-notice"><CheckCircle2 size={16} /><span>{notice}</span></div> : null}
    {!processorMode ? <>
      <div className="receivable-metrics">
        <div><span>Claims in register</span><strong>{summary?.claim_count ?? "—"}</strong><small>{summary?.open_claim_count ?? 0} open; includes drafts in register count</small></div>
        <div><span>Seller open balance</span><strong>{summary ? amount(summary.seller_reported_outstanding_total) : "—"}</strong><small>Seller assertions less seller-reported receipts</small></div>
        <div><span>Processor-confirmed remaining</span><strong>{summary ? amount(summary.processor_confirmed_outstanding_total) : "—"}</strong><small>Confirmed value less evidence-reviewed receipts</small></div>
        <div><span>Age basis</span><strong>{summary?.as_of || "Claim by claim"}</strong><small>Reviewed due dates; invoice age otherwise</small></div>
      </div>
      <section className="card receivable-aging-card" aria-label="Open receivable balance by age">
        <div className="panel-title"><div><p className="eyebrow">OPEN CLAIM AGING</p><h2>Where the seller balance sits</h2><p className="muted">Seller-reported balance includes seller-attested receipts; processor-confirmed balance subtracts only evidence-reviewed receipts.</p></div><span className="record-count">As of {summary?.as_of || "—"}</span></div>
        <div className="receivable-aging-grid"><strong>Age bucket</strong><strong>Seller-reported</strong><strong>Processor-confirmed</strong>
          {[
            "not_yet_due", "due_today", "overdue_1_30", "overdue_31_60", "overdue_61_90", "overdue_90_plus",
            "invoice_not_yet_issued", "invoice_today", "invoice_1_30", "invoice_31_60", "invoice_61_90", "invoice_90_plus", "date_unknown",
          ].filter((bucket) => summary?.aging_buckets?.[bucket] || summary?.seller_asserted_balance_by_age_bucket?.[bucket] || summary?.processor_confirmed_balance_by_age_bucket?.[bucket]).map((bucket) => <div className="receivable-aging-row" key={bucket}><span>{bucket.replaceAll("_", " ")}</span><b>{amount(summary?.seller_asserted_balance_by_age_bucket?.[bucket] || "0")}</b><b>{amount(summary?.processor_confirmed_balance_by_age_bucket?.[bucket] || "0")}</b></div>)}
          {!summary?.open_claim_count ? <p className="receivable-help receivable-span">Open a source-backed claim to see its age and separately attributed balances here.</p> : null}
        </div>
      </section>
      <div className="receivable-layout">
        <div className="receivable-column">
          <section className="card receivable-card">
            <div className="panel-title"><div><p className="eyebrow">PARTNER SETUP</p><h2>Connect a processor</h2><p className="muted">A claim only enters a processor inbox after you select a registered processor workspace.</p></div></div>
            <form className="receivable-form" onSubmit={createRelationship}>
              <label className="field"><span>Processor organization ID</span><input name="counterparty_organization_id" required minLength={36} maxLength={36} placeholder="UUID provided during authorized onboarding" /></label>
              <label className="field"><span>Name shown in your records</span><input name="counterparty_name" required minLength={2} maxLength={180} placeholder="e.g. Processor name" /></label>
              <label className="field"><span>Your processor account reference</span><input name="external_reference" required minLength={2} maxLength={120} placeholder="Account or supply relationship ID" /></label>
              <button className="button button-outline" disabled={busy}>Save processor relationship</button>
              <small className="receivable-help">Terravanta must provision the processor organization and its named reviewer. The organization ID is shared only with the authorized cooperative contact.</small>
            </form>
          </section>
          <section className="card receivable-card">
            <div className="panel-title"><div><p className="eyebrow">CLAIM INTAKE</p><h2>Open a receivable claim</h2><p className="muted">The amount is your cooperative’s assertion until the processor records its response.</p></div></div>
            <form className="receivable-form receivable-form-grid" onSubmit={createCase}>
              <label className="field"><span>Processor relationship</span><select name="relationship_id" required defaultValue=""><option value="">Choose relationship…</option>{relationships.map((r) => <option key={r.id} value={r.id}>{r.counterparty_name} · {r.external_reference} · {r.status}</option>)}</select></label>
              <label className="field"><span>Source statement type</span><select name="source_document_type" required defaultValue="processor_statement"><option value="processor_statement">Processor statement</option><option value="delivery_statement">Delivery statement</option><option value="payout_statement">Payout statement</option><option value="invoice">Invoice</option><option value="other">Other</option></select></label>
              <label className="field"><span>Statement / invoice reference</span><input name="source_reference" required minLength={2} maxLength={160} /></label>
              <label className="field"><span>Seller-asserted amount (KES)</span><input name="asserted_amount" type="number" min="0.01" step="0.01" required /></label>
              <label className="field"><span>Invoice date</span><input name="invoice_date" type="date" /></label>
              <label className="field"><span>Due date (optional)</span><input name="due_date" type="date" /></label>
              <label className="field"><span>Due-date review basis</span><select name="due_date_basis" defaultValue="manual_review"><option value="manual_review">Cooperative reviewer checked source document</option></select><small>Contract snapshots are not yet managed here; attach and review the source document before recording a due date.</small></label>
              <label className="field"><span>Statement period start</span><input name="period_start" type="date" /></label>
              <label className="field"><span>Statement period end</span><input name="period_end" type="date" /></label>
              <label className="field receivable-span"><span>Claim description / basis</span><textarea name="description" maxLength={4000} placeholder="What amount do you believe is outstanding, and which supply period does it relate to?" /></label>
              <div className="receivable-line-builder receivable-span"><div><strong>Claim components</strong><small>Optional, but recommended: break the total into accepted supply and adjustments so the processor can respond to each basis.</small></div>
                <div className="receivable-line-inputs">
                  <select aria-label="Claim component type" value={lineDraft.line_type} onChange={(e) => setLineDraft({ ...lineDraft, line_type: e.target.value })}><option value="accepted_supply">Accepted supply</option><option value="quality_adjustment">Quality adjustment</option><option value="deduction">Deduction</option><option value="credit_note">Credit note</option><option value="other">Other</option></select>
                  <select aria-label="Claim component direction" value={lineDraft.direction} onChange={(e) => setLineDraft({ ...lineDraft, direction: e.target.value })}><option value="increase">Add to claim</option><option value="decrease">Subtract</option><option value="informational">Reference only</option></select>
                  <input aria-label="Component amount" type="number" min="0" step="0.01" placeholder="Amount" value={lineDraft.amount} onChange={(e) => setLineDraft({ ...lineDraft, amount: e.target.value })} />
                  <input aria-label="Component source reference" placeholder="Weighbridge / statement ref" value={lineDraft.source_reference} onChange={(e) => setLineDraft({ ...lineDraft, source_reference: e.target.value })} />
                  <input aria-label="Component date" type="date" value={lineDraft.occurred_on} onChange={(e) => setLineDraft({ ...lineDraft, occurred_on: e.target.value })} />
                  <button type="button" className="button button-outline" disabled={!lineDraft.amount || Number(lineDraft.amount) < 0} onClick={() => { setClaimLines([...claimLines, { ...lineDraft }]); setLineDraft({ line_type: "accepted_supply", direction: "increase", source_reference: "", occurred_on: "", amount: "" }); }}>Add component</button>
                </div>
                {claimLines.length ? <div className="receivable-line-list">{claimLines.map((line, index) => <div key={`${line.line_type}-${index}`}><span>{line.line_type.replaceAll("_", " ")} · {line.direction} {line.source_reference ? `· ${line.source_reference}` : ""}</span><strong>{amount(line.amount)}</strong><button type="button" aria-label="Remove claim component" onClick={() => setClaimLines(claimLines.filter((_, i) => i !== index))}>×</button></div>)}<small>Signed components total: {amount(claimLines.reduce((total, line) => total + (line.direction === "increase" ? Number(line.amount) : line.direction === "decrease" ? -Number(line.amount) : 0), 0))}. When components are present, this must equal the seller-asserted amount.</small></div> : null}
              </div>
              <button className="button button-primary receivable-span" disabled={busy || !relationships.length}><FileUp size={14} />Create claim draft</button>
            </form>
          </section>
        </div>
        <div className="receivable-column">
          <section className="card receivable-card">
            <div className="panel-title"><div><p className="eyebrow">CLAIM REGISTER</p><h2>Receivables and aging</h2><p className="muted">Past-due aging uses reviewed due dates; unknown due dates show invoice age only.</p></div><span className="record-count">{cases.length} claims</span></div>
            <div className="receivable-case-list">{cases.length ? cases.map((row) => <button type="button" key={row.id} onClick={() => { setSelectedId(row.id); void api<Row>(`/api/v1/cooperative/receivables/cases/${row.id}`, token).then(setSelected).catch((e) => setError(e.message)); }} className={`receivable-case-row ${selectedId === row.id ? "selected" : ""}`}>
              <span className="receivable-case-icon"><Clock3 size={15} /></span><span className="receivable-case-main"><strong>{row.source_reference}</strong><small>{row.status.replaceAll("_", " ")} · {row.aging?.bucket?.replaceAll("_", " ")}</small></span><b>{amount(row.asserted_amount, row.currency)}</b>
            </button>) : <div className="receivable-empty"><Inbox size={18} /><strong>No processor claims yet</strong><span>Open a claim from an actual statement. Demo claims are not loaded here.</span></div>}</div>
          </section>
          {selectedCase ? <CaseDetail caseRecord={selectedCase} token={token} busy={busy} processorMode={false} onUpload={uploadEvidence} onAction={(path: string, label: string) => void run(() => api(path, token, { method: "POST" }), label)} onDownload={() => void download(`/api/v1/cooperative/receivables/cases/${selectedCase.id}/evidence-export`, `terravanta-claim-${selectedCase.source_reference}.zip`)} onDownloadArtifact={(artifactId: string, filename: string) => void download(`/api/v1/receivables/cases/${selectedCase.id}/evidence/${artifactId}`, filename)} onRecordDecision={recordDecision} onReceipt={recordAndAllocate} /> : null}
        </div>
      </div>
    </> : <>
      <div className="receivable-counterparty-layout">
        <section className="card receivable-card">
          <div className="panel-title"><div><p className="eyebrow">AP REVIEW QUEUE</p><h2>Claims submitted to your organization</h2><p className="muted">Claims are visible only when a cooperative names your processor organization as its counterparty.</p></div><span className="record-count">{cases.length} submitted</span></div>
          <div className="receivable-case-list">{cases.length ? cases.map((row) => <button type="button" key={row.id} onClick={() => { setSelectedId(row.id); void api<Row>(`/api/v1/processor/receivables/cases/${row.id}`, token).then(setSelected).catch((e) => setError(e.message)); }} className={`receivable-case-row ${selectedId === row.id ? "selected" : ""}`}>
            <span className="receivable-case-icon"><Inbox size={15} /></span><span className="receivable-case-main"><strong>{row.source_reference}</strong><small>{row.status.replaceAll("_", " ")} · {row.aging?.bucket?.replaceAll("_", " ")}</small></span><b>{amount(row.asserted_amount, row.currency)}</b>
          </button>) : <div className="receivable-empty"><Inbox size={18} /><strong>Inbox is clear</strong><span>No cooperative has submitted a claim to this processor account.</span></div>}</div>
        </section>
        {selectedCase ? <CaseDetail caseRecord={selectedCase} token={token} busy={busy} processorMode onRespond={respond} onDownloadArtifact={(artifactId: string, filename: string) => void download(`/api/v1/receivables/cases/${selectedCase.id}/evidence/${artifactId}`, filename)} /> : null}
      </div>
    </>}
    <div className="receivable-boundary"><ShieldCheck size={15} /><span>Amounts remain attributed to the seller, processor, or source evidence. This register does not issue payment demands, initiate payments, determine legal arrears, or promise settlement timing.</span></div>
  </section>;
}

function CaseDetail({ caseRecord, token, busy, processorMode, onUpload, onAction, onDownload, onDownloadArtifact, onRespond, onRecordDecision, onReceipt }: any) {
  const c = caseRecord; const amounts = c.amounts || {};
  return <section className="card receivable-card receivable-detail">
    <div className="panel-title"><div><p className="eyebrow">CLAIM FILE · {c.status.replaceAll("_", " ").toUpperCase()}</p><h2>{c.source_reference}</h2><p className="muted">{c.source_document_type.replaceAll("_", " ")} · Created {new Date(c.created_at).toLocaleDateString("en-KE")}</p></div>{!processorMode && c.status !== "draft" ? <button className="button button-outline" type="button" onClick={onDownload}><ArrowDownToLine size={14} />Evidence export</button> : null}</div>
    <p className="receivable-description">{c.description || "No description provided. Source statement remains the basis for the seller assertion."}</p>
    <div className="receivable-amount-grid">
      <div><Label>Seller asserted</Label><strong>{amount(amounts.seller_asserted, c.currency)}</strong></div>
      <div><Label>Processor confirmed</Label><strong>{amount(amounts.latest_processor_confirmed, c.currency)}</strong></div>
      <div><Label>Processor disputed</Label><strong>{amount(amounts.latest_processor_disputed, c.currency)}</strong></div>
      <div><Label>Reviewed receipts allocated</Label><strong>{amount(amounts.evidence_reviewed_receipts_allocated, c.currency)}</strong></div>
    </div>
    <div className="receivable-age"><Clock3 size={15} /><span><strong>{c.aging?.days_past_due === null ? "Due date not reviewed" : c.aging?.bucket === "due_today" ? "Due today" : c.aging?.days_past_due === 0 ? "Not overdue" : `${c.aging?.days_past_due} days past due`}</strong><small>{c.aging?.bucket?.replaceAll("_", " ")} · As of {c.aging?.as_of}{c.aging?.days_past_due === null && c.aging?.days_since_invoice !== null ? ` · ${c.aging?.days_since_invoice} days since invoice` : ""}</small></span></div>
    {c.lines?.length ? <div className="receivable-subsection"><h3>Claim components <small>seller source attribution</small></h3><div className="receivable-line-list">{c.lines.map((line: Row) => <div key={line.id}><span>{line.line_type.replaceAll("_", " ")} · {line.direction} · {line.source_reference || "No source ref"}{line.occurred_on ? ` · ${line.occurred_on}` : ""}</span><strong>{amount(line.amount, line.currency)}</strong></div>)}</div></div> : null}
    <div className="receivable-subsection"><h3>Source evidence <small>{c.evidence?.length || 0} file(s)</small></h3>
      {c.evidence?.length ? <div className="receivable-evidence-list">{c.evidence.map((f: Row) => <div key={f.id}><span><strong>{f.filename}</strong><small>{f.artifact_type} · SHA-256 {f.sha256.slice(0, 14)}… · {f.size_bytes ? `${Math.ceil(f.size_bytes / 1024)} KB` : "size not listed"} · File ID {f.id}</small></span><span className="receivable-file-actions"><span className="evidence-source">{f.source_party}</span>{onDownloadArtifact ? <button type="button" className="text-link" onClick={() => onDownloadArtifact(f.id, f.filename)}><ArrowDownToLine size={12} />Download</button> : null}</span></div>)}</div> : <p className="receivable-help">No files attached. A source document is required before the cooperative can assert the claim.</p>}
      {!processorMode && c.status !== "paid" && c.status !== "closed" ? <form className="receivable-upload" onSubmit={onUpload}><input name="file" type="file" accept=".pdf,.csv,application/pdf,text/csv" required /><select name="artifact_type" defaultValue="processor_statement"><option value="processor_statement">Processor statement</option><option value="delivery_evidence">Delivery / weighbridge evidence</option><option value="invoice">Invoice</option><option value="payment_evidence">Payment evidence</option><option value="other">Other evidence</option></select><input name="source_reference" placeholder="Document reference (optional)" /><button className="button button-outline" disabled={busy}><FileUp size={13} />Attach privately</button><small>Private authenticated storage · PDF/CSV only · {c.status === "draft" ? "Attach before asserting." : "Add follow-up evidence to the case record."}</small></form> : null}
    </div>
    {!processorMode && c.status === "draft" ? <div className="receivable-action-row"><button className="button button-outline" disabled={busy || !c.evidence?.length} type="button" onClick={() => onAction(`/api/v1/cooperative/receivables/cases/${c.id}/assert`, "Seller assertion recorded; submit the claim to the registered processor.")}><CheckCircle2 size={14} />Assert claim</button><small>Attach at least one source document first, then assert and submit.</small></div> : null}
    {!processorMode && c.status === "asserted" ? <div className="receivable-action-row"><button className="button button-primary" disabled={busy || !c.counterparty_organization_id} type="button" onClick={() => onAction(`/api/v1/cooperative/receivables/cases/${c.id}/submit`, "Claim submitted to the processor inbox.")}><Send size={14} />Submit to processor</button><small>{c.counterparty_organization_id ? "The registered processor workspace will receive this claim." : "Link an active processor organization before submission."}</small></div> : null}
    {processorMode && c.status !== "paid" && c.status !== "closed" ? <form className="receivable-response" onSubmit={onRespond}><h3>Record processor response</h3><div className="receivable-form-grid">
      <label className="field"><span>Response</span><select name="response_status" defaultValue="accepted"><option value="accepted">Accept full claim</option><option value="partially_accepted">Accept part</option><option value="disputed">Dispute</option><option value="rejected">Reject</option><option value="needs_information">Request information</option></select></label>
      <label className="field"><span>Amount confirmed (KES)</span><input name="confirmed_amount" type="number" min="0" step="0.01" /></label>
      <label className="field"><span>Amount disputed (KES)</span><input name="disputed_amount" type="number" min="0" step="0.01" /></label>
      <label className="field"><span>Processor case / remittance reference</span><input name="response_reference" maxLength={160} /></label>
      <label className="field receivable-span"><span>Response basis</span><textarea name="response_note" minLength={2} maxLength={4000} required placeholder="Record what your organization confirms, disputes, or needs next." /></label>
      <button className="button button-primary receivable-span" disabled={busy}>Record response</button>
    </div></form> : null}
    {!processorMode && c.confirmations?.length ? <div className="receivable-subsection"><h3>Processor responses <small>{c.confirmations.length}</small></h3>{c.confirmations.map((r: Row) => <div className="receivable-response-row" key={r.id}><span><strong>{r.response_status.replaceAll("_", " ")}</strong><small>{r.response_reference || "No processor reference"} · {new Date(r.confirmed_at).toLocaleString("en-KE")}</small><p>{r.response_note}</p></span><b>{amount(r.confirmed_amount, r.currency)}</b></div>)}</div> : null}
    {!processorMode && c.confirmations?.length ? <>
      <form className="receivable-response receivable-research" onSubmit={onRecordDecision}><h3>Paid-repeat decision · budget owner</h3><p>Record the decision after the owner is directly asked. A “approved paid repeat” also requires an attached quote, purchase order or decision email; the form remains an account attestation.</p><div className="receivable-form-grid">
        <label className="field"><span>Budget owner name</span><input name="budget_owner_name" required minLength={2} maxLength={180} /></label>
        <label className="field"><span>Title / role</span><input name="budget_owner_title" maxLength={120} placeholder="Finance manager, CEO…" /></label>
        <label className="field"><span>Organization</span><input name="budget_owner_organization" required minLength={2} maxLength={180} /></label>
        <label className="field"><span>Decision</span><select name="decision" defaultValue="not_decided"><option value="approved_paid_repeat">Approved paid repeat</option><option value="conditional_paid_repeat">Conditional interest in paid repeat</option><option value="declined">Declined</option><option value="not_decided">No decision yet</option></select></label>
        <label className="field"><span>How was the decision captured?</span><select name="decision_source" defaultValue="direct_statement"><option value="direct_statement">Direct statement</option><option value="email">Email</option><option value="meeting_notes">Meeting notes</option><option value="other">Other</option></select></label>
        <label className="field"><span>Price / budget amount (KES)</span><input name="price_amount" type="number" min="0" step="0.01" /></label>
        <label className="field"><span>Price unit / repeat scope</span><input name="price_unit" maxLength={120} placeholder="Per close, per month, one-off…" /></label>
        <label className="field"><span>Decision date</span><input name="decided_on" type="date" required defaultValue={new Date().toISOString().slice(0, 10)} /></label>
        <label className="field receivable-span"><span>Evidence file ID (optional, attach to case above first)</span><input name="evidence_artifact_id" placeholder="UUID" /></label>
        <label className="field receivable-span"><span>What did the owner say, and what conditions remain?</span><textarea name="decision_note" required minLength={3} maxLength={4000} /></label>
        <label className="field receivable-span"><span>Next step and owner</span><input name="next_step" maxLength={500} /></label>
        <button className="button button-primary receivable-span" disabled={busy}>Save budget-owner decision</button>
      </div></form>
      {c.pilot_decisions?.length ? (() => { const decision = c.pilot_decisions[c.pilot_decisions.length - 1]; return <div className="receivable-response-row"><span><strong>Latest decision: {decision.decision.replaceAll("_", " ")}</strong><small>{decision.budget_owner_name}, {decision.budget_owner_title || "title not given"} · {decision.budget_owner_organization}</small><p>{decision.decision_note}</p></span><b>{decision.price_amount ? `${amount(decision.price_amount)} ${decision.price_unit}` : "No price recorded"}</b></div>; })() : null}
      <div className="receivable-response"><h3>Record a receipt</h3><p>Only source-linked receipts reviewed by the cooperative reduce the evidence-reviewed balance.</p>{Number(amounts.seller_asserted_less_reported_receipts || 0) > 0 ? <form className="receivable-form-grid" onSubmit={onReceipt}>
        <label className="field"><span>Receipt reference</span><input name="source_reference" required minLength={2} maxLength={160} /></label>
        <label className="field"><span>Received date</span><input name="received_on" type="date" required defaultValue={new Date().toISOString().slice(0, 10)} /></label>
        <label className="field"><span>Received amount (KES)</span><input name="amount" type="number" min="0.01" step="0.01" required /></label>
        <label className="field"><span>Allocate to selected claim</span><input name="allocate_amount" type="number" min="0.01" step="0.01" placeholder="Blank allocates up to remaining claim balance" /></label>
        <label className="field"><span>Payment rail</span><select name="payment_rail" defaultValue="bank"><option value="bank">Bank transfer</option><option value="mpesa">M-Pesa</option><option value="cheque">Cheque</option><option value="other">Other</option></select></label>
        <label className="field"><span>Receipt evidence review</span><select name="verification_status" defaultValue="seller_attested"><option value="seller_attested">Seller-attested only</option><option value="bank_evidence_reviewed">Bank/payment evidence reviewed</option></select></label>
        <label className="field receivable-span"><span>Evidence file ID (required for reviewed receipt)</span><input name="evidence_artifact_id" placeholder="UUID from source evidence above" /></label>
        <button className="button button-outline receivable-span" disabled={busy}>Record receipt and allocation</button>
      </form> : <p className="receivable-help">The seller-asserted balance is fully allocated. Record a receipt against another open claim if additional settlement money arrived.</p>}</div>
    </> : null}
    {c.aging ? <small className="receivable-footnote">Aging is an operational view of entered dates and source basis, not a legal conclusion about arrears, default, or interest.</small> : null}
  </section>;
}
