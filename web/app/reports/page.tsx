"use client";
import dynamic from "next/dynamic";
import { useState } from "react";
import PageHead from "../PageHead";
import ReportPanel from "../ReportPanel";
import { useWorldState } from "@/lib/useWorldState";

const MapView = dynamic(() => import("../MapView"), {
  ssr: false, loading: () => <div className="map map-skeleton">loading map…</div>,
});

export default function Page() {
  const { state } = useWorldState();
  const [reportMode, setReportMode] = useState(false);
  const gauge = state ? Object.values(state.stages)[0] ?? null : null;
  return (
    <>
      <PageHead title="Citizen reports"
        sub="A lone report is ignored; three independent reporters move the risk map" />
      <MapView gaugeCm={gauge} reportMode={reportMode} />
      <div style={{ marginTop: 16 }}>
        <ReportPanel reportMode={reportMode} setReportMode={setReportMode} />
      </div>
    </>
  );
}
