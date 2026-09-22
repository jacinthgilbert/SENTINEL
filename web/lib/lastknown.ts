"use client";

/**
 * Last-known-good cache for API reads, in the PAGE rather than a service
 * worker.
 *
 * The service worker still handles this when it installs, but SW registration
 * can be blocked — by an embedded browser, a locked-down device, or a policy —
 * and "the map still renders with the network off" is the single most
 * convincing thing this project does. It must not depend on a feature that can
 * be switched off.
 *
 * Stale data is always returned WITH a flag, never silently.
 */

const KEY = "sentinel:lastknown:";
const MAX_AGE_MS = 6 * 60 * 60 * 1000;      // 6 h: older than that is not useful

export type Fresh<T> = { data: T; stale: boolean; ageMs: number };

function read<T>(path: string): Fresh<T> | null {
  try {
    const raw = localStorage.getItem(KEY + path);
    if (!raw) return null;
    const { t, data } = JSON.parse(raw);
    const age = Date.now() - t;
    if (age > MAX_AGE_MS) return null;
    return { data: data as T, stale: true, ageMs: age };
  } catch {
    return null;
  }
}

function write(path: string, data: unknown): void {
  try {
    localStorage.setItem(KEY + path, JSON.stringify({ t: Date.now(), data }));
  } catch {
    /* quota or private mode — caching is a bonus, never a requirement */
  }
}

/** Fetch JSON, falling back to the last good copy of the same path. */
export async function getCached<T>(api: string, path: string): Promise<Fresh<T>> {
  try {
    const res = await fetch(`${api}${path}`);
    if (!res.ok) throw new Error(String(res.status));
    const data = (await res.json()) as T;
    write(path, data);
    return { data, stale: false, ageMs: 0 };
  } catch (err) {
    const hit = read<T>(path);
    if (hit) return hit;
    throw err;
  }
}

export function hasSnapshot(paths: string[]): number {
  return paths.filter((p) => read(p) !== null).length;
}
