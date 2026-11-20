"use client";

import { Activity, BarChart3, Boxes, ClipboardList, FileText, Inbox, LayoutDashboard, Leaf, LockKeyhole, ReceiptText, Settings2, ShieldCheck, Stethoscope, Tractor, Wheat } from "lucide-react";

export type Section = "overview" | "farms" | "veterinary" | "crops" | "feed" | "production" | "traceability" | "assistant" | "settlements" | "receivables" | "reports" | "settings";
const farmerNavigation: { id: Section; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard }, { id: "farms", label: "Farms", icon: Tractor },
  { id: "veterinary", label: "Veterinary", icon: Stethoscope }, { id: "crops", label: "Crops & plots", icon: Leaf },
  { id: "feed", label: "Feed & nutrition", icon: Wheat }, { id: "production", label: "Production", icon: Activity },
  { id: "traceability", label: "Traceability & sharing", icon: Boxes }, { id: "assistant", label: "Veterinary assistant", icon: ClipboardList },
  { id: "reports", label: "Reports", icon: BarChart3 }, { id: "settings", label: "Settings", icon: Settings2 },
];
const veterinarianNavigation: { id: Section; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Case desk", icon: LayoutDashboard }, { id: "veterinary", label: "Assigned cases", icon: Stethoscope },
  { id: "assistant", label: "Case assistant", icon: ClipboardList }, { id: "settings", label: "Settings", icon: Settings2 },
];
const cooperativeNavigation: { id: Section; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Close desk", icon: LayoutDashboard }, { id: "settlements", label: "Payout settlements", icon: ClipboardList },
  { id: "receivables", label: "Processor receivables", icon: ReceiptText },
  { id: "traceability", label: "Shared member records", icon: Boxes }, { id: "reports", label: "Close history", icon: FileText },
  { id: "settings", label: "Access & controls", icon: Settings2 },
];
const processorNavigation: { id: Section; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "receivables", label: "Supplier claim inbox", icon: Inbox },
  { id: "settings", label: "Access & controls", icon: Settings2 },
];

export function Sidebar({ active, onChange, role, userName, farmName = "Farm workspace", location = "Location pending", workCount = 0 }: { active: Section; onChange: (section: Section) => void; role: string; userName?: string; farmName?: string; location?: string; workCount?: number }) {
  const accountName = userName || "Signed-in user";
  const initials = accountName.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "TV";
  const navigation = role === "cooperative_admin" ? cooperativeNavigation : role === "processor_admin" ? processorNavigation : role === "veterinarian" ? veterinarianNavigation : farmerNavigation;
  const primaryNavigation = role === "farmer" ? navigation.slice(0, 1) : navigation;
  const remainingNavigation = role === "farmer" ? navigation.slice(1) : [];
  const integrity = role === "cooperative_admin"
    ? { title: "Close actions are auditable", note: "Approvals stay with your team" }
    : role === "processor_admin"
      ? { title: "Responses are attributable", note: "Processor decisions stay on the record" }
      : role === "veterinarian"
      ? { title: "Clinical review stays human", note: "Sign only records you review" }
      : { title: "Organization access is assigned", note: "Co-op and processor menus need staff access" };
  const navigationLabel = role === "cooperative_admin" ? "PAYOUT & CLAIMS" : role === "processor_admin" ? "ACCOUNTS PAYABLE" : role === "veterinarian" ? "CASEWORK" : "FARMER WORKSPACE";
  return <aside className="sidebar">
    <a className="brand" href="#overview" onClick={(event) => { event.preventDefault(); onChange("overview"); }} aria-label="Terravanta overview">
      <span className="brand-mark"><Leaf size={20} /></span><span>terravanta<small>FARM INTELLIGENCE</small></span>
    </a>
    <div className="farm-switcher"><span className="farm-avatar">TV</span><div><strong>{farmName}</strong><small>{location}</small></div><span className="chevron">⌄</span></div>
    <p className="nav-label">{navigationLabel}</p>
    <nav aria-label="Main navigation" className="nav-list">
      {primaryNavigation.map(({ id, label, icon: Icon }) => <button type="button" key={id} onClick={() => onChange(id)} className={`nav-item ${active === id ? "active" : ""}`} aria-current={active === id ? "page" : undefined}>
        <Icon size={18} strokeWidth={1.8} /><span>{label}</span>{workCount > 0 && ((role === "cooperative_admin" && id === "settlements") || (role === "veterinarian" && id === "overview")) ? <em className="nav-count">{workCount > 99 ? "99+" : workCount}</em> : null}
      </button>)}
    </nav>
    {role === "farmer" ? <>
      <p className="nav-label organization-nav-label">ORGANIZATION WORKSPACES</p>
      <nav aria-label="Organization workspaces" className="nav-list">
        <button type="button" className="nav-item nav-item-locked" title="Cooperative access requires a cooperative administrator role. Open Settings for access details." onClick={() => onChange("settings")}><Boxes size={18} strokeWidth={1.8} /><span>Cooperative settlements</span><LockKeyhole size={14} /></button>
        <button type="button" className="nav-item nav-item-locked" title="Processor access requires a processor administrator role. Open Settings for access details." onClick={() => onChange("settings")}><ReceiptText size={18} strokeWidth={1.8} /><span>Processor receivables</span><LockKeyhole size={14} /></button>
      </nav>
    </> : null}
    {remainingNavigation.length ? <>
      <p className="nav-label farmer-management-label">FARM RECORDS</p>
      <nav aria-label="Farm management" className="nav-list farmer-management-nav">
      {remainingNavigation.map(({ id, label, icon: Icon }) => <button type="button" key={id} onClick={() => onChange(id)} className={`nav-item ${active === id ? "active" : ""}`} aria-current={active === id ? "page" : undefined}>
        <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
      </button>)}
      </nav>
    </> : null}
    <div className="sidebar-bottom"><div className="integrity-note"><ShieldCheck size={17} /><div><strong>{integrity.title}</strong><small>{integrity.note}</small></div></div><div className="profile"><div className="profile-avatar">{initials}</div><div><strong>{accountName}</strong><small>{role.replaceAll("_", " ")}</small></div><button type="button" aria-label="Open workspace settings" className="profile-more" onClick={() => onChange("settings")}>···</button></div></div>
  </aside>;
}
