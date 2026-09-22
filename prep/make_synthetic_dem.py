"""Synthetic stand-in DEM, georeferenced to the real AOI.

Lets every downstream stage — HAND, zones, inundation, the map — run and be
tested before the real COP30 download lands. Same grid, same CRS, same
transform as COP30 would produce, so when dem.tif arrives NOTHING else changes:
delete hand.tif and zones.geojson, re-run, and real numbers flow through.

Shape is a coastal city like Visakhapatnam: sea to the east, ridges inland,
two valleys draining seaward. It is NOT real terrain and must never be shown
to judges as such.
"""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.transform import from_bounds

import config as C

ARCSEC = 1.0 / 3600.0          # COP30 native resolution


def run() -> None:
    if C.DEM_TIF.exists():
        print("  dem.tif exists (real or synthetic) — skipping")
        return

    w, s = C.BBOX["west"], C.BBOX["south"]
    e, n = C.BBOX["east"], C.BBOX["north"]
    cols = int(round((e - w) / ARCSEC))
    rows = int(round((n - s) / ARCSEC))

    # normalised coords: x east-west (0 = west/inland, 1 = east/coast), y north-south
    x = np.linspace(0.0, 1.0, cols)[None, :]
    y = np.linspace(0.0, 1.0, rows)[:, None]

    # inland plateau falling to sea level in the east
    # -4 m at the eastern edge so the coast becomes sea (nodata), not a flat
    # plain that would otherwise route flow like an inland lake.
    z = np.broadcast_to(90.0 * (1.0 - x) ** 1.6 - 4.0, (rows, cols)).copy()

    # two ridges
    z += 55.0 * np.exp(-(((x - 0.22) / 0.10) ** 2)) * (0.6 + 0.4 * np.cos(4 * np.pi * y))
    z += 38.0 * np.exp(-(((x - 0.55) / 0.08) ** 2)) * (0.5 + 0.5 * np.sin(3 * np.pi * y))

    # two valleys cutting seaward, incised into the slope
    for y0, depth, width in ((0.32, 26.0, 0.055), (0.68, 22.0, 0.045)):
        axis = y0 + 0.05 * np.sin(2.2 * np.pi * x)          # meandering
        z -= depth * np.exp(-(((y - axis) / width) ** 2)) * (0.25 + 0.75 * x)

    # gentle texture so flow routing has something to work with
    rng = np.random.default_rng(17)
    z += rng.normal(0.0, 0.35, size=(rows, cols))

    sea = z < 0.0
    z = z.astype("float32")
    z[sea] = np.nan                      # sea -> nodata, flow drains off-grid

    transform = from_bounds(w, s, e, n, cols, rows)
    profile = dict(
        driver="GTiff", dtype="float32", count=1, width=cols, height=rows,
        crs="EPSG:4326", transform=transform, nodata=np.nan, compress="deflate",
    )
    C.DATA.mkdir(exist_ok=True)
    with rasterio.open(str(C.DEM_TIF), "w", **profile) as dst:
        dst.write(z, 1)

    (C.DATA / "dem.SYNTHETIC").write_text(
        "dem.tif is SYNTHETIC terrain, not real Visakhapatnam elevation.\n"
        "Delete dem.tif, hand.tif, zones.geojson and re-run prep to replace it.\n"
    )
    land = z[np.isfinite(z)]
    print(f"  wrote {C.DEM_TIF.name}  {cols}x{rows}  "
          f"elev {land.min():.1f}-{land.max():.1f} m  "
          f"sea {100*sea.mean():.0f}%   [SYNTHETIC]")


if __name__ == "__main__":
    run()
