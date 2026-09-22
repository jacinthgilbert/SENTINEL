"""H3 res-9 zones with min-HAND and population.

Aggregation trick: both rasters are small (AOI is ~8x10 km), so instead of
masking 750 hexagons against two rasters we walk the pixels once and bin them
into their H3 cell. O(pixels) instead of O(hexes x pixels).
"""

from __future__ import annotations

import json
from collections import defaultdict

import h3
import numpy as np
import rasterio

import config as C


# ── h3 v4 / v3 compatibility ─────────────────────────────────────────────
def _cell_of(lat: float, lon: float, res: int) -> str:
    try:
        return h3.latlng_to_cell(lat, lon, res)          # v4
    except AttributeError:
        return h3.geo_to_h3(lat, lon, res)               # v3


def _boundary_lonlat(cell: str) -> list[list[float]]:
    try:
        ring = h3.cell_to_boundary(cell)                 # v4 -> ((lat, lon), ...)
    except AttributeError:
        ring = h3.h3_to_geo_boundary(cell)               # v3
    coords = [[lon, lat] for lat, lon in ring]
    coords.append(coords[0])
    return coords


def _bbox_cells(res: int) -> set[str]:
    """Every H3 cell whose centre falls in the AOI. Geometry-only fallback."""
    import numpy as _np

    step = 0.0005                                        # ~55 m, finer than res 9
    lats = _np.arange(C.BBOX["south"], C.BBOX["north"], step)
    lons = _np.arange(C.BBOX["west"], C.BBOX["east"], step)
    return {_cell_of(float(la), float(lo), res) for la in lats for lo in lons}


def _bin_raster(path, res: int, how: str):
    """Walk pixel centres, bin values into H3 cells. Returns {cell: value}."""
    out: dict[str, float] = {}
    with rasterio.open(str(path)) as src:
        arr = src.read(1).astype("float64")
        nodata = src.nodata
        rows, cols = arr.shape
        # pixel-centre coordinate grids
        xs, ys = rasterio.transform.xy(
            src.transform,
            np.repeat(np.arange(rows), cols),
            np.tile(np.arange(cols), rows),
        )
        vals = arr.ravel()

    acc: dict[str, list[float]] = defaultdict(list)
    for x, y, v in zip(xs, ys, vals):
        if not np.isfinite(v):
            continue
        if nodata is not None and v == nodata:
            continue
        if how == "sum" and v <= 0:
            continue
        acc[_cell_of(y, x, res)].append(float(v))

    for cell, vs in acc.items():
        if how == "sum":
            out[cell] = float(sum(vs))
        elif how == "min":
            out[cell] = float(min(vs))
        else:                                    # "values" — keep the sample
            out[cell] = vs
    return out


DECILES = list(range(0, 101, 10))


def _hand_profile(values: list[float]) -> dict:
    """Compress a zone's HAND sample to deciles.

    Why not just the minimum: a res-9 hex covers ~117 DEM cells, and any hex
    touching a drainage line has min HAND = 0, so a min-based rule floods most
    of the city at 0.5 m. The decile curve is the zone's empirical CDF, which
    turns "is this zone flooded?" into "what FRACTION of it is under water at
    this stage?" — a graded choropleth instead of a binary one, computed at
    runtime by interpolation with no raster access.
    """
    arr = np.sort(np.asarray(values, dtype="float64"))
    return {
        "hand_deciles": [round(float(v), 2) for v in np.percentile(arr, DECILES)],
        "cells": int(arr.size),
    }


def run() -> None:
    if C.ZONES_GEOJSON.exists():
        print("  zones.geojson exists — skipping")
        return

    # Either raster may be absent (a download that has not run yet). Build what
    # we can; re-run after the missing file lands and zones.geojson is rebuilt.
    hand_min: dict[str, float] = {}
    pop_sum: dict[str, float] = {}

    hand_vals: dict[str, list[float]] = {}
    if C.HAND_TIF.exists():
        print("  binning HAND into H3 cells …")
        hand_vals = _bin_raster(C.HAND_TIF, C.H3_RES, how="values")
        hand_min = {k: float(min(v)) for k, v in hand_vals.items()}
    else:
        print(f"  ! {C.HAND_TIF.name} missing — hand_min_m will be null")

    if C.POP_TIF.exists():
        print("  binning population into H3 cells …")
        pop_sum = _bin_raster(C.POP_TIF, C.H3_RES, how="sum")
    else:
        print(f"  ! {C.POP_TIF.name} missing — population will be 0")

    cells = sorted(set(hand_vals) | set(pop_sum))
    if not cells:
        print("  ! no raster available — falling back to bbox fill "
              "(geometry only, no attributes)")
        cells = sorted(_bbox_cells(C.H3_RES))
    features = []
    for cell in cells:
        pop = int(round(pop_sum.get(cell, 0.0)))
        props = {
            "h3": cell,
            "population": pop,
            "elderly_frac": C.ELDERLY_FRAC_DEFAULT,
            "hand_min_m": (round(hand_min[cell], 2) if cell in hand_min else None),
        }
        if cell in hand_vals:
            props.update(_hand_profile(hand_vals[cell]))
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [_boundary_lonlat(cell)]},
        })

    C.ZONES_GEOJSON.write_text(
        json.dumps({"type": "FeatureCollection", "features": features})
    )

    total_pop = sum(f["properties"]["population"] for f in features)
    with_hand = sum(1 for f in features if f["properties"].get("hand_deciles"))
    print(f"  wrote {C.ZONES_GEOJSON.name}  {len(features)} zones  "
          f"{with_hand} with HAND profile  population {total_pop:,}")

    if with_hand:
        for stage in (0.5, 1.0, 2.0, 3.0):
            frac = []
            for f in features:
                d = f["properties"].get("hand_deciles")
                if d:
                    frac.append(float(np.interp(stage, d, np.linspace(0, 1, len(d)))))
            heavy = sum(1 for v in frac if v > 0.5)
            print(f"    stage {stage:>4.1f} m -> mean {100*np.mean(frac):4.1f}% of "
                  f"each zone under water, {heavy} zones >50% flooded")


if __name__ == "__main__":
    run()
