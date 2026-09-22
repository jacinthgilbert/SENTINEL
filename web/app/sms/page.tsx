"use client";

import { useCallback, useEffect, useState } from "react";
import PageHead from "../PageHead";
import { API } from "@/lib/api";

type Preview = { id: number; name: string; phone: string; lang: string; text: string };
type Recipient = {
  id: number; name: string; phone: string; lang: string;
  opted_in: boolean; last_status: string | null;
};
type Chan = { live: boolean; note: string; warning?: string };
type State = {
  armed: boolean; arm_threshold: string; worst_forecast_severity: string | null;
  lead_min: number; recipients_active: number; exercise: boolean;
  preview: Preview[]; channels: Record<string, Chan>;
};

const LANGS = [
  { code: "te", label: "తెలుగు" },
  { code: "hi", label: "हिन्दी" },
  { code: "en", label: "English" },
];

export default function SmsPage() {
  const [s, setS] = useState<State | null>(null);
  const [people, setPeople] = useState<Recipient[]>([]);
  const [channel, setChannel] = useState("simulated");
  const [form, setForm] = useState({ name: "", phone: "", lang: "te" });
  const [last, setLast] = useState<any>(null);
  const [probe, setProbe] = useState<any>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const pull = useCallback(() => {
    fetch(`${API}/notify/state`).then((r) => r.json()).then(setS).catch(() => {});
    fetch(`${API}/recipients`).then((r) => r.json())
      .then((d) => setPeople(d.recipients ?? [])).catch(() => {});
  }, []);

  useEffect(() => { pull(); const id = setInterval(pull, 4000); return () => clearInterval(id); }, [pull]);

  async function call(path: string, init?: RequestInit) {
    const r = await fetch(`${API}${path}`, init);
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail ?? `${r.status}`);
    return d;
  }

  async function addPerson() {
    setErr(null);
    try {
      await call("/recipients", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...form, opted_in: true }),
      });
      setForm({ name: "", phone: "", lang: "te" });
      pull();
    } catch (e: any) { setErr(e.message); }
  }

  async function toggleOptIn(p: Recipient) {
    try {
      await call(`/recipients/${p.id}/opt-in`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ opted_in: !p.opted_in }),
      });
      pull();
    } catch (e: any) { setErr(e.message); }
  }

  async function removePerson(p: Recipient) {
    try { await call(`/recipients/${p.id}`, { method: "DELETE" }); pull(); }
    catch (e: any) { setErr(e.message); }
  }

  async function runProbe() {
    setBusy("probe"); setErr(null);
    try { setProbe(await call("/notify/probe")); } catch (e: any) { setErr(e.message); }
    setBusy(null);
  }

  async function send(dry: boolean) {
    setBusy(dry ? "dry" : "send"); setErr(null);
    try {
      const d = await call("/notify/send", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ dry_run: dry, channel }),
      });
      setLast(d); setConfirming(false);
    } catch (e: any) { setErr(e.message); }
    setBusy(null);
  }

  async function refreshDelivery() {
    setBusy("refresh");
    try { const d = await call("/notify/refresh", { method: "POST" }); if (d.entry) setLast(d.entry); }
    catch (e: any) { setErr(e.message); }
    setBusy(null);
  }

  if (!s) return <><PageHead title="Send SMS" /><div className="card"><p className="note-text">Loading…</p></div></>;

  const chans = Object.keys(s.channels);
  const active = people.filter((p) => p.opted_in).length;
  const chanLive = s.channels[channel]?.live;

  return (
    <>
      <PageHead title="Send SMS" sub="Authority-authorised warnings to real phones" />

      {/* arming */}
      <div className="card">
        <div className="card-head">
          <div className="label">Authorisation</div>
          <span className={`chip${s.armed ? " on" : ""}`}>
            {s.armed ? "ARMED" : `needs ${s.arm_threshold}`}
          </span>
        </div>
        <p className="note-text">
          The send arms only when the <b>forecast</b> reaches <b>{s.arm_threshold}</b>,
          and still needs a person to press it — an officer authorises before a city is
          messaged. Currently <b>{s.worst_forecast_severity ?? "nothing"}</b>, lead time{" "}
          <b>{s.lead_min} min</b>.
          {s.exercise && <> Messages are marked <b>EXERCISE</b>.</>}
        </p>
        {!s.armed && (
          <p className="note-text warn">
            Not armed. Raise the rainfall on the Simulator page until the forecast
            crosses {s.arm_threshold}.
          </p>
        )}
      </div>

      {/* channel */}
      <div className="card">
        <div className="card-head">
          <div className="label">Channel</div>
          <div className="seg">
            {chans.map((k) => (
              <button key={k} className={channel === k ? "on" : ""}
                      onClick={() => setChannel(k)} title={s.channels[k].note}>
                {k}
              </button>
            ))}
          </div>
        </div>
        <p className="note-text">{s.channels[channel]?.note}</p>
        {s.channels[channel]?.warning && (
          <p className="note-text warn">{s.channels[channel].warning}</p>
        )}
        {channel === "phone" && (
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn sm" disabled={busy === "probe"} onClick={runProbe}>
              {busy === "probe" ? "checking…" : "Check phone is reachable"}
            </button>
            {probe && (
              <span className={probe.ok ? "ok" : "warn"}>
                {probe.status}{probe.detail ? ` — ${probe.detail}` : ""}
              </span>
            )}
          </div>
        )}
        {!chanLive && channel !== "simulated" && (
          <p className="note-text warn">
            Not configured — sending will fail. The simulated channel uses the same
            code path and always works.
          </p>
        )}
      </div>

      {/* recipients */}
      <div className="card">
        <div className="card-head">
          <div className="label">Recipients · {active} opted in</div>
        </div>

        <div className="row" style={{ marginTop: 12 }}>
          <input placeholder="name" value={form.name}
                 onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="+919876543210" value={form.phone}
                 onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <select value={form.lang} onChange={(e) => setForm({ ...form, lang: e.target.value })}>
            {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
          <button className="btn" onClick={addPerson}
                  disabled={!form.name.trim() || !form.phone.trim()}>Add</button>
        </div>
        {err && <p className="note-text warn">{err}</p>}

        {people.length > 0 && (
          <table className="tbl recip-tbl" style={{ marginTop: 14 }}>
            <thead>
              <tr><th>Name</th><th>Number</th><th>Language</th><th>Consent</th>
                  <th>Last status</th><th /></tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td className="mono">{p.phone}</td>
                  <td>{LANGS.find((l) => l.code === p.lang)?.label ?? p.lang}</td>
                  <td>
                    <button className={`btn sm${p.opted_in ? "" : " ghost"}`}
                            onClick={() => toggleOptIn(p)}>
                      {p.opted_in ? "opted in" : "opted out"}
                    </button>
                  </td>
                  <td className="muted">{p.last_status ?? "—"}</td>
                  <td className="num">
                    <button className="btn sm danger" onClick={() => removePerson(p)}>Remove</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="note-text">
          Only opted-in recipients are ever messaged, and numbers are masked
          everywhere outside the server. The list lives in a gitignored file.
        </p>
      </div>

      {/* preview + send */}
      <div className="card">
        <div className="label">What each person receives</div>
        {s.preview.length === 0 ? (
          <p className="note-text">No opted-in recipients yet.</p>
        ) : (
          <div className="previewlist">
            {s.preview.map((p) => (
              <div className="prev" key={p.id}>
                <b>{p.name}</b> <span className="muted">{p.phone} · {p.lang}</span>
                <div className="sms-body">{p.text}</div>
              </div>
            ))}
          </div>
        )}

        <div className="row" style={{ marginTop: 14 }}>
          <button className="btn" disabled={!s.preview.length || busy === "dry"}
                  onClick={() => send(true)}>
            {busy === "dry" ? "…" : "Dry run"}
          </button>
          {!confirming ? (
            <button className="btn primary"
                    disabled={!s.armed || !s.preview.length}
                    onClick={() => setConfirming(true)}>
              Send via {channel} to {active} {active === 1 ? "person" : "people"}
            </button>
          ) : null}
        </div>

        {confirming && (
          <div className="confirm-bar">
            <b>This sends real messages to real phones.</b>
            <span className="spacer" />
            <button className="btn primary" disabled={busy === "send"}
                    onClick={() => send(false)}>
              {busy === "send" ? "sending…" : "Yes, send now"}
            </button>
            <button className="btn ghost" onClick={() => setConfirming(false)}>Cancel</button>
          </div>
        )}

        {last && (
          <div className="previewlist">
            <div className="row">
              <div className="label">
                Last send · {last.dry_run ? "dry run" : last.channel} ·{" "}
                {last.accepted}/{last.recipients} accepted
                {last.delivered !== undefined && <> · {last.delivered} delivered</>}
              </div>
              <span className="spacer" />
              {!last.dry_run && (
                <button className="btn sm" disabled={busy === "refresh"} onClick={refreshDelivery}>
                  {busy === "refresh" ? "…" : "Re-check delivery"}
                </button>
              )}
            </div>
            <table className="tbl" style={{ marginTop: 8 }}>
              <tbody>
                {last.results.map((r: any) => (
                  <tr key={r.id}>
                    <td>{r.name}</td>
                    <td className="mono muted">{r.phone}</td>
                    <td className={r.status === "delivered" ? "ok" : r.ok ? "" : "warn"}>
                      {r.status}
                    </td>
                    <td className="muted small">{r.error ?? r.detail ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="note-text">
              <b>Accepted is not delivered.</b> Re-check to fetch the real outcome from
              the provider — that is where a silently dropped message shows up.
            </p>
          </div>
        )}
      </div>
    </>
  );
}
