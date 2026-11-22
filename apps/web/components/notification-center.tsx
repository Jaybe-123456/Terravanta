"use client";

import { useCallback, useEffect, useState } from "react";
import { Bell, Check, ChevronRight, LoaderCircle, X } from "lucide-react";
import { api } from "@/lib/api";
import type { Section } from "@/components/sidebar";

type InboxItem = {
  id: string;
  type: string;
  title: string;
  body: string;
  severity: "info" | "medium" | "high";
  action_section: string;
  created_at: string;
  read_at: string | null;
};

type InboxResponse = { items: InboxItem[]; unread_count: number };
const sections = new Set<Section>(["overview", "farms", "veterinary", "crops", "feed", "production", "traceability", "assistant", "settlements", "receivables", "reports", "settings"]);

function relativeTime(value: string): string {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (Math.abs(seconds) < 60) return formatter.format(seconds, "second");
  if (Math.abs(seconds) < 3600) return formatter.format(Math.round(seconds / 60), "minute");
  if (Math.abs(seconds) < 86400) return formatter.format(Math.round(seconds / 3600), "hour");
  return formatter.format(Math.round(seconds / 86400), "day");
}

export function NotificationCenter({ token, onNavigate }: { token: string; onNavigate: (section: Section) => void }) {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const result = await api<InboxResponse>("/api/v1/notifications?limit=30", token);
      setItems(result.items || []);
      setUnreadCount(result.unread_count || 0);
    } catch {
      // Inbox delivery should not block ordinary farm record workflows.
    }
  }, [token]);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), 45_000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  async function openItem(item: InboxItem) {
    setLoading(true);
    if (!item.read_at) {
      try {
        const updated = await api<InboxItem>(`/api/v1/notifications/${item.id}/read`, token, { method: "PATCH" });
        setItems((current) => current.map((entry) => entry.id === item.id ? updated : entry));
        setUnreadCount((count) => Math.max(0, count - 1));
      } catch {
        // Navigation still works if the read receipt cannot be saved.
      }
    }
    setOpen(false);
    if (sections.has(item.action_section as Section)) onNavigate(item.action_section as Section);
    setLoading(false);
  }

  return <div className="notification-center">
    <button className={`icon-button notification-trigger ${open ? "active" : ""}`} type="button" aria-label={unreadCount ? `Notifications, ${unreadCount} unread` : "Notifications"} aria-expanded={open} aria-controls="notification-inbox" onClick={() => setOpen((value) => !value)}>
      <Bell size={17} />{unreadCount > 0 ? <span className="notification-count">{unreadCount > 99 ? "99+" : unreadCount}</span> : null}
    </button>
    {open ? <section className="notification-popover" id="notification-inbox" aria-label="Notification inbox">
      <header className="notification-popover-header"><div><strong>Farm activity</strong><small>{unreadCount ? `${unreadCount} unread` : "You’re up to date"}</small></div><button type="button" className="notification-close" aria-label="Close notifications" onClick={() => setOpen(false)}><X size={15} /></button></header>
      {loading ? <div className="notification-loading"><LoaderCircle size={15} className="spinner" />Opening task…</div> : null}
      {items.length ? <div className="notification-list">{items.map((item) => <button className={`notification-item ${item.read_at ? "read" : "unread"}`} type="button" key={item.id} onClick={() => void openItem(item)}>
        <span className={`notification-severity ${item.severity}`} aria-hidden="true" />
        <span className="notification-copy"><strong>{item.title}</strong><span>{item.body}</span><small>{relativeTime(item.created_at)}</small></span>
        <ChevronRight size={15} className="notification-chevron" />
      </button>)}</div> : <div className="notification-empty"><span><Check size={17} /></span><strong>No notifications yet</strong><p>Important farm follow-ups and workflow updates will appear here.</p></div>}
      <footer className="notification-popover-footer">Notifications are private to your account and linked farm access.</footer>
    </section> : null}
  </div>;
}
