/**
 * Colour-blind-safe risk ramp.
 *
 * Deliberately NOT green->red: ~8% of men cannot separate those hues, and a
 * flood map that fails for 1 in 12 viewers fails the inclusion requirement in
 * the plan. This is a blue->yellow->magenta sequence, monotonic in lightness,
 * so it also survives greyscale printing and projector washout.
 */
export const RISK_STEPS = [
  { t: 0.0, color: "#2c7fb8", label: "Minimal" },
  { t: 0.2, color: "#41b6c4", label: "Low" },
  { t: 0.4, color: "#c7e9b4", label: "Moderate" },
  { t: 0.6, color: "#fecc5c", label: "High" },
  { t: 0.8, color: "#e7298a", label: "Severe" },
];

export function riskColor(frac: number): string {
  let out = RISK_STEPS[0].color;
  for (const s of RISK_STEPS) if (frac >= s.t) out = s.color;
  return out;
}

/** Water itself — distinct from the risk ramp so the two never read as one scale. */
export const WATER_FILL = "#0b5394";
export const WATER_LINE = "#8ab6e8";
