#!/usr/bin/env python
"""Step 2 orchestrator. Idempotent — every stage skips if its output exists.

    python prep/run.py            # everything, load included if DB is up
    python prep/run.py --no-load  # artifacts only
"""

from __future__ import annotations

import sys
import time

import config as C

STAGES = [
    ("DEM (Copernicus COP30)", "fetch_dem"),
    ("HAND (pysheds)", "make_hand"),
    ("Roads + facilities (OSM)", "fetch_osm"),
    ("Population (WorldPop 100 m)", "fetch_population"),
    ("Zones (H3 res-9)", "make_zones"),
]


def main() -> int:
    print(f"\nThe Sentinel — Step 2 geo prep · {C.CITY}")
    print(f"bbox  S{C.BBOX['south']} N{C.BBOX['north']} "
          f"W{C.BBOX['west']} E{C.BBOX['east']}\n")

    blocked: list[tuple[str, str]] = []
    for label, mod_name in STAGES:
        print(f"[{label}]")
        t0 = time.time()
        try:
            mod = __import__(mod_name)
            mod.run()
            print(f"  done in {time.time() - t0:.1f}s\n")
        except Exception as exc:                        # noqa: BLE001
            blocked.append((label, f"{type(exc).__name__}: {exc}"))
            print(f"  BLOCKED: {type(exc).__name__}: {str(exc)[:200]}")
            print("  continuing — later stages degrade rather than abort\n")

    if "--no-load" in sys.argv:
        print("skipping PostGIS load (--no-load)")
        return 0

    print("[PostGIS load]")
    try:
        import load

        load.run()
        print("  done\n")
    except Exception as exc:                            # noqa: BLE001
        print(f"  skipped: {type(exc).__name__}: {exc}")
        print("  (start the DB with `docker compose up -d db`, then "
              "`python prep/load.py`)\n")

    print("Artifacts:")
    for p in (C.DEM_TIF, C.HAND_TIF, C.POP_TIF, C.ROADS_GRAPHML,
              C.ROADS_GEOJSON, C.FACILITIES_GEOJSON, C.ZONES_GEOJSON):
        mark = "ok" if p.exists() else "--"
        size = f"{p.stat().st_size/1e6:7.2f} MB" if p.exists() else "        "
        print(f"  [{mark}] {size}  {p.name}")

    if blocked:
        print("\nBlocked stages (re-run `python prep/run.py` once fixed):")
        for label, err in blocked:
            print(f"  · {label}: {err[:160]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
