"use client";

import { useEffect, useState } from "react";
import { API } from "@/lib/api";
import { flushQueue, pendingCount, registerSW } from "@/lib/offline";
import { cachedTileCount, precache, tileUrls } from "@/lib/offlineTiles";

export default function OfflinePanel() {
  const [online, setOnline] = useState(true);
  const [pending, setPending] = useState(0);
  const [cached, setCached] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [sw, setSw] = useState<boolean | null>(null);
  const total = tileUrls().length;

  useEffect(() => {
    registerSW();
    setOnline(navigator.onLine);
    navigator.serviceWorker?.getRegistration()
      .then((r) => setSw(!!r)).catch(() => setSw(false));

    const refresh = async () => {
      const n = await pendingCount();
      setPending(n);
      setCached(await cachedTileCount());

      // The browser "online" event only fires when the DEVICE loses its
      // network. A backend that is merely unreachable — the far commoner
      // case — never triggers it, so anything queued would sit there
      // forever. Retry whenever something is pending and the service answers.
      if (n > 0) {
        try {
          const ok = await fetch(`${API}/health`).then((r) => r.ok).catch(() => false);
          if (ok) {
            const sent = await flushQueue(API);
            if (sent) {
              setBusy(`sent ${sent} queued report${sent === 1 ? "" : "s"}`);
              setTimeout(() => setBusy(null), 4000);
              setPending(await pendingCount());
            }
          }
        } catch { /* still unreachable */ }
      }
    };
    refresh();
    const id = setInterval(refresh, 3000);

    const up = async () => {
      setOnline(true);
      const n = await flushQueue(API);          // replay anything filed offline
      if (n) setBusy(`sent ${n} queued report${n === 1 ? "" : "s"}`);
      refresh();
    };
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      clearInterval(id);
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);

  async function download() {
    setBusy("downloading map…");
    const r = await precache((d, t) => setBusy(`downloading map… ${d}/${t}`));
    setBusy(r.done ? `map ready offline — ${r.done} tiles` : `failed (${r.failed})`);
    setTimeout(() => setBusy(null), 4000);
  }

  const pct = cached === null ? 0 : Math.min(100, Math.round((cached / total) * 100));

  return (
    <div className={`card offlinepanel${online ? "" : " off"}`}>
      <div className="fc-head">
        <div className="label">Works without a network</div>
        <span className="pill">
          <span className={`dot ${online ? "live" : "offline"}`} />
          {online ? "Online" : "Offline — running on cached data"}
        </span>
      </div>

      <div className="exp-grid">
        <div className="exp-cell">
          <div className="exp-n">{cached === null ? "—" : cached}</div>
          <div className="exp-l">map tiles stored</div>
          <div className="bar"><i style={{ width: `${pct}%` }} /></div>
        </div>
        <div className="exp-cell">
          <div className={`exp-n ${pending ? "warn2" : ""}`}>{pending}</div>
          <div className="exp-l">reports waiting to send</div>
        </div>
        <div className="exp-cell">
          <div className="exp-n">{total}</div>
          <div className="exp-l">tiles cover the city, z12–15</div>
        </div>
        <div className="exp-cell">
          <button className="btn" onClick={download} disabled={!!busy}>
            {busy ?? "Pre-download this area"}
          </button>
        </div>
      </div>

      <p className="fc-foot">
        Three caches, three strategies: basemap tiles <b>cache-first</b> (they never
        change, and re-fetching them during a flood wastes the only bandwidth left),
        API responses <b>network-first with a 2.5 s timeout</b> falling back to last
        known good, and the app shell network-first. Stale API responses are tagged
        so the interface says <em>last known</em> rather than passing them off as live.
      </p>
      <p className="fc-foot">
        Tiles are stored with the Cache API and read back by a Leaflet layer that
        checks the cache before the network, so this works whether or not a
        service worker installs
        {sw === false && <> — and here it did <b>not</b>, which is exactly why the
          offline path does not depend on one</>}. API reads fall back to a
        last-known-good copy held in the page.
      </p>
      <p className="fc-foot">
        A report filed with no signal is queued in IndexedDB and sent when the network
        returns. That matters most in a real flood: the person standing in the water
        has the worst connectivity in the city and the most valuable report on the map.
        The SMS and voice channels never needed the app at all.
      </p>
    </div>
  );
}
