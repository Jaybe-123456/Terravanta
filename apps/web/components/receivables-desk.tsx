"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowDownToLine, CheckCircle2, Clock3, FileUp, Inbox, RefreshCw, Send, ShieldCheck, TimerReset } from "lucide-react";
import { API_URL, api } from "@/lib/api";

type Row = Record<string, any>;

function amount(value: unknown, currency = "KES") {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? new Intl.NumberFormat("en-KE", { style: "currency", currency, maximumFractionDigits: 2 }).format(numeric) : String(value);
}

function durationHours(value: unknown) {
  if (value === null || value === undefined) return "—";
  const hours = Number(value);
  if (!Number.isFinite(hours)) return "—";
  if (hours < 24) return `${Math.round(hours)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

function Label({ children }: { children: React.ReactNode }) { return <span className="receivable-label">{children}</span>; }

export function ReceivablesDesk({ role, token, initialCaseId = "" }: { role: string; token: string; initialCaseId?: string }) {
  const processorMode = role === "processor_admin";
  const [cases, setCases] = useState<Row[]>([]);
  const [relationships, setRelationships] = useState<Row[]>([]);
  const [summary, setSummary] = useState<Row | null>(null);
  const [performance, setPerformance] = useState<Row | null>(null);
  const [performanceError, setPerformanceError] = useState("");
  const [performanceWindow, setPerformanceWindow] = useState(90);
  const [selectedId, setSelectedId] = useState(initialCaseId);
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
        setPerformanceError("");
        try {
          setPerformance(await api<Row>(`/api/v1/cooperative/receivables/performance?window_days=${performanceWindow}`, token));
        } catch (e) {
          setPerformance(null);
          setPerformanceError(e instanceof Error ? e.message : "Performance measures could not be loaded");
        }
      }
      const nextId = selectedId && list.some((item) => item.id === selectedId) ? selectedId : list[0]?.id || "";
      setSelectedId(nextId);
      setSelected(nextId ? await api<Row>(`${processorMode ? "/api/v1/processor" : "/api/v1/cooperative"}/receivables/cases/${nextId}`, token) : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load receivables workspace");
    }
  }, [performanceWindow, processorMode, selectedId, token]);

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

  async function reviewDueDate(event: React.FormEvent<HTMLFormElement>, caseId: string) {
    event.preventDefault();
    const form = event.currentTarget;
    const v = Object.fromEntries(new FormData(form));
    const success = await run(() => api(`/api/v1/cooperative/receivables/cases/${caseId}/due-date-review`, token, {
      method: "POST",
      body: JSON.stringify({ due_date: v.due_date, evidence_artifact_id: v.evidence_artifact_id, review_note: v.review_note }),
    }), "Due date review saved with its supporting source document.");
    if (success) form.reset();
  }

  async function submitRequestedInformation(event: React.FormEvent<HTMLFormElement>, caseId: string) {
    event.preventDefault();
    const form = event.currentTarget;
    const v = Object.fromEntries(new FormData(form));
    const success = await run(() => api(`/api/v1/cooperative/receivables/cases/${caseId}/information-response`, token, {
      method: "POST",
      body: JSON.stringify({ evidence_artifact_ids: [v.evidence_artifact_id], response_note: v.response_note }),
    }), "Your response and selected evidence are now in the processor's claim timeline.");
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
      <section className="card receivable-performance" aria-label="Claim close performance">
        <div className="receivable-performance-heading">
          <div><p className="eyebrow">MEASURED CLAIM OPERATIONS</p><h2>How the close is moving</h2><p className="muted">Actual claims opened in the selected period. Response and settlement times use recorded events only.</p></div>
          <label className="receivable-period-select"><span>Claim cohort</span><select value={performanceWindow} onChange={(event) => setPerformanceWindow(Number(event.target.value))}><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={180}>Last 180 days</option><option value={365}>Last 12 months</option></select></label>
        </div>
        {performanceError ? <div className="receivable-performance-error" role="status"><strong>Performance view unavailable</strong><span>{performanceError}</span><small>Claim register and ordinary case work remain available.</small></div> : performance ? <>
          <div className="receivable-performance-metrics">
            <div><span>Claims opened</span><strong>{performance.cohort?.claims_opened ?? 0}</strong><small>{performance.cohort?.claims_submitted ?? 0} submitted in this cohort</small></div>
            <div><span>Draft to submission</span><strong>{durationHours(performance.timing?.median_draft_to_submission_hours)}</strong><small>{performance.timing?.submission_timing_sample_size ?? 0} measured submissions</small></div>
            <div><span>Submission to first response</span><strong>{durationHours(performance.timing?.median_submission_to_first_response_hours)}</strong><small>{performance.timing?.first_response_sample_size ?? 0} claims with a response</small></div>
            <div><span>Exceptions or rework</span><strong>{performance.rework?.rate_percent == null ? "—" : `${performance.rework.rate_percent}%`}</strong><small>{performance.rework?.claims_with_rework_or_exception ?? 0} claims · info request, dispute or rejection</small></div>
            <div><span>Submission to paid or closed</span><strong>{performance.timing?.median_submission_to_paid_or_closed_days == null ? "—" : `${performance.timing.median_submission_to_paid_or_closed_days}d`}</strong><small>{performance.timing?.resolution_sample_size ?? 0} measured resolutions</small></div>
          </div>
          <div className="receivable-queue-readiness">
            <div><strong>Current queue</strong><span>{performance.current_queue?.open_claims ?? 0} open · {performance.current_queue?.missing_source_evidence ?? 0} without source evidence · {performance.current_queue?.missing_due_date_support ?? 0} without source-linked due date review</span></div>
            <div className="receivable-stage-counts">{Object.entries(performance.current_queue?.stage_counts || {}).map(([stage, count]) => <span key={stage}><b>{String(count)}</b>{stage.replaceAll("_", " ")}</span>)}</div>
          </div>
          <small className="receivable-metric-basis">Cohort: {performance.cohort_basis}. Rework rate uses submitted claims as its denominator. This is an operational measure, not a legal arrears determination.</small>
          {!performance.cohort?.claims_opened ? <div className="receivable-performance-empty"><TimerReset size={17} /><span><strong>No claims in this period yet</strong><small>Measures will populate from real claim activity; no demo values are shown.</small></span></div> : null}
        </> : <div className="receivable-performance-empty"><TimerReset size={17} /><span><strong>Loading measured claim activity</strong><small>These measures are calculated from this cooperative’s recorded cases and events.</small></span></div>}
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
          {selectedCase ? <CaseDetail caseRecord={selectedCase} token={token} busy={busy} processorMode={false} onUpload={uploadEvidence} onAction={(path: string, label: string) => void run(() => api(path, token, { method: "POST" }), label)} onDownload={() => void download(`/api/v1/cooperative/receivables/cases/${selectedCase.id}/evidence-export`, `terravanta-claim-${selectedCase.source_reference}.zip`)} onDownloadArtifact={(artifactId: string, filename: string) => void download(`/api/v1/receivables/cases/${selectedCase.id}/evidence/${artifactId}`, filename)} onRecordDecision={recordDecision} onReceipt={recordAndAllocate} onReviewDueDate={reviewDueDate} onSubmitInformation={submitRequestedInformation} /> : null}
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

function CaseDetail({ caseRecord, token, busy, processorMode, onUpload, onAction, onDownload, onDownloadArtifact, onRespond, onRecordDecision, onReceipt, onReviewDueDate, onSubmitInformation }: any) {
  const c = caseRecord; const amounts = c.amounts || {};
  return <section className="card receivable-card receivable-detail">
    <div className="panel-title"><div><p className="eyebrow">CLAIM FILE · {c.status.replaceAll("_", " ").toUpperCase()}</p><h2>{c.source_reference}</h2><p className="muted">{c.source_document_type.replaceAll("_", " ")} · Created {new Date(c.created_at).toLocaleDateString("en-KE")}</p></div>{!processorMode && c.status !== "draft" ? <button className="button button-outline" type="button" onClick={onDownload}><ArrowDownToLine size={14} />Evidence export</button> : null}</div>
    <p className="receivable-description">{c.description || "No description provided. Source statement remains the basis for the seller assertion."}</p>
    {c.workflow ? <section className="receivable-workflow" aria-label="Claim workflow progress">
      <div className="receivable-workflow-heading"><div><p className="eyebrow">STAGE-GATED CLAIM FILE</p><h3>{c.workflow.label}</h3><p>{c.workflow.next_action}</p></div><span>{c.workflow.steps?.filter((step: Row) => step.complete).length || 0}/{c.workflow.steps?.length || 0} milestones</span></div>
      <ol className="receivable-workflow-steps">{c.workflow.steps?.map((step: Row) => <li key={step.key} className={step.complete ? "complete" : "pending"}><span>{step.complete ? <CheckCircle2 size={13} /> : <i />}</span><b>{step.label}</b></li>)}</ol>
      {c.workflow.blockers?.length ? <div className="receivable-workflow-blockers">{c.workflow.blockers.map((blocker: Row) => <p key={blocker.code} className={`blocker-${blocker.severity}`}><strong>{blocker.severity === "required" ? "Required" : blocker.severity === "waiting" ? "Waiting" : "Review"}</strong>{blocker.message}</p>)}</div> : null}
    </section> : null}
    <div className="receivable-amount-grid">
      <div><Label>Seller asserted</Label><strong>{amount(amounts.seller_asserted, c.currency)}</strong></div>
      <div><Label>Processor confirmed</Label><strong>{amount(amounts.latest_processor_confirmed, c.currency)}</strong></div>
      <div><Label>Processor disputed</Label><strong>{amount(amounts.latest_processor_disputed, c.currency)}</strong></div>
      <div><Label>Reviewed receipts allocated</Label><strong>{amount(amounts.evidence_reviewed_receipts_allocated, c.currency)}</strong></div>
    </div>
    <div className="receivable-age"><Clock3 size={15} /><span><strong>{c.aging?.days_past_due === null ? "Due date not reviewed" : c.aging?.bucket === "due_today" ? "Due today" : c.aging?.days_past_due === 0 ? "Not overdue" : `${c.aging?.days_past_due} days past due`}</strong><small>{c.aging?.bucket?.replaceAll("_", " ")} · As of {c.aging?.as_of}{c.aging?.days_past_due === null && c.aging?.days_since_invoice !== null ? ` · ${c.aging?.days_since_invoice} days since invoice` : ""}</small></span></div>
    {!processorMode && c.status !== "paid" && c.status !== "closed" ? <form className="receivable-date-review" onSubmit={(event) => onReviewDueDate(event, c.id)}>
      <div><h3>Review the due date <small>{c.workflow?.due_date_source_supported ? "source linked" : "supporting source needed"}</small></h3><p>Past-due aging uses this reviewer-entered date and attached evidence. It is not a legal conclusion.</p></div>
      <label className="field"><span>Due date</span><input name="due_date" type="date" required defaultValue={c.due_date || ""} /></label>
      <label className="field"><span>Supporting source document</span><select name="evidence_artifact_id" required defaultValue={c.evidence?.[0]?.id || ""} disabled={!c.evidence?.length}><option value="" disabled>Select attached evidence</option>{c.evidence?.map((file: Row) => <option key={file.id} value={file.id}>{file.filename} · {file.artifact_type.replaceAll("_", " ")}</option>)}</select></label>
      <label className="field receivable-span"><span>What in the document supports this date?</span><textarea name="review_note" minLength={5} maxLength={1000} required placeholder="For example: invoice page 1 states payment due 30 days after 12 Oct 2026." /></label>
      <button className="button button-outline receivable-span" disabled={busy || !c.evidence?.length}>Save date review and source link</button>
      {!c.evidence?.length ? <small className="receivable-help receivable-span">Attach an invoice, contract extract or processor statement above before reviewing the due date.</small> : null}
    </form> : null}
    {!processorMode && c.workflow?.stage === "information_requested" ? <form className="receivable-response receivable-information-response" onSubmit={(event) => onSubmitInformation(event, c.id)}>
      <h3>Send the requested information</h3><p>Attach any new source files above, then select one file and describe what it answers. The processor sees this in the claim timeline when its inbox refreshes.</p>
      <label className="field"><span>Supporting file already attached to this claim</span><select name="evidence_artifact_id" required defaultValue=""><option value="" disabled>Select a source file</option>{c.evidence?.map((file: Row) => <option key={file.id} value={file.id}>{file.filename} · {file.artifact_type.replaceAll("_", " ")}</option>)}</select></label>
      <label className="field"><span>Response note</span><textarea name="response_note" minLength={5} maxLength={2000} required placeholder="Explain which requested item this source document answers." /></label>
      <button className="button button-primary" disabled={busy || !c.evidence?.length}>Send response to processor</button>
    </form> : null}
    {c.lines?.length ? <div className="receivable-subsection"><h3>Claim components <small>source-linked line items</small></h3><div className="receivable-line-list">{c.lines.map((line: Row) => {
      const sourceFile = c.evidence?.find((file: Row) => file.id === line.evidence_artifact_id);
      return <div className="receivable-component-row" key={line.id}><span><strong>{line.line_type.replaceAll("_", " ")} · {line.direction} · {line.source_reference || "No source ref"}</strong><small>Line {line.line_number}{line.occurred_on ? ` · ${line.occurred_on}` : ""}{line.source_locator ? ` · ${line.source_locator}` : " · locator not recorded"}{sourceFile ? ` · ${sourceFile.filename}` : " · source file not linked"}</small></span><strong>{amount(line.amount, line.currency)}</strong>{sourceFile && onDownloadArtifact ? <button type="button" className="text-link" onClick={() => onDownloadArtifact(sourceFile.id, sourceFile.filename)}><ArrowDownToLine size={12} />Source</button> : null}</div>;
    })}</div></div> : null}
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
    {c.events?.length ? <details className="receivable-activity"><summary>Claim activity · {c.events.length} recorded events</summary><ol>{c.events.map((event: Row) => <li key={event.id}><span className="receivable-activity-icon"><CheckCircle2 size={13} /></span><div><strong>{event.event_type.replaceAll("_", " ")}</strong><small>{new Date(event.created_at).toLocaleString("en-KE")}{event.from_status || event.to_status ? ` · ${event.from_status || "created"} → ${event.to_status || "recorded"}` : ""}</small>{event.note ? <p>{event.note}</p> : null}</div></li>)}</ol></details> : null}
    {c.aging ? <small className="receivable-footnote">Aging is an operational view of entered dates and source basis, not a legal conclusion about arrears, default, or interest.</small> : null}
  </section>;
}
