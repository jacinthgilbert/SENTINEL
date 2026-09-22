"""Response prioritisation: where to send teams and supplies.

Greedy and explainable, not an optimiser. Every row carries the reason it
ranks where it does, because an officer who cannot see why a zone is third
will not trust the list — and a solver nobody can interrogate at 3 a.m. is
worse than an ordering everybody can argue with.

    priority = risk x exposure x criticality / shelter_relief

  risk          forecast risk for the zone (what will be true, not what is)
  exposure      exposed population, or 1 when the population layer is absent
  criticality   hospitals and schools inside the zone raise it
  shelter_relief capacity reachable within 2 km lowers it — a zone beside a
                 large usable shelter needs less sent to it than an identical
                 zone with nowhere to go
"""

from __future__ import annotations

import functools
import logging
import math

import facilities as facilities_mod
import risk as risk_mod
import routing as routing_mod
import zones as zones_mod

log = logging.getLogger("sentinel.dispatch")

SHELTER_RADIUS_M = 2000.0
RELIEF_SCALE = 500.0            # capacity that counts as "one shelter's worth"
W_HOSPITAL = 0.50
W_SCHOOL = 0.25
DEFAULT_TEAMS = 6


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@functools.lru_cache(maxsize=1)
def _zone_centroids() -> dict[str, tuple[float, float]]:
    out = {}
    for f in zones_mod.geojson()["features"]:
        ring = (f.get("geometry") or {}).get("coordinates", [[]])[0]
        if not ring:
            continue
        lons = [c[0] for c in ring]
        lats = [c[1] for c in ring]
        out[f["properties"]["h3"]] = (sum(lats) / len(lats), sum(lons) / len(lons))
    return out


def plan(stage_m: float, forecast_stage_m: float | None, rain_mm_hr: float,
         reports_by_zone: dict[str, float] | None = None,
         teams: int = DEFAULT_TEAMS, limit: int = 12) -> dict:
    r = risk_mod.assess(stage_m=stage_m, rain_mm_hr=rain_mm_hr,
                        forecast_stage_m=forecast_stage_m,
                        reports_by_zone=reports_by_zone)
    fa = facilities_mod.assess(stage_m=stage_m, forecast_stage_m=forecast_stage_m)
    centroids = _zone_centroids()
    have_pop = r["summary"]["population_layer_loaded"]

    fac = fa["facilities"]
    shelters = [f for f in fac if f["is_shelter"] and not f["at_risk"]]

    rows = []
    for z in r["zones"]:
        score_risk = z.get("risk_forecast", z["risk"])
        if score_risk < 0.25:
            continue
        c = centroids.get(z["h3"])
        if not c:
            continue
        zlat, zlon = c

        hosp = sum(1 for f in fac
                   if f["kind"] == "hospital"
                   and _haversine_m(zlat, zlon, f["lat"], f["lon"]) <= 250)
        sch = sum(1 for f in fac
                  if f["kind"] == "school"
                  and _haversine_m(zlat, zlon, f["lat"], f["lon"]) <= 250)
        criticality = 1.0 + W_HOSPITAL * hosp + W_SCHOOL * sch

        cap = sum(f["capacity"] for f in shelters
                  if _haversine_m(zlat, zlon, f["lat"], f["lon"]) <= SHELTER_RADIUS_M)
        relief = max(1.0, cap / RELIEF_SCALE)

        exposure = z["exposed"] if have_pop else 1
        priority = score_risk * max(exposure, 1) * criticality / relief

        drivers = []
        if score_risk >= 0.7:
            drivers.append("forecast warning level")
        elif score_risk >= 0.45:
            drivers.append("forecast watch level")
        if have_pop and z["exposed"]:
            drivers.append(f"{z['exposed']:,} exposed")
        if hosp:
            drivers.append(f"{hosp} hospital{'s' if hosp > 1 else ''} inside")
        if sch:
            drivers.append(f"{sch} school{'s' if sch > 1 else ''} inside")
        if cap == 0:
            drivers.append("no usable shelter within 2 km")
        if (reports_by_zone or {}).get(z["h3"], 0) > 0:
            drivers.append("corroborated citizen reports")

        rows.append({
            "h3": z["h3"], "lat": round(zlat, 5), "lon": round(zlon, 5),
            "priority": round(priority, 3),
            "risk_forecast": round(score_risk, 3),
            "severity": z.get("severity_forecast") or z.get("severity"),
            "exposed": z["exposed"] if have_pop else None,
            "elderly_exposed": z["elderly_exposed"] if have_pop else None,
            "hospitals": hosp, "schools": sch,
            "shelter_capacity_2km": cap,
            "criticality": round(criticality, 2),
            "drivers": drivers,
        })

    # Without the population layer every exposure is 1, so scores tie in
    # clumps and the order inside a clump would otherwise be arbitrary.
    # Break ties on things an officer would actually use: critical facilities
    # first, then the zones with least shelter nearby, then deterministically.
    rows.sort(key=lambda x: (-x["priority"], -x["criticality"],
                             x["shelter_capacity_2km"], x["h3"]))

    # Route each of the top zones out, so stranding is caught before a team is
    # sent by road to somewhere no road reaches.
    assigned = 0
    for row in rows[:limit]:
        try:
            rt = routing_mod.route(row["lat"], row["lon"], stage_m)
        except FileNotFoundError:
            rt = {"ok": False}
        row["reachable"] = bool(rt.get("ok"))
        row["access"] = ("stranded" if not rt.get("ok")
                         else "flooded route" if rt.get("degraded") else "clear")
        row["eta_s"] = rt.get("travel_time_s")
        row["shelter"] = (rt.get("shelter") or {}).get("name")
        if not rt.get("ok"):
            row["drivers"] = ["NO ROAD ACCESS — boat or air"] + row["drivers"]
        if assigned < teams:
            assigned += 1
            row["team"] = f"Team {assigned}"

    return {
        "stage_m": round(stage_m, 3),
        "population_layer_loaded": have_pop,
        "teams_available": teams,
        "teams_assigned": assigned,
        "zones_over_threshold": len(rows),
        "shelters_usable": len(shelters),
        "shelter_capacity_usable": sum(f["capacity"] for f in shelters),
        "formula": "risk x exposure x criticality / shelter_relief",
        "ranking_note": (
            None if have_pop else
            "Population layer absent: exposure is held at 1 for every zone, so "
            "priorities tie and are broken by critical facilities, then by least "
            "shelter capacity nearby. Run `make prep` for true ordering."
        ),
        "rows": rows[:limit],
    }
