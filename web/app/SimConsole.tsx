"use client";

import { useCallback, useEffect, useState } from "react";
import { API } from "@/lib/api";

type Sim = {
  mode: "live" | "scenario";
  playing: boolean;
  speed: number;
  speeds: number[];
  rain_mm_hr: number;
  max_rain_mm_hr: number;
  presets: Record<string, number>;
  tick: number;
  gauge_cm: number;
  tick_interval_s: number;
};

async function control(body: Record<string, unknown>): Promise<Sim> {
  const r = await fetch(`${API}/sim/control`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`sim/control -> ${r.status}`);
  return r.json();
}

export default function SimConsole({ tick }: { tick: number | null }) {
  const [sim, setSim] = useState<Sim | null>(null);
  // Local echo so dragging feels instant instead of waiting on a round trip.
  const [rain, setRain] = useState(0);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/sim`)
      .then((r) => r.json())
      .then((s: Sim) => {
        setSim(s);
        setRain(s.rain_mm_hr);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  const send = useCallback(async (body: Record<string, unknown>) => {
    try {
      const s = await control(body);
      setSim(s);
      if (body.mode || body.reset) setRain(s.rain_mm_hr);
      setErr(null);
    } catch (e: any) {
      setErr(e.message ?? String(e));
    }
  }, []);

  if (!sim) return <div className="console console-loading">sim console…</div>;

  const scenario = sim.mode === "scenario";

  return (
    <div className={`console${scenario ? " scenario" : ""}`}>
      <div className="console-row">
        <div className="seg">
          <button
            className={!scenario ? "on" : ""}
            onClick={() => send({ mode: "live" })}
          >
            Live
          </button>
          <button
            className={scenario ? "on" : ""}
            onClick={() => send({ mode: "scenario" })}
          >
            Scenario
          </button>
        </div>

        {scenario && (
          <>
            <button
              className="btn"
              onClick={() => send({ playing: !sim.playing })}
              title={sim.playing ? "Pause the world clock" : "Resume"}
            >
              {sim.playing ? "❚❚ Pause" : "▶ Play"}
            </button>

            <div className="seg">
              {sim.speeds.map((s) => (
                <button
                  key={s}
                  className={sim.speed === s ? "on" : ""}
                  onClick={() => send({ speed: s })}
                >
                  {s}×
                </button>
              ))}
            </div>

            <button className="btn ghost" onClick={() => send({ reset: true })}>
              Reset
            </button>

            <span className="clockhint">
              1 min here = {sim.speed} min of weather
            </span>
          </>
        )}

        {!scenario && (
          <span className="clockhint">
            Synthetic live feed · switch to Scenario to drive the rain
          </span>
        )}
      </div>

      {scenario && (
        <div className="console-row">
          <label className="slider">
            <span className="slabel">
              Rainfall <b>{rain.toFixed(0)}</b> mm/hr
            </span>
            <input
              type="range"
              min={0}
              max={sim.max_rain_mm_hr}
              step={5}
              value={rain}
              onChange={(e) => {
                const v = Number(e.target.value);
                setRain(v);
                send({ rain_mm_hr: v });
              }}
            />
          </label>

          <div className="seg presets">
            {Object.entries(sim.presets).map(([name, v]) => (
              <button
                key={name}
                className={rain === v ? "on" : ""}
                onClick={() => {
                  setRain(v);
                  send({ rain_mm_hr: v });
                }}
              >
                {name}
              </button>
            ))}
          </div>
        </div>
      )}

      {scenario && (
        <p className="console-note">
          The slider sets <b>rainfall</b>, never water level. Stage is whatever the
          reservoir makes of the rain — so the water lags, and that lag is the
          window a 30–120 minute forecast lives in.
        </p>
      )}

      {err && <div className="console-err">{err}</div>}
    </div>
  );
}
