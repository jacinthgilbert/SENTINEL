"use client";

export type Theme = "dark" | "light";
const KEY = "sentinel:theme";

export function getTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark") return v;
  } catch { /* private mode */ }
  return "dark";
}

export function applyTheme(t: Theme): void {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem(KEY, t); } catch { /* ignore */ }
  // Let the map (which paints vectors in JS, not CSS) recolour itself.
  window.dispatchEvent(new CustomEvent("sentinel:theme", { detail: t }));
}
