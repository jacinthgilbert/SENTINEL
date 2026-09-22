"use client";

import { useWorldState } from "@/lib/useWorldState";

const TEXT: Record<string, string> = {
  connecting: "Connecting…", live: "Live",
  stale: "Stale — last known", offline: "Offline — last known",
};

export default function PageHead({ title, sub }: { title: string; sub?: string }) {
  const { state, status } = useWorldState();
  return (
    <header className="page-head">
      <div>
        <h1 className="page-title">{title}</h1>
        {sub && <p className="page-sub">{sub}</p>}
      </div>
      <span className="pill">
        {state?.mode === "scenario" && <span className="badge">EXERCISE</span>}
        <span className={`dot ${status}`} />
        {TEXT[status]}
        {state && <span className="muted">· {state.rainfall_mm_hr.toFixed(0)} mm/hr</span>}
      </span>
    </header>
  );
}
