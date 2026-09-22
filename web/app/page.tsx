"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import PageHead from "./PageHead";
import SimConsole from "./SimConsole";
import { useWorldState } from "@/lib/useWorldState";

const MapView = dynamic(() => import("./MapView"), {
  ssr: false, loading: () => <div className="map map-skeleton">loading map…</div>,
});

export default function Overview() {
  const { state } = useWorldState();
  const [reportMode] = useState(false);
  const gauge = state ? Object.values(state.stages)[0] ?? null : null;

  return (
    <>
      <PageHead title="Overview" sub="Live flood picture for Visakhapatnam" />

      <div className="grid-3">
        <div className="stat">
          <div className="stat-l">Rainfall</div>
          <div className="stat-n">{state ? state.rainfall_mm_hr.toFixed(1) : "—"}<span className="unit">mm/hr</span></div>
          <div className="bar"><i style={{ width: `${Math.min(100, ((state?.rainfall_mm_hr ?? 0) / 150) * 100)}%` }} /></div>
        </div>
        <div className="stat">
          <div className="stat-l">Gauge stage</div>
          <div className="stat-n">{gauge !== null ? gauge.toFixed(0) : "—"}<span className="unit">cm</span></div>
          <div className="bar"><i style={{ width: `${Math.min(100, ((gauge ?? 0) / 300) * 100)}%` }} /></div>
        </div>
        <div className="stat">
          <div className="stat-l">World clock</div>
          <div className="stat-n" style={{ fontSize: 19 }}>
            {state ? new Date(state.t).toLocaleTimeString() : "—"}
          </div>
          <div className="stat-l">tick {state?.tick ?? "—"} · {state?.mode ?? "—"}</div>
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <MapView gaugeCm={gauge} reportMode={reportMode} />
      </div>

      <div style={{ marginTop: 16 }}><SimConsole tick={state?.tick ?? null} /></div>
    </>
  );
}
