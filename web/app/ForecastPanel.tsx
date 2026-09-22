"use client";

import { useEffect, useState } from "react";
import { API } from "@/lib/api";

type Horizon = {
  horizon_min: number;
  stage_p10_cm: number;
  stage_p50_cm: number;
  stage_p90_cm: number;
  band_width_cm: number;
};
type Nowcast = {
  ready: boolean;
  reason?: string;
  buckets?: number;
  stage_now_cm?: number;
  horizons?: Horizon[];
  clamped_to_channel_bed?: boolean;
  mode?: string;
};
type Contribution = {
  label: string; value: number; unit: string; phi_cm: number; share: number;
};
type Explain = { ready: boolean; contributions?: Contribution[]; method?: string };

const HORIZON_FOR_WHY = 60;

export default function ForecastPanel({ tick }: { tick: number | null }) {
  const [nc, setNc] = useState<Nowcast | null>(null);
  const [why, setWhy] = useState<Explain | null>(null);
  const [skill, setSkill] = useState<any>(null);
  const [showWhy, setShowWhy] = useState(false);

  // Forecasts are cheap; refresh on a slow cadence rather than every tick.
  useEffect(() => {
    let alive = true;
    const pull = () =>
      fetch(`${API}/nowcast`)
        .then((r) => r.json())
        .then((d) => alive && setNc(d))
        .catch(() => {});
    pull();
    const id = setInterval(pull, 3000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  useEffect(() => {
    fetch(`${API}/nowcast/skill`).then((r) => r.json()).then(setSkill).catch(() => {});
  }, []);

  useEffect(() => {
    if (!showWhy) return;
    fetch(`${API}/nowcast/explain?horizon_min=${HORIZON_FOR_WHY}`)
      .then((r) => r.json())
      .then(setWhy)
      .catch(() => {});
  }, [showWhy, nc?.stage_now_cm]);

  if (!nc) return null;

  if (!nc.ready) {
    return (
      <div className="card">
        <div className="label">Nowcast</div>
        <p className="fc-warm">
          Warming up — {nc.buckets ?? 0} of 13 five-minute buckets.
          {" "}Raise the speed to fill history faster.
        </p>
      </div>
    );
  }

  const now = nc.stage_now_cm ?? 0;
  const all = [now, ...(nc.horizons ?? []).flatMap((h) => [h.stage_p10_cm, h.stage_p90_cm])];
  const lo = Math.min(...all), hi = Math.max(...all);
  const span = Math.max(20, hi - lo);
  const pct = (v: number) => ((v - lo) / span) * 100;

  const m30 = skill?.metrics?.["30"];
  const storms = m30?.by_regime?.storms?.skill;

  return (
    <div className="card">
      <div className="fc-head">
        <div className="label">Nowcast · water level</div>
        <button className="btn ghost sm" onClick={() => setShowWhy((v) => !v)}>
          {showWhy ? "Hide why" : "Why?"}
        </button>
      </div>

      <table className="fc-table">
        <tbody>
          <tr className="fc-now">
            <td className="fc-h">now</td>
            <td className="fc-v">{now.toFixed(0)}<span className="unit">cm</span></td>
            <td className="fc-bar"><i className="tick" style={{ left: `${pct(now)}%` }} /></td>
          </tr>
          {(nc.horizons ?? []).map((h) => (
            <tr key={h.horizon_min}>
              <td className="fc-h">+{h.horizon_min}m</td>
              <td className="fc-v">
                {h.stage_p50_cm.toFixed(0)}<span className="unit">cm</span>
              </td>
              <td className="fc-bar">
                <span
                  className="band"
                  style={{
                    left: `${pct(h.stage_p10_cm)}%`,
                    width: `${Math.max(1.5, pct(h.stage_p90_cm) - pct(h.stage_p10_cm))}%`,
                  }}
                />
                <i className="tick" style={{ left: `${pct(h.stage_p50_cm)}%` }} />
              </td>
              <td className="fc-band">±{(h.band_width_cm / 2).toFixed(0)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="fc-foot">
        Bars are the <b>80% interval</b>, calibrated on a held-out split so the
        stated confidence is the measured one.
        {storms !== undefined && (
          <> On storm days the model beats persistence by <b>{Math.round(storms * 100)}%</b>.</>
        )}
        {nc.clamped_to_channel_bed && (
          <> <span className="warn">Clamped at the channel bed.</span></>
        )}
      </p>

      {showWhy && why?.ready && (
        <div className="why">
          <div className="label">Why — +{HORIZON_FOR_WHY} min</div>
          {(why.contributions ?? []).slice(0, 5).map((c) => (
            <div className="why-row" key={c.label}>
              <span className="why-label">{c.label}</span>
              <span className="why-val">{c.value} {c.unit}</span>
              <span className={`why-phi ${c.phi_cm >= 0 ? "up" : "down"}`}>
                {c.phi_cm >= 0 ? "+" : "−"}{Math.abs(c.phi_cm).toFixed(1)} cm
              </span>
              <span className="why-share">{Math.round(c.share * 100)}%</span>
            </div>
          ))}
          <p className="fc-foot">{why.method}</p>
        </div>
      )}
    </div>
  );
}
