"""Step 2 configuration — Visakhapatnam."""

from __future__ import annotations

import os
from pathlib import Path

# ── area of interest ─────────────────────────────────────────────────────
# City core plus the low-lying northern stretch. ~7.8 x 9.5 km.
BBOX = dict(south=17.690, north=17.760, west=83.200, east=83.290)
CITY = "Visakhapatnam"

H3_RES = 9                      # ~174 m edge, ~0.105 km^2 per hex

# ── data sources (all free) ──────────────────────────────────────────────
OPENTOPO_URL = "https://portal.opentopography.org/API/globaldem"
DEM_TYPE = "COP30"              # Copernicus 30 m: newer, fewer voids than raw SRTM

# WorldPop 100 m constrained 2020, India. ~506 MB, but it serves HTTP range
# requests, so GDAL /vsicurl/ reads only our window.
WORLDPOP_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained"
    "/2020/BSGM/IND/ind_ppp_2020_constrained.tif"
)

# Share of population aged 60+, Andhra Pradesh (Census 2011 order of magnitude).
# Placeholder until a real age-structure raster is wired in — see README caveat.
ELDERLY_FRAC_DEFAULT = 0.10

# Cells of flow accumulation before a pixel counts as channel. Tune if the
# drainage network comes out too sparse or too dense for the terrain.
ACC_THRESHOLD = 200

# ── paths ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

DEM_TIF = DATA / "dem.tif"
HAND_TIF = DATA / "hand.tif"
POP_TIF = DATA / "population.tif"
ROADS_GRAPHML = DATA / "roads.graphml"
ROADS_GEOJSON = DATA / "road_segments.geojson"
FACILITIES_GEOJSON = DATA / "facilities.geojson"
ZONES_GEOJSON = DATA / "zones.geojson"


def api_key() -> str:
    key = os.getenv("OPENTOPO_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "OPENTOPO_API_KEY not set.\n"
            "  export $(grep -v '^#' .env | xargs)   # or use python-dotenv"
        )
    return key
