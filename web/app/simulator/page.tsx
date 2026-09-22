"use client";
import PageHead from "../PageHead";
import SimConsole from "../SimConsole";
import { useWorldState } from "@/lib/useWorldState";

export default function Page() {
  const { state } = useWorldState();
  return (
    <>
      <PageHead title="Simulator"
        sub="Drive the rainfall; the reservoir, water and alerts follow the same path a real gauge drives" />
      <SimConsole tick={state?.tick ?? null} />
      <div className="card">
        <div className="label">Why the slider sets rain, not water</div>
        <p className="note-text">
          Dragging the water level directly would skip the rainfall → runoff → stage
          chain the forecast model exists to predict — the very thing being judged.
          The reservoir has a ~170 second time constant, so at 10× you watch rain
          lead water by about 17 seconds. <b>That gap is the forecasting window.</b>
        </p>
      </div>
    </>
  );
}
