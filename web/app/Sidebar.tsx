"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { API } from "@/lib/api";

type Item = { href: string; label: string; ico: string };

const GROUPS: { label: string; items: Item[] }[] = [
  {
    label: "Situation",
    items: [
      { href: "/", label: "Overview", ico: "◱" },
      { href: "/forecast", label: "Forecast", ico: "◷" },
      { href: "/risk", label: "Risk & exposure", ico: "◈" },
      { href: "/evacuation", label: "Evacuation", ico: "⤳" },
    ],
  },
  {
    label: "Response",
    items: [
      { href: "/alerts", label: "Alerts", ico: "◉" },
      { href: "/sms", label: "Send SMS", ico: "✉" },
      { href: "/reports", label: "Citizen reports", ico: "◍" },
      { href: "/command", label: "Command", ico: "▦" },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/simulator", label: "Simulator", ico: "⚙" },
      { href: "/offline", label: "Offline", ico: "⊘" },
    ],
  },
];

export default function Sidebar({
  collapsed, onToggle,
}: { collapsed: boolean; onToggle: () => void }) {
  const path = usePathname();
  const [alerts, setAlerts] = useState(0);

  useEffect(() => {
    const pull = () =>
      fetch(`${API}/alerts?limit=1`).then((r) => r.json())
        .then((d) => setAlerts(d.count ?? 0)).catch(() => {});
    pull();
    const id = setInterval(pull, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">▲</span>
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
              return (
                <Link key={it.href} href={it.href} className={`nav-item${on ? " on" : ""}`}
                      title={collapsed ? it.label : undefined}>
                  <span className="nav-ico">{it.ico}</span>
                  <span className="nav-text">{it.label}</span>
                  {it.href === "/alerts" && alerts > 0 && (
                    <span className="nav-badge">{alerts > 99 ? "99+" : alerts}</span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-foot">
        <button className="collapse-btn" onClick={onToggle}>
          {collapsed ? "»" : "« Collapse"}
        </button>
      </div>
    </aside>
  );
}
