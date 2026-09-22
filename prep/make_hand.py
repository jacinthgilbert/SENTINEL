"""DEM -> HAND (Height Above Nearest Drainage).

The precompute that makes the demo slider possible: once HAND exists,
stage -> inundation is a threshold comparison on a cached array (~20 ms),
rather than solving hydraulics per frame.
"""

from __future__ import annotations

import numpy as np
import rasterio

import config as C
import hydrology as H


def run() -> None:
    if C.HAND_TIF.exists():
        print("  hand.tif exists — skipping")
        return

    with rasterio.open(str(C.DEM_TIF)) as src:
        dem = src.read(1).astype("float64")
        profile = src.profile
        transform = src.transform
        nodata = src.nodata
        bounds = src.bounds

    nd = ~np.isfinite(dem)
    if nodata is not None:
        nd |= dem == nodata
    nd |= dem < -1000

    mean_lat = (bounds.bottom + bounds.top) / 2
    dx, dy = H.cell_size_m(transform, mean_lat)
    print(f"  grid {dem.shape[1]}x{dem.shape[0]}  cell ~{dx:.1f}x{dy:.1f} m  "
          f"elev {np.nanmin(dem[~nd]):.0f}-{np.nanmax(dem[~nd]):.0f} m")

    print("  filling depressions (priority-flood + eps) …")
    filled = H.fill_depressions(dem, nd)

    print("  D8 flow direction …")
    down = H.flow_direction(filled, nd, dx, dy)

    print("  flow accumulation …")
    acc = H.accumulation(down, filled, nd)

    channels = (acc > C.ACC_THRESHOLD) & ~nd
    pct = 100.0 * channels.sum() / max(1, (~nd).sum())
    print(f"  drainage network: {channels.sum():,} cells ({pct:.2f}% of valid grid)")
    if pct < 0.05:
        print("  ! sparse — consider lowering ACC_THRESHOLD in config.py")
    elif pct > 12:
        print("  ! dense — consider raising ACC_THRESHOLD in config.py")

    print("  computing HAND …")
    h = H.hand(filled, down, channels, nd)

    profile.update(dtype="float32", count=1, nodata=np.nan, compress="deflate")
    with rasterio.open(str(C.HAND_TIF), "w", **profile) as dst:
        dst.write(h.astype("float32"), 1)

    valid = h[np.isfinite(h)]
    print(f"  wrote {C.HAND_TIF.name}  min={valid.min():.1f}  "
          f"median={np.median(valid):.1f}  p95={np.percentile(valid, 95):.1f}  "
          f"max={valid.max():.1f} m")


if __name__ == "__main__":
    run()
