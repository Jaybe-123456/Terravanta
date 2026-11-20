"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, Boxes, Check, ChevronDown, CircleHelp, CloudOff, Download, FileText, FileUp, GitBranch, Leaf, LoaderCircle, LogOut, Menu, Plus, RefreshCw, ShieldCheck, Sparkles, Stethoscope, Upload, Wifi, X } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { Sidebar, type Section } from "@/components/sidebar";
import { TerrasWidget } from "@/components/terras-widget";
import { ReceivablesDesk } from "@/components/receivables-desk";
import { API_URL, AUTH_MODE, SUPABASE_CONFIGURED, api, clearSession, consumeSupabaseRedirect, flushOfflineQueue, loginDemo, loginSupabase, logoutSupabase, persistSession, requestSupabasePasswordReset, restoreSession, signUpSupabase, updateSupabasePassword, uploadDocument, writeApi } from "@/lib/api";
import { buildReconciliationCsv } from "@/lib/reconciliation-export";

type AnyRecord = Record<string, any>;
type FormValues = Record<string, FormDataEntryValue>;
type Toast = { text: string; error?: boolean } | null;

function localDateString(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dateInput(daysAgo = 0) {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  return localDateString(date);
}

function Field({ label, name, type = "text", required = true, placeholder = "", min, max, step, minLength, maxLength, defaultValue, autoComplete }: { label: string; name: string; type?: string; required?: boolean; placeholder?: string; min?: string; max?: string; step?: string; minLength?: number; maxLength?: number; defaultValue?: string; autoComplete?: string }) {
  return <label className="field"><span>{label}</span><input name={name} type={type} required={required} placeholder={placeholder} min={min} max={max} step={step} minLength={minLength} maxLength={maxLength} defaultValue={defaultValue} autoComplete={autoComplete} /></label>;
}

function SelectField({ label, name, options, required = true }: { label: string; name: string; options: Array<{ label: string; value: string }>; required?: boolean }) {
  return <label className="field"><span>{label}</span><select name={name} required={required} defaultValue=""><option value="" disabled>Choose…</option>{options.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select></label>;
}

function PanelTitle({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: React.ReactNode }) {
  return <div className="panel-title"><div>{eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}<h2>{title}</h2>{description ? <p className="muted">{description}</p> : null}</div>{action}</div>;
}

function Empty({ title, detail }: { title: string; detail: string }) {
  return <div className="empty"><span className="empty-icon"><CircleHelp size={19} /></span><strong>{title}</strong><p>{detail}</p></div>;
}

function StatusPill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "green" | "amber" | "red" }) {
  return <span className={`status-pill ${tone}`}><i />{children}</span>;
}

