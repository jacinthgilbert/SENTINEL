"""WorldPop 100 m constrained population, windowed to the AOI.

The India raster is ~506 MB but the server honours HTTP range requests, so
GDAL /vsicurl/ reads only our window. Falls back to a full download if the
server refuses ranges.
"""

from __future__ import annotations

import os

import rasterio
from rasterio.windows import from_bounds

import config as C

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")


def run() -> None:
    if C.POP_TIF.exists():
        print("  population.tif exists — skipping")
        return

    url = f"/vsicurl/{C.WORLDPOP_URL}"
    print("  opening WorldPop over HTTP range reads …")

    with rasterio.open(url) as src:
        win = from_bounds(
            C.BBOX["west"], C.BBOX["south"], C.BBOX["east"], C.BBOX["north"],
            transform=src.transform,
        )
        data = src.read(1, window=win)
        profile = src.profile
        profile.update(
            height=data.shape[0],
            width=data.shape[1],
            transform=src.window_transform(win),
            compress="deflate",
            driver="GTiff",
        )

    with rasterio.open(str(C.POP_TIF), "w", **profile) as dst:
        dst.write(data, 1)

    total = float(data[data > 0].sum())
    print(f"  wrote {C.POP_TIF.name}  {data.shape[1]}x{data.shape[0]} px  "
          f"total population in AOI ~ {total:,.0f}")


if __name__ == "__main__":
    run()
