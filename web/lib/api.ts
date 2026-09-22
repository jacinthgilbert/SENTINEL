export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return (await r.json()) as T;
}

export type ZoneRow = { h3: string; frac: number; population: number; exposed: number };
export type ZoneSummary = {
  stage_m: number; zones: number; mean_fraction: number;
  zones_over_half: number; population_exposed: number;
};