export default function Home() {
  const [active, setActive] = useState<Section>("overview");
  const [token, setToken] = useState("");
  const [role, setRole] = useState("farmer");
  const [farm, setFarm] = useState<AnyRecord | null>(null);
  const [farmId, setFarmId] = useState("");
  const [dashboard, setDashboard] = useState<AnyRecord | null>(null);
  const [animals, setAnimals] = useState<AnyRecord[]>([]);
  const [plots, setPlots] = useState<AnyRecord[]>([]);
  const [feedBatches, setFeedBatches] = useState<AnyRecord[]>([]);
  const [production, setProduction] = useState<AnyRecord[]>([]);
  const [deliveries, setDeliveries] = useState<AnyRecord[]>([]);
  const [resourceCycle, setResourceCycle] = useState<AnyRecord | null>(null);
  const [alerts, setAlerts] = useState<AnyRecord[]>([]);
  const [passport, setPassport] = useState<AnyRecord | null>(null);
  const [coopDeliveries, setCoopDeliveries] = useState<AnyRecord[]>([]);
  const [reconciliationRuns, setReconciliationRuns] = useState<AnyRecord[]>([]);
  const [activeReconciliation, setActiveReconciliation] = useState<AnyRecord | null>(null);
  const [settlementCloses, setSettlementCloses] = useState<AnyRecord[]>([]);
  const [activeSettlementClose, setActiveSettlementClose] = useState<AnyRecord | null>(null);
  const [cooperatives, setCooperatives] = useState<AnyRecord[]>([]);
  const [vetQueue, setVetQueue] = useState<AnyRecord[]>([]);
  const [aiResponse, setAiResponse] = useState<AnyRecord | null>(null);
  const [documentResult, setDocumentResult] = useState<AnyRecord | null>(null);
  const [toast, setToast] = useState<Toast>(null);
  const [loading, setLoading] = useState(true);
  const [workspaceError, setWorkspaceError] = useState("");
  const [saving, setSaving] = useState(false);
  const [online, setOnline] = useState(true);
  const [queued, setQueued] = useState(0);
  const [mobileNav, setMobileNav] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authMessage, setAuthMessage] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [passwordRecovery, setPasswordRecovery] = useState(false);
  const [currentUserName, setCurrentUserName] = useState("");
  const demoMode = AUTH_MODE === "demo";

  const refreshQueue = useCallback(async () => {
    if (!token) return;
    try {
      const result = await flushOfflineQueue(token);
      setQueued(result.pending);
      if (result.synced > 0) setToast({ text: `${result.synced} offline record${result.synced === 1 ? "" : "s"} synced` });
    } catch {
      // IndexedDB is unavailable in some private browsing contexts; online records continue to work.
    }
  }, [token]);

  const loadWorkspace = useCallback(async (accessToken: string, currentRole: string) => {
    setLoading(true);
    setWorkspaceError("");
    try {
      if (currentRole === "processor_admin") {
        setActive("receivables");
        setFarm(null); setFarmId(""); setDashboard(null);
        setLoading(false);
        return;
      }
      if (currentRole === "cooperative_admin") {
        const [shared, runs, closes] = await Promise.all([
          api<AnyRecord[]>("/api/v1/cooperative/deliveries", accessToken),
          api<AnyRecord[]>("/api/v1/cooperative/reconciliation/runs", accessToken),
          api<AnyRecord[]>("/api/v1/cooperative/settlement-closes", accessToken),
        ]);
        const activeRun = runs.length ? await api<AnyRecord>(`/api/v1/cooperative/reconciliation/runs/${runs[0].id}`, accessToken) : null;
        const latestClose = closes.length ? await api<AnyRecord>(`/api/v1/cooperative/settlement-closes/${closes[0].id}`, accessToken) : null;
        setCoopDeliveries(shared); setReconciliationRuns(runs); setActiveReconciliation(activeRun); setSettlementCloses(closes); setActiveSettlementClose(latestClose);
        setLoading(false);
        return;
      }
      const farms = await api<AnyRecord[]>("/api/v1/farms", accessToken);
      const primary = farms[0];
      if (!primary) {
        setFarm(null); setFarmId(""); setDashboard(null); setAnimals([]); setPlots([]); setFeedBatches([]); setProduction([]); setDeliveries([]); setResourceCycle(null); setAlerts([]); setPassport(null); setVetQueue([]); setCooperatives([]);
        if (currentRole === "farmer") { setActive("farms"); setToast({ text: "Create your first farm to start a private Terravanta record." }); }
        else { setActive("overview"); setToast({ text: "No farm has been assigned to this account yet.", error: true }); }
        return;
      }
      setFarm(primary);
      setFarmId(primary.id);
      const overview = await api<AnyRecord>("/api/v1/dashboard", accessToken);
      setDashboard(overview);
      setFarm(overview.farm);
      const secondaryResults = await Promise.allSettled([
        api<AnyRecord[]>(`/api/v1/farms/${primary.id}/animals`, accessToken),
        api<AnyRecord[]>(`/api/v1/farms/${primary.id}/plots`, accessToken),
        api<AnyRecord[]>(`/api/v1/farms/${primary.id}/feed-batches`, accessToken),
        api<AnyRecord[]>(`/api/v1/farms/${primary.id}/production-records`, accessToken),
        api<AnyRecord[]>(`/api/v1/farms/${primary.id}/deliveries`, accessToken),
        api<AnyRecord>(`/api/v1/farms/${primary.id}/resource-cycle`, accessToken),
        api<AnyRecord[]>("/api/v1/alerts", accessToken),
        api<AnyRecord>(`/api/v1/farms/${primary.id}/passport`, accessToken),
        currentRole === "veterinarian" ? api<AnyRecord[]>("/api/v1/veterinary/queue", accessToken) : Promise.resolve([]),
        currentRole === "farmer" ? api<AnyRecord[]>("/api/v1/cooperatives", accessToken) : Promise.resolve([]),
      ]);
      const value = <T,>(index: number, fallback: T): T => {
        const result = secondaryResults[index];
        return result.status === "fulfilled" ? result.value as T : fallback;
      };
      setAnimals(value(0, [])); setPlots(value(1, [])); setFeedBatches(value(2, []));
      setProduction(value(3, [])); setDeliveries(value(4, [])); setResourceCycle(value(5, null));
      setAlerts(value(6, [])); setPassport(value(7, null)); setVetQueue(value(8, [])); setCooperatives(value(9, []));
      const failures = secondaryResults.flatMap((result) => result.status === "rejected"
        ? [result.reason instanceof Error ? result.reason.message : "A supporting farm-record request failed"]
        : []);
      if (failures.length) setWorkspaceError(`Overview loaded, but some supporting records did not load: ${failures.join(" · ")}`);
      await refreshQueue();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not load the workspace";
      setWorkspaceError(message);
      setToast({ text: message, error: true });
    } finally {
      setLoading(false);
    }
  }, [refreshQueue]);

  useEffect(() => {
    let cancelled = false;
    const start = async () => {
      try {
        const redirect = !demoMode ? await consumeSupabaseRedirect() : null;
        if (redirect?.passwordRecovery) {
          if (!cancelled) { setPasswordRecovery(true); setLoading(false); }
          return;
        }
        let session = redirect?.session || null;
        session = session || await restoreSession();
        if (session?.access_token) {
          const profile = await api<AnyRecord>("/api/v1/me", session.access_token);
          if (cancelled) return;
          session.user = { id: profile.id, name: profile.name, email: profile.email, role: profile.role };
          setCurrentUserName(profile.name); setRole(profile.role); setToken(session.access_token);
          return;
        }
      } catch (error) {
        if (!cancelled && !demoMode) setAuthError(error instanceof Error ? error.message : "Could not restore your session.");
      }
      if (!demoMode) { if (!cancelled) setLoading(false); return; }
      try {
        const session = await loginDemo("farmer");
        if (cancelled) return;
        await persistSession(session);
        setCurrentUserName(session.user.name); setRole(session.user.role); setToken(session.access_token);
      } catch (error) {
        if (!cancelled) { const message = error instanceof Error ? error.message : "API unavailable"; setAuthError(message); setToast({ text: message, error: true }); setLoading(false); }
      }
    };
    void start();
    return () => { cancelled = true; };
  }, [demoMode]);

  useEffect(() => { if (token) void loadWorkspace(token, role); }, [token, role, loadWorkspace]);

  useEffect(() => {
    const updateOnline = () => { setOnline(navigator.onLine); };
    const syncWhenOnline = () => { setOnline(true); if (token) void refreshQueue().then(() => loadWorkspace(token, role)); };
    const updateOffline = () => setOnline(false);
    const updateQueue = () => { void import("@/lib/offline-queue").then(({ queueOwnerId, readQueue }) => readQueue(queueOwnerId()).then((items) => setQueued(items.length))); };
    updateOnline(); updateQueue();
    window.addEventListener("online", syncWhenOnline); window.addEventListener("offline", updateOffline); window.addEventListener("terravanta-queue-change", updateQueue);
    return () => { window.removeEventListener("online", syncWhenOnline); window.removeEventListener("offline", updateOffline); window.removeEventListener("terravanta-queue-change", updateQueue); };
  }, [refreshQueue, loadWorkspace, token, role]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  async function switchRole(nextRole: string) {
    if (!demoMode) return;
    setLoading(true);
    try {
      const session = await loginDemo(nextRole);
      await persistSession(session);
      setCurrentUserName(session.user.name);
      setRole(session.user.role); setToken(session.access_token); setActive("overview"); setToast({ text: `Signed in as ${session.user.name}` });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Sign-in failed"; setAuthError(message); setToast({ text: message, error: true }); setLoading(false);
    }
  }

  async function signIn(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setAuthBusy(true); setAuthError(""); setAuthMessage("");
    try {
      const session = await loginSupabase(String(values.get("email") || ""), String(values.get("password") || ""));
      await persistSession(session);
      setCurrentUserName(session.user.name);
      setRole(session.user.role); setToken(session.access_token); setActive("overview");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Sign-in failed.");
    } finally { setAuthBusy(false); }
  }

  async function registerFarmer(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setAuthBusy(true); setAuthError(""); setAuthMessage("");
    try {
      const session = await signUpSupabase(String(values.get("full_name") || "").trim(), String(values.get("email") || "").trim(), String(values.get("password") || ""));
      if (!session) {
        form.reset();
        setAuthMessage("Check your email for a confirmation link. After confirming, return here to sign in.");
        return;
      }
      await persistSession(session);
      setCurrentUserName(session.user.name);
      setRole(session.user.role); setToken(session.access_token); setActive("farms");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Account creation failed.");
    } finally { setAuthBusy(false); }
  }

  async function requestPasswordReset(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setAuthBusy(true); setAuthError(""); setAuthMessage("");
    try {
      await requestSupabasePasswordReset(String(values.get("email") || "").trim());
      setAuthMessage("If that address has a Terravanta account, Supabase has sent a password-reset link.");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Could not request a password reset.");
    } finally { setAuthBusy(false); }
  }

  async function resetPassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const password = String(values.get("new_password") || "");
    if (password !== String(values.get("confirm_password") || "")) {
      setAuthError("The passwords do not match.");
      return;
    }
    setAuthBusy(true); setAuthError(""); setAuthMessage("");
    try {
      const session = await updateSupabasePassword(password);
      await persistSession(session);
      setCurrentUserName(session.user.name); setRole(session.user.role); setToken(session.access_token);
      setPasswordRecovery(false); setActive("overview");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Could not update your password.");
    } finally { setAuthBusy(false); }
  }

  async function exitPasswordRecovery() {
    await clearSession();
    setPasswordRecovery(false); setAuthError(""); setAuthMessage("");
  }

  async function signOut() {
    if (AUTH_MODE === "supabase") await logoutSupabase(token); else await clearSession();
    setToken(""); setRole("farmer"); setFarm(null); setDashboard(null); setCoopDeliveries([]); setCurrentUserName(""); setAuthError(""); setAuthMessage("");
  }

  async function reload() {
    if (token) await loadWorkspace(token, role);
  }

  async function verifyHealthEvent(eventId: string) {
    setSaving(true);
    try { await api(`/api/v1/health-events/${eventId}/verify`, token, { method: "POST" }); setToast({ text: "Clinical record verified by the veterinarian" }); await reload(); }
    catch (error) { setToast({ text: error instanceof Error ? error.message : "Could not verify this clinical record", error: true }); }
    finally { setSaving(false); }
  }

  async function submitForm(event: React.FormEvent<HTMLFormElement>, path: string, transform?: (values: Record<string, FormDataEntryValue>) => Record<string, unknown>) {
    event.preventDefault();
    const form = event.currentTarget;
    const entries = Object.fromEntries(new FormData(form).entries());
    const body = transform ? transform(entries) : entries as Record<string, unknown>;
    setSaving(true);
    try {
      const result = await writeApi(path, token, body);
      if ("queuedOffline" in result) setToast({ text: "Saved on this device. It will sync when connection returns." });
      else { setToast({ text: "Record saved" }); form.reset(); await reload(); }
    } catch (error) {
      setToast({ text: error instanceof Error ? error.message : "Could not save this record", error: true });
    } finally { setSaving(false); }
  }

  async function saveConsent(recipient: { grantee_org_id?: string; grantee_email?: string }) {
    setSaving(true);
    try {
      await writeApi(`/api/v1/farms/${farmId}/consents`, token, { scope: "delivery_summary", ...recipient });
      setToast({ text: "Delivery summary sharing enabled for the selected cooperative" }); await reload();
    } catch (error) { setToast({ text: error instanceof Error ? error.message : "Could not update sharing", error: true }); }
    finally { setSaving(false); }
  }

  async function importCollectionSheet(file: File) {
    setSaving(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api<AnyRecord>("/api/v1/cooperative/reconciliation/runs", token, { method: "POST", body: form });
      setActiveReconciliation(result);
      const matched = result.run?.matched_rows || 0;
      const total = result.run?.total_rows || 0;
      setToast({ text: `Imported ${total} rows; ${matched} matched automatically and the rest need review.` });
      await loadWorkspace(token, role);
    } catch (error) {
      setToast({ text: error instanceof Error ? error.message : "Could not import the collection sheet", error: true });
    } finally { setSaving(false); }
  }

  async function openReconciliationRun(runId: string) {
    try {
      const result = await api<AnyRecord>(`/api/v1/cooperative/reconciliation/runs/${runId}`, token);
      setActiveReconciliation(result);
    } catch (error) {
      setToast({ text: error instanceof Error ? error.message : "Could not open that reconciliation", error: true });
    }
  }

  async function reviewReconciliationItem(itemId: string, decision: "confirmed" | "follow_up", note: string) {
    setSaving(true);
    try {
      const result = await api<AnyRecord>(`/api/v1/cooperative/reconciliation/items/${itemId}/review`, token, {
        method: "POST", body: JSON.stringify({ decision, note }),
      });
      setActiveReconciliation(result);
      setToast({ text: decision === "confirmed" ? "Delivery linkage confirmed by the cooperative reviewer." : "Follow-up decision recorded for the cooperative team." });
      await loadWorkspace(token, role);
    } catch (error) {
      setToast({ text: error instanceof Error ? error.message : "Could not record the review", error: true });
    } finally { setSaving(false); }
  }

  async function createSettlementClose(form: FormData) {
    setSaving(true);
    try {
      const result = await api<AnyRecord>("/api/v1/cooperative/settlement-closes", token, { method: "POST", body: form });
      setActiveSettlementClose(result);
      setToast({ text: `Settlement close created for ${result.close.member_count} members. Review all flagged variances before approval.` });
      await loadWorkspace(token, role);
    } catch (error) {
      setToast({ text: error instanceof Error ? error.message : "Could not reconcile settlement exports", error: true });
    } finally { setSaving(false); }
  }

  async function openSettlementClose(closeId: string) {
    try {
      const result = await api<AnyRecord>(`/api/v1/cooperative/settlement-closes/${closeId}`, token);
      setActiveSettlementClose(result);
    } catch (error) {
      setToast({ text: error instanceof Error ? error.message : "Could not open settlement close", error: true });
    }
  }

  async function reviewSettlementException(closeId: string, itemId: string, decision: "accept_with_note" | "follow_up", note: string) {
    setSaving(true);
    try {
      const result = await api<AnyRecord>(`/api/v1/cooperative/settlement-closes/${closeId}/items/${itemId}/review`, token, {
        method: "POST", body: JSON.stringify({ decision, note }),
      });
      setActiveSettlementClose(result);
      setToast({ text: decision === "accept_with_note" ? "Exception accepted with an audit note; source values were not changed." : "Follow-up recorded. The close remains open until the exception is accepted or resolved." });
      await loadWorkspace(token, role);
    } catch (error) {
      setToast({ text: error instanceof Error ? error.message : "Could not record exception review", error: true });
    } finally { setSaving(false); }
  }

  async function approveSettlementClose(closeId: string, note: string) {
    setSaving(true);
    try {
      const result = await api<AnyRecord>(`/api/v1/cooperative/settlement-closes/${closeId}/approve`, token, {
        method: "POST", body: JSON.stringify({ note }),
      });
      setActiveSettlementClose(result);
      setToast({ text: "Settlement close approved. Source exports remain unchanged." });
      await loadWorkspace(token, role);
    } catch (error) {
      setToast({ text: error instanceof Error ? error.message : "Could not approve settlement close", error: true });
    } finally { setSaving(false); }
  }

  async function downloadSettlementPack(closeId: string) {
    try {
      const response = await fetch(`${API_URL}/api/v1/cooperative/settlement-closes/${closeId}/statement-pack`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" });
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.detail || "Could not download the approved statement pack");
      }
      const href = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = href; link.download = `terravanta-settlement-${closeId}.csv`; link.click(); URL.revokeObjectURL(href);
    } catch (error) {
      setToast({ text: error instanceof Error ? error.message : "Could not download statement pack", error: true });
    }
  }

  async function revokeConsent(consentId: string) {
    setSaving(true);
    try { await api(`/api/v1/consents/${consentId}`, token, { method: "DELETE" }); setToast({ text: "Sharing consent revoked" }); await reload(); }
    catch (error) { setToast({ text: error instanceof Error ? error.message : "Could not revoke consent", error: true }); }
    finally { setSaving(false); }
  }

  async function askAssistant(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const entries = Object.fromEntries(new FormData(form).entries());
    setSaving(true); setAiResponse(null);
    try {
      const result = await api("/api/v1/ai/veterinary-assistant", token, { method: "POST", body: JSON.stringify({ animal_id: entries.animal_id, question: entries.question, allow_external_processing: entries.allow_external_processing === "on" }) });
      setAiResponse(result); await reload();
    } catch (error) { setToast({ text: error instanceof Error ? error.message : "AI request failed", error: true }); }
    finally { setSaving(false); }
  }

  async function extractDocument(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const file = new FormData(form).get("file");
    if (!(file instanceof File) || !file.size) { setToast({ text: "Choose a document first", error: true }); return; }
    setSaving(true); setDocumentResult(null);
    const allowExternalProcessing = new FormData(form).get("allow_external_processing") === "on";
    try { setDocumentResult(await uploadDocument(`/api/v1/documents/extract?farm_id=${encodeURIComponent(farmId)}`, token, file, allowExternalProcessing)); }
    catch (error) { setToast({ text: error instanceof Error ? error.message : "Document extraction failed", error: true }); }
    finally { setSaving(false); }
  }

  async function reviewDocument() {
    if (!documentResult?.id) return;
    setSaving(true);
    try {
      await api(`/api/v1/documents/${documentResult.id}/review`, token, { method: "POST" });
      setDocumentResult((previous: AnyRecord) => ({ ...previous, status: "reviewed" }));
      setToast({ text: "Extraction marked reviewed. It remains separate from official records." });
    } catch (error) {
      setToast({ text: error instanceof Error ? error.message : "Could not mark the extraction reviewed", error: true });
    } finally { setSaving(false); }
  }

  const toFarm = (path: string) => `/api/v1/farms/${farmId}${path}`;
  const onNav = (section: Section) => { setActive(section); setMobileNav(false); };
  const isCoop = role === "cooperative_admin";
  const isProcessor = role === "processor_admin";
  const farmLabel = farm?.name || "Farm workspace";
  const workCount = isCoop
    ? settlementCloses.filter((close) => close.status !== "approved").reduce((total, close) => total + Number(close.unresolved_exception_count ?? close.pending_review_count ?? 0), 0)
    : role === "veterinarian" ? vetQueue.filter((item) => !item.verified).length : 0;

  if (loading && !token) return <main className="boot-screen"><span className="boot-mark"><Leaf size={25} /></span><LoaderCircle className="spinner" size={20} /><p>Opening Terravanta workspace…</p></main>;
  if (!token) return <SignInScreen demoMode={demoMode} passwordRecovery={passwordRecovery} busy={authBusy} error={authError} message={authMessage} onSubmit={signIn} onRegister={registerFarmer} onForgot={requestPasswordReset} onReset={resetPassword} onExitRecovery={exitPasswordRecovery} onDemo={switchRole} />;

  return <div className="app-shell">
    <div className={`sidebar-wrap ${mobileNav ? "open" : ""}`}><Sidebar active={active} onChange={onNav} role={role} userName={currentUserName} farmName={isCoop ? "Cooperative workspace" : isProcessor ? "Processor AP workspace" : farmLabel} location={isCoop ? "Cooperative organization" : isProcessor ? "Supplier claims" : `${farm?.subcounty || "Location pending"}, ${farm?.county || "Kenya"}`} workCount={workCount} /><button className="sidebar-scrim" aria-label="Close menu" onClick={() => setMobileNav(false)} /></div>
    <main className="main-shell">
      <header className="topbar">
        <div className="topbar-left"><button className="mobile-menu icon-button" aria-label="Open menu" onClick={() => setMobileNav(true)}><Menu size={20} /></button><div className="breadcrumbs"><span>Workspace</span><span>/</span><strong>{isCoop ? "Cooperative operations" : isProcessor ? "Processor accounts payable" : role === "veterinarian" ? "Veterinary casework" : farm?.name || "Overview"}</strong></div></div>
        <div className="topbar-actions"><span className={`sync-state ${online ? "" : "offline"}`}><i />{online ? <Wifi size={14} /> : <CloudOff size={14} />}{online ? "Online" : "Offline"}{queued ? <b>{queued}</b> : null}</span><button className="icon-button refresh-button" title="Refresh records" onClick={() => void reload()}><RefreshCw size={17} /></button>{demoMode ? <label className="role-picker" aria-label="Switch synthetic demo role"><select value={role} onChange={(event) => void switchRole(event.target.value)}><option value="farmer">Farmer demo</option><option value="veterinarian">Veterinarian demo</option><option value="cooperative_admin">Cooperative demo</option></select><ChevronDown size={14} /></label> : <button className="button button-outline" onClick={() => void signOut()}><LogOut size={14} />Sign out</button>}</div>
      </header>
      <div className="content-wrap">
        <div className="page-heading"><div><p className="eyebrow">{isProcessor ? "PROCESSOR · ACCOUNTS PAYABLE" : isCoop ? "COOPERATIVE · SETTLEMENT OPERATIONS" : role === "veterinarian" ? "VETERINARY · ASSIGNED CASEWORK" : farm ? `${farm.county?.toUpperCase() || "KENYA"} · ${(farm.farming_system || "farm").toUpperCase()}` : "FARM IDENTITY & RECORDS"}</p><h1>{sectionTitle(active, isCoop, role)}</h1><p>{sectionDescription(active, farm?.name, isCoop, role)}</p></div><div className="heading-badges"><span className="synthetic-badge"><span />{demoMode ? "SYNTHETIC DEMO MODE" : isProcessor ? "PROCESSOR RECORDS" : isCoop ? "COOPERATIVE RECORDS" : farm?.is_synthetic ? "SYNTHETIC DEMO DATA" : farm ? "FARMER-SUBMITTED DATA" : "EMPTY WORKSPACE"}</span><span className="date-chip">{new Intl.DateTimeFormat("en-KE", { weekday: "short", day: "numeric", month: "short", year: "numeric" }).format(new Date())}</span></div></div>

        {loading && token ? <div className="loading-strip" role="status"><LoaderCircle className="spinner" size={17} /> Syncing farm records…</div> : null}
        {workspaceError && !loading ? <div className="workspace-load-error" role="alert"><div><strong>Some workspace data could not be loaded</strong><p>{workspaceError}</p></div><button type="button" className="button button-outline" onClick={() => void reload()}><RefreshCw size={14} />Retry</button></div> : null}
        {(isCoop || isProcessor) && active === "receivables" ? <ReceivablesDesk role={role} token={token} /> : isCoop ? <CooperativeWorkspace section={active} deliveries={coopDeliveries} runs={reconciliationRuns} activeRun={activeReconciliation} closes={settlementCloses} activeClose={activeSettlementClose} busy={saving} importFile={importCollectionSheet} openRun={openReconciliationRun} reviewItem={reviewReconciliationItem} createClose={createSettlementClose} openClose={openSettlementClose} reviewException={reviewSettlementException} approveClose={approveSettlementClose} downloadPack={downloadSettlementPack} onNavigate={onNav} /> : isProcessor ? active === "settings" ? <CooperativeAccessControls /> : <ReceivablesDesk role={role} token={token} /> : active === "overview" && role === "veterinarian" ? <VeterinarianDashboard cases={vetQueue} busy={saving} verify={verifyHealthEvent} onNavigate={onNav} /> : active === "overview" ? <Overview dashboard={dashboard} alerts={alerts} resourceCycle={resourceCycle} loading={loading} error={workspaceError} onRetry={reload} onNavigate={onNav} /> : null}
        {active === "farms" && !isCoop ? <FarmsView farm={farm} passport={passport} farmId={farmId} userName={currentUserName} token={token} busy={saving} submit={submitForm} reload={reload} revokeConsent={revokeConsent} /> : null}
        {active === "veterinary" && !isCoop ? <VeterinaryView animals={animals} farmId={farmId} token={token} role={role} busy={saving} submit={submitForm} askAssistant={askAssistant} aiResponse={aiResponse} cases={vetQueue} verify={verifyHealthEvent} /> : null}
        {active === "crops" && !isCoop ? <CropsView farmId={farmId} plots={plots} cycle={resourceCycle} busy={saving} submit={submitForm} /> : null}
        {active === "feed" && !isCoop ? <FeedView farmId={farmId} batches={feedBatches} animals={animals} plots={plots} busy={saving} submit={submitForm} cycle={resourceCycle} /> : null}
        {active === "production" && !isCoop ? <ProductionView farmId={farmId} production={production} animals={animals} plots={plots} deliveries={deliveries} busy={saving} submit={submitForm} /> : null}
        {active === "traceability" && !isCoop ? <TraceabilityView passport={passport} deliveries={deliveries} cooperatives={cooperatives} busy={saving} saveConsent={saveConsent} revokeConsent={revokeConsent} /> : null}
        {active === "assistant" && !isCoop ? <AssistantView animals={animals} busy={saving} askAssistant={askAssistant} response={aiResponse} documentResult={documentResult} extractDocument={extractDocument} reviewDocument={reviewDocument} /> : null}
        {active === "reports" && !isCoop ? <ReportsView dashboard={dashboard} alerts={alerts} passport={passport} /> : null}
        {active === "settings" && !isCoop ? <SettingsView role={role} userName={currentUserName} farm={farm} passport={passport} online={online} queued={queued} /> : null}
      </div>
      <footer className="page-footer"><span>Terravanta</span><span>Records stay attributed to their source · {farm?.code || "consent-controlled"}</span><a href={`${API_URL}/docs`} target="_blank" rel="noreferrer">API documentation <ArrowRight size={13} /></a></footer>
    </main>
    <TerrasWidget token={token} role={role} farmId={farmId} onNavigate={onNav} onSaved={reload} />
    {toast ? <div role="status" className={`toast ${toast.error ? "error" : ""}`}><span>{toast.error ? <AlertTriangle size={17} /> : <Check size={17} />}{toast.text}</span><button aria-label="Dismiss notification" onClick={() => setToast(null)}><X size={16} /></button></div> : null}
    <div className="sr-only" aria-live="polite">{loading ? "Loading records" : "Records loaded"}</div>
  </div>;
}

