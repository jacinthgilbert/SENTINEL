"""Dynamic evacuation routing.

Roads are not removed from the graph — edges are given an infinite cost by a
weight callable evaluated per query. That means flood state changes cost
nothing to apply: no graph rebuild, no topology recompute, so a route can be
recomputed on every slider frame.

Two behaviours worth knowing about:

  · STRANDING is reported, not hidden. If flooding cuts every path to every
    usable shelter, that is the single most important fact on the screen.
  · DEGRADED ROUTES. When no dry route exists, the router retries with flooded
    roads penalised rather than forbidden and flags the result. A hard block
    that simply fails is worse than a route labelled "risky" — people will
    move regardless, and they should move along the least-bad road.
"""

from __future__ import annotations

import functools
import logging

import networkx as nx
import numpy as np
import rasterio

import paths
import zones as zones_mod

log = logging.getLogger("sentinel.routing")

# A road is impassable once water over it reaches this depth. Below it, cars
# slow but pass; above it, most vehicles stall and pedestrians are at risk.
IMPASSABLE_DEPTH_M = 0.30
# Cost multiplier for a flooded road in a degraded (no dry route) retry.
DEGRADED_PENALTY = 25.0
SAMPLES_PER_EDGE = 3


@functools.lru_cache(maxsize=1)
def _graph():
    """Load the road graph and attach a flood threshold to every edge."""
    if not paths.DATA.joinpath("roads.graphml").exists():
        raise FileNotFoundError("data/roads.graphml missing — run make prep")

    G = nx.read_graphml(str(paths.DATA / "roads.graphml"))
    # graphml stores everything as strings
    for n, d in G.nodes(data=True):
        d["x"] = float(d["x"])
        d["y"] = float(d["y"])

    pts, index = [], []
    for u, v, k, d in G.edges(keys=True, data=True):
        try:
            d["travel_time"] = float(d.get("travel_time", 0) or 0)
        except (TypeError, ValueError):
            d["travel_time"] = 0.0
        if d["travel_time"] <= 0:
            d["travel_time"] = float(d.get("length", 50) or 50) / 8.0   # ~30 km/h

        x1, y1 = G.nodes[u]["x"], G.nodes[u]["y"]
        x2, y2 = G.nodes[v]["x"], G.nodes[v]["y"]
        for t in np.linspace(0.0, 1.0, SAMPLES_PER_EDGE):
            pts.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
        index.append((u, v, k))

    # Lowest point along the road decides when it floods.
    if paths.HAND_TIF.exists() and pts:
        with rasterio.open(paths.HAND_TIF) as src:
            vals = [float(s[0]) for s in src.sample(pts)]
        for i, (u, v, k) in enumerate(index):
            chunk = vals[i * SAMPLES_PER_EDGE:(i + 1) * SAMPLES_PER_EDGE]
            finite = [c for c in chunk if np.isfinite(c)]
            G.edges[u, v, k]["hand_m"] = min(finite) if finite else float("inf")
    else:
        for u, v, k in index:
            G.edges[u, v, k]["hand_m"] = float("inf")

    R = G.reverse(copy=True)
    log.info("road graph: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G, R


@functools.lru_cache(maxsize=1)
def _shelter_nodes() -> list[dict]:
    """Snap every shelter-capable facility to its nearest graph node."""
    G, _ = _graph()
    nodes = list(G.nodes(data=True))
    xs = np.array([d["x"] for _, d in nodes])
    ys = np.array([d["y"] for _, d in nodes])
    ids = [n for n, _ in nodes]

    out = []
    for f in zones_mod.facilities().get("features", []):
        p = f["properties"]
        if not p.get("is_shelter"):
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        i = int(np.argmin((xs - lon) ** 2 + (ys - lat) ** 2))
        out.append({"node": ids[i], "name": p.get("name") or "unnamed",
                    "capacity": int(p.get("capacity") or 0),
                    "lon": lon, "lat": lat})
    return out


def nearest_node(lat: float, lon: float) -> str:
    G, _ = _graph()
    nodes = list(G.nodes(data=True))
    xs = np.array([d["x"] for _, d in nodes])
    ys = np.array([d["y"] for _, d in nodes])
    i = int(np.argmin((xs - lon) ** 2 + (ys - lat) ** 2))
    return nodes[i][0]


def _weight(stage_m: float, degraded: bool):
    """Per-query cost. Returning None makes NetworkX skip the edge entirely.

    On a MultiDiGraph NetworkX passes a dict of PARALLEL EDGES keyed by edge
    key, not the attribute dict — so the cheapest passable parallel edge wins.
    Treating that outer dict as attributes is a KeyError waiting to happen.
    """
    cut = stage_m - IMPASSABLE_DEPTH_M

    def cost(d: dict) -> float | None:
        tt = float(d.get("travel_time", 0.0) or 0.0)
        if d.get("hand_m", float("inf")) <= cut:
            return tt * DEGRADED_PENALTY if degraded else None
        return tt

    def w(u, v, data):
        # Attribute dict (simple graph) vs key -> attribute dict (multigraph).
        if "travel_time" in data or "hand_m" in data:
            return cost(data)
        best = None
        for d in data.values():
            if not isinstance(d, dict):
                continue
            c = cost(d)
            if c is not None and (best is None or c < best):
                best = c
        return best
    return w


@functools.lru_cache(maxsize=128)
def _to_shelter(stage_cm: int, degraded: bool):
    """Multi-source Dijkstra from every usable shelter over the REVERSED graph.

    One pass answers "nearest shelter and the path to it" for every node in the
    city, which is what makes per-citizen routing a dictionary lookup.
    """
    G, R = _graph()
    stage_m = stage_cm / 100.0
    shelters = _shelter_nodes()
    usable = [s for s in shelters if s["node"] in R]
    if not usable:
        return {}, {}, []

    dist, paths_ = nx.multi_source_dijkstra(
        R, {s["node"] for s in usable}, weight=_weight(stage_m, degraded)
    )
    return dist, paths_, usable


def route(lat: float, lon: float, stage_m: float) -> dict:
    G, _ = _graph()
    origin = nearest_node(lat, lon)
    stage_cm = int(round(stage_m * 100))

    degraded = False
    dist, paths_, usable = _to_shelter(stage_cm, False)
    if origin not in paths_:
        # No dry route. Retry allowing flooded roads at heavy penalty rather
        # than telling someone in a flood that no route exists.
        degraded = True
        dist, paths_, usable = _to_shelter(stage_cm, True)

    if origin not in paths_:
        return {"ok": False, "stranded": True, "degraded": degraded,
                "reason": "no route to any usable shelter"}

    # multi_source_dijkstra on the REVERSED graph returns paths that run
    # SHELTER -> ORIGIN. The real journey is the reverse of that, so the
    # shelter is element 0 and the drawn line has to be flipped.
    node_path = list(reversed(paths_[origin]))      # origin -> ... -> shelter
    shelter_node = node_path[-1]
    shelter = next((s for s in usable if s["node"] == shelter_node), None)

    coords = [[G.nodes[n]["x"], G.nodes[n]["y"]] for n in node_path]
    flooded_crossed = 0
    if degraded:
        cut = stage_m - IMPASSABLE_DEPTH_M
        for a, b in zip(node_path, node_path[1:]):
            data = G.get_edge_data(a, b) or G.get_edge_data(b, a) or {}
            best = min((d.get("hand_m", float("inf")) for d in data.values()),
                       default=float("inf"))
            if best <= cut:
                flooded_crossed += 1

    return {
        "ok": True,
        "stranded": False,
        "degraded": degraded,
        "flooded_segments_crossed": flooded_crossed,
        "travel_time_s": round(float(dist[origin]), 1),
        "shelter": shelter,
        "geometry": {"type": "LineString", "coordinates": coords},
    }


def coverage(stage_m: float) -> dict:
    """How much of the city can still reach a shelter at all."""
    G, _ = _graph()
    stage_cm = int(round(stage_m * 100))
    dist, paths_, usable = _to_shelter(stage_cm, False)
    total = G.number_of_nodes()
    reachable = len(paths_)
    d_dist, d_paths, _ = _to_shelter(stage_cm, True)

    # Median over the DEGRADED solution, which covers nearly every node.
    # Taking it over dry-reachable nodes only is survivorship bias: as
    # flooding worsens the distant nodes become unreachable and drop out, so
    # the median FALLS and the dashboard appears to say that flooding improved
    # evacuation times. Including everyone who can still move keeps it monotonic.
    med = round(float(np.median(list(d_dist.values()))), 1) if d_dist else None
    med_dry = round(float(np.median(list(dist.values()))), 1) if dist else None

    return {
        "stage_m": round(stage_m, 3),
        "nodes_total": total,
        "reachable_dry": reachable,
        "reachable_degraded": len(d_paths),
        "stranded": total - len(d_paths),
        "usable_shelters": len(usable),
        "impassable_depth_m": IMPASSABLE_DEPTH_M,
        "median_time_to_shelter_s": med,
        "median_time_dry_routes_only_s": med_dry,
    }


def priority_routes(stage_m: float, limit: int = 8) -> dict:
    """Routes out of at-risk critical facilities, worst first.

    Hospitals before schools: a hospital holds people who cannot self-evacuate.
    """
    import facilities as facilities_mod

    fa = facilities_mod.assess(stage_m=stage_m)
    order = {"hospital": 0, "school": 1, "shelter": 2}
    at_risk = sorted(
        (f for f in fa["facilities"] if f["at_risk"] and not f["is_shelter"]),
        key=lambda f: (order.get(f["kind"], 9), f["hand_m"] if f["hand_m"] is not None else 9e9),
    )[:limit]

    out = []
    for f in at_risk:
        r = route(f["lat"], f["lon"], stage_m)
        out.append({"from": {"name": f["name"], "kind": f["kind"],
                             "lat": f["lat"], "lon": f["lon"]}, **r})
    return {"stage_m": round(stage_m, 3), "count": len(out), "routes": out}
