"use client";

import { useState } from "react";
import { ArrowRight, Bot, Check, ChevronRight, LoaderCircle, Send, ShieldCheck, Sparkles, X } from "lucide-react";
import { api, writeApi } from "@/lib/api";
import type { Section } from "@/components/sidebar";

type TerrasResult = {
  reply: string;
  mode: "local_rules";
  intent: string;
  destination: Section;
  api_workflow: string | null;
  draft: { product_type: string; quantity: number; unit: string } | null;
  required_inputs: string[];
  requires_confirmation: boolean;
  external_model_used: false;
  safety_note: string;
};

const examples: Record<string, string[]> = {
  farmer: ["Record 24 liters of milk", "Open my feed records", "Find veterinary records"],
  veterinarian: ["Open my assigned cases", "Find a veterinary record"],
  cooperative_admin: ["Help me close the payout period", "Show shared member deliveries", "Open close history"],
};

function browserDate() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export function TerrasWidget({ token, role, farmId, onNavigate, onSaved }: {
  token: string;
  role: string;
  farmId: string;
  onNavigate: (section: Section) => void;
  onSaved: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<TerrasResult | null>(null);
  const [quantity, setQuantity] = useState("");
  const [recordedOn, setRecordedOn] = useState(browserDate);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [savedMessage, setSavedMessage] = useState("");

  async function ask(message = prompt) {
    if (!message.trim()) return;
    setBusy(true); setError(""); setSavedMessage(""); setResult(null); setPrompt(message);
    try {
      const routed = await api<TerrasResult>("/api/v1/terras/route", token, { method: "POST", body: JSON.stringify({ message }) });
      setResult(routed);
      setQuantity(routed.draft ? String(routed.draft.quantity) : "");
      setRecordedOn(browserDate());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Terras could not reach the Terravanta API.");
    } finally { setBusy(false); }
  }

  async function saveMilkDraft() {
    if (!result?.draft || !farmId || !Number.isFinite(Number(quantity)) || Number(quantity) <= 0 || !recordedOn) return;
    setBusy(true); setError("");
    try {
      const saved = await writeApi(`/api/v1/farms/${farmId}/production-records`, token, {
        product_type: "milk", quantity: Number(quantity), unit: "liters", recorded_on: recordedOn,
      });
      if ("queuedOffline" in saved) {
        setSavedMessage("Saved on this device. It will sync when the connection returns.");
      } else {
        setSavedMessage("Milk production record saved and linked to your farm.");
        await onSaved();
      }
      setResult(null); setPrompt("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The production record could not be saved.");
    } finally { setBusy(false); }
  }

  function openDestination() {
    if (!result) return;
    onNavigate(result.destination);
    setOpen(false);
  }

  return <>
    <button type="button" className="terras-launcher" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}>
      <span className="terras-launcher-icon"><Sparkles size={17} /></span><span>Ask Terras</span><span className="terras-launcher-shortcut">Guide</span>
    </button>
    {open ? <div className="terras-layer" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <aside className="terras-panel" role="dialog" aria-modal="true" aria-labelledby="terras-title">
        <header className="terras-header"><div className="terras-avatar"><Bot size={20} /></div><div><p className="eyebrow">TERRAVANTA WORKFLOW GUIDE</p><h2 id="terras-title">Terras</h2><span>Role-aware help for the next farm operation</span></div><button type="button" className="icon-button" aria-label="Close Terras" onClick={() => setOpen(false)}><X size={17} /></button></header>
        <div className="terras-body">
          <div className="terras-intro"><strong>What do you need done?</strong><p>Ask in plain language. Terras finds an existing Terravanta workflow and can prepare a reviewable milk record.</p></div>
          <form className="terras-input" onSubmit={(event) => { event.preventDefault(); void ask(); }}>
            <label className="sr-only" htmlFor="terras-prompt">Describe the task</label>
            <textarea id="terras-prompt" rows={3} maxLength={600} placeholder="For example: Help me close the payout period" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
            <div className="terras-input-bottom"><span>{prompt.length}/600</span><button type="submit" className="button button-primary" disabled={busy || !prompt.trim()}>{busy ? <LoaderCircle className="spinner" size={14} /> : <Send size={14} />}Find workflow</button></div>
          </form>
          {!result && !error && !savedMessage ? <div className="terras-examples"><span>TRY A TASK</span>{(examples[role] || examples.farmer).map((example) => <button type="button" key={example} onClick={() => void ask(example)} disabled={busy}>{example}<ChevronRight size={14} /></button>)}</div> : null}
          {error ? <div className="terras-error" role="alert">{error}</div> : null}
          {savedMessage ? <div className="terras-success" role="status"><Check size={17} /><span>{savedMessage}</span></div> : null}
          {result ? <section className="terras-result" aria-live="polite">
            <div className="terras-result-kicker"><span>WORKFLOW FOUND</span><span className="terras-mode">Local routing · no model call</span></div>
            <p>{result.reply}</p>
            {result.draft ? <div className="terras-draft">
              <div className="terras-draft-head"><div><span className="eyebrow">REVIEWABLE DRAFT</span><strong>Milk production</strong></div><span className="terras-draft-status">Not saved</span></div>
              <div className="terras-draft-fields"><label>Quantity in liters<input inputMode="decimal" type="number" min="0.01" step="0.01" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><label>Record date<input type="date" value={recordedOn} onChange={(event) => setRecordedOn(event.target.value)} /></label></div>
              <button type="button" className="button button-primary terras-save" disabled={busy || !farmId || Number(quantity) <= 0 || !recordedOn} onClick={() => void saveMilkDraft()}>{busy ? <LoaderCircle className="spinner" size={14} /> : <Check size={14} />}Review and save record</button>
              <small>Nothing is written until you confirm. The Terravanta API checks farm membership and farmer role when saving.</small>
            </div> : null}
            {result.required_inputs.length ? <div className="terras-inputs-needed"><strong>Needed for this workflow</strong><ul>{result.required_inputs.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
            {result.api_workflow ? <div className="terras-route"><span>EXISTING API WORKFLOW</span><code>{result.api_workflow}</code></div> : null}
            <div className="terras-safety"><ShieldCheck size={16} /><span>{result.safety_note}</span></div>
            {!result.draft ? <button type="button" className="button button-outline terras-open-workflow" onClick={openDestination}>Open {result.destination.replaceAll("_", " ")} workspace <ArrowRight size={14} /></button> : <button type="button" className="terras-text-action" onClick={openDestination}>Review the full Production workspace <ArrowRight size={13} /></button>}
          </section> : null}
        </div>
        <footer className="terras-footer"><span>Tasks stay within your signed-in role.</span><span>AI provider not connected to Terras.</span></footer>
      </aside>
    </div> : null}
  </>;
}
