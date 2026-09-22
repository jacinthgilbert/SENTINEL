"""Where the precomputed artifacts live: /data in Docker, ../data locally."""

from __future__ import annotations

import os
from pathlib import Path

_env = os.getenv("DATA_DIR")
if _env:
    DATA = Path(_env)
elif Path("/data").is_dir():
    DATA = Path("/data")
else:
    DATA = Path(__file__).resolve().parent.parent / "data"

HAND_TIF = DATA / "hand.tif"
ZONES_GEOJSON = DATA / "zones.geojson"
FACILITIES_GEOJSON = DATA / "facilities.geojson"
SYNTHETIC_FLAG = DATA / "dem.SYNTHETIC"
