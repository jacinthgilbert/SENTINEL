"use client";
import ForecastPanel from "../ForecastPanel";
import PageHead from "../PageHead";
import { useWorldState } from "@/lib/useWorldState";

export default function Page() {
  const { state } = useWorldState();
  return (
    <>
      <PageHead title="Forecast"
        sub="Water level 30–120 minutes ahead, with calibrated uncertainty and exact attributions" />
      <ForecastPanel tick={state?.tick ?? null} />
    </>
  );
}
