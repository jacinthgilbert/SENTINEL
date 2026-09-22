"""WorldPop 100 m constrained population, windowed to the AOI.

Tries a windowed read over HTTP first. WorldPop advertises `accept-ranges:
bytes` but ignores actual `Range:` headers (it answers 200 with the whole
stream instead of 206), so that usually fails — in which case we fall back to
downloading the ~506 MB India raster once and keeping it, so later runs are
instant.
"""

from __future__ import annotations

import os
import shutil

import rasterio
from rasterio.windows import from_bounds

import config as C

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

FULL_TIF = C.DATA / "worldpop_ind.tif"          # gitignored; cached between runs
_CHUNK = 1 << 20


def _window_from(src_path: str) -> None:
    with rasterio.open(src_path) as src:
        win = from_bounds(
            C.BBOX["west"], C.BBOX["south"], C.BBOX["east"], C.BBOX["north"],
            transform=src.transform,
        )
        data = src.read(1, window=win)
        profile = src.profile
        profile.update(
            height=data.shape[0], width=data.shape[1],
            transform=src.window_transform(win),
            compress="deflate", driver="GTiff",
        )
    with rasterio.open(str(C.POP_TIF), "w", **profile) as dst:
        dst.write(data, 1)

    total = float(data[data > 0].sum())
    print(f"  wrote {C.POP_TIF.name}  {data.shape[1]}x{data.shape[0]} px  "
          f"population in AOI ~ {total:,.0f}")


def _download_full() -> None:
    import requests

    tmp = FULL_TIF.with_suffix(".part")
    print(f"  downloading the full India raster (~506 MB) to {FULL_TIF.name} …")
    print("  one-time: later runs reuse it")

    with requests.get(C.WORLDPOP_URL, stream=True, timeout=(30, 120)) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        done = 0
        next_mark = 25 << 20
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(_CHUNK):
                fh.write(chunk)
                done += len(chunk)
                if done >= next_mark:
                    pct = f" ({100*done/total:.0f}%)" if total else ""
                    print(f"    {done/1e6:,.0f} MB{pct}", flush=True)
                    next_mark += 25 << 20
    shutil.move(tmp, FULL_TIF)
    print(f"  downloaded {FULL_TIF.stat().st_size/1e6:,.0f} MB")


def run() -> None:
    if C.POP_TIF.exists():
        print("  population.tif exists — skipping")
        return

    if FULL_TIF.exists():
        print(f"  using cached {FULL_TIF.name}")
        _window_from(str(FULL_TIF))
        return

    try:
        print("  trying a windowed read over HTTP …")
        _window_from(f"/vsicurl/{C.WORLDPOP_URL}")
        return
    except Exception as exc:                          # noqa: BLE001
        print(f"  windowed read unavailable ({type(exc).__name__}) — "
              f"falling back to full download")

    _download_full()
    _window_from(str(FULL_TIF))


if __name__ == "__main__":
    run()
