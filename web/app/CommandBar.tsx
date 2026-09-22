"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { API } from "@/lib/api";
import { applyTheme, getTheme } from "@/lib/theme";

type Action = { id: string; label: string; hint?: string; group: string; run: () => void };

export default function CommandBar() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const post = (path: string, body: unknown) =>
    fetch(`${API}${path}`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => {});

  const actions: Action[] = useMemo(() => {
    const go = (href: string, label: string) => ({
      id: `go${href}`, label, group: "Go to", hint: href,
      run: () => router.push(href),
    });
    return [
      go("/", "Overview"), go("/forecast", "Forecast"),
      go("/risk", "Risk & exposure"),
      go("/alerts", "Alerts"), go("/sms", "Send SMS"),
      go("/reports", "Citizen reports"), go("/command", "Command"),
      go("/offline", "Offline"),
      { id: "cloudburst", label: "Cloudburst — 140 mm/hr", group: "Scenario", hint: "C",
        run: () => post("/sim/control", { mode: "scenario", rain_mm_hr: 140 }) },
      { id: "heavy", label: "Heavy rain — 60 mm/hr", group: "Scenario",
        run: () => post("/sim/control", { mode: "scenario", rain_mm_hr: 60 }) },
      { id: "calm", label: "Calm — stop the rain", group: "Scenario",
        run: () => post("/sim/control", { rain_mm_hr: 0 }) },
      { id: "reset", label: "Reset demo to a clean state", group: "Scenario", hint: "R",
        run: () => post("/demo/reset", {}) },
      { id: "pause", label: "Pause the world clock", group: "Scenario",
        run: () => post("/sim/control", { playing: false }) },
      { id: "play", label: "Resume the world clock", group: "Scenario",
        run: () => post("/sim/control", { playing: true }) },
      { id: "theme", label: "Toggle light / dark theme", group: "View", hint: "T",
        run: () => applyTheme(getTheme() === "dark" ? "light" : "dark") },
    ];
  }, [router]);

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return actions;
    return actions.filter((a) =>
      (a.label + a.group).toLowerCase().includes(t));
  }, [q, actions]);

  useEffect(() => { setSel(0); }, [q]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(
        (e.target as HTMLElement)?.tagName ?? "");

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); setOpen((o) => !o); return;
      }
      if (e.key === "Escape") { setOpen(false); return; }
      if (typing) return;

      // Single-key demo shortcuts, only when not typing and the bar is shut.
      if (!open) {
        if (e.key.toLowerCase() === "c") post("/sim/control", { mode: "scenario", rain_mm_hr: 140 });
        if (e.key.toLowerCase() === "r") post("/demo/reset", {});
        if (e.key.toLowerCase() === "t") applyTheme(getTheme() === "dark" ? "light" : "dark");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 30); }, [open]);

  if (!open) return null;

  const fire = (a: Action) => { a.run(); setOpen(false); setQ(""); };

  let lastGroup = "";
  return (
    <div className="cmd-backdrop" onClick={() => setOpen(false)}>
      <div className="cmd" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef} className="cmd-input" value={q} placeholder="Type a page or action…"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, shown.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
            if (e.key === "Enter" && shown[sel]) { e.preventDefault(); fire(shown[sel]); }
          }}
        />
        <div className="cmd-list">
          {shown.length === 0 && <div className="cmd-empty">No matches</div>}
          {shown.map((a, i) => {
            const head = a.group !== lastGroup ? (lastGroup = a.group) : null;
            return (
              <div key={a.id}>
                {head && <div className="cmd-group">{head}</div>}
                <button className={`cmd-item${i === sel ? " on" : ""}`}
                        onMouseEnter={() => setSel(i)} onClick={() => fire(a)}>
                  <span>{a.label}</span>
                  {a.hint && <kbd>{a.hint}</kbd>}
                </button>
              </div>
            );
          })}
        </div>
        <div className="cmd-foot">
          <kbd>↑</kbd><kbd>↓</kbd> move · <kbd>↵</kbd> run · <kbd>esc</kbd> close
          <span className="spacer" />
          <span className="muted">C cloudburst · R reset · T theme</span>
        </div>
      </div>
    </div>
  );
}
