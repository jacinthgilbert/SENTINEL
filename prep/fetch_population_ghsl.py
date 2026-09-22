"""Population from GHS-POP (JRC), windowed to the AOI.

Fallback for when data.worldpop.org is unreachable or throttled — it was
serving at 7 KB/s while this was built, roughly 20 hours for the India raster,
and it ignores HTTP Range headers so a windowed read is impossible.

GHS-POP R2023A ships as 10-degree WGS84 tiles at 3 arcsec (~95 m here), so the
one tile covering Visakhapatnam is ~20 MB rather than ~506 MB. Units are
persons per cell, same as WorldPop, so nothing downstream changes.

Source: European Commission JRC, Global Human Settlement Layer. Free and open;
attribution required.
"""

from __future__ import annotations

import io
import zipfile

import numpy as np
import rasterio
import requests
from rasterio.windows import from_bounds

import config as C

BASE = ("https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/"
        "GHS_POP_E2020_GLOBE_R2023A_4326_3ss/V1-0/tiles/"
        "GHS_POP_E2020_GLOBE_R2023A_4326_3ss_V1_0_R{r}_C{c}.zip")


def _tile_for(lat: float, lon: float) -> tuple[int, int]:
    """GHSL 10-degree tile index: R1 starts at 90N, C1 at 180W."""
    return int((90.0 - lat) // 10) + 1, int((lon + 180.0) // 10) + 1


def run() -> None:
    if C.POP_TIF.exists():
        print("  population.tif exists — skipping")
        return

    lat = (C.BBOX["south"] + C.BBOX["north"]) / 2
    lon = (C.BBOX["west"] + C.BBOX["east"]) / 2
    r, c = _tile_for(lat, lon)
    zip_path = C.DATA / f"ghs_pop_R{r}_C{c}.zip"

    if not zip_path.exists():
        url = BASE.format(r=r, c=c)
        print(f"  downloading GHS-POP tile R{r}_C{c} (~20 MB) …")
        resp = requests.get(url, timeout=(30, 600))
        resp.raise_for_status()
        zip_path.write_bytes(resp.content)
    print(f"  using {zip_path.name} ({zip_path.stat().st_size/1e6:.0f} MB)")

    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".tif")]
        if not names:
            raise SystemExit(f"no GeoTIFF inside {zip_path.name}")
        data = zf.read(names[0])

    with rasterio.open(io.BytesIO(data)) as src:
        win = from_bounds(C.BBOX["west"], C.BBOX["south"],
                          C.BBOX["east"], C.BBOX["north"], transform=src.transform)
        arr = src.read(1, window=win)
        profile = src.profile
        profile.update(height=arr.shape[0], width=arr.shape[1],
                       transform=src.window_transform(win),
                       driver="GTiff", compress="deflate")

    arr = np.where(np.isfinite(arr) & (arr > 0), arr, 0).astype("float32")
    with rasterio.open(str(C.POP_TIF), "w", **profile) as dst:
        dst.write(arr, 1)

    print(f"  wrote {C.POP_TIF.name}  {arr.shape[1]}x{arr.shape[0]} px  "
          f"population in AOI ~ {float(arr.sum()):,.0f}")
    (C.DATA / "population.SOURCE").write_text(
        f"GHS-POP E2020 R2023A, 4326 3ss, tile R{r}_C{c} (JRC GHSL). "
        "Persons per ~95 m cell. Attribution required.\n"
    )


if __name__ == "__main__":
    run()
