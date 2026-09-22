"use client";

/**
 * Offline support for the citizen view.
 *
 * Reports filed with no connection are queued in IndexedDB and replayed when
 * the network returns. This is the part that matters most in a real flood:
 * the person standing in the water has the worst connectivity in the city,
 * and their report is the most valuable one on the map.
 */

const DB = "sentinel";
const STORE = "queued_reports";
const AOI = { west: 83.2, south: 17.69, east: 83.29, north: 17.76 };
const ZOOMS = [12, 13, 14, 15];

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest): Promise<T> {
  const db = await openDB();
  return new Promise<T>((resolve, reject) => {
    const r = fn(db.transaction(STORE, mode).objectStore(STORE));
    r.onsuccess = () => resolve(r.result as T);
    r.onerror = () => reject(r.error);
  });
}

export async function queueReport(fields: Record<string, string>): Promise<void> {
  await tx("readwrite", (s) => s.add({ fields, queued_at: Date.now() }));
}

export async function pendingCount(): Promise<number> {
  try { return await tx<number>("readonly", (s) => s.count()); } catch { return 0; }
}

export async function flushQueue(api: string): Promise<number> {
  let sent = 0;
  let rows: any[] = [];
  try { rows = await tx<any[]>("readonly", (s) => s.getAll()); } catch { return 0; }
  for (const row of rows) {
    const fd = new FormData();
    for (const [k, v] of Object.entries(row.fields)) fd.append(k, String(v));
    try {
      const res = await fetch(`${api}/reports`, { method: "POST", body: fd });
      if (!res.ok) continue;
      await tx("readwrite", (s) => s.delete(row.id));
      sent++;
    } catch {
      break;                       // still offline; keep the rest for later
    }
  }
  return sent;
}

/** Submit a report, falling back to the queue when the network is gone. */
export async function submitReport(
  api: string, fields: Record<string, string>
): Promise<{ queued: boolean }> {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.append(k, v);
  try {
    const res = await fetch(`${api}/reports`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(String(res.status));
    return { queued: false };
  } catch {
    await queueReport(fields);
    return { queued: true };
  }
}

export function registerSW(): void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

// ── tile pre-download ──────────────────────────────────────────────────
function lon2x(lon: number, z: number) { return Math.floor(((lon + 180) / 360) * 2 ** z); }
function lat2y(lat: number, z: number) {
  const r = (lat * Math.PI) / 180;
  return Math.floor(((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 2 ** z);
}

export function tileUrls(): string[] {
  const urls: string[] = [];
  for (const z of ZOOMS) {
    const x0 = lon2x(AOI.west, z), x1 = lon2x(AOI.east, z);
    const y0 = lat2y(AOI.north, z), y1 = lat2y(AOI.south, z);
    for (let x = x0; x <= x1; x++) {
      for (let y = y0; y <= y1; y++) {
        urls.push(`https://a.tile.openstreetmap.org/${z}/${x}/${y}.png`);
      }
    }
  }
  return urls;
}

export function precacheTiles(
  onProgress: (done: number, total: number) => void
): Promise<{ done: number; failed: number; total: number }> {
  return new Promise((resolve) => {
    const urls = tileUrls();
    const sw = navigator.serviceWorker?.controller;
    if (!sw) { resolve({ done: 0, failed: urls.length, total: urls.length }); return; }
    const onMsg = (e: MessageEvent) => {
      const d = e.data || {};
      if (d.type === "PRECACHE_PROGRESS") onProgress(d.done, d.total);
      if (d.type === "PRECACHE_DONE") {
        navigator.serviceWorker.removeEventListener("message", onMsg);
        resolve(d);
      }
    };
    navigator.serviceWorker.addEventListener("message", onMsg);
    sw.postMessage({ type: "PRECACHE_TILES", urls });
  });
}
