"""Critical infrastructure exposure.

Each facility is sampled against the HAND raster ONCE at load, so at request
time "is this hospital cut off?" is a float comparison rather than a spatial
join. Shelter capacity is netted against demand, which is what an operations
officer actually needs: not "how many shelters exist" but "how many usable
places remain once the flooded ones are removed".
"""

from __future__ import annotations

import functools
import logging

import numpy as np
import rasterio

import inundation
import paths
import zones as zones_mod

log = logging.getLogger("sentinel.facilities")

# A facility is treated as cut off slightly before water reaches its floor:
# access roads flood first, and a hospital nobody can drive to is unavailable.
ACCESS_MARGIN_M = 0.25


@functools.lru_cache(maxsize=1)
def _indexed() -> list[dict]:
    fc = zones_mod.facilities()
    feats = fc.get("features", [])
    pts = [(f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1])
           for f in feats if f.get("geometry", {}).get("type") == "Point"]

    hands: list[float] = []
    if paths.HAND_TIF.exists() and pts:
        with rasterio.open(paths.HAND_TIF) as src:
            for v in src.sample(pts):
                x = float(v[0])
                hands.append(x if np.isfinite(x) else float("inf"))
    else:
        hands = [float("inf")] * len(pts)

    out = []
    for f, (lon, lat), h in zip(feats, pts, hands):
        p = f["properties"]
        out.append({
            "kind": p.get("kind"),
            "name": p.get("name") or "unnamed",
            "capacity": int(p.get("capacity") or 0),
            "is_shelter": bool(p.get("is_shelter")),
            "lon": lon, "lat": lat,
            "hand_m": None if not np.isfinite(h) else round(h, 2),
        })
    log.info("facilities indexed: %d (%d with HAND)",
             len(out), sum(1 for o in out if o["hand_m"] is not None))
    return out


def assess(stage_m: float, forecast_stage_m: float | None = None,
           exposed_population: int | None = None) -> dict:
    feats = _indexed()
    threshold = stage_m + ACCESS_MARGIN_M
    f_threshold = (forecast_stage_m + ACCESS_MARGIN_M
                   if forecast_stage_m is not None else None)

    rows = []
    for f in feats:
        h = f["hand_m"]
        cut = h is not None and h <= threshold
        cut_soon = (f_threshold is not None and h is not None
                    and h <= f_threshold and not cut)
        rows.append({**f, "at_risk": cut, "at_risk_forecast": cut_soon})

    def count(kind: str, pred) -> int:
        return sum(1 for r in rows if r["kind"] == kind and pred(r))

    shelters = [r for r in rows if r["is_shelter"]]
    usable = [r for r in shelters if not r["at_risk"]]
    usable_forecast = [r for r in shelters
                       if not r["at_risk"] and not r["at_risk_forecast"]]

    cap_total = sum(r["capacity"] for r in shelters)
    cap_usable = sum(r["capacity"] for r in usable)
    cap_forecast = sum(r["capacity"] for r in usable_forecast)

    summary = {
        "hospitals_total": count("hospital", lambda r: True),
        "hospitals_at_risk": count("hospital", lambda r: r["at_risk"]),
        "hospitals_at_risk_forecast": count("hospital", lambda r: r["at_risk_forecast"]),
        "schools_total": count("school", lambda r: True),
        "schools_at_risk": count("school", lambda r: r["at_risk"]),
        "shelters_total": len(shelters),
        "shelters_usable": len(usable),
        "shelter_capacity_total": cap_total,
        "shelter_capacity_usable": cap_usable,
        "shelter_capacity_usable_forecast": cap_forecast,
        "access_margin_m": ACCESS_MARGIN_M,
    }
    if exposed_population is not None:
        summary["shelter_demand"] = exposed_population
        summary["shelter_shortfall"] = max(0, exposed_population - cap_usable)
        summary["shelter_utilisation"] = (
            round(exposed_population / cap_usable, 3) if cap_usable else None
        )
    return {"summary": summary, "facilities": rows}
