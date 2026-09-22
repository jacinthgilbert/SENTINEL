"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { API } from "@/lib/api";
import { applyTheme, getTheme, type Theme } from "@/lib/theme";

type Item = { href: string; label: string; ico: string; badge?: keyof Badges };
type Badges = {
  escalating: number; stranded: number; alerts: number;
  reports: number; pending: number;
};

const GROUPS: { label: string; items: Item[] }[] = [
  {
    label: "Situation",
    items: [
      { href: "/", label: "Overview", ico: "◱" },
      { href: "/forecast", label: "Forecast", ico: "◷" },
      { href: "/risk", label: "Risk & exposure", ico: "◈", badge: "escalating" },
      { href: "/evacuation", label: "Evacuation", ico: "⤳", badge: "stranded" },
    ],
  },
  {
    label: "Response",
    items: [
      { href: "/alerts", label: "Alerts", ico: "◉", badge: "alerts" },
      { href: "/sms", label: "Send SMS", ico: "✉" },
      { href: "/reports", label: "Citizen reports", ico: "◍", badge: "reports" },
      { href: "/command", label: "Command", ico: "▦" },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/simulator", label: "Simulator", ico: "⚙" },
      { href: "/offline", label: "Offline", ico: "⊘", badge: "pending" },
    ],
  },
];

const ZERO: Badges = { escalating: 0, stranded: 0, alerts: 0, reports: 0, pending: 0 };

export default function Sidebar({
  collapsed, onToggle,
}: { collapsed: boolean; onToggle: () => void }) {
  const path = usePathname();
  const [b, setB] = useState<Badges>(ZERO);
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => { setTheme(getTheme()); }, []);

  useEffect(() => {
    let alive = true;
    const pull = async () => {
      try {
        // One call covers most of the nav; /situation is a consistent snapshot.
        const s = await fetch(`${API}/situation`).then((r) => r.json());
        if (!alive) return;
        setB((prev) => ({
          ...prev,
          escalating: s.risk?.zones_escalating ?? 0,
          stranded: s.routing?.stranded ?? 0,
          alerts: s.alerts?.total ?? 0,
          reports: s.reports?.verified ?? 0,
        }));
      } catch { /* offline — keep the last numbers */ }
      try {
        const { pendingCount } = await import("@/lib/offline");
        const n = await pendingCount();
        if (alive) setB((prev) => ({ ...prev, pending: n }));
      } catch { /* ignore */ }
    };
    pull();
    const id = setInterval(pull, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const flip = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
  };

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/sentinel-mark.png" alt="" />
        </span>
        <span className="brand-text">
          <div className="brand-name">SENTINEL</div>
          <div className="brand-sub">Visakhapatnam</div>
        </span>
      </div>

      <nav className="nav">
        {GROUPS.map((g) => (
          <div className="nav-group" key={g.label}>
            <div className="nav-label">{g.label}</div>
            {g.items.map((it) => {
              const on = it.href === "/" ? path === "/" : path.startsWith(it.href);
              const n = it.badge ? b[it.badge] : 0;
              return (
                <Link key={it.href} href={it.href} className={`nav-item${on ? " on" : ""}`}
                      title={collapsed ? it.label : undefined}>
                  <span className="nav-ico">{it.ico}</span>
                  <span className="nav-text">{it.label}</span>
                  {n > 0 && (
                    <span className={`nav-badge${it.badge === "stranded" ? " danger" : ""}`}>
                      {n > 99 ? "99+" : n}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-foot">
        <div className="theme-row">
          <div className="seg">
            <button className={theme === "dark" ? "on" : ""}
                    onClick={() => theme !== "dark" && flip()} title="Dark">
              ☾<span> Dark</span>
            </button>
            <button className={theme === "light" ? "on" : ""}
                    onClick={() => theme !== "light" && flip()} title="Light">
              ☀<span> Light</span>
            </button>
          </div>
        </div>
        <button className="collapse-btn" onClick={onToggle}>
          {collapsed ? "»" : "« Collapse"}
        </button>
      </div>
    </aside>
  );
}
