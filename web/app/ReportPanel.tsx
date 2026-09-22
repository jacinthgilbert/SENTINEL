"use client";

import { useEffect, useState } from "react";
import { API } from "@/lib/api";

type Props = { reportMode: boolean; setReportMode: (v: boolean) => void };
type Feature = {
  properties: {
    id: number; reporter: string; depth_cm: number | null; trust: number;
    verified: boolean; cv_confidence: number; cv_model: string;
    cv_trained: boolean; nearby: number;
    components: Record<string, number | null>;
  };
};

// Rendered when the backend is unreachable. The panel must NOT disappear
// offline: that is exactly when someone is standing in the water with a report
// worth more than anything else on the map.
const OFFLINE_DATA = {
  geojson: { features: [] },
  total: 0, verified: 0, unverified: 0, zones_influenced: 0,
  cv_model: "heuristic-v1", min_trust: 0.5, offline: true,
};

export default function ReportPanel({ reportMode, setReportMode }: Props) {
  const [data, setData] = useState<any>(OFFLINE_DATA);
  const [live, setLive] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    const pull = () =>
      fetch(`${API}/reports`)
        .then((r) => r.json())
        .then((d) => { if (alive) { setData(d); setLive(true); } })
        .catch(() => { if (alive) setLive(false); });   // keep the last view
    pull();
    const id = setInterval(pull, 2500);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const feats: Feature[] = data.geojson?.features ?? [];

  return (
    <div className="card reportpanel">
      <div className="fc-head">
        <div className="label">Citizen reports</div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className={`btn sm${reportMode ? " on" : ""}`}
            onClick={() => setReportMode(!reportMode)}
          >
            {reportMode ? "Click the map to file…" : "Report flooding"}
          </button>
          <button
            className="btn sm ghost"
            onClick={() => fetch(`${API}/reports/reset`, { method: "POST" })}
          >
            Clear
          </button>
        </div>
      </div>

      <div className="exp-grid">
        <div className="exp-cell">
          <div className="exp-n">{data.total}</div>
          <div className="exp-l">reports in window</div>
        </div>
        <div className="exp-cell">
          <div className="exp-n warn1">{data.verified}</div>
          <div className="exp-l">corroborated</div>
        </div>
        <div className="exp-cell">
          <div className="exp-n muted-n">{data.unverified}</div>
          <div className="exp-l">unverified · ignored</div>
        </div>
        <div className="exp-cell hi">
          <div className="exp-n">{data.zones_influenced}</div>
          <div className="exp-l">zones whose risk moved</div>
        </div>
      </div>

      <div className="replist">
        {feats.length === 0 && (
          <p className="fc-foot">
            {live ? (
              <>None yet. Hit <b>Report flooding</b>, then click the map — file two
                more nearby from different reporters and watch them corroborate.</>
            ) : (
              <>No connection to the service. You can still file a report: it is
                saved on this device and sent the moment the network returns.</>
            )}
          </p>
        )}
        {feats.slice(0, 8).map((f) => {
          const p = f.properties;
          return (
            <div key={p.id} className="rep">
              <button className="rep-head" onClick={() => setOpen(open === p.id ? null : p.id)}>
                <span className={`dot ${p.verified ? "live" : "offline"}`} />
                <b>{p.reporter}</b>
                <span className="muted">{p.depth_cm ?? "—"} cm</span>
                <span className="trustbar">
                  <i style={{ width: `${Math.round(p.trust * 100)}%` }} />
                </span>
                <span className="trustnum">{p.trust.toFixed(2)}</span>
                <span className={p.verified ? "ok" : "muted"}>
                  {p.verified ? "counts" : "ignored"}
                </span>
              </button>
              {open === p.id && (
                <div className="rep-detail">
                  {Object.entries(p.components).map(([k, v]) => (
                    <div className="why-row" key={k}>
                      <span className="why-label">{k.replace(/_/g, " ")}</span>
                      <span className="why-share">
                        {v === null ? "no photo" : (v as number).toFixed(2)}
                      </span>
                    </div>
                  ))}
                  <p className="fc-foot">
                    {p.nearby} independent reporter{p.nearby === 1 ? "" : "s"} nearby.
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <p className="fc-foot missing">
        <b>Vision model is a heuristic, not trained.</b> <code>{data.cv_model}</code>{" "}
        scores colour and texture, capped at 0.75 confidence so it cannot
        out-vote the other trust components. The intended model is a
        FloodNet-Supervised fine-tune; shipping a random number dressed as a
        classifier would silently drive zone risk.
      </p>
      <p className="fc-foot">
        A reporter cannot vouch for themselves, and one reporter counts once
        however many reports they file. Reports below{" "}
        <b>{data.min_trust}</b> trust never reach the risk map.
      </p>
    </div>
  );
}
