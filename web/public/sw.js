/* The Sentinel — offline service worker.
 *
 * Three caches, three strategies, because the right answer differs per resource:
 *
 *   tiles  CacheFirst  — basemap never changes, and re-fetching it during a
 *                        flood wastes the only bandwidth anyone has left.
 *   api    NetworkFirst with a short timeout — fresh when possible, LAST KNOWN
 *                        GOOD when not. Stale risk data clearly labelled beats
 *                        a blank screen.
 *   shell  NetworkFirst — the app itself.
 *
 * Reports filed while offline are queued by the PAGE in IndexedDB, not here:
 * replaying POSTs from a worker is far more machinery for the same result.
 */
const VERSION = "sentinel-v1";
const TILES = `${VERSION}-tiles`;
const API = `${VERSION}-api`;
const SHELL = `${VERSION}-shell`;

const SHELL_URLS = ["/", "/authority", "/manifest.json", "/icon.svg"];
const API_TIMEOUT_MS = 2500;
const TILE_MAX = 1200;

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(SHELL).then((c) => c.addAll(SHELL_URLS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

async function trim(cacheName, max) {
  const c = await caches.open(cacheName);
  const keys = await c.keys();
  if (keys.length > max) await Promise.all(keys.slice(0, keys.length - max).map((k) => c.delete(k)));
}

async function cacheFirst(req, cacheName) {
  const c = await caches.open(cacheName);
  const hit = await c.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok) { c.put(req, res.clone()); trim(cacheName, TILE_MAX); }
  return res;
}

async function networkFirst(req, cacheName) {
  const c = await caches.open(cacheName);
  try {
    const res = await Promise.race([
      fetch(req),
      new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), API_TIMEOUT_MS)),
    ]);
    if (res && res.ok) c.put(req, res.clone());
    return res;
  } catch {
    const hit = await c.match(req);
    if (hit) {
      // Mark it so the UI can say "last known", never passing stale off as live.
      const h = new Headers(hit.headers);
      h.set("x-sentinel-cache", "stale");
      return new Response(await hit.blob(), { status: 200, headers: h });
    }
    return new Response(JSON.stringify({ offline: true }), {
      status: 503, headers: { "content-type": "application/json" },
    });
  }
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;                 // POSTs are queued by the page
  const url = new URL(req.url);

  if (/tile\.openstreetmap\.org$/.test(url.hostname)) {
    event.respondWith(cacheFirst(req, TILES));
    return;
  }
  if (url.port === "8000" || url.pathname.startsWith("/api")) {
    event.respondWith(networkFirst(req, API));
    return;
  }
  if (url.origin === self.location.origin && req.mode === "navigate") {
    event.respondWith(networkFirst(req, SHELL));
  }
});

// Bulk tile pre-download, driven from the page.
self.addEventListener("message", async (event) => {
  const msg = event.data || {};
  if (msg.type !== "PRECACHE_TILES") return;
  const c = await caches.open(TILES);
  let done = 0, failed = 0;
  for (const u of msg.urls) {
    try {
      const hit = await c.match(u);
      if (hit) { done++; continue; }
      const res = await fetch(u, { mode: "no-cors" });
      await c.put(u, res.clone());
      done++;
    } catch { failed++; }
    if (done % 15 === 0) {
      event.source?.postMessage({ type: "PRECACHE_PROGRESS", done, total: msg.urls.length });
    }
  }
  event.source?.postMessage({ type: "PRECACHE_DONE", done, failed, total: msg.urls.length });
});
