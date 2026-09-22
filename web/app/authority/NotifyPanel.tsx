"use client";

import { useEffect, useState } from "react";
import { API } from "@/lib/api";

type Preview = { id: number; name: string; phone: string; lang: string; text: string };
type State = {
  armed: boolean; arm_threshold: string; worst_forecast_severity: string | null;
  lead_min: number; recipients_active: number; exercise: boolean;
  preview: Preview[];
  channels: Record<string, { live: boolean; note: string; warning?: string }>;
};

export default function NotifyPanel() {
  const [s, setS] = useState<State | null>(null);
  const [last, setLast] = useState<any>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "", lang: "te" });
  const [channel, setChannel] = useState("simulated");
  const [err, setErr] = useState<string | null>(null);

  const pull = () =>
    fetch(`${API}/notify/state`).then((r) => r.json()).then(setS).catch(() => {});

  useEffect(() => {
    pull();
    const id = setInterval(pull, 4000);
    return () => clearInterval(id);
  }, []);

  async function addRecipient() {
    setErr(null);
    try {
      const r = await fetch(`${API}/recipients`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...form, opted_in: true }),
      });
      if (!r.ok) throw new Error((await r.json()).detail ?? "failed");
      setForm({ name: "", phone: "", lang: "te" });
      pull();
    } catch (e: any) { setErr(e.message); }
  }

  async function doSend(dry: boolean) {
    setBusy(true); setErr(null);
    try {
      const r = await fetch(`${API}/notify/send`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ dry_run: dry, channel }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? "send failed");
      setLast(d);
      setConfirming(false);
      if (!dry) {
        // Accepted != delivered. Re-check the real outcome after a few seconds.
        setTimeout(async () => {
          const rr = await fetch(`${API}/notify/refresh`, { method: "POST" });
          setLast((await rr.json()).entry ?? d);
        }, 8000);
      }
    } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  if (!s) return null;
  // Order matters: simulated always works, so it leads and is the safe default.
  const order = ["simulated", "phone", "sms"];
  const chans = order.filter((k) => s.channels?.[k]);

  return (
    <div className="card notifypanel" style={{ marginTop: 16 }}>
      <div className="fc-head">
        <div className="label">Send warning to residents</div>
        <span className={`chip${s.armed ? " on" : ""}`}>
          {s.armed ? "ARMED" : `needs ${s.arm_threshold}`}
        </span>
      </div>

      <p className="fc-foot">
        Arms only when the <b>forecast</b> reaches <b>{s.arm_threshold}</b>, and still
        needs a human to press it — an officer authorises before a city is messaged.
        Currently: <b>{s.worst_forecast_severity ?? "nothing"}</b>.
        {s.exercise && <> · messages will be marked <b>EXERCISE</b></>}
      </p>

      <div className="notifyrow">
        <span className="muted">Channel</span>
        <div className="seg">
          {chans.map((k) => (
            <button key={k} className={channel === k ? "on" : ""}
                    onClick={() => setChannel(k)}
                    title={s.channels[k].note}>
              {k}{s.channels[k].live ? "" : " ·off"}
            </button>
          ))}
        </div>
        <span className="muted" style={{ flex: 1, minWidth: 220 }}>
          {s.channels[channel]?.note}
        </span>
      </div>
      {s.channels[channel] && !s.channels[channel].live && channel !== "simulated" && (
        <p className="fc-foot warn">
          {channel} is not sending. Falling back to the on-screen handset keeps the
          demo working; the same message and code path is used either way.
        </p>
      )}

      {/* recipients */}
      <div className="notifyrow">
        <input placeholder="name" value={form.name}
               onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input placeholder="+919876543210" value={form.phone}
               onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        <select value={form.lang} onChange={(e) => setForm({ ...form, lang: e.target.value })}>
          <option value="te">తెలుగు</option>
          <option value="hi">हिन्दी</option>
          <option value="en">English</option>
        </select>
        <button className="btn sm" onClick={addRecipient}>Add recipient</button>
        <span className="muted">{s.recipients_active} opted in</span>
      </div>
      {err && <p className="fc-foot warn">{err}</p>}

      {/* what each person gets */}
      {s.preview.length > 0 && (
        <div className="previewlist">
          {s.preview.map((p) => (
            <div className="prev" key={p.id}>
              <b>{p.name}</b> <span className="muted">{p.phone} · {p.lang}</span>
              <div className="sms-body">{p.text}</div>
            </div>
          ))}
        </div>
      )}

      {/* send */}
      <div className="notifyrow" style={{ marginTop: 10 }}>
        <button className="btn sm" disabled={busy || !s.preview.length}
                onClick={() => doSend(true)}>
          Dry run
        </button>
        {!confirming ? (
          <button className="btn" disabled={!s.armed || busy || !s.preview.length}
                  onClick={() => setConfirming(true)}>
            Send via {channel} to {s.recipients_active}{" "}
            {s.recipients_active === 1 ? "person" : "people"}
          </button>
        ) : (
          <>
            <span className="warn">
              This sends real messages to real phones. Confirm?
            </span>
            <button className="btn" disabled={busy} onClick={() => doSend(false)}>
              Yes, send
            </button>
            <button className="btn ghost sm" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </>
        )}
      </div>

      {/* results */}
      {last && (
        <div className="previewlist">
          <div className="label" style={{ marginTop: 8 }}>
            Last send · {last.dry_run ? "dry run" : last.channel} ·{" "}
            {last.accepted}/{last.recipients} accepted
            {last.delivered !== undefined && <> · <b>{last.delivered} delivered</b></>}
          </div>
          {last.results.map((r: any) => (
            <div className="why-row" key={r.id}>
              <span className="why-label">{r.name} <span className="muted">{r.phone}</span></span>
              <span className={r.status === "delivered" ? "ok"
                              : r.ok ? "" : "warn"}>{r.status}</span>
              <span className="why-share">{r.error ?? ""}</span>
            </div>
          ))}
          {last.results.some((r: any) => r.detail) && (
            <p className="fc-foot warn">
              {last.results.find((r: any) => r.detail)?.detail}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