function SignInScreen({ demoMode, passwordRecovery, busy, error, message, onSubmit, onRegister, onForgot, onReset, onExitRecovery, onDemo }: { demoMode: boolean; passwordRecovery: boolean; busy: boolean; error: string; message: string; onSubmit: (event: React.FormEvent<HTMLFormElement>) => void; onRegister: (event: React.FormEvent<HTMLFormElement>) => void; onForgot: (event: React.FormEvent<HTMLFormElement>) => void; onReset: (event: React.FormEvent<HTMLFormElement>) => void; onExitRecovery: () => void; onDemo: (role: string) => void }) {
  const [registering, setRegistering] = useState(false);
  const [recovering, setRecovering] = useState(false);
  const resetMode = passwordRecovery && !demoMode;
  const submit = resetMode ? onReset : recovering ? onForgot : registering ? onRegister : onSubmit;
  const title = demoMode ? "Open the farm workspace" : resetMode ? "Choose a new password" : recovering ? "Reset your password" : registering ? "Create a farmer account" : "Sign in to Terravanta";
  return <main className="auth-shell"><section className="auth-card"><a className="brand auth-brand" href="#"><span className="brand-mark"><Leaf size={21} /></span><span>Terravanta<small>FARM INTELLIGENCE</small></span></a><p className="eyebrow">FARM RECORDS · VETERINARY REVIEW · TRACEABILITY</p><h1>{title}</h1><p className="muted">One connected record for farmers, veterinarians and cooperatives.</p>
    {demoMode ? <>{error ? <div className="auth-error" role="alert">{error}</div> : null}<div className="synthetic-notice"><ShieldCheck size={17} /><span><strong>Synthetic demo environment</strong><small>Every farm, animal, person and delivery shown here is fictional.</small></span></div><div className="auth-demo-actions"><button className="button button-primary" disabled={busy} onClick={() => onDemo("farmer")}>Farmer workspace</button><button className="button button-outline" disabled={busy} onClick={() => onDemo("veterinarian")}>Veterinarian workspace</button><button className="button button-outline" disabled={busy} onClick={() => onDemo("cooperative_admin")}>Cooperative portal</button></div><small className="auth-footnote">Demo access is available only when explicitly enabled in local configuration.</small></> : <>
      {!SUPABASE_CONFIGURED ? <div className="auth-error" role="alert">Supabase Auth is not configured. Add your project URL and publishable anon key to `.env`, then rebuild the web service.</div> : null}
      {error ? <div className="auth-error" role="alert">{error}</div> : null}
      {message ? <div className="auth-info" role="status">{message}</div> : null}
      <form className="auth-form" onSubmit={submit}>
        {registering && !recovering && !resetMode ? <Field label="Full name" name="full_name" autoComplete="name" minLength={2} /> : null}
        {!resetMode ? <Field label="Email address" name="email" type="email" autoComplete="email" /> : null}
        {!recovering && !resetMode ? <Field label="Password" name="password" type="password" autoComplete={registering ? "new-password" : "current-password"} minLength={8} /> : null}
        {resetMode ? <><Field label="New password" name="new_password" type="password" autoComplete="new-password" minLength={8} /><Field label="Confirm new password" name="confirm_password" type="password" autoComplete="new-password" minLength={8} /></> : null}
        <button className="button button-primary" disabled={busy || !SUPABASE_CONFIGURED}>{busy ? resetMode ? "Updating password…" : recovering ? "Requesting link…" : registering ? "Creating account…" : "Signing in…" : resetMode ? "Update password" : recovering ? "Send reset link" : registering ? "Create farmer account" : "Sign in securely"}</button>
      </form>
      {resetMode ? <button type="button" className="auth-mode-toggle" disabled={busy} onClick={onExitRecovery}>Return to sign in</button> : recovering ? <button type="button" className="auth-mode-toggle" disabled={busy} onClick={() => setRecovering(false)}>Return to sign in</button> : <>
        {!registering ? <button type="button" className="auth-mode-toggle" disabled={busy} onClick={() => setRecovering(true)}>Forgot password?</button> : null}
        <button type="button" className="auth-mode-toggle" disabled={busy} onClick={() => setRegistering((value) => !value)}>{registering ? "Already registered? Sign in" : "New farmer? Create an account"}</button>
      </>}
      <small className="auth-footnote">Supabase manages sign-in, email confirmation, password recovery and sessions. New sign-ups start with farmer access; veterinarian, cooperative and processor workspaces require an assigned organization or farm role.</small>
    </>}</section><p className="auth-bottom">Farm-level data access is checked by the Terravanta API and PostgreSQL policies.</p></main>;
}

function sectionTitle(section: Section, coop: boolean, role: string) {
  if (role === "processor_admin") return ({ receivables: "Supplier claim inbox", settings: "Access & controls" } as Partial<Record<Section, string>>)[section] || "Processor workspace";
  if (coop) return ({ overview: "Settlement close desk", settlements: "Milk payout settlements", receivables: "Processor receivables", traceability: "Consented member records", reports: "Settlement history", settings: "Access & controls" } as Partial<Record<Section, string>>)[section] || "Cooperative operations";
  if (role === "veterinarian") return ({ overview: "Assigned case desk", farms: "Assigned farm records", veterinary: "Clinical case review", assistant: "Veterinary case assistant", reports: "Review activity", settings: "Workspace settings" } as Partial<Record<Section, string>>)[section] || "Veterinary workspace";
  return ({ overview: "Your farm, at a glance", farms: "Farm identity & passport", veterinary: "Herd health records", crops: "Crops & land use", feed: "Feed & resource cycle", production: "Production records", traceability: "Traceability & sharing", assistant: "Veterinary intelligence", settlements: "Payout settlements", receivables: "Processor claims", reports: "Farm reports", settings: "Workspace settings" } as Record<Section, string>)[section];
}

function sectionDescription(section: Section, farmName?: string, coop = false, role = "farmer") {
  if (role === "processor_admin") return section === "settings" ? "Processor workspace access and review responsibilities." : "Review cooperative claims, record your AP position, and leave a traceable response for the seller.";
  if (coop) return ({
    overview: "See the latest payout close, unresolved reviews and the next action for your finance team.",
    settlements: "Reconcile your source exports, resolve evidence-linked exceptions and approve a reviewable close.",
    receivables: "Build an evidence-backed claim against a processor, age amounts from reviewed terms and record the counterparty response.",
    traceability: "Review delivery summaries shared by farm owners and keep source links visible.",
    reports: "Browse close periods and the review status recorded by your cooperative team.",
    settings: "Understand cooperative access, data scope and approval responsibilities.",
  } as Partial<Record<Section, string>>)[section] || "Cooperative settlement operations.";
  if (role === "veterinarian" && section === "overview") return "Work the assigned clinical queue by follow-up urgency and verification status.";
  if (role === "veterinarian" && section === "veterinary") return "Review submitted animal-health events, recorded evidence and follow-up dates for assigned farms.";
  if (section === "overview") return `Connected records across ${farmName || "your farm"}. Information is attributed to its source.`;
  return ({ farms: "Farm registration details, source labels and your digital farm passport.", veterinary: "Health events are linked to an animal and show whether a veterinarian verified them.", crops: "Connect plots, forage crops and compost applications to the farm record.", feed: "Track batch quantities, animal allocations, manure and compost as recorded links.", production: "Capture daily milk and crop production, then connect a record to a delivery lot.", traceability: "Follow a product lot from its source record to delivery and manage consent.", assistant: "AI output is a review draft. It cannot diagnose, prescribe or sign veterinary records.", settlements: "Compare member-level collection, settlement and payout figures with a named review process.", receivables: "Review processor claims and source records shared by your cooperative.", reports: "Transparent indicators built from farm records and simple rules.", settings: "Role, consent and local sync status for this workspace." } as Record<Section, string>)[section];
}

