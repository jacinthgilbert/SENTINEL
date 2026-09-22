"use client";

import { useEffect, useRef, useState } from "react";
import type * as L from "leaflet";

import { API, getJSON, ZoneRow, ZoneSummary } from "@/lib/api";
import { getCached } from "@/lib/lastknown";
import { submitReport } from "@/lib/offline";
import { makeOfflineTileLayer } from "@/lib/offlineTiles";
import { riskColor, RISK_STEPS, WATER_FILL, WATER_LINE } from "@/lib/palette";

const CENTER: [number, number] = [17.725, 83.245];

/** Visible on a dark basemap AND when tiles fail to load entirely. */
const ZONE_BASE_STYLE = {
  color: "#6B5B48",
  weight: 0.6,
  opacity: 0.5,
  fillColor: "#A1907B",
  fillOpacity: 0.05,
};
const REFETCH_CM = 5;        // only re-request when the gauge really moved

type Props = { gaugeCm: number | null; reportMode?: boolean };

type RiskZone = {
  h3: string; risk: number; severity: string | null;
  risk_forecast?: number; severity_forecast?: string | null;
};

export default function MapView({ gaugeCm, reportMode = false }: Props) {
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
  // Set once the vector layers exist. Without this the first draw races map
  // init, and a CONSTANT gauge (rain = 0) never re-triggers the effect — so
  // the map would sit empty forever until something moved.
  const [ready, setReady] = useState(false);
  const [staleData, setStaleData] = useState(false);
  // "now" vs "+60m": the toggle that turns a status map into a warning map.
  const [view, setView] = useState<"now" | "forecast">("now");
  const riskRef = useRef<RiskZone[]>([]);
  const routeRef = useRef<L.GeoJSON | null>(null);
  const [routeInfo, setRouteInfo] = useState<any>(null);
  const [showPriority, setShowPriority] = useState(false);
  const reportLayerRef = useRef<L.GeoJSON | null>(null);
  const reportModeRef = useRef(reportMode);
  reportModeRef.current = reportMode;
  const [err, setErr] = useState<string | null>(null);

  // ── init once ──────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const leaflet = (await import("leaflet")).default;
      if (cancelled || !hostRef.current || mapRef.current) return;
      LRef.current = leaflet;

      const map = leaflet.map(hostRef.current, { zoomControl: true }).setView(CENTER, 13);
      // Cache-first tiles, with no dependence on a service worker.
      const tiles = makeOfflineTileLayer(
        leaflet,
        "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        { attribution: "&copy; OpenStreetMap contributors", maxZoom: 19 }
      ).addTo(map);

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
        const zones = (await getCached<GeoJSON.FeatureCollection>(API, "/zones")).data;
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

        routeRef.current = leaflet
          .geoJSON(undefined, {
            style: (f: any) => ({
              color: f?.properties?.degraded ? "#D9A441" : "#7E9B5F",
              weight: f?.properties?.priority ? 3 : 4.5,
              opacity: 0.95,
              dashArray: f?.properties?.degraded ? "6 5" : undefined,
            }),
          })
          .addTo(map);

        reportLayerRef.current = leaflet
          .geoJSON(undefined, {
            pointToLayer: (f: any, latlng: any) => {
              const p = f.properties ?? {};
              return leaflet.circleMarker(latlng, {
                radius: 5 + 5 * (p.trust ?? 0),
                color: p.verified ? "#F3E7D3" : "#7A6A58",
                weight: p.verified ? 1.5 : 1,
                dashArray: p.verified ? undefined : "2 2",
                fillColor: p.verified ? "#C9803F" : "#4A3F33",
                fillOpacity: p.verified ? 0.9 : 0.45,
              });
            },
            onEachFeature: (f: any, layer: any) => {
              const p = f.properties ?? {};
              layer.bindTooltip(
                `${p.reporter} · ${p.depth_cm ?? "?"} cm · trust ${(p.trust ?? 0).toFixed(2)}` +
                (p.verified ? " · counts" : " · unverified")
              );
            },
          })
          .addTo(map);

        // Click anywhere: route, or file a report when report mode is on.
        map.on("click", async (e: any) => {
          if (reportModeRef.current) {
            // Queues to IndexedDB and replays later if there is no network.
            const r = await submitReport(API, {
              lat: String(e.latlng.lat),
              lon: String(e.latlng.lng),
              depth_cm: "45",
              reporter: `citizen-${Math.floor(Math.random() * 900 + 100)}`,
            });
            if (r.queued) setRouteInfo({ queued: true });
            return;
          }
          try {
            const r = await fetch(`${API}/route`, {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ lat: e.latlng.lat, lon: e.latlng.lng }),
            }).then((x) => x.json());
            setRouteInfo(r);
            if (!routeRef.current) return;
            routeRef.current.clearLayers();
            if (r.ok) {
              routeRef.current.addData({
                type: "Feature",
                properties: { degraded: r.degraded },
                geometry: r.geometry,
              } as any);
            }
          } catch { /* keep the last route on screen */ }
        });

        const fac = (await getCached<GeoJSON.FeatureCollection>(API, "/facilities")).data;
        leaflet
          .geoJSON(fac, {
            pointToLayer: (f, latlng) => {
              const kind = (f.properties as any)?.kind ?? "";
              const shelter = (f.properties as any)?.is_shelter;
              return leaflet.circleMarker(latlng, {
                radius: 4,
                color: "#ffffff",
                weight: 1,
                fillColor: kind === "hospital" ? "#B3462F" : shelter ? "#D9A441" : "#8FA07A",
                fillOpacity: 0.95,
              });
            },
            onEachFeature: (f, layer) => {
              const p = f.properties as any;
              layer.bindTooltip(`${p.name ?? "unnamed"} — ${p.kind}`);
            },
          })
          .addTo(map);
        setReady(true);
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
    if (!ready || gaugeCm == null || !waterRef.current || !LRef.current) return;
    if (Math.abs(gaugeCm - lastCm.current) < REFETCH_CM) return;
    lastCm.current = gaugeCm;

    let stale = false;
    (async () => {
      try {
        const fcRes = await getCached<any>(API, "/inundation/current");
        const fc = fcRes.data;
        if (stale || !waterRef.current) return;
        setStaleData(fcRes.stale);
        waterRef.current.clearLayers();
        waterRef.current.addData(fc);
        setArea(fc.properties?.flooded_km2 ?? null);
        setSynthetic(Boolean(fc.properties?.synthetic_terrain));

        const stageM = fc.properties?.stage_m ?? 0;
        const [zRes, rkRes] = await Promise.all([
          getCached<{ summary: ZoneSummary; zones: ZoneRow[] }>(
            API, `/zones/flooded?stage_m=${stageM}`
          ),
          getCached<{ zones: RiskZone[] }>(API, "/risk?horizon_min=60"),
        ]);
        if (stale) return;
        setSummary(zRes.data.summary);
        riskRef.current = rkRes.data.zones;
        paint();
      } catch (e: any) {
        setErr(e.message ?? String(e));
      }
    })();
    return () => {
      stale = true;
    };
  }, [gaugeCm, ready, view]);

  // Repaint on toggle without refetching.
  useEffect(() => { paint(); }, [view]);

  // Offline first-load: the refresh below is gated on a gauge value from the
  // SSE stream, and that stream is precisely what dies in an outage. Paint
  // once from last-known-good as soon as the layers exist, so opening the app
  // DURING a flood still shows the last risk picture instead of a grey map.
  useEffect(() => {
    if (!ready) return;
    let stale = false;
    (async () => {
      try {
        const [fcRes, rkRes] = await Promise.all([
          getCached<any>(API, "/inundation/current"),
          getCached<{ zones: RiskZone[] }>(API, "/risk?horizon_min=60"),
        ]);
        if (stale) return;
        if (!fcRes.stale && !rkRes.stale) return;      // live path will handle it
        setStaleData(true);
        if (waterRef.current && fcRes.data) {
          waterRef.current.clearLayers();
          waterRef.current.addData(fcRes.data);
          setArea(fcRes.data.properties?.flooded_km2 ?? null);
          setSynthetic(Boolean(fcRes.data.properties?.synthetic_terrain));
        }
        riskRef.current = rkRes.data.zones ?? [];
        // The zone-summary endpoint is cached under a stage-specific key that
        // will not match offline, so derive the headline counts from the risk
        // rows we do have rather than showing blanks.
        const rows = rkRes.data.zones ?? [];
        setSummary({
          stage_m: fcRes.data?.properties?.stage_m ?? 0,
          zones: rows.length,
          mean_fraction: 0,
          zones_over_half: rows.filter((z) => (z.risk ?? 0) > 0.5).length,
          population_exposed: 0,
        });
        paint();
      } catch { /* nothing cached yet: a first-ever load with no network */ }
    })();
    return () => { stale = true; };
  }, [ready]);

  // Citizen reports layer, refreshed on the same cadence as the panel.
  useEffect(() => {
    if (!ready) return;
    let stale = false;
    const pull = async () => {
      try {
        const d = await getJSON<any>("/reports");
        if (stale || !reportLayerRef.current) return;
        reportLayerRef.current.clearLayers();
        if (d.geojson?.features?.length) reportLayerRef.current.addData(d.geojson);
      } catch { /* ignore */ }
    };
    pull();
    const id = setInterval(pull, 2500);
    return () => { stale = true; clearInterval(id); };
  }, [ready]);

  // Priority routes: out of at-risk hospitals and schools, worst first.
  useEffect(() => {
    if (!ready || !routeRef.current) return;
    if (!showPriority) { routeRef.current.clearLayers(); setRouteInfo(null); return; }
    let stale = false;
    (async () => {
      try {
        const d = await getJSON<any>("/routes/priority?limit=8");
        if (stale || !routeRef.current) return;
        routeRef.current.clearLayers();
        for (const r of d.routes ?? []) {
          if (!r.ok) continue;
          routeRef.current.addData({
            type: "Feature",
            properties: { degraded: r.degraded, priority: true },
            geometry: r.geometry,
          } as any);
        }
        setRouteInfo({ priority: true, count: (d.routes ?? []).filter((r: any) => r.ok).length });
      } catch { /* ignore */ }
    })();
    return () => { stale = true; };
  }, [showPriority, ready, gaugeCm]);

  function paint() {
    const rows = riskRef.current;
    if (!rows.length || !zoneRef.current) return;
    const key = view === "now" ? "risk" : "risk_forecast";
    const sevKey = view === "now" ? "severity" : "severity_forecast";
    const by = new Map(rows.map((r) => [r.h3, r]));

    zoneRef.current.setStyle((f: any) => {
      const r = by.get(f.properties?.h3);
      const score = (r?.[key as keyof RiskZone] as number) ?? 0;
      if (!r || score <= 0.02) return ZONE_BASE_STYLE;

      // A zone calm now but warned later gets an outline, not just a fill:
      // the whole product is the difference between the two views.
      const escalating =
        view === "forecast" && !!r.severity_forecast && !r.severity;
      return {
        ...ZONE_BASE_STYLE,
        color: escalating ? "#E8B96B" : ZONE_BASE_STYLE.color,
        weight: escalating ? 1.6 : ZONE_BASE_STYLE.weight,
        opacity: escalating ? 0.95 : ZONE_BASE_STYLE.opacity,
        fillColor: riskColor(score),
        fillOpacity: 0.18 + 0.52 * Math.min(1, score),
        _sev: r[sevKey as keyof RiskZone],
      } as any;
    });
  }

  return (
    <div className="mapwrap">
      <div
        ref={hostRef}
        className={`map${noBasemap ? " map-nobase" : ""}${reportMode ? " reporting" : ""}`}
      />

      {reportMode && (
        <div className="note reportnote">
          Report mode — click the map to file a flood report from that spot
        </div>
      )}

      {staleData && (
        <div className="note stalenote">
          Last known — no connection to the service. Risk shown is the most
          recent good data, not live.
        </div>
      )}

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

      <div className="viewtoggle seg">
        <button className={view === "now" ? "on" : ""} onClick={() => setView("now")}>
          Now
        </button>
        <button
          className={view === "forecast" ? "on" : ""}
          onClick={() => setView("forecast")}
        >
          +60 min
        </button>
      </div>

      <button
        className={`routebtn btn${showPriority ? " on" : ""}`}
        onClick={() => setShowPriority((v) => !v)}
      >
        {showPriority ? "Hide evacuation routes" : "Evacuation routes"}
      </button>

      {routeInfo && (
        <div className="routeinfo">
          {routeInfo.queued ? (
            <>Offline — report saved, will send when the network returns</>
          ) : routeInfo.priority ? (
            <>Routing <b>{routeInfo.count}</b> at-risk facilities to shelters</>
          ) : routeInfo.ok ? (
            <>
              <b>{Math.round(routeInfo.travel_time_s / 60)} min</b> to{" "}
              {routeInfo.shelter?.name ?? "shelter"}
              {routeInfo.degraded && (
                <span className="warn">
                  {" "}· risky — crosses {routeInfo.flooded_segments_crossed} flooded
                  {routeInfo.flooded_segments_crossed === 1 ? " road" : " roads"}
                </span>
              )}
            </>
          ) : (
            <span className="warn">Stranded — no route to any usable shelter</span>
          )}
        </div>
      )}

      <div className="legend">
        <div className="legend-title">Zone risk</div>
        {RISK_STEPS.map((s) => (
          <div key={s.label} className="legend-row">
            <i style={{ background: s.color }} />
            {s.label}
          </div>
        ))}
        <div className="legend-row" style={{ marginTop: 8 }}>
          <i style={{ background: WATER_FILL }} /> Inundated
        </div>
        {view === "forecast" && (
          <div className="legend-row">
            <i style={{ background: "transparent", border: "1.5px solid #E8B96B" }} />
            Escalating
          </div>
        )}
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
