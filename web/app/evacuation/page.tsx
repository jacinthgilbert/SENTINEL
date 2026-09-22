"use client";
import dynamic from "next/dynamic";
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
      <PageHead title="Evacuation"
        sub="Click anywhere on the map to route to the nearest usable shelter" />
      <MapView gaugeCm={gauge} />
      <div className="card" style={{ marginTop: 16 }}>
        <div className="label">How routing works</div>
        <p className="note-text">
          A road is impassable once water over it reaches <b>0.30 m</b>. Rather than
          rebuilding the graph, a weight function evaluated per query makes those
          edges untraversable, so routes recompute as fast as the slider moves.
          When flooding severs every dry path the router retries with flooded roads
          penalised rather than forbidden and marks the result <b>risky</b> — a route
          labelled dangerous beats no route at all, because people will move anyway.
        </p>
      </div>
    </>
  );
}
