/**
 * Risk ramp — earth tones, accessibility first.
 *
 * Pale sand → straw → ochre → clay → deep rust: monotonic in lightness and
 * separated in hue, so it survives colour blindness, greyscale and a washed-out
 * projector. Deliberately NOT green→red; roughly 8% of men cannot separate
 * those, and a flood map failing for 1 in 12 viewers fails the inclusion goal.
 *
 * The light variant is darkened, because the pale end of the dark ramp
 * disappears against parchment.
 */
type Step = { t: number; color: string; label: string };

const DARK: Step[] = [
  { t: 0.0, color: "#EADFC8", label: "Minimal" },
  { t: 0.2, color: "#DCC084", label: "Low" },
  { t: 0.4, color: "#C89A4E", label: "Moderate" },
  { t: 0.6, color: "#A65A3A", label: "High" },
  { t: 0.8, color: "#6E2A1E", label: "Severe" },
];

const LIGHT: Step[] = [
  { t: 0.0, color: "#E0CEA6", label: "Minimal" },
  { t: 0.2, color: "#CBA75F", label: "Low" },
  { t: 0.4, color: "#B07F34", label: "Moderate" },
  { t: 0.6, color: "#93482C", label: "High" },
  { t: 0.8, color: "#5E2317", label: "Severe" },
];

function isLight(): boolean {
  if (typeof document === "undefined") return false;
  return document.documentElement.dataset.theme === "light";
}

export function riskSteps(): Step[] {
  return isLight() ? LIGHT : DARK;
}

/** Kept as a constant export for legends rendered outside a theme context. */
export const RISK_STEPS = DARK;

export function riskColor(frac: number): string {
  const steps = riskSteps();
  let out = steps[0].color;
  for (const s of steps) if (frac >= s.t) out = s.color;
  return out;
}

export const WATER_FILL = "#3E5C6B";
export const WATER_LINE = "#7FA3B3";

/** Zone outline/fill for zones with no meaningful risk. */
export function zoneBaseStyle() {
  return isLight()
    ? { color: "#8A7A62", weight: 0.6, opacity: 0.5, fillColor: "#B6A88F", fillOpacity: 0.05 }
    : { color: "#6B5B48", weight: 0.6, opacity: 0.5, fillColor: "#A1907B", fillOpacity: 0.05 };
}
