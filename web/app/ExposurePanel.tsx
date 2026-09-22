"use client";

import { useEffect, useState } from "react";
import { API } from "@/lib/api";

type RiskSummary = {
  by_severity: Record<string, number>;
  zones_escalating: number;
  population_layer_loaded: boolean;
  population_exposed: number | null;
  elderly_exposed: number | null;
  horizon_min: number;
  weights: Record<string, number>;
};
type Coverage = {
  nodes_total: number; reachable_dry: number; stranded: number;
  usable_shelters: number; median_time_to_shelter_s: number | null;
};
type FacSummary = {
  hospitals_total: number; hospitals_at_risk: number;
  hospitals_at_risk_forecast: number;
  schools_total: number; schools_at_risk: number;
  shelters_total: number; shelters_usable: number;
  shelter_capacity_total: number; shelter_capacity_usable: number;
  shelter_demand?: number; shelter_shortfall?: number;
};

export default function ExposurePanel() {
  const [risk, setRisk] = useState<RiskSummary | null>(null);
  const [fac, setFac] = useState<FacSummary | null>(null);
  const [cov, setCov] = useState<Coverage | null>(null);

  useEffect(() => {
    let alive = true;
    const pull = () => {
      fetch(`${API}/risk?zones=false`).then((r) => r.json())
        .then((d) => alive && setRisk(d.summary)).catch(() => {});
      fetch(`${API}/facilities/at-risk`).then((r) => r.json())
        .then((d) => alive && setFac(d.summary)).catch(() => {});
      fetch(`${API}/routes/coverage`).then((r) => r.json())
        .then((d) => alive && setCov(d)).catch(() => {});
    };
    pull();
    const id = setInterval(pull, 3000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (!risk || !fac) return null;
  const sev = risk.by_severity ?? {};

  return (
    <div className="card">
      <div className="label">Exposure &amp; critical infrastructure</div>

      <div className="exp-grid">
        <div className="exp-cell">
          <div className="exp-n warn3">{sev.warning ?? 0}</div>
          <div className="exp-l">zones warned</div>
        </div>
        <div className="exp-cell">
          <div className="exp-n warn2">{sev.watch ?? 0}</div>
          <div className="exp-l">watch</div>
        </div>
        <div className="exp-cell">
          <div className="exp-n warn1">{sev.advisory ?? 0}</div>
          <div className="exp-l">advisory</div>
        </div>
        <div className="exp-cell hi">
          <div className="exp-n">{risk.zones_escalating}</div>
          <div className="exp-l">escalating by +{risk.horizon_min}m</div>
        </div>
      </div>

      <div className="exp-grid">
        <div className="exp-cell">
          <div className="exp-n">
            {fac.hospitals_at_risk}<span className="of">/{fac.hospitals_total}</span>
          </div>
          <div className="exp-l">hospitals cut off</div>
        </div>
        <div className="exp-cell">
          <div className="exp-n">
            {fac.schools_at_risk}<span className="of">/{fac.schools_total}</span>
          </div>
          <div className="exp-l">schools affected</div>
        </div>
        <div className="exp-cell">
          <div className="exp-n">
            {fac.shelters_usable}<span className="of">/{fac.shelters_total}</span>
          </div>
          <div className="exp-l">shelters usable</div>
        </div>
        <div className="exp-cell">
          <div className="exp-n">{fac.shelter_capacity_usable.toLocaleString()}</div>
          <div className="exp-l">places available</div>
        </div>
      </div>

      {cov && (
        <div className="exp-grid">
          <div className="exp-cell">
            <div className="exp-n">
              {Math.round((100 * cov.reachable_dry) / cov.nodes_total)}
              <span className="of">%</span>
            </div>
            <div className="exp-l">road network can reach a shelter</div>
          </div>
          <div className="exp-cell">
            <div className="exp-n warn3">{cov.stranded}</div>
            <div className="exp-l">junctions cut off entirely</div>
          </div>
          <div className="exp-cell">
            <div className="exp-n">
              {cov.median_time_to_shelter_s
                ? Math.round(cov.median_time_to_shelter_s / 60)
                : "—"}
              <span className="of"> min</span>
            </div>
            <div className="exp-l">median time to shelter</div>
          </div>
          <div className="exp-cell">
            <div className="exp-n">{cov.usable_shelters}</div>
            <div className="exp-l">shelters reachable</div>
          </div>
        </div>
      )}

      {risk.population_layer_loaded ? (
        <p className="fc-foot">
          <b>{risk.population_exposed?.toLocaleString()}</b> people in flooded area,
          of whom <b>{risk.elderly_exposed?.toLocaleString()}</b> are elderly.
          {fac.shelter_shortfall ? (
            <> Shelter shortfall <b className="warn">{fac.shelter_shortfall.toLocaleString()}</b>.</>
          ) : null}
        </p>
      ) : (
        <p className="fc-foot missing">
          <b>Population layer not loaded.</b> Exposed-population figures are
          withheld rather than shown as zero — run <code>make prep</code> to
          fetch WorldPop 100 m. Shelter capacity is an OSM per-type default,
          not surveyed data.
        </p>
      )}

      <p className="fc-foot">
        Risk = {Object.entries(risk.weights)
          .map(([k, v]) => `${v} × ${k}`)
          .join(" + ")}. Linear on purpose: every number here has to be
        explainable to an official in one sentence.
      </p>
    </div>
  );
}
