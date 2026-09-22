"use client";

import { useEffect, useRef, useState } from "react";
import type * as L from "leaflet";

import { API, getJSON, ZoneRow, ZoneSummary } from "@/lib/api";
import { riskColor, RISK_STEPS, WATER_FILL, WATER_LINE } from "@/lib/palette";

const CENTER: [number, number] = [17.725, 83.245];

/** Visible on a dark basemap AND when tiles fail to load entirely. */
const ZONE_BASE_STYLE = {
  color: "#5b7085",
  weight: 0.6,
  opacity: 0.55,
  fillColor: "#8fa3b8",
  fillOpacity: 0.06,
};
const REFETCH_CM = 5;        // only re-request when the gauge really moved

type Props = { gaugeCm: number | null };

export default function MapView({ gaugeCm }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const waterRef = useRef<L.GeoJSON | null>(null);
  const zoneRef = useRef<L.GeoJSON | null>(null);
  const LRef = useRef<typeof L | null>(null);
  const lastCm = useRef<number>(-999);

  const [summary, setSummary] = useState<ZoneSummary | null>(null);
  const [area, setArea] = useState<number | null>(null);
  const [synthetic, setSynthetic] = useState(false);
  const [noBasemap, setNoBasemap] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // ── init once ──────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const leaflet = (await import("leaflet")).default;
      if (cancelled || !hostRef.current || mapRef.current) return;
      LRef.current = leaflet;

      const map = leaflet.map(hostRef.current, { zoomControl: true }).setView(CENTER, 13);
      const tiles = leaflet
        .tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: "&copy; OpenStreetMap contributors",
          maxZoom: 19,
        })
        .addTo(map);

      // Offline or blocked tiles must degrade to a readable map, not a black
      // rectangle — the zone and water layers carry the information anyway.
      let failures = 0;
      tiles.on("tileerror", () => {
        if (++failures >= 3) setNoBasemap(true);
      });
      tiles.on("tileload", () => setNoBasemap(false));

      mapRef.current = map;

      // zones first so water draws on top
      try {
        const zones = await getJSON<GeoJSON.FeatureCollection>("/zones");
        zoneRef.current = leaflet
          .geoJSON(zones, {
            style: () => ZONE_BASE_STYLE,
          })
          .addTo(map);

        waterRef.current = leaflet
          .geoJSON(undefined, {
            style: () => ({
              color: WATER_LINE, weight: 0.8, fillColor: WATER_FILL, fillOpacity: 0.55,
            }),
          })
          .addTo(map);

        const fac = await getJSON<GeoJSON.FeatureCollection>("/facilities");
        leaflet
          .geoJSON(fac, {
            pointToLayer: (f, latlng) => {
              const kind = (f.properties as any)?.kind ?? "";
              const shelter = (f.properties as any)?.is_shelter;
              return leaflet.circleMarker(latlng, {
                radius: 4,
                color: "#ffffff",
                weight: 1,
                fillColor: kind === "hospital" ? "#e7298a" : shelter ? "#fecc5c" : "#41b6c4",
                fillOpacity: 0.95,
              });
            },
            onEachFeature: (f, layer) => {
              const p = f.properties as any;
              layer.bindTooltip(`${p.name ?? "unnamed"} — ${p.kind}`);
            },
          })
          .addTo(map);
      } catch (e: any) {
        setErr(e.message ?? String(e));
      }
    })();
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  // ── follow the gauge ───────────────────────────────────────────────────
  useEffect(() => {
    if (gaugeCm == null || !waterRef.current || !LRef.current) return;
    if (Math.abs(gaugeCm - lastCm.current) < REFETCH_CM) return;
    lastCm.current = gaugeCm;

    let stale = false;
    (async () => {
      try {
        const fc = await getJSON<any>("/inundation/current");
        if (stale || !waterRef.current) return;
        waterRef.current.clearLayers();
        waterRef.current.addData(fc);
        setArea(fc.properties?.flooded_km2 ?? null);
        setSynthetic(Boolean(fc.properties?.synthetic_terrain));

        const stageM = fc.properties?.stage_m ?? 0;
        const z = await getJSON<{ summary: ZoneSummary; zones: ZoneRow[] }>(
          `/zones/flooded?stage_m=${stageM}`
        );
        if (stale) return;
        setSummary(z.summary);

        const byH3 = new Map(z.zones.map((r) => [r.h3, r.frac]));
        zoneRef.current?.setStyle((f: any) => {
          const frac = byH3.get(f.properties?.h3) ?? 0;
          if (frac <= 0.01) return ZONE_BASE_STYLE;
          return {
            ...ZONE_BASE_STYLE,
            fillColor: riskColor(frac),
            fillOpacity: 0.18 + 0.52 * frac,
          };
        });
      } catch (e: any) {
        setErr(e.message ?? String(e));
      }
    })();
    return () => {
      stale = true;
    };
  }, [gaugeCm]);

  return (
    <div className="mapwrap">
      <div ref={hostRef} className={`map${noBasemap ? " map-nobase" : ""}`} />

      {noBasemap && (
        <div className="note">
          Basemap tiles unreachable — zones and water still render from local data.
        </div>
      )}

      {synthetic && (
        <div className="banner">
          SYNTHETIC TERRAIN — not real Visakhapatnam elevation. Replace{" "}
          <code>data/dem.tif</code> and re-run prep.
        </div>
      )}

      <div className="legend">
        <div className="legend-title">Zone flooded fraction</div>
        {RISK_STEPS.map((s) => (
          <div key={s.label} className="legend-row">
            <i style={{ background: s.color }} />
            {s.label}
          </div>
        ))}
        <div className="legend-row" style={{ marginTop: 8 }}>
          <i style={{ background: WATER_FILL }} /> Inundated
        </div>
      </div>

      <div className="mapstats">
        <span><b>{area?.toFixed(2) ?? "—"}</b> km² flooded</span>
        <span><b>{summary?.zones_over_half ?? "—"}</b> zones &gt;50%</span>
        <span><b>{summary?.population_exposed?.toLocaleString() ?? "—"}</b> exposed</span>
      </div>

      {err && <div className="err">{err}</div>}
    </div>
  );
}
