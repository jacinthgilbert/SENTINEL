"""Real elevation from AWS Open Data terrain tiles.

Fallback for when portal.opentopography.org is unreachable — a blocked DNS
entry, a dead key, or a blown 200-call daily quota. Same output contract as
fetch_dem.py: a float32 GeoTIFF in EPSG:4326 on the COP30 1-arcsec grid, so
every downstream stage is unchanged.

Source: s3.amazonaws.com/elevation-tiles-prod — the Terrain Tiles public
dataset (SRTM, NED, and national DEMs, depending on the region). No key, no
quota. "Terrarium" PNG encoding:

    elevation_m = (R * 256 + G + B / 256) - 32768

Tiles are Web Mercator, so the mosaic is reprojected to WGS84 rather than
being handed downstream in the wrong CRS — the HAND code computes metre cell
sizes from a geographic transform and would silently produce nonsense.
"""

from __future__ import annotations

import io
import math

import numpy as np
import rasterio
import requests
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

import config as C

BASE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
ZOOM = 13                      # ~18 m/px at this latitude; finer than COP30
ARCSEC = 1.0 / 3600.0          # output grid, matching COP30
TILE = 256


def _x(lon: float, z: int) -> int:
    return int(math.floor((lon + 180.0) / 360.0 * 2 ** z))


def _y(lat: float, z: int) -> int:
    r = math.radians(lat)
    return int(math.floor((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 2 ** z))


def _tile_bounds(x: int, y: int, z: int):
    n = 2.0 ** z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def run() -> None:
    if C.DEM_TIF.exists():
        print("  dem.tif exists — delete it (or `make fresh-terrain`) to refetch")
        return
    from PIL import Image

    x0, x1 = _x(C.BBOX["west"], ZOOM), _x(C.BBOX["east"], ZOOM)
    y0, y1 = _y(C.BBOX["north"], ZOOM), _y(C.BBOX["south"], ZOOM)
    cols, rows = x1 - x0 + 1, y1 - y0 + 1
    print(f"  {cols}x{rows} terrain tiles at z{ZOOM} (AWS Terrain Tiles, no key)")

    mosaic = np.full((rows * TILE, cols * TILE), np.nan, dtype="float32")
    got = 0
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            url = BASE.format(z=ZOOM, x=tx, y=ty)
            try:
                r = requests.get(url, timeout=60)
                r.raise_for_status()
                a = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"), dtype="float64")
            except Exception as exc:                          # noqa: BLE001
                print(f"  ! tile {ZOOM}/{tx}/{ty} failed ({type(exc).__name__})")
                continue
            elev = (a[..., 0] * 256.0 + a[..., 1] + a[..., 2] / 256.0) - 32768.0
            ry, rx = (ty - y0) * TILE, (tx - x0) * TILE
            mosaic[ry:ry + TILE, rx:rx + TILE] = elev.astype("float32")
            got += 1
    if got == 0:
        raise SystemExit("no terrain tiles fetched")
    print(f"  fetched {got}/{cols*rows} tiles")

    mw, _, _, mn = _tile_bounds(x0, y0, ZOOM)
    _, ms, me, _ = _tile_bounds(x1, y1, ZOOM)
    src_transform = from_bounds(mw, ms, me, mn, mosaic.shape[1], mosaic.shape[0])

    # Mercator mosaic -> WGS84 on the COP30 grid, cropped to the AOI.
    w, s = C.BBOX["west"], C.BBOX["south"]
    e, n = C.BBOX["east"], C.BBOX["north"]
    out_w = int(round((e - w) / ARCSEC))
    out_h = int(round((n - s) / ARCSEC))
    dst = np.full((out_h, out_w), np.nan, dtype="float32")
    dst_transform = from_bounds(w, s, e, n, out_w, out_h)

    reproject(
        source=mosaic, destination=dst,
        src_transform=src_transform, src_crs="EPSG:4326",
        dst_transform=dst_transform, dst_crs="EPSG:4326",
        resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan,
    )

    # Sea: terrain tiles give 0 or slightly negative over water. Mark it nodata
    # so flow routing drains off-grid instead of ponding in a flat ocean.
    sea = ~np.isfinite(dst) | (dst <= 0.0)
    dst[sea] = np.nan

    profile = dict(driver="GTiff", dtype="float32", count=1,
                   width=out_w, height=out_h, crs="EPSG:4326",
                   transform=dst_transform, nodata=np.nan, compress="deflate")
    C.DATA.mkdir(exist_ok=True)
    with rasterio.open(str(C.DEM_TIF), "w", **profile) as f:
        f.write(dst, 1)

    land = dst[np.isfinite(dst)]
    print(f"  wrote {C.DEM_TIF.name}  {out_w}x{out_h}  "
          f"elev {land.min():.1f}-{land.max():.1f} m  sea {100*sea.mean():.0f}%   [REAL]")
    (C.DATA / "dem.SOURCE").write_text(
        "Real elevation from AWS Terrain Tiles (elevation-tiles-prod), "
        f"terrarium z{ZOOM}, reprojected to EPSG:4326 at 1 arcsec.\n"
        "Underlying data: SRTM and national DEMs. Attribution required.\n"
    )


if __name__ == "__main__":
    run()
