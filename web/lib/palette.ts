/**
 * Risk ramp — earth tones, but accessibility first.
 *
 * Pale sand → straw → ochre → clay → deep rust. Monotonic in lightness and
 * separated in hue, so it survives colour blindness, greyscale printing and a
 * washed-out projector. Deliberately NOT green→red: roughly 8% of men cannot
 * separate those, and a flood map that fails for 1 in 12 viewers fails the
 * inclusion requirement.
 */
export const RISK_STEPS = [
  { t: 0.0, color: "#EADFC8", label: "Minimal" },
  { t: 0.2, color: "#DCC084", label: "Low" },
  { t: 0.4, color: "#C89A4E", label: "Moderate" },
  { t: 0.6, color: "#A65A3A", label: "High" },
  { t: 0.8, color: "#6E2A1E", label: "Severe" },
];

export function riskColor(frac: number): string {
  let out = RISK_STEPS[0].color;
  for (const s of RISK_STEPS) if (frac >= s.t) out = s.color;
  return out;
}

/** Water is cool on purpose — it must never read as part of the risk scale. */
export const WATER_FILL = "#3E5C6B";
export const WATER_LINE = "#7FA3B3";
