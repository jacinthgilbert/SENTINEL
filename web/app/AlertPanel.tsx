"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { API } from "@/lib/api";

type Lang = { code: string; cap: string; name: string; english_name: string };
type Msg = {
  alert_id: string; zone_label: string; severity: string; status: string;
  language: string; language_name: string; text: string; sent: string;
};
type Alert = {
  id: string; zone_label: string; severity: string; certainty: string;
  confidence: number; lead_min: number; status: string;
  reason: { label: string; phi_cm: number; share: number }[];
};
type Channels = Record<string, { live: boolean; note: string }>;

const SEV_CLASS: Record<string, string> = {
  warning: "warn3", watch: "warn2", advisory: "warn1",
};

export default function AlertPanel() {
  const [langs, setLangs] = useState<Lang[]>([]);
  const [lang, setLang] = useState("te");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [channels, setChannels] = useState<Channels>({});
  const [limited, setLimited] = useState(0);
  const [speaking, setSpeaking] = useState<string | null>(null);
  const seen = useRef<Set<string>>(new Set());
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    let alive = true;
    const pull = async () => {
      try {
        const [o, a] = await Promise.all([
          fetch(`${API}/alerts/outbox?limit=30`).then((r) => r.json()),
          fetch(`${API}/alerts?limit=6`).then((r) => r.json()),
        ]);
        if (!alive) return;
        setLangs(o.languages ?? []);
        setMsgs(o.messages ?? []);
        setAlerts(a.alerts ?? []);
        setChannels(a.channels ?? {});
        setLimited(a.rate_limited_last_cycle ?? 0);

        // Buzz the handset when something genuinely new lands.
        const newest = (o.messages ?? [])[0];
        if (newest && !seen.current.has(newest.alert_id)) {
          seen.current.add(newest.alert_id);
          if (seen.current.size > 1) { setFlash(true); setTimeout(() => setFlash(false), 900); }
        }
      } catch { /* keep the last inbox on screen */ }
    };
    pull();
    const id = setInterval(pull, 2500);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const shown = useMemo(() => msgs.filter((m) => m.language === lang), [msgs, lang]);
  const latest = alerts[0];

  function speak(m: Msg) {
    // Voice for people who cannot read the screen. Browser speech here;
    // production renders Piper WAVs and plays them over a Twilio call.
    try {
      const u = new SpeechSynthesisUtterance(m.text);
      u.lang = m.language === "te" ? "te-IN" : m.language === "hi" ? "hi-IN" : "en-IN";
      u.onend = () => setSpeaking(null);
      setSpeaking(m.alert_id + m.language);
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    } catch { setSpeaking(null); }
  }

  return (
    <div className="card">
      <div className="fc-head">
        <div className="label">Alerting</div>
        <div className="chan">
          {Object.entries(channels).map(([k, v]) => (
            <span key={k} className={`chip${v.live ? " on" : ""}`} title={v.note}>
              {k}
            </span>
          ))}
        </div>
      </div>

      <div className="alertgrid">
        {/* ── the handset ─────────────────────────────────────────────── */}
        <div className={`phone${flash ? " buzz" : ""}`}>
          <div className="phone-top">
            <span>Sentinel SMS</span>
            <span className="sig">▮▮▮</span>
          </div>

          <div className="seg langtabs">
            {langs.map((l) => (
              <button key={l.code} className={lang === l.code ? "on" : ""}
                      onClick={() => setLang(l.code)}>
                {l.name}
              </button>
            ))}
          </div>

          <div className="inbox">
            {shown.length === 0 && (
              <p className="empty">No messages yet. Raise the rainfall and wait for
                the forecast to cross a threshold.</p>
            )}
            {shown.map((m, i) => (
              <div className={`sms ${SEV_CLASS[m.severity] ?? ""}`} key={m.alert_id + i}>
                <div className="sms-head">
                  <b>{m.zone_label}</b>
                  {m.status === "Exercise" && <span className="exercise">EXERCISE</span>}
                </div>
                <div className="sms-body">{m.text}</div>
                <button className="btn sm speakbtn" onClick={() => speak(m)}>
                  {speaking === m.alert_id + m.language ? "speaking…" : "▶ voice"}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* ── what the operator sees ──────────────────────────────────── */}
        <div className="alertmeta">
          {latest ? (
            <>
              <div className="metarow">
                <span className={`sevtag ${SEV_CLASS[latest.severity]}`}>
                  {latest.severity}
                </span>
                <span className="muted">CAP certainty</span> <b>{latest.certainty}</b>
                <span className="muted">· confidence</span>{" "}
                <b>{Math.round(latest.confidence * 100)}%</b>
                <span className="muted">· lead</span> <b>{latest.lead_min} min</b>
              </div>

              <div className="label" style={{ marginTop: 10 }}>Why this fired</div>
              {latest.reason?.length ? (
                latest.reason.map((c) => (
                  <div className="why-row" key={c.label}>
                    <span className="why-label">{c.label}</span>
                    <span className={`why-phi ${c.phi_cm >= 0 ? "up" : "down"}`}>
                      {c.phi_cm >= 0 ? "+" : "−"}{Math.abs(c.phi_cm).toFixed(1)} cm
                    </span>
                    <span className="why-share">{Math.round(c.share * 100)}%</span>
                  </div>
                ))
              ) : (
                <p className="fc-foot">No attribution recorded for this alert.</p>
              )}

              <a className="btn sm caplink" href={`${API}/alerts/${latest.id}.xml`}
                 target="_blank" rel="noreferrer">
                View CAP 1.2 XML
              </a>
            </>
          ) : (
            <p className="fc-foot">No alerts yet.</p>
          )}

          <p className="fc-foot">
            One CAP document carries every language as repeated{" "}
            <code>&lt;info&gt;</code> blocks. In scenario mode the document is
            marked <b>status=Exercise</b> — the field CAP provides for drills.
            {limited > 0 && (
              <> Rate limit held back <b>{limited}</b> zone alerts this cycle;
                production would aggregate hexes into wards.</>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
