"""Road graph + critical facilities from OpenStreetMap (free, no key)."""

from __future__ import annotations

import geopandas as gpd
import networkx as nx
import osmnx as ox

import config as C

FACILITY_TAGS = {
    "amenity": ["hospital", "clinic", "school", "college", "community_centre", "shelter"],
    "emergency": ["shelter"],
    "building": ["civic"],
}

KIND_MAP = {
    "hospital": "hospital",
    "clinic": "hospital",
    "school": "school",
    "college": "school",
    "shelter": "shelter",
    "community_centre": "shelter",
    "civic": "shelter",
}

# OSM in Visakhapatnam tags almost no emergency=shelter. In practice Andhra
# Pradesh designates schools and community halls as relief centres during
# cyclones and floods, so those are marked shelter-capable rather than
# inventing shelters that do not exist. Capacity is a per-type default, NOT
# surveyed data — say so in the pitch.
DEFAULT_CAPACITY = {"shelter": 500, "school": 300, "hospital": 0}
SHELTER_CAPABLE = {"shelter", "school"}


def run() -> None:
    bbox = (C.BBOX["west"], C.BBOX["south"], C.BBOX["east"], C.BBOX["north"])

    # ── road graph ───────────────────────────────────────────────────────
    if C.ROADS_GRAPHML.exists():
        print("  roads.graphml exists — skipping graph")
        G = ox.load_graphml(str(C.ROADS_GRAPHML))
    else:
        print("  downloading drivable network …")
        G = ox.graph_from_bbox(bbox, network_type="drive")
        G = ox.add_edge_speeds(G)
        G = ox.add_edge_travel_times(G)
        ox.save_graphml(G, str(C.ROADS_GRAPHML))

    n_comp = nx.number_weakly_connected_components(G)
    print(f"  graph: {G.number_of_nodes():,} nodes  {G.number_of_edges():,} edges  "
          f"{n_comp} component(s)")
    if n_comp > 1:
        big = max(nx.weakly_connected_components(G), key=len)
        stranded = G.number_of_nodes() - len(big)
        print(f"  ! {stranded} nodes outside the largest component — routing will "
              f"strand them. Step 7 falls back to the largest component.")

    # ── road segments for PostGIS ────────────────────────────────────────
    if not C.ROADS_GEOJSON.exists():
        edges = ox.graph_to_gdfs(G, nodes=False, edges=True).reset_index()
        edges["id"] = range(1, len(edges) + 1)
        keep = ["id", "geometry"]
        for col in ("name", "highway", "travel_time"):
            if col in edges.columns:
                edges[col] = edges[col].astype(str)
                keep.append(col)
        edges[keep].to_file(C.ROADS_GEOJSON, driver="GeoJSON")
        print(f"  wrote {C.ROADS_GEOJSON.name}  {len(edges):,} segments")

    # ── facilities ───────────────────────────────────────────────────────
    if C.FACILITIES_GEOJSON.exists():
        print("  facilities.geojson exists — skipping")
        return

    print("  downloading facilities …")
    gdf = ox.features_from_bbox(bbox, FACILITY_TAGS).copy()
    # Centroid in a metric CRS, then back to WGS84 (geographic centroids are wrong).
    metric = gdf.estimate_utm_crs()
    gdf["geometry"] = gdf.geometry.to_crs(metric).centroid.to_crs(gdf.crs)

    def classify(row) -> str | None:
        for col in ("emergency", "amenity", "building"):
            v = row.get(col)
            if isinstance(v, str) and v in KIND_MAP:
                return KIND_MAP[v]
        return None

    gdf["kind"] = gdf.apply(classify, axis=1)
    gdf = gdf[gdf["kind"].notna()]
    gdf["name"] = gdf.get("name", "").fillna("unnamed")
    gdf["capacity"] = gdf["kind"].map(DEFAULT_CAPACITY).fillna(0).astype(int)
    gdf["is_shelter"] = gdf["kind"].isin(SHELTER_CAPABLE)

    out = gpd.GeoDataFrame(
        gdf[["kind", "name", "capacity", "is_shelter", "geometry"]].reset_index(drop=True),
        crs=gdf.crs,
    )
    out.to_file(C.FACILITIES_GEOJSON, driver="GeoJSON")
    counts = "  ".join(f"{k}={v}" for k, v in out["kind"].value_counts().items())
    shelters = int(out["is_shelter"].sum())
    cap = int(out.loc[out["is_shelter"], "capacity"].sum())
    print(f"  wrote {C.FACILITIES_GEOJSON.name}  {counts}")
    print(f"  shelter-capable: {shelters} sites, ~{cap:,} places")


if __name__ == "__main__":
    run()
