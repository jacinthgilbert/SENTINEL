"""Bulk-load the precomputed layers into PostGIS."""

from __future__ import annotations

import json
import os

import config as C

TABLES = ("zones", "facilities", "road_segments")


def _features(path):
    return json.loads(path.read_text())["features"]


def run() -> None:
    import psycopg

    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL not set")

    with psycopg.connect(url, connect_timeout=5) as conn, conn.cursor() as cur:
        for t in TABLES:
            cur.execute(f"TRUNCATE {t} CASCADE")

        # ── zones ────────────────────────────────────────────────────────
        rows = [
            (
                f["properties"]["h3"],
                json.dumps(f["geometry"]),
                f["properties"]["population"],
                f["properties"]["elderly_frac"],
                f["properties"]["hand_min_m"],
            )
            for f in _features(C.ZONES_GEOJSON)
        ]
        cur.executemany(
            "INSERT INTO zones (h3, geom, population, elderly_frac, hand_min_m) "
            "VALUES (%s, ST_GeomFromGeoJSON(%s), %s, %s, %s)",
            rows,
        )
        print(f"  zones: {len(rows)}")

        # ── facilities ───────────────────────────────────────────────────
        rows = [
            (
                f["properties"]["kind"],
                f["properties"].get("name"),
                f["properties"].get("capacity") or 0,
                json.dumps(f["geometry"]),
            )
            for f in _features(C.FACILITIES_GEOJSON)
        ]
        cur.executemany(
            "INSERT INTO facilities (kind, name, capacity, geom) "
            "VALUES (%s, %s, %s, ST_GeomFromGeoJSON(%s))",
            rows,
        )
        print(f"  facilities: {len(rows)}")

        # ── road segments ────────────────────────────────────────────────
        rows = [
            (f["properties"]["id"], json.dumps(f["geometry"]))
            for f in _features(C.ROADS_GEOJSON)
            if f["geometry"]["type"] == "LineString"
        ]
        cur.executemany(
            "INSERT INTO road_segments (id, geom) "
            "VALUES (%s, ST_GeomFromGeoJSON(%s))",
            rows,
        )
        print(f"  road_segments: {len(rows)}")

        conn.commit()


if __name__ == "__main__":
    run()