function Overview({ dashboard, alerts, resourceCycle, loading, error, onRetry, onNavigate }: { dashboard: AnyRecord | null; alerts: AnyRecord[]; resourceCycle: AnyRecord | null; loading: boolean; error: string; onRetry: () => Promise<void>; onNavigate: (section: Section) => void }) {
  if (!dashboard) {
    const title = loading ? "Loading farm records" : error ? "Overview could not load" : "No farm record yet";
    const detail = loading
      ? "Terravanta is fetching this farm’s records from the API."
      : error
        ? error
        : "Register your farm to connect livestock, crops, veterinary records and production.";
    return <div className="overview-empty-layout">
      <section className="card overview-load-state">
        <Empty title={title} detail={detail} />
        {error && !loading ? <button type="button" className="button button-outline" onClick={() => void onRetry()}><RefreshCw size={14} />Retry loading records</button> : null}
        {!loading && !error ? <button type="button" className="button button-primary" onClick={() => onNavigate("farms")}>Register a farm <ArrowRight size={14} /></button> : null}
      </section>
      <TerravantaVideoFeature />
    </div>;
  }
  const stats = dashboard.stats;
  const cards = [
    { title: "Registered animals", value: stats.animals, unit: "head", icon: "🐄", sub: "Across the active herd", tone: "green" },
    { title: "Open health cases", value: stats.active_cases, unit: "cases", icon: "✚", sub: "Needs follow-up review", tone: "amber" },
    { title: "Milk · 7 days", value: stats.milk_liters_7d.toLocaleString(), unit: "litres", icon: "◌", sub: `${latestTrend(dashboard)} L last entry`, tone: "blue" },
    { title: "Feed inventory", value: stats.feed_inventory_kg.toLocaleString(), unit: "kg", icon: "⌁", sub: `${stats.crop_plots} plots connected`, tone: "earth" },
  ];
  return <>
    <section className="welcome-banner"><div className="welcome-art"><span className="sun" /><span className="hill hill-back" /><span className="hill hill-front" /><span className="welcome-leaf"><Leaf size={42} /></span></div><div className="welcome-copy"><span className="banner-label">MIXED FARM · {dashboard.farm?.code}</span><h2>Good records grow<br />stronger farms.</h2><p>Your livestock, crops, feed and production—together in one trusted record.</p><button className="button button-light" onClick={() => onNavigate("farms")}>View farm passport <ArrowRight size={15} /></button></div><div className="banner-stat"><span>Farm area</span><strong>{dashboard.farm?.size_acres} <small>ac</small></strong><span>{dashboard.farm?.subcounty}, {dashboard.farm?.county}</span></div></section>
    <TerravantaVideoFeature />
    <div className="stats-grid">{cards.map((item) => <article className="stat-card" key={item.title}><div className="stat-top"><span className={`stat-icon ${item.tone}`}>{item.icon}</span><span className="stat-quiet">{item.unit}</span></div><p>{item.title}</p><div className="stat-value">{item.value}<span>{item.unit === "head" ? "" : ` ${item.unit}`}</span></div><small>{item.sub}</small></article>)}</div>
    <div className="dashboard-grid"><section className="card production-card"><PanelTitle eyebrow="DAILY COLLECTION" title="Milk production" description="Recorded volume · litres" action={<button className="text-link" onClick={() => onNavigate("production")}>View records <ArrowRight size={14} /></button>} /><div className="chart-summary"><strong>{latestTrend(dashboard)} <span>L</span></strong><span className="trend-chip"><ArrowUpRight size={14} />Recorded entries</span></div>{dashboard.milk_trend?.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={dashboard.milk_trend} margin={{ top: 8, right: 10, left: -24, bottom: 0 }}><defs><linearGradient id="milkFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#74aa79" stopOpacity={0.2} /><stop offset="100%" stopColor="#74aa79" stopOpacity={0.01} /></linearGradient></defs><CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#edf0e9" /><XAxis dataKey="date" tickFormatter={(value) => new Date(`${value}T00:00:00`).toLocaleDateString("en-KE", { weekday: "short" })} tickLine={false} axisLine={false} tick={{ fill: "#89918a", fontSize: 11 }} /><Tooltip formatter={(value) => [`${value} L`, "Recorded"]} labelFormatter={(value) => new Date(`${value}T00:00:00`).toLocaleDateString("en-KE", { weekday: "long", month: "short", day: "numeric" })} contentStyle={{ borderRadius: 10, border: "1px solid #e8ece4", boxShadow: "0 8px 24px #1b392011" }} /><Area type="monotone" dataKey="liters" stroke="#477b53" strokeWidth={2.5} fill="url(#milkFill)" activeDot={{ r: 5, fill: "#477b53", stroke: "white", strokeWidth: 3 }} /></AreaChart></ResponsiveContainer></div> : <Empty title="No milk entries yet" detail="Add the first daily production record to build this trend." />}</section>
      <section className="card alerts-card"><PanelTitle eyebrow="NEEDS ATTENTION" title="Production & health alerts" action={<button className="icon-button small-action" onClick={() => onNavigate("veterinary")} aria-label="Review health alerts"><ArrowRight size={16} /></button>} />{alerts.length ? <div className="alert-list">{alerts.slice(0, 3).map((alert) => <div className="alert-item" key={alert.id}><span className={`alert-symbol ${alert.severity === "high" ? "red" : "amber"}`}><AlertTriangle size={15} /></span><div><strong>{alert.title}</strong><p>{alert.supporting_data}</p><small>{alert.trigger}</small></div><ChevronDown size={14} className="alert-expand" /></div>)}</div> : <Empty title="No active rule alerts" detail="Alerts appear when recorded values meet a visible rule." />}<button className="button button-outline full-button" onClick={() => onNavigate("reports")}>Review farm indicators <ArrowRight size={15} /></button></section></div>
    <div className="dashboard-grid lower-grid"><section className="card cycle-card"><PanelTitle eyebrow="CROP ↔ LIVESTOCK" title="Your recorded resource loop" description="Counts below come from links recorded on this farm; no nutrient balance is inferred." action={<button className="text-link" onClick={() => onNavigate("feed")}>Manage feed & compost <ArrowRight size={14} /></button>} /><ResourceCycleMini cycle={resourceCycle} onNavigate={onNavigate} /></section><section className="card activity-card"><PanelTitle eyebrow="RECENT RECORDS" title="Farm activity" action={<button className="text-link" onClick={() => onNavigate("veterinary")}>Review animal health <ArrowRight size={14} /></button>} />{dashboard.activities?.length ? <div className="activity-list">{dashboard.activities.slice(0, 4).map((item: AnyRecord, index: number) => <div className="activity-row" key={`${item.kind}-${item.date}-${index}`}><span className={`activity-icon ${item.kind === "Veterinary" ? "vet" : "milk"}`}>{item.kind === "Veterinary" ? "✚" : "◌"}</span><div><strong>{item.text}</strong><small>{item.kind} · {new Date(`${item.date}T00:00:00`).toLocaleDateString("en-KE", { day: "numeric", month: "short" })}{item.verified ? " · Vet verified" : " · Farmer submitted"}</small></div><span className="activity-dot" /></div>)}</div> : <Empty title="No recent records" detail="Farm records will appear here." />}</section></div>
  </>;
}

function TerravantaVideoFeature() {
  return <section className="card product-video-feature" aria-labelledby="product-video-title">
    <div className="product-video-copy"><p className="eyebrow">PRODUCT WALKTHROUGH</p><h2 id="product-video-title">From payout records to a reviewable close.</h2><p>See how Terravanta compares collection, processor settlement and farmer payout records, then routes exceptions for human review.</p><span className="product-video-note"><ShieldCheck size={14} />Silent preview · example data is synthetic · no payments are initiated</span></div>
    <video className="product-explainer-video" controls playsInline preload="none" width="1280" height="720" poster="/videos/terravanta-payout-close-poster.png" aria-label="Terravanta product walkthrough of a cooperative payout close">
      <source src="/videos/terravanta-payout-close.mp4" type="video/mp4" />
      Your browser does not support the Terravanta explainer video.
    </video>
  </section>;
}

function VeterinarianDashboard({ cases, busy, verify, onNavigate }: AnyRecord) {
  const today = dateInput();
  const pendingVerification = cases.filter((item: AnyRecord) => !item.verified);
  const followUps = cases.filter((item: AnyRecord) => item.follow_up_on);
  const overdue = followUps.filter((item: AnyRecord) => item.follow_up_on < today);
  const dueToday = followUps.filter((item: AnyRecord) => item.follow_up_on === today);
  const noFollowUpDate = cases.filter((item: AnyRecord) => !item.follow_up_on).length;
  const cards = [
    { title: "Assigned open cases", value: cases.length, unit: "cases", icon: "✚", tone: "amber", sub: "Visible to your account" },
    { title: "Awaiting verification", value: pendingVerification.length, unit: "records", icon: "✓", tone: "green", sub: "Review before signing" },
    { title: "Follow-up due today", value: dueToday.length, unit: "cases", icon: "◷", tone: "blue", sub: "Based on recorded dates" },
    { title: "Past follow-up date", value: overdue.length, unit: "cases", icon: "!", tone: "earth", sub: `${noFollowUpDate} without a recorded date` },
  ];
  const queue = [...cases].sort((a: AnyRecord, b: AnyRecord) => {
    const rank = (item: AnyRecord) => !item.follow_up_on ? 3 : item.follow_up_on < today ? 0 : item.follow_up_on === today ? 1 : 2;
    return rank(a) - rank(b) || String(a.follow_up_on || "9999-12-31").localeCompare(String(b.follow_up_on || "9999-12-31"));
  });
  const followUpState = (item: AnyRecord) => !item.follow_up_on
    ? { label: "No date recorded", tone: "neutral" as const }
    : item.follow_up_on < today ? { label: "Past date", tone: "red" as const }
      : item.follow_up_on === today ? { label: "Due today", tone: "amber" as const }
        : { label: "Scheduled", tone: "green" as const };
  return <div className="vet-dashboard">
    <section className="vet-priority-strip"><span className="vet-priority-icon"><Stethoscope size={19} /></span><div><strong>Assigned clinical work, sorted by recorded follow-up date</strong><small>Calendar order helps organize review; it is not a clinical severity score or diagnostic recommendation.</small></div><button className="button button-outline" onClick={() => onNavigate("veterinary")}>Open all case records <ArrowRight size={14} /></button></section>
    <TerravantaVideoFeature />
    <div className="stats-grid">{cards.map((item) => <article className="stat-card" key={item.title}><div className="stat-top"><span className={`stat-icon ${item.tone}`}>{item.icon}</span><span className="stat-quiet">{item.unit}</span></div><p>{item.title}</p><div className="stat-value">{item.value}<span> {item.unit}</span></div><small>{item.sub}</small></article>)}</div>
    <section className="card vet-case-queue"><PanelTitle eyebrow="ASSIGNED CLINICAL QUEUE" title="Work the next review" description="Case facts and follow-up dates come from farm records. Verification signs the existing record; it does not create a diagnosis." action={<StatusPill tone={pendingVerification.length ? "amber" : "green"}>{pendingVerification.length} need verification</StatusPill>} />
      {cases.length ? <div className="table-scroll"><table><thead><tr><th>Animal / farm</th><th>Event</th><th>Recorded observation</th><th>Follow-up clock</th><th>Record provenance</th><th>Action</th></tr></thead><tbody>{queue.map((item: AnyRecord) => {
        const followUp = followUpState(item);
        return <tr key={item.id}><td><strong>{item.animal_name} · {item.animal_tag}</strong><small className="cell-sub">{item.farm_name} · {item.farm_code}</small></td><td className="capitalize">{item.event_type.replaceAll("_", " ")}<small className="cell-sub">Occurred {item.occurred_on}</small></td><td>{item.summary}</td><td><StatusPill tone={followUp.tone}>{followUp.label}</StatusPill>{item.follow_up_on ? <small className="cell-sub">{item.follow_up_on}</small> : null}</td><td><StatusPill tone={item.verified ? "green" : "amber"}>{item.verified ? "Veterinarian verified" : "Farmer-submitted"}</StatusPill></td><td>{item.verified ? <span className="muted">Signed</span> : <button className="button button-outline" disabled={busy} onClick={() => void verify(item.id)}>Review & verify</button>}</td></tr>;
      })}</tbody></table></div> : <Empty title="No open cases in your assigned queue" detail="New farmer-submitted health events on assigned farms will appear here for veterinary review." />}
      <div className="provenance-banner"><ShieldCheck size={18} /><p><strong>Professional oversight.</strong> Verification records the responsible veterinarian and preserves the submitted event. It does not certify an AI interpretation.</p></div>
    </section>
  </div>;
}

function latestTrend(dashboard: AnyRecord) { return dashboard?.milk_trend?.at(-1)?.liters ?? 0; }

function ResourceCycleMini({ cycle, onNavigate }: { cycle: AnyRecord | null; onNavigate: (section: Section) => void }) {
  const plots = cycle?.plots?.length || 0;
  const feedBatches = cycle?.feed_batches?.length || 0;
  const allocations = cycle?.allocations?.length || 0;
  const manure = cycle?.manure?.length || 0;
  const compost = cycle?.compost?.length || 0;
  const applications = cycle?.applications?.length || 0;
  const nodes = [
    { icon: "🌿", title: "Farm plots", detail: `${plots} plots recorded`, section: "crops" as Section },
    { icon: "🐄", title: "Animal feed", detail: `${allocations} allocations · ${feedBatches} batches`, section: "feed" as Section },
    { icon: "♻", title: "Manure & compost", detail: `${manure} manure · ${compost} compost`, section: "feed" as Section },
    { icon: "🌱", title: "Plot application", detail: `${applications} applications`, section: "crops" as Section },
  ];
  return <><div className="resource-cycle resource-cycle-live">{nodes.map((node, index) => <Fragment key={node.title}>{index ? <ArrowRight size={15} aria-hidden="true" /> : null}<button type="button" className="cycle-node cycle-node-action" onClick={() => onNavigate(node.section)}><span>{node.icon}</span><strong>{node.title}</strong><small>{node.detail}</small></button></Fragment>)}</div><small className="resource-cycle-note">{cycle?.note || "Record each handoff to connect crops, feed and compost."}</small></>;
}

function FarmsView({ farm, passport, farmId, userName, busy, submit, revokeConsent }: AnyRecord) {
  return <div className="two-column"><section className="card"><PanelTitle eyebrow="FARM IDENTITY" title={farm?.name || "Register a farm"} description="Submitted information is clearly separated from verified records." /><div className="farm-id-card"><div className="farm-emblem"><Leaf size={22} /></div><div><small>FARM IDENTIFIER</small><strong>{farm?.code || "Created after registration"}</strong></div><StatusPill tone={farm?.verification_status === "verified" ? "green" : "amber"}>{String(farm?.verification_status || "farmer_submitted").replaceAll("_", " ")}</StatusPill></div>{farm ? <div className="detail-grid">{[["Owner", farm.owner_name], ["Location", `${farm.subcounty}, ${farm.county}`], ["Farm size", `${farm.size_acres} acres`], ["Farming system", farm.farming_system], ["Coordinates", farm.latitude ? `${farm.latitude}, ${farm.longitude}` : "Not recorded"], ["Record source", farm.is_synthetic ? "Synthetic demonstration data" : "Farmer submitted"]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div> : <Empty title="No farms yet" detail="Register a farm to start building its digital passport." />}<div className="subsection-title"><h3>{farm ? "Add another farm" : "Create farm identity"}</h3></div><form className="form-grid" onSubmit={(event) => submit(event, "/api/v1/farms", (v: FormValues) => ({ name: v.name, owner_name: v.owner_name, county: v.county, subcounty: v.subcounty, latitude: v.latitude ? Number(v.latitude) : null, longitude: v.longitude ? Number(v.longitude) : null, size_acres: Number(v.size_acres), farming_system: v.farming_system, production_activities: String(v.production_activities || "").split(",").map((s) => s.trim()).filter(Boolean) }))}><Field label="Farm name" name="name" placeholder="e.g. Sunrise Mixed Farm" /><Field label="Owner" name="owner_name" placeholder="Full name" defaultValue={userName} /><Field label="County" name="county" placeholder="County" /><Field label="Subcounty" name="subcounty" placeholder="Subcounty" /><Field label="Area (acres)" name="size_acres" type="number" step="0.1" min="0" /><Field label="Farming system" name="farming_system" defaultValue="mixed" /><Field label="Latitude" name="latitude" type="number" step="any" required={false} /><Field label="Longitude" name="longitude" type="number" step="any" required={false} /><label className="field span-two"><span>Production activities (comma separated)</span><input name="production_activities" placeholder="Dairy, maize, fodder" /></label><button className="button button-primary form-submit" disabled={busy}><Plus size={15} />{busy ? "Saving…" : "Register farm"}</button></form></section><div className="stacked"><section className="card passport-card"><PanelTitle eyebrow="DIGITAL FARM PASSPORT" title="Verified record summary" description="Record counts and provenance for this farm." />{passport ? <><div className="passport-counts">{Object.entries(passport.counts || {}).map(([key, value]) => <div key={key}><strong>{value as string | number}</strong><span>{key.replaceAll("_", " ")}</span></div>)}</div><div className="provenance-list"><p><i className="source-dot farmer-dot" /> Farmer submitted <span>Farm profile</span></p><p><i className="source-dot vet-dot" /> Veterinarian verified <span>{passport.counts?.health_events_verified || 0} health events</span></p><p><i className="source-dot system-dot" /> System generated <span>Identifiers and alerts</span></p></div></> : <Empty title="Passport is empty" detail="Add verified records to build the passport." />}</section><section className="card"><PanelTitle eyebrow="LOCATION" title={farm?.county || "Farm location"} /><div className="map-placeholder"><span className="map-contour contour-one" /><span className="map-contour contour-two" /><span className="map-pin"><Leaf size={16} /></span><div className="map-label">{farm?.name || "Farm location"}<small>{farm?.subcounty || "Location pending"} · {farm?.latitude ?? "coordinates pending"}</small></div><span className="map-scale">N ↑</span></div><small className="map-caption">Location from farmer-submitted coordinates. No boundary verification is shown.</small></section></div></div>;
}

function VeterinaryView({ animals, farmId, role, busy, submit, askAssistant, aiResponse, cases, verify }: AnyRecord) {
  return <div className="stacked">{role === "veterinarian" ? <section className="card"><PanelTitle eyebrow="VETERINARY REVIEW QUEUE" title={`${cases.length} open cases`} description="Review farmer-submitted events and sign only records you have reviewed." />{cases.length ? <div className="table-scroll"><table><thead><tr><th>Animal / farm</th><th>Clinical event</th><th>Follow-up</th><th>Verification</th><th></th></tr></thead><tbody>{cases.map((item: AnyRecord) => <tr key={item.id}><td><strong>{item.animal_name} · {item.animal_tag}</strong><small className="cell-sub">{item.farm_name}</small></td><td>{item.summary}<small className="cell-sub">{item.occurred_on}</small></td><td>{item.follow_up_on || "Not recorded"}</td><td><StatusPill tone={item.verified ? "green" : "amber"}>{item.verified ? "Verified" : "Needs review"}</StatusPill></td><td>{item.verified ? null : <button className="button button-outline" disabled={busy} onClick={() => void verify(item.id)}>Verify</button>}</td></tr>)}</tbody></table></div> : <Empty title="No open clinical cases" detail="New health events for assigned farms will appear in your queue." />}</section> : null}<div className="two-column main-two-col"><div className="stacked"><section className="card"><PanelTitle eyebrow="REGISTERED HERD" title={`${animals.length} animals`} description="Animal identities and their record source." action={<span className="record-count">{farmId.slice(0, 8)}</span>} />{animals.length ? <div className="table-scroll"><table><thead><tr><th>Animal</th><th>Tag</th><th>Species / breed</th><th>Sex</th><th>Records</th></tr></thead><tbody>{animals.map((animal: AnyRecord) => <tr key={animal.id}><td><div className="animal-cell"><span className="animal-avatar">🐄</span><strong>{animal.name}</strong></div></td><td className="mono">{animal.tag}</td><td>{animal.species}<small className="cell-sub">{animal.breed}</small></td><td className="capitalize">{animal.sex}</td><td><StatusPill tone="green">Profile active</StatusPill></td></tr>)}</tbody></table></div> : <Empty title="No animals registered" detail="Add a livestock profile to start veterinary record keeping." />}<div className="subsection-title"><h3>Register animal</h3></div><form className="form-grid" onSubmit={(event) => submit(event, `/api/v1/farms/${farmId}/animals`, (v: FormValues) => v)}><Field label="Animal name" name="name" /><Field label="Ear tag / unique ID" name="tag" /><SelectField label="Species" name="species" options={[{ label: "Cattle", value: "Cattle" }, { label: "Goat", value: "Goat" }, { label: "Sheep", value: "Sheep" }, { label: "Poultry", value: "Poultry" }]} /><Field label="Breed" name="breed" required={false} /><SelectField label="Sex" name="sex" options={[{ label: "Female", value: "female" }, { label: "Male", value: "male" }, { label: "Unknown", value: "unknown" }]} /><Field label="Date of birth" name="date_of_birth" type="date" required={false} /><button className="button button-primary form-submit" disabled={busy}><Plus size={15} />Add animal</button></form></section></div><div className="stacked"><section className="card"><PanelTitle eyebrow="HEALTH EVENT" title="Add clinical record" description="Vet verification is recorded separately from farmer-submitted notes." /><form className="form-grid" onSubmit={(event) => submit(event, `/api/v1/animals/${new FormData(event.currentTarget).get("animal_id")}/health-events`, (v: FormValues) => ({ event_type: v.event_type, occurred_on: v.occurred_on, summary: v.summary, observations: { observation: v.observations }, follow_up_on: v.follow_up_on || null, verify_record: v.verify_record === "on" }))}><SelectField label="Animal" name="animal_id" options={animals.map((animal: AnyRecord) => ({ label: `${animal.name} · ${animal.tag}`, value: animal.id }))} /><SelectField label="Event type" name="event_type" options={[{ label: "Clinical observation", value: "clinical_observation" }, { label: "Vaccination", value: "vaccination" }, { label: "Treatment record", value: "treatment" }, { label: "Veterinary visit", value: "veterinary_visit" }, { label: "Reproductive event", value: "reproductive" }]} /><Field label="Date observed" name="occurred_on" type="date" defaultValue={dateInput()} /><Field label="Follow-up date" name="follow_up_on" type="date" required={false} /><label className="field span-two"><span>Clinical summary / observation</span><textarea name="summary" required minLength={4} placeholder="Record observed facts, not a diagnosis…" /></label><Field label="Observation detail" name="observations" required={false} placeholder="e.g. appetite not recorded" /><label className={`check-row span-two ${role !== "veterinarian" ? "disabled-check" : ""}`}><input name="verify_record" type="checkbox" disabled={role !== "veterinarian"} /><span><strong>Mark as veterinarian verified</strong><small>{role === "veterinarian" ? "Your authenticated role will be recorded as verifier." : "Only a veterinarian can verify a clinical record."}</small></span></label><button className="button button-primary form-submit" disabled={busy}><Plus size={15} />Save health event</button></form></section><AssistantForm animals={animals} busy={busy} askAssistant={askAssistant} response={aiResponse} compact /></div></div></div>;
}

function AssistantForm({ animals, busy, askAssistant, response, compact = false }: AnyRecord) {
  return <section className={`card ai-card ${compact ? "compact-ai" : ""}`}><PanelTitle eyebrow="AI-ASSISTED REVIEW" title="Ask about a case" description="External model access requires explicit consent for this request." /><form className="ai-form" onSubmit={askAssistant}><SelectField label="Animal" name="animal_id" options={animals.map((animal: AnyRecord) => ({ label: `${animal.name} · ${animal.tag}`, value: animal.id }))} /><label className="field"><span>Your question</span><textarea name="question" required minLength={4} placeholder="Summarize the recorded history and note missing fields…" /></label><label className="check-row"><input name="allow_external_processing" type="checkbox" /><span><strong>Allow this case context to be sent to NVIDIA</strong><small>Review the provider terms. Private farm data is not sent unless checked.</small></span></label><button className="button button-dark" disabled={busy}><Sparkles size={15} />{busy ? "Reviewing…" : "Request review draft"}</button></form>{response ? <div className="ai-response"><div className="ai-response-head"><Sparkles size={16} /><strong>{response.status === "success" ? "Draft response" : response.status.replaceAll("_", " ")}</strong><StatusPill tone={response.model_generated ? "amber" : "neutral"}>{response.model_generated ? "AI generated · review" : "No model answer"}</StatusPill></div><p>{response.answer}</p><small>{response.safety_note}</small>{response.sources?.length ? <div className="source-citations"><strong>Retrieved sources</strong>{response.sources.map((source: AnyRecord) => <a key={source.id} href={source.url} target="_blank" rel="noreferrer">{source.title} ↗</a>)}</div> : <small>No approved reference sources are configured. Animal record facts appear below as a separate context.</small>}<details><summary>Recorded facts sent for review</summary><pre>{JSON.stringify(response.recorded_facts, null, 2)}</pre></details></div> : null}</section>;
}

function CropsView({ farmId, plots, cycle, busy, submit }: AnyRecord) {
  return <div className="two-column"><section className="card"><PanelTitle eyebrow="PLOTS & CROP TYPES" title={`${plots.length} registered plots`} description="Record crop use and mark forage plots as potential feed sources." />{plots.length ? <div className="plot-list">{plots.map((plot: AnyRecord) => <div className="plot-row" key={plot.id}><span className={`plot-icon ${plot.is_feed_crop ? "fodder" : "crop"}`}><Leaf size={17} /></span><div><strong>{plot.name}</strong><small>{plot.crop_type} · {plot.area_acres} acres</small></div>{plot.is_feed_crop ? <StatusPill tone="green">Feed crop</StatusPill> : <StatusPill>Crop plot</StatusPill>}</div>)}</div> : <Empty title="No plots recorded" detail="Register a plot to connect crop production with livestock resources." />}<div className="subsection-title"><h3>Register a plot</h3></div><form className="form-grid" onSubmit={(event) => submit(event, `/api/v1/farms/${farmId}/plots`, (v: FormValues) => ({ ...v, area_acres: Number(v.area_acres), planting_date: v.planting_date || null, is_feed_crop: v.is_feed_crop === "on" }))}><Field label="Plot name" name="name" placeholder="North paddock" /><Field label="Area (acres)" name="area_acres" type="number" min="0.1" step="0.1" /><Field label="Crop type" name="crop_type" placeholder="Napier grass, maize…" /><Field label="Planting date" name="planting_date" type="date" required={false} /><label className="check-row span-two"><input type="checkbox" name="is_feed_crop" /><span><strong>Used as a feed crop</strong><small>Links this plot to fodder/feed records.</small></span></label><button className="button button-primary form-submit" disabled={busy}><Plus size={15} />Add crop plot</button></form></section><div className="stacked"><section className="card cycle-full"><PanelTitle eyebrow="INTEGRATED RESOURCE RECORDS" title="Crop–livestock cycle" description="Relationships shown only when recorded. No nutrient balance is inferred." /><div className="cycle-vertical"><div><span className="cycle-step">01</span><span className="cycle-step-icon green-bg">🌿</span><div><strong>Fodder plots</strong><small>{cycle?.plots?.filter((p: AnyRecord) => p.is_feed_crop).length || 0} recorded as feed crops</small></div></div><i /><div><span className="cycle-step">02</span><span className="cycle-step-icon amber-bg">🐄</span><div><strong>Livestock feed</strong><small>{cycle?.allocations?.length || 0} recorded feed allocations</small></div></div><i /><div><span className="cycle-step">03</span><span className="cycle-step-icon soil-bg">♻</span><div><strong>Manure → compost</strong><small>{cycle?.manure?.length || 0} manure records · {cycle?.compost?.length || 0} batches</small></div></div><i /><div><span className="cycle-step">04</span><span className="cycle-step-icon green-bg">🌱</span><div><strong>Compost to plots</strong><small>{cycle?.applications?.length || 0} application records</small></div></div></div></section><section className="card"><PanelTitle eyebrow="SOIL & WATER" title="Measurement records" /><Empty title="No tests on file" detail="Soil and water test results can be attached to farm records once entered and verified." /></section></div></div>;
}

function FeedView({ farmId, batches, animals, plots, busy, submit, cycle }: AnyRecord) {
  return <><div className="two-column"><section className="card"><PanelTitle eyebrow="ON-FARM FEED" title="Feed inventory" description="Recorded batch quantities. This is not a ration recommendation." />{batches.length ? <div className="feed-list">{batches.map((batch: AnyRecord) => <div className="feed-row" key={batch.id}><div className="feed-icon">⌁</div><div className="feed-main"><strong>{batch.name}</strong><small>{batch.ingredients?.join(" · ") || "Ingredients not recorded"}</small><span className="feed-meter"><i style={{ width: `${Math.min(100, Math.max(8, batch.quantity_kg / 12))}%` }} /></span></div><strong className="feed-quantity">{batch.quantity_kg.toLocaleString()} <small>kg</small></strong>{batch.aflatoxin_status === "pending_test" ? <StatusPill tone="amber">Test pending</StatusPill> : null}</div>)}</div> : <Empty title="No feed batches yet" detail="Create a feed batch to track stock and source." />}<div className="subsection-title"><h3>Record feed batch</h3></div><form className="form-grid" onSubmit={(event) => submit(event, `/api/v1/farms/${farmId}/feed-batches`, (v: FormValues) => ({ ...v, quantity_kg: Number(v.quantity_kg), batch_date: v.batch_date, ingredients: String(v.ingredients || "").split(",").map((x) => x.trim()).filter(Boolean), plot_id: v.plot_id || null }))}><Field label="Feed batch name" name="name" /><Field label="Quantity (kg)" name="quantity_kg" type="number" min="0.1" step="0.1" /><Field label="Batch date" name="batch_date" type="date" defaultValue={dateInput()} /><SelectField label="Feed source plot" name="plot_id" required={false} options={plots.map((plot: AnyRecord) => ({ label: `${plot.name} · ${plot.crop_type}`, value: plot.id }))} /><Field label="Ingredients (comma separated)" name="ingredients" required={false} /><Field label="Storage conditions" name="storage_conditions" required={false} placeholder="Dry, raised store" /><SelectField label="Aflatoxin check" name="aflatoxin_status" options={[{ label: "Not tested", value: "not_tested" }, { label: "Test pending", value: "pending_test" }, { label: "Result recorded", value: "result_recorded" }]} /><button className="button button-primary form-submit" disabled={busy}><Plus size={15} />Add feed batch</button></form></section><section className="card"><PanelTitle eyebrow="ANIMAL ALLOCATION" title="Allocate feed" description="Subtracts the entered quantity from the recorded batch." /><form className="form-grid" onSubmit={(event) => submit(event, `/api/v1/farms/${farmId}/feed-allocations`, (v: FormValues) => ({ ...v, allocated_kg: Number(v.allocated_kg) }))}><SelectField label="Feed batch" name="feed_batch_id" options={batches.map((batch: AnyRecord) => ({ label: `${batch.name} · ${batch.quantity_kg} kg`, value: batch.id }))} /><SelectField label="Animal" name="animal_id" options={animals.map((animal: AnyRecord) => ({ label: `${animal.name} · ${animal.tag}`, value: animal.id }))} /><Field label="Quantity (kg)" name="allocated_kg" type="number" min="0.1" step="0.1" /><Field label="Allocation date" name="allocated_on" type="date" defaultValue={dateInput()} /><button className="button button-primary form-submit" disabled={busy}><Plus size={15} />Save allocation</button></form><div className="safety-callout"><AlertTriangle size={17} /><p><strong>Aflatoxin monitoring is a workflow prompt.</strong> Pending test status is not a safety determination, and milk is never auto-certified.</p></div><div className="subsection-title"><h3>Resource links</h3></div><div className="mini-resource-lines"><span>Feed allocations <strong>{cycle?.allocations?.length || 0}</strong></span><span>Manure records <strong>{cycle?.manure?.length || 0}</strong></span><span>Compost applications <strong>{cycle?.applications?.length || 0}</strong></span></div></section></div><CompostForms farmId={farmId} cycle={cycle} plots={plots} busy={busy} submit={submit} /></>;
}

function CompostForms({ farmId, cycle, plots, busy, submit }: AnyRecord) {
  const manure = cycle?.manure || [];
  const compost = cycle?.compost || [];
  return <section className="card compost-card"><PanelTitle eyebrow="MANURE & COMPOST" title="Close the resource loop" description="Record manure collection, compost batches and their application to crop plots." /><div className="three-forms"><form className="mini-form" onSubmit={(event) => submit(event, `/api/v1/farms/${farmId}/manure-records`, (v: FormValues) => ({ ...v, quantity_kg: Number(v.quantity_kg) }))}><h3><span>01</span>Collect manure</h3><Field label="Collection date" name="collected_on" type="date" defaultValue={dateInput()} /><Field label="Quantity (kg)" name="quantity_kg" type="number" step="0.1" min="0.1" /><Field label="Source note" name="source_notes" required={false} placeholder="Shed collection" /><button className="button button-outline" disabled={busy}><Plus size={14} />Record collection</button></form><form className="mini-form" onSubmit={(event) => submit(event, `/api/v1/farms/${farmId}/compost-batches`, (v: FormValues) => ({ ...v, manure_record_id: v.manure_record_id || null, quantity_kg: Number(v.quantity_kg) }))}><h3><span>02</span>Create compost batch</h3><Field label="Batch name" name="name" placeholder="Compost heap A" /><SelectField label="Manure source" name="manure_record_id" required={false} options={manure.map((row: AnyRecord) => ({ label: `${row.quantity_kg} kg · ${row.collected_on}`, value: row.id }))} /><Field label="Start date" name="created_on" type="date" defaultValue={dateInput()} /><Field label="Quantity (kg)" name="quantity_kg" type="number" step="0.1" min="0.1" /><button className="button button-outline" disabled={busy}><Plus size={14} />Create batch</button></form><form className="mini-form" onSubmit={(event) => submit(event, `/api/v1/farms/${farmId}/compost-applications`, (v: FormValues) => ({ ...v, quantity_kg: Number(v.quantity_kg) }))}><h3><span>03</span>Apply to a plot</h3><SelectField label="Compost batch" name="compost_batch_id" options={compost.map((row: AnyRecord) => ({ label: `${row.name} · ${row.status}`, value: row.id }))} /><SelectField label="Crop plot" name="plot_id" options={plots.map((plot: AnyRecord) => ({ label: `${plot.name} · ${plot.crop_type}`, value: plot.id }))} /><Field label="Application date" name="applied_on" type="date" defaultValue={dateInput()} /><Field label="Quantity (kg)" name="quantity_kg" type="number" step="0.1" min="0.1" /><button className="button button-outline" disabled={busy}><Plus size={14} />Record application</button></form></div></section>;
}

function ProductionView({ farmId, production, animals, plots, deliveries, busy, submit }: AnyRecord) {
  return <div className="two-column"><section className="card"><PanelTitle eyebrow="OUTPUT RECORDS" title="Production log" description="Daily milk and crop harvest records linked to animals or plots." />{production.length ? <div className="table-scroll"><table><thead><tr><th>Date</th><th>Product</th><th>Quantity</th><th>Source</th></tr></thead><tbody>{production.map((row: AnyRecord) => <tr key={row.id}><td>{new Date(`${row.recorded_on}T00:00:00`).toLocaleDateString("en-KE", { day: "numeric", month: "short", year: "numeric" })}</td><td className="capitalize">{row.product_type}</td><td><strong>{row.quantity} {row.unit}</strong></td><td>{row.animal_id ? animals.find((item: AnyRecord) => item.id === row.animal_id)?.tag || "Animal" : row.plot_id ? plots.find((item: AnyRecord) => item.id === row.plot_id)?.name || "Plot" : "Farm"}</td></tr>)}</tbody></table></div> : <Empty title="No production entries" detail="Record the first milk or crop harvest to begin traceability." />}<div className="subsection-title"><h3>Record production</h3></div><form className="form-grid" onSubmit={(event) => submit(event, `/api/v1/farms/${farmId}/production-records`, (v: FormValues) => ({ ...v, quantity: Number(v.quantity), animal_id: v.animal_id || null, plot_id: v.plot_id || null }))}><SelectField label="Product type" name="product_type" options={[{ label: "Milk", value: "milk" }, { label: "Maize", value: "maize" }, { label: "Vegetables", value: "vegetables" }, { label: "Eggs", value: "eggs" }]} /><Field label="Quantity" name="quantity" type="number" step="0.1" min="0.1" /><SelectField label="Unit" name="unit" options={[{ label: "Litres", value: "L" }, { label: "Kilograms", value: "kg" }, { label: "Crates", value: "crates" }]} /><Field label="Recorded date" name="recorded_on" type="date" defaultValue={dateInput()} /><SelectField label="Animal source" name="animal_id" required={false} options={animals.map((animal: AnyRecord) => ({ label: `${animal.name} · ${animal.tag}`, value: animal.id }))} /><SelectField label="Plot source" name="plot_id" required={false} options={plots.map((plot: AnyRecord) => ({ label: `${plot.name} · ${plot.crop_type}`, value: plot.id }))} /><button className="button button-primary form-submit" disabled={busy}><Plus size={15} />Save production record</button></form></section><div className="stacked"><section className="card"><PanelTitle eyebrow="FARM → BUYER" title="Create delivery & product lot" description="A delivery is linked to a production record and a traceable lot." /><form className="form-grid" onSubmit={(event) => submit(event, `/api/v1/farms/${farmId}/deliveries`, (v: FormValues) => ({ ...v, quantity: Number(v.quantity) }))}><SelectField label="Source production record" name="production_record_id" options={production.map((row: AnyRecord) => ({ label: `${row.recorded_on} · ${row.quantity} ${row.unit} ${row.product_type}`, value: row.id }))} /><Field label="Buyer" name="buyer_name" placeholder="Buyer or cooperative" /><Field label="Delivery date" name="delivery_date" type="date" defaultValue={dateInput()} /><Field label="Delivered quantity" name="quantity" type="number" min="0.1" step="0.1" /><SelectField label="Unit" name="unit" options={[{ label: "Litres", value: "L" }, { label: "Kilograms", value: "kg" }]} /><Field label="Delivery reference" name="reference" required={false} placeholder="Receipt number" /><button className="button button-primary form-submit" disabled={busy}><Plus size={15} />Create lot & delivery</button></form></section><section className="card"><PanelTitle eyebrow="DELIVERY HISTORY" title={`${deliveries.length} deliveries`} />{deliveries.length ? deliveries.slice(0, 4).map((item: AnyRecord) => <div className="delivery-row" key={item.id}><span className="delivery-icon">↗</span><div><strong>{item.buyer}</strong><small>{item.delivery?.delivery_date} · {item.lot?.lot_code}</small></div><b>{item.delivery?.quantity} {item.delivery?.unit}</b></div>) : <Empty title="No deliveries recorded" detail="Create a delivery linked to a production record." />}</section></div></div>;
}

function TraceabilityView({ passport, deliveries, cooperatives, busy, saveConsent, revokeConsent }: AnyRecord) {
  const activeConsents = passport?.sharing?.filter((row: AnyRecord) => row.status === "active") || [];
  const [targetOrgId, setTargetOrgId] = useState("");
  const [targetEmail, setTargetEmail] = useState("");
  const targetHasGrant = activeConsents.some((grant: AnyRecord) =>
    grant.scope === "delivery_summary" && (
      targetEmail.trim() ? grant.grantee_email?.toLowerCase() === targetEmail.trim().toLowerCase() : grant.grantee_org_id === targetOrgId
    ),
  );
  useEffect(() => { if (!targetOrgId && cooperatives?.length) setTargetOrgId(cooperatives[0].id); }, [cooperatives, targetOrgId]);
  return <div className="two-column">
    <section className="card">
      <PanelTitle eyebrow="TRACEABILITY" title="From farm record to delivery" description="Each lot points back to its source production entry." />
      {deliveries.length ? <div className="trace-list">{deliveries.map((row: AnyRecord) => <div className="trace-item" key={row.id}><div className="trace-step"><span>01</span><i /><span>02</span><i /><span>03</span></div><div className="trace-copy"><div><small>SOURCE LOT</small><strong>{row.lot?.lot_code}</strong><p>{row.lot?.product_type} · {row.lot?.quantity} {row.lot?.unit}</p></div><ArrowRight size={20} /><div><small>DELIVERY</small><strong>{row.buyer}</strong><p>{row.delivery?.delivery_date} · {row.delivery?.reference || "No reference"}</p></div><StatusPill tone={row.delivery?.status === "accepted" ? "green" : "amber"}>{row.delivery?.status}</StatusPill></div></div>)}</div> : <Empty title="No traceability chain yet" detail="Record production, then create a delivery to link its source lot." />}
      <div className="provenance-banner"><ShieldCheck size={18} /><p><strong>Provenance stays visible.</strong> The farm profile is farmer-submitted. Clinical events are separately marked as veterinarian verified when signed by an authorized vet.</p></div>
    </section>
    <div className="stacked">
      <section className="card consent-card">
        <PanelTitle eyebrow="CONSENT CONTROL" title="Cooperative sharing" description="Share only delivery summaries with a registered cooperative or its verified account email." />
        {activeConsents.length ? <div className="active-grants">{activeConsents.map((grant: AnyRecord) => <div className="consent-status" key={grant.id}><span className="consent-icon active"><ShieldCheck size={20} /></span><div><strong>{grant.grantee_name || grant.grantee_email}</strong><small>{grant.scope.replaceAll("_", " ")} · active</small></div><button className="button button-danger-outline" disabled={busy} onClick={() => void revokeConsent(grant.id)}>Revoke</button></div>)}</div> : <div className="consent-status"><span className="consent-icon"><ShieldCheck size={20} /></span><div><strong>Nothing is currently shared</strong><small>Farm records remain private until you grant access.</small></div></div>}
        <p className="consent-copy">Shared delivery fields: farm name and code, lot, product type, delivery date, quantity, status and reference. Veterinary, animal-health and laboratory records are excluded.</p>
        {cooperatives.length ? <label className="field"><span>Registered cooperative</span><select value={targetOrgId} onChange={(event) => { setTargetOrgId(event.target.value); setTargetEmail(""); }}><option value="">Choose…</option>{cooperatives.map((org: AnyRecord) => <option key={org.id} value={org.id}>{org.name}</option>)}</select></label> : null}
        <label className="field"><span>Or share with a cooperative administrator email</span><input type="email" value={targetEmail} onChange={(event) => setTargetEmail(event.target.value)} placeholder="coordinator@example.org" /></label>
        <button className="button button-primary" disabled={busy || (!targetOrgId && !targetEmail.trim()) || targetHasGrant} onClick={() => void saveConsent(targetEmail.trim() ? { grantee_email: targetEmail.trim() } : { grantee_org_id: targetOrgId })}><ShieldCheck size={15} />{targetHasGrant ? "Delivery summaries already shared" : "Grant delivery-summary access"}</button>
        <small className="map-caption">Email grants work only for an account that has cooperative administrator access in Terravanta. You can revoke a grant at any time.</small>
      </section>
      <section className="card"><PanelTitle eyebrow="COOPERATIVE PORTAL" title="Read-only access" /><div className="portal-preview"><span><ShieldCheck size={18} /></span><div><strong>Consented records only</strong><small>Portal access is checked on the API for every request.</small></div><ArrowRight size={15} /></div></section>
    </div>
  </div>;
}
function AssistantView({ animals, busy, askAssistant, response, documentResult, extractDocument, reviewDocument }: AnyRecord) {
  return <div className="two-column"><div className="stacked"><AssistantForm animals={animals} busy={busy} askAssistant={askAssistant} response={response} /><section className="safety-callout broad"><ShieldCheck size={19} /><p><strong>Veterinary oversight remains required.</strong> The assistant is limited to recorded facts and approved references. Do not use model output to diagnose, prescribe, calculate treatment doses, or authorize treatment.</p></section></div><div className="stacked"><section className="card"><PanelTitle eyebrow="DOCUMENT EXTRACTION" title="Upload a farm document" description="Extracted values remain a draft until a person reviews them." /><form className="upload-form" onSubmit={extractDocument}><label className="upload-drop"><FileUp size={25} /><strong>Select a document</strong><small>PDF, JPEG or PNG · up to 8 MB</small><input name="file" type="file" accept="application/pdf,image/jpeg,image/png" required /></label><label className="check-row"><input name="allow_external_processing" type="checkbox" /><span><strong>Allow image document processing by NVIDIA</strong><small>Checked image uploads are sent to the configured Parse endpoint; review provider terms and data handling before using hosted services. Selectable PDF text is extracted locally.</small></span></label><button className="button button-dark" disabled={busy}><Sparkles size={15} />{busy ? "Extracting…" : "Extract draft fields"}</button></form>{documentResult ? <div className="extraction-result"><div className="ai-response-head"><FileUp size={16} /><strong>{documentResult.filename}</strong><StatusPill tone="amber">{documentResult.status.replaceAll("_", " ")}</StatusPill></div><p>{documentResult.extracted_text || documentResult.extracted_fields?.notice || "No text was extracted. Enter visible values manually."}</p><pre>{JSON.stringify(documentResult.extracted_fields, null, 2)}</pre><button className="button button-outline" type="button" onClick={() => void reviewDocument()} disabled={busy || documentResult.status === "reviewed"}>{documentResult.status === "reviewed" ? "Reviewed" : "Mark extraction reviewed"}</button><small>Nothing was written to official farm records. Confirm values, then enter them through the relevant workflow.</small></div> : <div className="inline-note"><AlertTriangle size={16} /><span>Image parsing requires explicit consent and a configured Nemotron Parse endpoint. Structured field mapping additionally requires NVIDIA_API_KEY. Selectable PDF text can be extracted locally.</span></div>}</section><section className="card"><PanelTitle eyebrow="AI PROVIDER STATUS" title="Backend-only model access" /><div className="provider-status"><span className="provider-mark">N</span><div><strong>NVIDIA NIM provider</strong><small>Model IDs are environment configured. API credentials stay on the backend.</small></div><StatusPill tone="amber">Key required</StatusPill></div><p className="muted small-copy">No model call is fabricated when credentials are missing or a request fails. Provider outcome and latency are logged without storing raw clinical prompts.</p></section></div></div>;
}

function ReportsView({ dashboard, alerts, passport }: AnyRecord) {
  return <div className="two-column"><section className="card"><PanelTitle eyebrow="FARM INDICATORS" title="Transparent record summary" description="Counts come directly from farm records; no predictive model is used." /><div className="report-grid">{Object.entries(dashboard?.stats || {}).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{value as string | number}</strong><small>Recorded value</small></div>)}</div></section><div className="stacked"><section className="card"><PanelTitle eyebrow="RULE-BASED ALERTS" title={`${alerts.length} current alerts`} />{alerts.length ? alerts.map((alert: AnyRecord) => <div className="report-alert" key={alert.id}><AlertTriangle size={16} /><div><strong>{alert.title}</strong><small>{alert.trigger}</small><p>{alert.next_action}</p></div></div>) : <Empty title="No rule alerts" detail="Alerts are calculated from visible follow-up, stock and production rules." />}</section><section className="card"><PanelTitle eyebrow="DATA PROVENANCE" title="Passport sources" /><div className="provenance-list"><p><i className="source-dot farmer-dot" /> Farmer submitted <span>{passport?.farm?.verification_status || "—"}</span></p><p><i className="source-dot vet-dot" /> Veterinarian verified <span>{passport?.counts?.health_events_verified || 0} events</span></p><p><i className="source-dot system-dot" /> System generated <span>Rule alerts</span></p></div></section></div></div>;
}

function SettingsView({ role, userName, farm, passport, online, queued }: AnyRecord) {
  const initials = String(userName || "TV").split(/\s+/).filter(Boolean).slice(0, 2).map((part: string) => part[0]).join("").toUpperCase();
  const organizationAccessCopy = "This account has farmer access. Ask the Terravanta pilot operator to invite a verified Supabase identity and assign cooperative or processor organization membership. Keep farm-record ownership separate; role changes require operator review.";
  return <div className="two-column"><section className="card"><PanelTitle eyebrow="ACCOUNT & ACCESS" title="Current workspace role" description="Role checks are enforced on the server for each operation." /><div className="settings-role"><div className="profile-avatar large">{initials || "TV"}</div><div><strong>{userName || "Signed-in user"}</strong><small>{role.replaceAll("_", " ")}{role === "farmer" ? " · farm record owner" : role === "veterinarian" ? " · authorized clinical reviewer" : " · consented read-only access"}</small></div><StatusPill tone="green">Active</StatusPill></div><div className="settings-info"><span>Authentication mode</span><strong>{AUTH_MODE === "demo" ? "Synthetic demo" : "Supabase Auth"}</strong><small>{role === "farmer" ? organizationAccessCopy : "Access roles are assigned by Terravanta. Your current role controls which workspace menus and records are available."}</small></div><div className="settings-info"><span>Active farm</span><strong>{farm ? `${farm.name} · ${farm.code}` : "No farm registered"}</strong><small>{farm?.is_synthetic ? "Synthetic demo dataset" : farm ? "Farmer submitted records" : "Create a farm to begin your private record."}</small></div></section><div className="stacked"><section className="card"><PanelTitle eyebrow="OFFLINE SYNC" title="Local record queue" /><div className="sync-card"><span className={`sync-large ${online ? "online" : "offline"}`}>{online ? <Wifi size={19} /> : <CloudOff size={19} />}</span><div><strong>{online ? "Connected" : "Offline"}</strong><small>{queued ? `${queued} record${queued === 1 ? "" : "s"} waiting to sync` : "No records waiting to sync"}</small></div></div><p className="muted small-copy">Farm and health event forms save to this browser while offline. Queued records sync after connectivity returns. AI requests need a connection.</p></section><section className="card"><PanelTitle eyebrow="CONSENT" title="Active sharing grants" />{passport?.sharing?.filter((row: AnyRecord) => row.status === "active").length ? passport.sharing.filter((row: AnyRecord) => row.status === "active").map((row: AnyRecord) => <div className="consent-list-row" key={row.id}><ShieldCheck size={17} /><div><strong>{row.grantee_email}</strong><small>{row.scope.replaceAll("_", " ")}</small></div></div>) : <Empty title="No active sharing grants" detail="Delivery data stays private until the farm owner grants consent." />}</section></div></div>;
}

function CooperativeWorkspace({ section, deliveries, runs, activeRun, closes, activeClose, busy, importFile, openRun, reviewItem, createClose, openClose, reviewException, approveClose, downloadPack, onNavigate }: AnyRecord) {
  if (section === "overview") return <CooperativeOverview closes={closes} deliveries={deliveries} onNavigate={onNavigate} openClose={openClose} />;
  if (section === "settlements") return <SettlementCloseWorkbench closes={closes} activeClose={activeClose} busy={busy} createClose={createClose} openClose={openClose} reviewException={reviewException} approveClose={approveClose} downloadPack={downloadPack} />;
  if (section === "traceability") return <CooperativeMemberRecordsView deliveries={deliveries} runs={runs} activeRun={activeRun} busy={busy} importFile={importFile} openRun={openRun} reviewItem={reviewItem} />;
  if (section === "reports") return <CooperativeCloseHistory closes={closes} openClose={openClose} onNavigate={onNavigate} />;
  if (section === "settings") return <CooperativeAccessControls />;
  return <Empty title="This cooperative view is not available" detail="Choose close desk, payout settlements, shared member records or close history." />;
}

function CooperativeOverview({ closes, deliveries, onNavigate, openClose }: AnyRecord) {
  const latest = closes[0];
  const openPeriods = closes.filter((close: AnyRecord) => close.status !== "approved");
  const unresolvedExceptions = openPeriods.reduce((total: number, close: AnyRecord) => total + Number(close.unresolved_exception_count ?? close.pending_review_count ?? 0), 0);
  const oldestOpenPeriods = [...openPeriods].sort((a: AnyRecord, b: AnyRecord) => String(a.period_start).localeCompare(String(b.period_start)));
  const exceptionClose = oldestOpenPeriods.find((close: AnyRecord) => Number(close.unresolved_exception_count ?? close.pending_review_count ?? 0) > 0);
  const signoffClose = oldestOpenPeriods[0];
  const approvedPeriods = closes.filter((close: AnyRecord) => close.status === "approved").length;
  const recordedCloseMinutes = closes
    .filter((close: AnyRecord) => close.status === "approved" && close.created_at && close.approved_at)
    .map((close: AnyRecord) => (Date.parse(close.approved_at) - Date.parse(close.created_at)) / 60_000)
    .filter((minutes: number) => Number.isFinite(minutes) && minutes >= 0)
    .sort((a: number, b: number) => a - b);
  const middleCloseIndex = Math.floor(recordedCloseMinutes.length / 2);
  const medianCloseMinutes = !recordedCloseMinutes.length
    ? null
    : recordedCloseMinutes.length % 2
      ? recordedCloseMinutes[middleCloseIndex]
      : (recordedCloseMinutes[middleCloseIndex - 1] + recordedCloseMinutes[middleCloseIndex]) / 2;
  const autoMatchPercent = latest?.member_count ? Math.round((latest.reconciled_count / latest.member_count) * 100) : null;
  const issueLabels: Record<string, string> = {
    missing_collection: "Missing collection row",
    missing_processor_settlement: "Missing processor row",
    missing_payout: "Missing payout row",
    volume_variance: "Volume mismatch",
    processor_amount_variance: "Processor arithmetic mismatch",
    payout_variance: "Payout amount mismatch",
  };
  const latestIssueReasons = Object.entries(latest?.issue_counts || {})
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 4);
  const latestStatus = latest?.status === "approved" ? "Approved" : latest ? "Review required" : "No close yet";
  function openPeriod(id: string) { onNavigate("settlements"); void openClose(id); }
  return <div className="coop-dashboard">
    <section className="coop-hero">
      <div className="coop-hero-copy"><p className="coop-kicker">COOPERATIVE FINANCE WORKSPACE</p><h2>Close each payout period with evidence.</h2><p>Bring collection, processor settlement and payout exports into one review queue. Your team owns every exception and approval.</p><div className="coop-hero-actions"><button className="button coop-primary-button" onClick={() => onNavigate("settlements")}>{latest ? "Open settlement desk" : "Start first settlement close"}<ArrowRight size={15} /></button><button className="coop-text-button" onClick={() => onNavigate("traceability")}>Review consented delivery records</button></div></div>
      <div className="coop-latest-card"><div className="coop-latest-top"><span>Most recent period</span><StatusPill tone={latest?.status === "approved" ? "green" : latest ? "amber" : "neutral"}>{latestStatus}</StatusPill></div>{latest ? <><strong>{latest.period_start} <span>to</span> {latest.period_end}</strong><div className="coop-latest-meta"><span>{latest.member_count} member rows</span><span>{latest.unresolved_exception_count ?? latest.pending_review_count ?? 0} unresolved</span></div><button type="button" className="coop-inline-link" onClick={() => openPeriod(latest.id)}>Continue this close <ArrowRight size={14} /></button></> : <><strong>No period imported</strong><p>Start with one completed period using your existing exports.</p></>}</div>
    </section>

    <TerravantaVideoFeature />

    <section className="coop-kpis" aria-label="Cooperative activity indicators">
      <article className="coop-kpi"><span>Unresolved member exceptions</span><strong>{unresolvedExceptions}</strong><small>{openPeriods.length ? "Across unapproved periods" : "No open settlement periods"}</small></article>
      <article className="coop-kpi"><span>Approved periods</span><strong>{approvedPeriods}</strong><small>Named cooperative sign-off recorded</small></article>
      <article className="coop-kpi"><span>Latest close auto-matched</span><strong>{autoMatchPercent === null ? "—" : `${autoMatchPercent}%`}</strong><small>{latest ? `${latest.reconciled_count}/${latest.member_count} member rows · ${latest.period_start} to ${latest.period_end}` : "No settlement data yet"}</small></article>
      <article className="coop-kpi"><span>Median import-to-sign-off</span><strong>{medianCloseMinutes === null ? "—" : formatCloseDuration(medianCloseMinutes)}</strong><small>{recordedCloseMinutes.length ? `Measured across ${recordedCloseMinutes.length} approved close${recordedCloseMinutes.length === 1 ? "" : "s"}` : "Appears after an approved close"}</small></article>
    </section>

    <section className="card coop-pattern-card"><div><p className="eyebrow">LATEST PERIOD · EXCEPTION PATTERN</p><h2>What the close desk needs to resolve</h2><p>Counts come from source-row and arithmetic checks in the latest imported close.</p></div>{latestIssueReasons.length ? <div className="coop-reason-list">{latestIssueReasons.map(([code, count]) => <span className="coop-reason-chip" key={code}><strong>{Number(count)}</strong>{issueLabels[code] || code.replaceAll("_", " ")}</span>)}</div> : <span className="coop-pattern-empty">{latest ? "No exception patterns in this period" : "Exception patterns appear after your first import"}</span>}<small className="coop-pattern-note">These are deterministic reconciliation checks, not predicted fraud or payment outcomes. Close duration starts at Terravanta import, so it excludes source preparation and work outside the platform. {deliveries.length} consented delivery summaries are available in shared member records.</small></section>

    <div className="coop-dashboard-grid">
      <section className="card coop-next-action">
        <PanelTitle eyebrow="NEXT ACTION" title={!latest ? "Choose a completed period" : unresolvedExceptions ? `Resolve ${unresolvedExceptions} open exception${unresolvedExceptions === 1 ? "" : "s"}` : signoffClose ? "An open close is ready for sign-off" : "Prepare the next payout close"} description={!latest ? "No live metrics are shown before a close is imported." : unresolvedExceptions ? "Open the oldest period with unresolved items, compare each variance with its source rows, and leave a reviewer note. Follow-up items remain unresolved." : signoffClose ? "Check the summary and add an approval note. Approval does not initiate payment." : "When the next period is ready, bring in its three source exports."} />
        <button className="button button-primary" onClick={() => exceptionClose ? openPeriod(exceptionClose.id) : signoffClose ? openPeriod(signoffClose.id) : onNavigate("settlements")}>{!latest ? "Start first close" : unresolvedExceptions ? "Review unresolved items" : signoffClose ? "Review and approve" : "Start next close"}<ArrowRight size={15} /></button>
      </section>
      <section className="card coop-scope-card"><PanelTitle eyebrow="WHAT TERRAVANTA DOES" title="A reviewable close workflow" /><ol className="coop-process"><li><span>01</span><div><strong>Bring three exports</strong><small>Collection, processor settlement and payout</small></div></li><li><span>02</span><div><strong>Compare member totals</strong><small>Volume, arithmetic and payout consistency</small></div></li><li><span>03</span><div><strong>Resolve exceptions</strong><small>Named reviewer, source references and note</small></div></li><li><span>04</span><div><strong>Approve and export</strong><small>Statement pack after sign-off</small></div></li></ol><p className="coop-boundary-note"><ShieldCheck size={16} /> No AI call, ledger write-back or payment execution is part of this workflow.</p></section>
    </div>

    <section className="card coop-recent-card"><div className="coop-section-head"><PanelTitle eyebrow="PERIOD ACTIVITY" title="Recent settlement closes" description="Counts and status are returned from your cooperative records." /><button className="coop-text-button" onClick={() => onNavigate("reports")}>View close history <ArrowRight size={14} /></button></div>{closes.length ? <div className="coop-period-list">{closes.slice(0, 4).map((close: AnyRecord) => <button type="button" className="coop-period-row" key={close.id} onClick={() => openPeriod(close.id)}><span className="coop-period-icon"><FileUp size={16} /></span><span className="coop-period-main"><strong>{close.period_start} <span>to</span> {close.period_end}</strong><small>{close.member_count} members · {close.collection_row_count + close.processor_row_count + close.payout_row_count} source rows</small></span><span className="coop-period-counts"><strong>{close.reconciled_count}/{close.member_count} reconciled</strong><small>{close.unresolved_exception_count ?? close.pending_review_count ?? 0} unresolved exceptions</small></span><StatusPill tone={close.status === "approved" ? "green" : "amber"}>{close.status.replaceAll("_", " ")}</StatusPill><ArrowRight className="coop-period-arrow" size={16} /></button>)}</div> : <Empty title="No settlement close has been run" detail="The dashboard will show period coverage and review workload after your first import." />}</section>
  </div>;
}

function formatCloseDuration(minutes: number) {
  const rounded = Math.round(minutes);
  if (rounded < 60) return `${rounded}m`;
  const hours = Math.floor(rounded / 60);
  const remainingMinutes = rounded % 60;
  if (hours < 24) return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours ? `${days}d ${remainingHours}h` : `${days}d`;
}

function CooperativeCloseHistory({ closes, openClose, onNavigate }: AnyRecord) {
  return <section className="card coop-history-card"><div className="coop-section-head"><PanelTitle eyebrow="AUDITABLE PERIOD ARCHIVE" title="Settlement close history" description="Each row is an imported close with its own source fingerprint and review trail." /><button className="button button-primary" onClick={() => onNavigate("settlements")}><Plus size={15} />New settlement close</button></div>{closes.length ? <div className="coop-period-list">{closes.map((close: AnyRecord) => <button type="button" className="coop-period-row" key={close.id} onClick={() => { onNavigate("settlements"); void openClose(close.id); }}><span className="coop-period-icon"><FileUp size={16} /></span><span className="coop-period-main"><strong>{close.period_start} <span>to</span> {close.period_end}</strong><small>Created {new Date(close.created_at).toLocaleString("en-KE")} · {close.collection_row_count + close.processor_row_count + close.payout_row_count} source rows</small></span><span className="coop-period-counts"><strong>{close.reconciled_count}/{close.member_count} reconciled</strong><small>{close.unresolved_exception_count ?? close.pending_review_count ?? 0} unresolved exceptions</small></span><StatusPill tone={close.status === "approved" ? "green" : "amber"}>{close.status.replaceAll("_", " ")}</StatusPill><ArrowRight className="coop-period-arrow" size={16} /></button>)}</div> : <Empty title="Your close archive is empty" detail="Imported payout periods will appear here with their reconciliation and review status." />}</section>;
}

function CooperativeAccessControls() {
  return <div className="coop-access-grid"><section className="card"><PanelTitle eyebrow="ACCESS BOUNDARY" title="Your cooperative role" description="Terravanta checks cooperative membership on the API before returning settlement or delivery records." /><div className="coop-access-row"><span className="coop-access-icon"><ShieldCheck size={19} /></span><div><strong>Settlement reviewer and approver</strong><small>Your actions are attributed to your signed-in account and recorded in the audit trail.</small></div></div><div className="coop-access-row"><span className="coop-access-icon"><Boxes size={19} /></span><div><strong>Farmer-shared delivery summaries</strong><small>Only active delivery-summary consent is visible in the member records workspace.</small></div></div><div className="coop-access-row"><span className="coop-access-icon"><FileText size={19} /></span><div><strong>Clinical records stay private</strong><small>Animal-health and veterinary case details are excluded from this cooperative portal.</small></div></div></section><section className="card"><PanelTitle eyebrow="DATA HANDLING" title="What this release stores" /><ul className="coop-control-list"><li>Settlement source files are parsed by the API; original file binaries are not retained.</li><li>Member totals, sanitized source references and row numbers remain attached to the close for review.</li><li>AI is not called for financial matching, and the workflow cannot initiate a payment.</li><li>Ask your Terravanta operator for the pilot environment's retention and deletion procedure before importing sensitive records.</li></ul></section></div>;
}

function CooperativeMemberRecordsView({ deliveries, runs, activeRun, busy, importFile, openRun, reviewItem }: {
  deliveries: AnyRecord[];
  runs: AnyRecord[];
  activeRun: AnyRecord | null;
  busy: boolean;
  importFile: (file: File) => void;
  openRun: (id: string) => void;
  reviewItem: (id: string, decision: "confirmed" | "follow_up", note: string) => void;
}) {
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const farmCount = new Set(deliveries.map((row) => row.farm_code)).size;
  const liters = deliveries.filter((row) => row.product_type === "milk" && row.delivery.unit === "L").reduce((sum, row) => sum + row.delivery.quantity, 0);
  const gaps = deliveries.filter((row) => row.documentation_gaps?.length).length;
  const summary = activeRun?.run;
  const items: AnyRecord[] = activeRun?.items || [];
  const statusTone = (status: string) => status === "matched" || status === "confirmed" ? "green" : status === "consent_revoked" || status === "invalid_row" ? "red" : "amber";
  function downloadReconciliation() {
    if (!summary || !items.length) return;
    const blob = new Blob([buildReconciliationCsv(items)], { type: "text/csv;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = `${String(summary.filename || "collection").replace(/\.csv$/i, "").replace(/[^\w.-]+/g, "_")}.reconciled.csv`;
    link.click();
    URL.revokeObjectURL(href);
  }
  return <>
    <div className="stats-grid"><article className="stat-card"><div className="stat-top"><span className="stat-icon green">⌂</span><span className="stat-quiet">farms</span></div><p>Consented farms</p><div className="stat-value">{farmCount}<span> farms</span></div><small>Only active grants</small></article><article className="stat-card"><div className="stat-top"><span className="stat-icon blue">↗</span><span className="stat-quiet">records</span></div><p>Shared deliveries</p><div className="stat-value">{deliveries.length}<span> deliveries</span></div><small>Read-only summaries</small></article><article className="stat-card"><div className="stat-top"><span className="stat-icon earth">◌</span><span className="stat-quiet">litres</span></div><p>Consented milk volume</p><div className="stat-value">{liters.toLocaleString()}<span> L</span></div><small>Sum of shared delivery rows</small></article><article className="stat-card"><div className="stat-top"><span className="stat-icon amber">!</span><span className="stat-quiet">rows</span></div><p>Delivery gaps</p><div className="stat-value">{gaps}<span> rows</span></div><small>Missing reference on shared records</small></article></div>
    <section className="card reconciliation-card">
      <PanelTitle eyebrow="COOPERATIVE RECONCILIATION SERVICE" title="Collection sheet to verified delivery record" description="Upload your daily intake CSV. Terravanta matches rows against farm-consented delivery records, routes exceptions to a reviewer, and preserves the resulting trace." action={<a className="button button-outline" download="terravanta-collection-template.csv" href="data:text/csv;charset=utf-8,farm_code%2Ccollection_date%2Cmilk_litres%2Creceipt_reference%0A"><FileUp size={15} />CSV template</a>} />
      <div className="reconciliation-controls">
        <label className="collection-upload"><Upload size={17} /><span><strong>Import collection CSV</strong><small>Up to 2 MB · 2,000 rows · UTF-8</small></span><input type="file" accept=".csv,text/csv" disabled={busy} onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) importFile(file); event.currentTarget.value = ""; }} /></label>
        <div className="reconciliation-privacy"><ShieldCheck size={17} /><span><strong>Consent-scoped matching</strong><small>Uses delivery summaries shared with this cooperative. No veterinary records or external AI are used.</small></span></div>
      </div>
      {runs.length ? <div className="run-history"><div className="subsection-title"><h3>Recent reconciliation runs</h3></div><div className="run-list">{runs.map((run) => <button className={`run-chip ${summary?.id === run.id ? "selected" : ""}`} key={run.id} onClick={() => openRun(run.id)}><span><strong>{run.filename}</strong><small>{new Date(run.created_at).toLocaleString()} · {run.total_rows} rows</small></span><span className="run-counts"><b>{run.matched_rows} matched</b><small>{run.open_rows} open</small></span></button>)}</div></div> : <div className="reconciliation-empty"><GitBranch size={20} /><div><strong>No intake sheet reconciled yet</strong><small>Start with one exported daily collection sheet to see exact matches and exceptions here.</small></div></div>}
      {summary ? <>
        <div className="reconciliation-summary"><div><span>Rows received</span><strong>{summary.total_rows}</strong></div><div><span>Auto-matched</span><strong>{summary.matched_rows}</strong></div><div><span>Exceptions</span><strong>{summary.exception_rows}</strong></div><div><span>Review complete</span><strong>{summary.resolved_rows}/{summary.total_rows}</strong></div><StatusPill tone={summary.status === "complete" ? "green" : "amber"}>{summary.status.replaceAll("_", " ")}</StatusPill><button className="button button-outline button-small" disabled={!items.length} onClick={downloadReconciliation}><Download size={13} />Download result CSV</button></div>
        <div className="table-scroll reconciliation-table"><table><thead><tr><th>Intake row</th><th>Farm & date</th><th>Submitted</th><th>Recorded delivery</th><th>Match result</th><th>Review</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}>
          <td><strong>#{item.row_number}</strong><small className="cell-sub mono">{item.receipt_reference || "No receipt reference"}</small></td>
          <td><strong>{item.farm_name || item.farm_code || "Not shared"}</strong><small className="cell-sub">{item.collection_date || "Invalid date"}</small></td>
          <td><strong>{item.submitted_quantity || "—"}{item.submitted_quantity ? " L" : ""}</strong><small className="cell-sub">As entered on intake sheet</small></td>
          <td>{item.matched_delivery ? <><strong>{item.matched_delivery.quantity} {item.matched_delivery.unit}</strong><small className="cell-sub">{item.matched_delivery.reference || item.matched_delivery.lot_code} · {item.matched_delivery.date}</small></> : <span className="muted">No consented link</span>}</td>
          <td><StatusPill tone={statusTone(item.status)}>{item.status.replaceAll("_", " ")}</StatusPill>{item.discrepancies?.length ? <small className="cell-sub">{item.discrepancies.join("; ")}</small> : null}</td>
          <td>{item.review_status === "pending" ? <div className="review-actions">{item.matched_delivery ? <button className="button button-outline button-small" disabled={busy} onClick={() => reviewItem(item.id, "confirmed", "")}><Check size={13} />Confirm</button> : null}<input aria-label={`Follow-up note for row ${item.row_number}`} placeholder="Follow-up note (3+ chars)" value={reviewNotes[item.id] || ""} onChange={(event) => setReviewNotes((notes) => ({ ...notes, [item.id]: event.target.value }))} /><button className="button button-outline button-small" disabled={busy || (reviewNotes[item.id] || "").trim().length < 3} onClick={() => reviewItem(item.id, "follow_up", reviewNotes[item.id].trim())}>Log follow-up</button></div> : <><StatusPill tone={item.review_status === "confirmed" || item.review_status === "not_required" ? "green" : "amber"}>{item.review_status.replaceAll("_", " ")}</StatusPill>{item.review_note ? <small className="cell-sub">{item.review_note}</small> : null}</>}</td>
        </tr>)}</tbody></table></div>
        <div className="trace-panel"><div><PanelTitle eyebrow="AUDITABLE TRACE" title="Source-to-intake graph" description="Each row traces from the farm’s consented product lot and delivery to the cooperative intake entry, or to an explicit exception." /></div><div className="trace-items">{items.slice(0, 12).map((item) => <div className="trace-row" key={item.id}><span className="trace-row-label">Row {item.row_number}</span><div className="trace-nodes">{item.trace_graph.map((node: AnyRecord, index: number) => <span className={`trace-node ${node.type}`} key={node.id}>{index ? <ArrowRight size={13} /> : null}<b>{node.label}</b></span>)}</div></div>)}</div></div>
      </> : null}
    </section>
    <section className="card coop-card"><PanelTitle eyebrow="RESTRICTED READ-ONLY PORTAL" title="Farm delivery summaries" description="Only records covered by active farm-owner consent are returned by the API." />{deliveries.length ? <div className="table-scroll"><table><thead><tr><th>Farm</th><th>Product lot</th><th>Delivery date</th><th>Quantity</th><th>Documentation</th><th>Access scope</th></tr></thead><tbody>{deliveries.map((row) => <tr key={row.delivery.id}><td><strong>{row.farm_name}</strong><small className="cell-sub">{row.farm_code} · {row.synthetic ? "synthetic" : "farmer submitted"}</small></td><td className="mono">{row.lot_code}<small className="cell-sub capitalize">{row.product_type}</small></td><td>{row.delivery.delivery_date}</td><td>{row.delivery.quantity} {row.delivery.unit}</td><td>{row.documentation_gaps?.length ? <StatusPill tone="amber">Missing reference</StatusPill> : <StatusPill tone="green">Reference recorded</StatusPill>}</td><td><StatusPill tone="green">{row.scope.replaceAll("_", " ")}</StatusPill></td></tr>)}</tbody></table></div> : <Empty title="No farms have shared records" detail="A farm owner must grant delivery-summary consent before records appear here." />}<div className="provenance-banner"><ShieldCheck size={18} /><p><strong>Private veterinary and quality-test records are excluded.</strong> Revoked consent is removed from future API responses. Reconciliation is deterministic and keeps each reviewer action in the audit trail.</p></div></section>
  </>;
}

