"use client";

import { Activity, BarChart3, Boxes, ClipboardList, FileText, LayoutDashboard, Leaf, Settings2, ShieldCheck, Stethoscope, Tractor, Wheat } from "lucide-react";

export type Section = "overview" | "farms" | "veterinary" | "crops" | "feed" | "production" | "traceability" | "assistant" | "reports" | "settings";
const navigation: { id: Section; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard }, { id: "farms", label: "Farms", icon: Tractor },
  { id: "veterinary", label: "Veterinary", icon: Stethoscope }, { id: "crops", label: "Crops & plots", icon: Leaf },
  { id: "feed", label: "Feed & nutrition", icon: Wheat }, { id: "production", label: "Production", icon: Activity },
  { id: "traceability", label: "Traceability", icon: Boxes }, { id: "assistant", label: "AI assistant", icon: ClipboardList },
  { id: "reports", label: "Reports", icon: BarChart3 }, { id: "settings", label: "Settings", icon: Settings2 },
];

export function Sidebar({ active, onChange, role, userName, farmName = "Farm workspace", location = "Location pending" }: { active: Section; onChange: (section: Section) => void; role: string; userName?: string; farmName?: string; location?: string }) {
  const accountName = userName || "Signed-in user";
  const initials = accountName.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "TV";
  return <aside className="sidebar">
    <a className="brand" href="#overview" onClick={(event) => { event.preventDefault(); onChange("overview"); }} aria-label="Terravanta overview">
      <span className="brand-mark"><Leaf size={20} /></span><span>terravanta<small>FARM INTELLIGENCE</small></span>
    </a>
    <div className="farm-switcher"><span className="farm-avatar">TV</span><div><strong>{farmName}</strong><small>{location}</small></div><span className="chevron">⌄</span></div>
    <p className="nav-label">WORKSPACE</p>
    <nav aria-label="Main navigation" className="nav-list">
      {navigation.map(({ id, label, icon: Icon }) => <button type="button" key={id} onClick={() => onChange(id)} className={`nav-item ${active === id ? "active" : ""}`} aria-current={active === id ? "page" : undefined}>
        <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
      </button>)}
    </nav>
    <div className="sidebar-bottom"><div className="integrity-note"><ShieldCheck size={17} /><div><strong>Farm records protected</strong><small>Sharing is consent controlled</small></div></div><div className="profile"><div className="profile-avatar">{initials}</div><div><strong>{accountName}</strong><small>{role.replaceAll("_", " ")}</small></div><button aria-label="Account options" className="profile-more">···</button></div></div>
  </aside>;
}
