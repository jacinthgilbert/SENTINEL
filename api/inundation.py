"""stage -> inundation extent, by thresholding the precomputed HAND raster.

This is the step that makes the demo slider possible. HAND is computed once in
prep; at runtime "where is flooded at 1.4 m?" is a comparison on a cached
327 KB array plus a polygonisation — tens of milliseconds, fast enough to
redraw while someone drags a slider.

Pure function of stage. No DB, no clock, no network.
"""

from __future__ import annotations

import functools
import logging

import numpy as np
import rasterio
from rasterio.features import shapes

import paths

log = logging.getLogger("sentinel.inundation")

MAX_STAGE_M = 10.0
_SIMPLIFY_DEG = 1e-5          # ~1 m; drops pixel staircase without visible change
_MIN_PART_CELLS = 4           # discard speckle: isolated 1-3 cell fragments
PREWARM_CM = range(0, 301, 10)   # 0.0-3.0 m at 10 cm — the slider's working range

# Gauge zero relative to the channel bed. A reading at the datum means the
# channel is full but nothing has spilled, i.e. HAND threshold 0.
GAUGE_DATUM_CM = 40.0


def stage_from_gauge(level_cm: float) -> float:
    """Gauge reading (cm) -> water depth above the channel (m), for HAND."""
    return max(0.0, (float(level_cm) - GAUGE_DATUM_CM) / 100.0)


@functools.lru_cache(maxsize=1)
def _hand():
    """Load HAND once. Returns (array, transform, cell_area_m2, is_synthetic)."""
    if not paths.HAND_TIF.exists():
        raise FileNotFoundError(
            f"{paths.HAND_TIF} missing — run prep/run.py (or make_synthetic_dem.py)"
        )
    with rasterio.open(paths.HAND_TIF) as src:
        arr = src.read(1).astype("float32")
        transform = src.transform
        lat = (src.bounds.bottom + src.bounds.top) / 2

    # degrees -> m^2 at this latitude
    dx = abs(transform.a) * 111_320.0 * float(np.cos(np.radians(lat)))
    dy = abs(transform.e) * 111_320.0
    log.info("HAND loaded %s cell=%.1fx%.1f m", arr.shape, dx, dy)
    return arr, transform, dx * dy, paths.SYNTHETIC_FLAG.exists()


def clamp(stage_m: float) -> float:
    return float(min(max(stage_m, 0.0), MAX_STAGE_M))


def stats(stage_m: float) -> dict:
    """Flooded area at this stage. Cheap — no polygonisation."""
    arr, _, cell_m2, synthetic = _hand()
    s = clamp(stage_m)
    mask = np.isfinite(arr) & (arr <= s)
    cells = int(mask.sum())
    return {
        "stage_m": round(s, 3),
        "flooded_cells": cells,
        "flooded_km2": round(cells * cell_m2 / 1e6, 4),
        "synthetic_terrain": synthetic,
    }


@functools.lru_cache(maxsize=256)
def extent(stage_cm: int) -> dict:
    """GeoJSON of the flooded area. Keyed on whole cm so slider drags hit cache."""
    arr, transform, cell_m2, synthetic = _hand()
    s = clamp(stage_cm / 100.0)

    mask = (np.isfinite(arr) & (arr <= s)).astype("uint8")
    features = []
    if mask.any():
        from shapely.geometry import shape
        from shapely.geometry import mapping

        min_area_deg2 = _MIN_PART_CELLS * abs(transform.a) * abs(transform.e)
        for geom, value in shapes(mask, mask=mask.astype(bool), transform=transform):
            if value != 1:
                continue
            g = shape(geom)
            if g.area < min_area_deg2:        # speckle: not real, and costly to ship
                continue
            g = g.simplify(_SIMPLIFY_DEG, preserve_topology=True)
            if g.is_empty:
                continue
            features.append({"type": "Feature", "properties": {}, "geometry": mapping(g)})

    cells = int(mask.sum())
    return {
        "type": "FeatureCollection",
        "properties": {
            "stage_m": round(s, 3),
            "flooded_km2": round(cells * cell_m2 / 1e6, 4),
            "parts": len(features),
            "synthetic_terrain": synthetic,
        },
        "features": features,
    }


def prewarm() -> int:
    """Fill the extent cache so no slider position ever pays the cold cost."""
    n = 0
    for cm in PREWARM_CM:
        try:
            extent(cm)
            n += 1
        except FileNotFoundError:
            return 0
    log.info("prewarmed %d inundation levels", n)
    return n
