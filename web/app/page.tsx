"use client";

import dynamic from "next/dynamic";
import SimConsole from "./SimConsole";
import { useWorldState } from "@/lib/useWorldState";

// Leaflet touches window on import, so it cannot server-render.
const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => <div className="map map-skeleton">loading map…</div>,
});

const STATUS_TEXT: Record<string, string> = {
  connecting: "Connecting…",
  live: "Live",
  stale: "Stale — showing last known",
  offline: "Offline — showing last known",
};

export default function Home() {
  const { state, status, ageMs } = useWorldState();
  const gauge = state ? Object.values(state.stages)[0] ?? null : null;

  return (
    <main className="wrap wide">
      <header className="head">
        <div>
          <h1>The Sentinel</h1>
          <p className="sub">Flood early-warning and response · Visakhapatnam</p>
        </div>
        <span className="pill">
          {state?.mode === "scenario" && <span className="badge">SCENARIO</span>}
          <span className={`dot ${status}`} />
          {STATUS_TEXT[status]}
          {ageMs !== null && status !== "live" && (
            <span style={{ color: "var(--muted)" }}>· {Math.round(ageMs / 1000)}s</span>
          )}
        </span>
      </header>

      <div className="grid">
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
            {gauge !== null ? gauge.toFixed(0) : "—"}
            <span className="unit">cm</span>
          </div>
          <div className="bar">
            <i style={{ width: `${Math.min(100, ((gauge ?? 0) / 200) * 100)}%` }} />
          </div>
        </div>
        <div className="card">
          <div className="label">World clock</div>
          <div className="value" style={{ fontSize: 20 }}>
            {state ? new Date(state.t).toLocaleTimeString() : "—"}
          </div>
          <div className="label" style={{ marginTop: 8 }}>
            tick {state?.tick ?? "—"} · {state?.mode ?? "—"}
          </div>
        </div>
      </div>

      <SimConsole tick={state?.tick ?? null} />

      <MapView gaugeCm={gauge} />

      <footer>
        <strong>Step 4 — digital twin.</strong> Live and Scenario run the identical
        pipeline; only the source of <code>rainfall_mm_hr</code> differs. Drive the
        rain and the reservoir, HAND threshold, extent and zone shading all follow —
        the same code path that a real gauge would drive.
      </footer>
    </main>
  );
}
