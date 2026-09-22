"use client";

import { useWorldState } from "@/lib/useWorldState";

const STATUS_TEXT: Record<string, string> = {
  connecting: "Connecting…",
  live: "Live",
  stale: "Stale — showing last known",
  offline: "Offline — showing last known",
};

export default function Home() {
  const { state, status, ageMs } = useWorldState();
  const stage = state ? Object.values(state.stages)[0] : undefined;

  return (
    <main className="wrap">
      <h1>The Sentinel</h1>
      <p className="sub">Flood early-warning and response · Visakhapatnam</p>

      <span className="pill">
        <span className={`dot ${status}`} />
        {STATUS_TEXT[status]}
        {ageMs !== null && status !== "live" && (
          <span style={{ color: "var(--muted)" }}>· {Math.round(ageMs / 1000)}s ago</span>
        )}
      </span>

      <div className="grid">
        <div className="card">
          <div className="label">World clock</div>
          <div className="value" style={{ fontSize: 20 }}>
            {state ? new Date(state.t).toLocaleTimeString() : "—"}
          </div>
          <div className="label" style={{ marginTop: 8 }}>
            tick {state?.tick ?? "—"} · {state?.mode ?? "—"}
          </div>
        </div>

        <div className="card">
          <div className="label">Rainfall</div>
          <div className="value">
            {state ? state.rainfall_mm_hr.toFixed(1) : "—"}
            <span className="unit">mm/hr</span>
          </div>
          <div className="bar">
            <i style={{ width: `${Math.min(100, ((state?.rainfall_mm_hr ?? 0) / 60) * 100)}%` }} />
          </div>
        </div>

        <div className="card">
          <div className="label">Gauge stage</div>
          <div className="value">
            {stage !== undefined ? stage.toFixed(0) : "—"}
            <span className="unit">cm</span>
          </div>
          <div className="bar">
            <i style={{ width: `${Math.min(100, ((stage ?? 0) / 200) * 100)}%` }} />
          </div>
        </div>
      </div>

      <footer>
        <strong>Step 1 — the spine.</strong> Synthetic adapter driving a linear reservoir.
        Kill the API with <code>docker compose stop api</code>: this page holds its last
        value and the pill turns amber, then grey. Restart it and the stream reconnects
        on its own. That is the offline ladder, working from day one.
      </footer>
    </main>
  );
}
