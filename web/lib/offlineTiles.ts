"use client";

/**
 * Basemap tiles cached with the Cache API directly from the page.
 *
 * No service worker required: tiles are stored by an ordinary fetch, and a
 * Leaflet tile layer subclass checks the cache before the network. OSM tile
 * servers send permissive CORS headers, so the response body is readable and
 * can be turned into a blob URL — an opaque no-cors response could be stored
 * but never read back, which is the trap here.
 */

export const TILE_CACHE = "sentinel-tiles";
const AOI = { west: 83.2, south: 17.69, east: 83.29, north: 17.76 };
const ZOOMS = [12, 13, 14, 15];
const CONCURRENCY = 6;

function lon2x(lon: number, z: number) { return Math.floor(((lon + 180) / 360) * 2 ** z); }
function lat2y(lat: number, z: number) {
  const r = (lat * Math.PI) / 180;
  return Math.floor(((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 2 ** z);
}

export function tileUrls(): string[] {
  const urls: string[] = [];
  for (const z of ZOOMS) {
    for (let x = lon2x(AOI.west, z); x <= lon2x(AOI.east, z); x++) {
      for (let y = lat2y(AOI.north, z); y <= lat2y(AOI.south, z); y++) {
        urls.push(`https://a.tile.openstreetmap.org/${z}/${x}/${y}.png`);
      }
    }
  }
  return urls;
}

export async function cachedTileCount(): Promise<number> {
  try { return (await (await caches.open(TILE_CACHE)).keys()).length; } catch { return 0; }
}

export async function precache(
  onProgress: (done: number, total: number) => void
): Promise<{ done: number; failed: number; total: number }> {
  const urls = tileUrls();
  let done = 0, failed = 0, i = 0;
  let cache: Cache;
  try { cache = await caches.open(TILE_CACHE); }
  catch { return { done: 0, failed: urls.length, total: urls.length }; }

  async function worker() {
    while (i < urls.length) {
      const u = urls[i++];
      try {
        if (await cache.match(u)) { done++; }
        else {
          const res = await fetch(u, { mode: "cors" });
          if (!res.ok) throw new Error(String(res.status));
          await cache.put(u, res.clone());
          done++;
        }
      } catch { failed++; }
      if ((done + failed) % 10 === 0) onProgress(done, urls.length);
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  onProgress(done, urls.length);
  return { done, failed, total: urls.length };
}

/** Leaflet tile layer that prefers the local cache over the network. */
export function makeOfflineTileLayer(L: any, url: string, opts: any) {
  const Layer = L.TileLayer.extend({
    createTile(coords: any, done: (e: Error | null, t: HTMLElement) => void) {
      const img = document.createElement("img");
      img.alt = "";
      const tileUrl = (this as any).getTileUrl(coords);
      img.onload = () => done(null, img);
      img.onerror = () => done(new Error("tile failed"), img);
      (async () => {
        try {
          const c = await caches.open(TILE_CACHE);
          const hit = await c.match(tileUrl);
          if (hit) { img.src = URL.createObjectURL(await hit.blob()); return; }
        } catch { /* fall through to network */ }
        img.src = tileUrl;
      })();
      return img;
    },
  });
  return new Layer(url, opts);
}
