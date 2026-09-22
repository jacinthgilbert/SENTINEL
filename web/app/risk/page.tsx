"use client";
import dynamic from "next/dynamic";
import ExposurePanel from "../ExposurePanel";
import PageHead from "../PageHead";
import { useWorldState } from "@/lib/useWorldState";

const MapView = dynamic(() => import("../MapView"), {
  ssr: false, loading: () => <div className="map map-skeleton">loading map…</div>,
});

export default function Page() {
  const { state } = useWorldState();
  const gauge = state ? Object.values(state.stages)[0] ?? null : null;
  return (
    <>
      <PageHead title="Risk & exposure"
        sub="Zone risk now and in 60 minutes, with population and critical infrastructure" />
      <MapView gaugeCm={gauge} />
      <div style={{ marginTop: 16 }}><ExposurePanel /></div>
    </>
  );
}
