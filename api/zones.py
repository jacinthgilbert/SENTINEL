"""Per-zone flood fraction from the precomputed HAND decile curve.

Each zone carries its HAND empirical CDF as 11 deciles. "What fraction of this
zone is under water at stage s" is then a linear interpolation — no raster
access, ~1 us per zone, so all 545 zones update on every slider frame.

Using the zone MINIMUM instead would flood 60% of the city at 0.5 m, because a
res-9 hex spans ~117 DEM cells and almost every hex touches a drainage line.
"""

from __future__ import annotations

import functools
import json

import numpy as np

import paths

_LEVELS = np.linspace(0.0, 1.0, 11)          # deciles -> cumulative fraction


@functools.lru_cache(maxsize=1)
def _zones() -> list[dict]:
    if not paths.ZONES_GEOJSON.exists():
        raise FileNotFoundError(f"{paths.ZONES_GEOJSON} missing — run prep/run.py")
    return json.loads(paths.ZONES_GEOJSON.read_text())["features"]


@functools.lru_cache(maxsize=1)
def geojson() -> dict:
    """The static zone layer for the map."""
    return json.loads(paths.ZONES_GEOJSON.read_text())


@functools.lru_cache(maxsize=1)
def facilities() -> dict:
    if not paths.FACILITIES_GEOJSON.exists():
        raise FileNotFoundError(f"{paths.FACILITIES_GEOJSON} missing")
    return json.loads(paths.FACILITIES_GEOJSON.read_text())


def flooded_fraction(stage_m: float) -> list[dict]:
    """[{h3, frac, population, exposed}] for every zone with a HAND profile."""
    out = []
    for f in _zones():
        p = f["properties"]
        d = p.get("hand_deciles")
        if not d:
            continue
        frac = float(np.interp(stage_m, d, _LEVELS))
        pop = int(p.get("population") or 0)
        out.append({
            "h3": p["h3"],
            "frac": round(frac, 4),
            "population": pop,
            "exposed": int(round(pop * frac)),
        })
    return out


def summary(stage_m: float) -> dict:
    rows = flooded_fraction(stage_m)
    if not rows:
        return {"stage_m": stage_m, "zones": 0}
    fr = np.array([r["frac"] for r in rows])
    return {
        "stage_m": round(stage_m, 3),
        "zones": len(rows),
        "mean_fraction": round(float(fr.mean()), 4),
        "zones_over_half": int((fr > 0.5).sum()),
        "population_exposed": int(sum(r["exposed"] for r in rows)),
    }
