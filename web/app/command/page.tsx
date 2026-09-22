"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import PageHead from "../PageHead";
import { API } from "@/lib/api";

type Row = {
  h3: string; priority: number; risk_forecast: number; severity: string | null;
  exposed: number | null; hospitals: number; schools: number;
  shelter_capacity_2km: number; drivers: string[];
  team?: string; access?: string; eta_s?: number | null; reachable?: boolean;
};

const SEV: Record<string, string> = { warning: "warn3", watch: "warn2", advisory: "warn1" };
const ACCESS: Record<string, string> = {
  clear: "ok", "flooded route": "warnish", stranded: "bad",
};

export default function Authority() {
  const [sit, setSit] = useState<any>(null);
  const [plan, setPlan] = useState<any>(null);
  const [teams, setTeams] = useState(6);

  useEffect(() => {
    let alive = true;
    const pull = () => {
      fetch(`${API}/situation`).then((r) => r.json())
        .then((d) => alive && setSit(d)).catch(() => {});
      fetch(`${API}/dispatch?teams=${teams}&limit=12`).then((r) => r.json())
        .then((d) => alive && setPlan(d)).catch(() => {});
    };
    pull();
    const id = setInterval(pull, 3000);
    return () => { alive = false; clearInterval(id); };
  }, [teams]);

  if (!sit || !plan) {
    return (
      <>
        <PageHead title="Command" sub="Everything an operations officer needs, in one view" />
        <div className="card"><p className="note-text">Loading situation…</p></div>
      </>
    );
  }

  const r = sit.risk, f = sit.facilities, rt = sit.routing, w = sit.world;
  const sev = r.by_severity ?? {};

  return (
    <>
      <PageHead title="Command" sub="Ranked response priorities and the live situation" />

      {/* ── headline state ─────────────────────────────────────────── */}
      <div className="exp-grid">
        <div className="exp-cell"><div className="exp-n warn3">{sev.warning ?? 0}</div>
          {/* Explicitly "now": the dispatch table ranks on FORECAST severity,
              so early in an event this reads 0 beside a table of warnings. */}
          <div className="exp-l">zones warned now</div></div>
        <div className="exp-cell hi"><div className="exp-n">{r.zones_escalating}</div>
          <div className="exp-l">escalating by +{r.horizon_min}m</div></div>
        <div className="exp-cell"><div className="exp-n">
          {r.population_layer_loaded ? r.population_exposed?.toLocaleString() : "—"}</div>
          <div className="exp-l">people exposed</div></div>
        <div className="exp-cell"><div className="exp-n warn3">{rt.stranded}</div>
          <div className="exp-l">junctions cut off</div></div>
      </div>

      <div className="exp-grid">
        <div className="exp-cell"><div className="exp-n">
          {f.hospitals_at_risk}<span className="of">/{f.hospitals_total}</span></div>
          <div className="exp-l">hospitals cut off</div></div>
        <div className="exp-cell"><div className="exp-n">
          {f.shelters_usable}<span className="of">/{f.shelters_total}</span></div>
          <div className="exp-l">shelters usable</div></div>
        <div className="exp-cell"><div className="exp-n">
          {f.shelter_capacity_usable.toLocaleString()}</div>
          <div className="exp-l">places available</div></div>
        <div className="exp-cell"><div className="exp-n">
          {sit.reports.verified}<span className="of">/{sit.reports.total}</span></div>
          <div className="exp-l">reports corroborated</div></div>
      </div>

      {/* ── dispatch ───────────────────────────────────────────────── */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="fc-head">
          <div className="label">Response priorities</div>
          <div className="seg">
            {[4, 6, 10, 20].map((n) => (
              <button key={n} className={teams === n ? "on" : ""} onClick={() => setTeams(n)}>
                {n} teams
              </button>
            ))}
          </div>
        </div>

        <table className="dtable">
          <thead>
            <tr>
              <th>#</th><th>Team</th><th>Zone</th><th className="num">Priority</th>
              <th>Severity</th><th>Access</th><th className="num">ETA</th>
              <th>Why it ranks here</th>
            </tr>
          </thead>
          <tbody>
            {(plan.rows as Row[]).map((row, i) => (
              <tr key={row.h3} className={row.team ? "assigned" : ""}>
                <td className="muted">{i + 1}</td>
                <td>{row.team ? <b>{row.team}</b> : <span className="muted">—</span>}</td>
                <td className="mono">{row.h3.slice(-7)}</td>
                <td className="num"><b>{row.priority.toFixed(2)}</b></td>
                <td>
                  <span className={`sevtag ${SEV[row.severity ?? ""] ?? ""}`}>
                    {row.severity ?? "—"}
                  </span>
                </td>
                <td className={ACCESS[row.access ?? ""] ?? "muted"}>{row.access ?? "—"}</td>
                <td className="num">{row.eta_s ? `${Math.round(row.eta_s / 60)}m` : "—"}</td>
                <td className="muted small">{row.drivers.join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <p className="fc-foot">
          <code>{plan.formula}</code> — greedy and explainable on purpose. Shelter
          capacity within 2 km <em>lowers</em> priority: a zone beside a large
          usable shelter needs less sent to it than an identical zone with
          nowhere to go.
        </p>
        {plan.ranking_note && <p className="fc-foot missing">{plan.ranking_note}</p>}
      </div>

      {/* ── alerts ─────────────────────────────────────────────────── */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="label">Alerts issued</div>
        {sit.alerts.recent.length === 0 ? (
          <p className="fc-foot">None yet.</p>
        ) : (
          sit.alerts.recent.map((a: any) => (
            <div className="why-row" key={a.id}>
              <span className="why-label">
                <span className={`sevtag ${SEV[a.severity]}`}>{a.severity}</span>{" "}
                {a.zone_label}
              </span>
              <span className="why-share">{a.certainty}</span>
              <span className="why-share">{a.lead_min}m lead</span>
              <a className="link" href={`${API}/alerts/${a.id}.xml`} target="_blank" rel="noreferrer">
                CAP
              </a>
            </div>
          ))
        )}
        <p className="fc-foot">
          {sit.alerts.total} issued this session
          {sit.alerts.rate_limited > 0 && <>, {sit.alerts.rate_limited} held back by the rate limit</>}.
        </p>
      </div>
    </>
  );
}