function SettlementCloseWorkbench({ closes, activeClose, busy, createClose, openClose, reviewException, approveClose, downloadPack }: {
  closes: AnyRecord[];
  activeClose: AnyRecord | null;
  busy: boolean;
  createClose: (form: FormData) => void;
  openClose: (id: string) => void;
  reviewException: (closeId: string, itemId: string, decision: "accept_with_note" | "follow_up", note: string) => void;
  approveClose: (closeId: string, note: string) => void;
  downloadPack: (closeId: string) => void;
}) {
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [approvalNote, setApprovalNote] = useState("");
  const now = new Date();
  const periodStartDefault = localDateString(new Date(now.getFullYear(), now.getMonth(), 1));
  const close = activeClose?.close;
  const items: AnyRecord[] = activeClose?.items || [];
  const unresolvedExceptionCount = items.filter((item) => item.status !== "reconciled" && item.review_status !== "accepted_with_note").length;
  function submitClose(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const payload = new FormData();
    payload.set("period_start", String(values.get("period_start") || ""));
    payload.set("period_end", String(values.get("period_end") || ""));
    for (const key of ["collection_file", "processor_file", "payout_file"]) {
      const file = values.get(key);
      if (file instanceof File) payload.set(key, file);
    }
    createClose(payload);
  }
  const linkTemplate = (name: string, headers: string) => <a className="text-link" download={name} href={`data:text/csv;charset=utf-8,${encodeURIComponent(`${headers}\n`)}`}>Download template</a>;
  return <section className="card reconciliation-card settlement-workbench">
    <PanelTitle eyebrow="SETTLEMENT ASSURANCE · REVIEWABLE AUTOMATION" title="Close the milk payout period" description="Reconcile existing collection, processor settlement and payout exports. Exact arithmetic is automated; exceptions require a named cooperative reviewer before the close can be approved." />
    <form className="settlement-import" onSubmit={submitClose}>
      <div className="settlement-period"><Field label="Period start" name="period_start" type="date" defaultValue={periodStartDefault} /><Field label="Period end" name="period_end" type="date" defaultValue={dateInput()} /></div>
      <div className="settlement-files">
        <label className="settlement-file"><span><strong>1 · Collection export</strong><small>member_code, delivery_date, quantity_liters, receipt_reference</small>{linkTemplate("terravanta-collection-close-template.csv", "member_code,delivery_date,quantity_liters,receipt_reference")}</span><input name="collection_file" type="file" accept=".csv,text/csv" required disabled={busy} /></label>
        <label className="settlement-file"><span><strong>2 · Processor settlement export</strong><small>member_code, settlement_date, accepted_liters, gross_amount_kes, deductions_kes, net_amount_kes, settlement_reference</small>{linkTemplate("terravanta-processor-settlement-template.csv", "member_code,settlement_date,accepted_liters,gross_amount_kes,deductions_kes,net_amount_kes,settlement_reference")}</span><input name="processor_file" type="file" accept=".csv,text/csv" required disabled={busy} /></label>
        <label className="settlement-file"><span><strong>3 · Farmer payout export</strong><small>member_code, payout_date, amount_kes, payout_reference</small>{linkTemplate("terravanta-payout-template.csv", "member_code,payout_date,amount_kes,payout_reference")}</span><input name="payout_file" type="file" accept=".csv,text/csv" required disabled={busy} /></label>
      </div>
      <button className="button button-primary" disabled={busy}><GitBranch size={15} />{busy ? "Reconciling exports…" : "Reconcile payout period"}</button>
    </form>
    <div className="reconciliation-privacy"><ShieldCheck size={17} /><span><strong>Evidence-first, model-independent processing</strong><small>CSV files stay in the API workflow. Matching uses member code, period, litres and amount arithmetic; no NVIDIA request, payment instruction or source-record edit is made. Each input file is SHA-256 fingerprinted to prevent duplicate imports.</small></span></div>
    {closes.length ? <div className="run-history"><div className="subsection-title"><h3>Recent settlement closes</h3></div><div className="run-list">{closes.map((row) => <button className={`run-chip ${close?.id === row.id ? "selected" : ""}`} key={row.id} type="button" onClick={() => openClose(row.id)}><span><strong>{row.period_start} – {row.period_end}</strong><small>{row.member_count} members · {row.collection_row_count + row.processor_row_count + row.payout_row_count} source rows</small></span><span className="run-counts"><b>{row.reconciled_count} reconciled</b><small>{row.unresolved_exception_count ?? row.pending_review_count ?? 0} unresolved</small></span></button>)}</div></div> : null}
    {close ? <>
      <div className="reconciliation-summary"><div><span>Member records</span><strong>{close.member_count}</strong></div><div><span>Auto-reconciled</span><strong>{close.reconciled_count}</strong></div><div><span>Exceptions</span><strong>{close.exception_count}</strong></div><div><span>Still unresolved</span><strong>{close.unresolved_exception_count ?? unresolvedExceptionCount}</strong></div><StatusPill tone={close.status === "approved" ? "green" : unresolvedExceptionCount ? "amber" : "green"}>{close.status.replaceAll("_", " ")}</StatusPill></div>
      <div className="table-scroll reconciliation-table"><table><thead><tr><th>Member</th><th>Collection / processor</th><th>Volume variance</th><th>Gross · deductions · net</th><th>Paid · variance</th><th>Reconciliation</th><th>Reviewer action</th></tr></thead><tbody>{items.map((item) => {
        const note = reviewNotes[item.id] || "";
        const reviewOpen = item.review_status !== "accepted_with_note";
        return <tr key={item.id}>
          <td><strong>{item.member_code}</strong><small className="cell-sub">Collection rows {item.source_rows?.collection?.join(", ") || "—"} · processor {item.source_rows?.processor?.join(", ") || "—"} · payout {item.source_rows?.payout?.join(", ") || "—"}</small></td>
          <td>{Number(item.collection_liters).toLocaleString()} L <ArrowRight size={12} /> {Number(item.processor_liters).toLocaleString()} L</td>
          <td><strong>{Number(item.volume_variance_liters).toFixed(1)} L</strong></td>
          <td>{Number(item.gross_amount_kes).toLocaleString()} · {Number(item.deductions_kes).toLocaleString()} · <strong>{Number(item.net_amount_kes).toLocaleString()} KES</strong><small className="cell-sub">Processor arithmetic variance: {Number(item.processor_arithmetic_variance_kes).toFixed(2)} KES</small></td>
          <td>{Number(item.payout_amount_kes).toLocaleString()} KES<small className="cell-sub">Variance to net: {Number(item.payout_variance_kes).toFixed(2)} KES</small></td>
          <td><StatusPill tone={item.status === "reconciled" ? "green" : "amber"}>{item.status.replaceAll("_", " ")}</StatusPill>{item.issues?.length ? <small className="cell-sub">{item.issues.map((issue: string) => issue.replaceAll("_", " ")).join(" · ")}</small> : null}</td>
          <td>{item.status === "reconciled" ? <StatusPill tone="green">Automatic match</StatusPill> : <div className="review-actions"><StatusPill tone={item.review_status === "accepted_with_note" ? "green" : "amber"}>{item.review_status.replaceAll("_", " ")}</StatusPill>{reviewOpen ? <><input aria-label={`Reviewer note for ${item.member_code}`} placeholder="Explain decision (3+ chars)" value={note} onChange={(event) => setReviewNotes((all) => ({ ...all, [item.id]: event.target.value }))} /><button type="button" className="button button-outline button-small" disabled={busy || note.trim().length < 3} onClick={() => reviewException(close.id, item.id, "accept_with_note", note.trim())}>Accept with note</button><button type="button" className="button button-outline button-small" disabled={busy || note.trim().length < 3} onClick={() => reviewException(close.id, item.id, "follow_up", note.trim())}>Record follow-up</button></> : <small className="cell-sub">{item.review_note}</small>}</div>}</td>
        </tr>;
      })}</tbody></table></div>
      <div className="settlement-approval"><div><strong>{close.status === "approved" ? "Close approved by a named cooperative user" : unresolvedExceptionCount ? `${unresolvedExceptionCount} exception${unresolvedExceptionCount === 1 ? "" : "s"} must be resolved first` : "Close is ready for cooperative sign-off"}</strong><small>{close.status === "approved" ? `Approval note: ${close.approval_note}` : "Approval records accountability; it does not authorize or execute a bank or mobile-money payment."}</small></div>{close.status === "approved" ? <button type="button" className="button button-primary" onClick={() => downloadPack(close.id)}><Download size={15} />Download farmer statement pack</button> : <div className="settlement-approve-controls"><input aria-label="Close approval note" placeholder="Close approval note (5+ chars)" value={approvalNote} onChange={(event) => setApprovalNote(event.target.value)} /><button type="button" className="button button-primary" disabled={busy || unresolvedExceptionCount > 0 || approvalNote.trim().length < 5} onClick={() => approveClose(close.id, approvalNote.trim())}><Check size={15} />Approve settlement close</button></div>}</div>
      <small className="map-caption">Source files: {close.collection_filename}, {close.processor_filename}, {close.payout_filename}. Hashes: {Object.values(close.source_hashes || {}).map((hash: any) => String(hash).slice(0, 12)).join(" · ")}. A statement pack is an export for cooperative review and delivery; it is not proof that a bank transfer completed.</small>
    </> : <div className="reconciliation-empty"><GitBranch size={20} /><div><strong>No payout period closed yet</strong><small>Import the three exports already used in your operation to reconcile volumes, processor arithmetic and payouts.</small></div></div>}
  </section>;
}
