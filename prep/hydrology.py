"""Self-contained D8 hydrology: depression filling, flow routing, HAND.

Replaces pysheds. Two reasons: llvmlite/numba has no wheel on every platform a
teammate might use, and pysheds is GPL-3.0 while the rest of this project is
not. ~150 lines of numpy, no compiled extensions.

Algorithms:
  · Priority-Flood + epsilon  (Barnes, Lehman & Mulla 2014) for depression fill
  · D8 steepest descent       (O'Callaghan & Mark 1984) for flow direction
  · HAND                      (Rennó et al. 2008; Nobre et al. 2011)
"""

from __future__ import annotations

import heapq

import numpy as np

# 8 neighbours: (row offset, col offset)
_NB = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
_EPS = 1e-4          # metres; guarantees a strictly descending path off flats


def fill_depressions(dem: np.ndarray, nodata_mask: np.ndarray) -> np.ndarray:
    """Priority-Flood with epsilon gradient.

    Every valid cell ends up with a strictly descending path to the edge, so D8
    can never dead-end in a pit or a flat.
    """
    rows, cols = dem.shape
    filled = dem.astype("float64", copy=True)
    closed = nodata_mask.copy()
    heap: list[tuple[float, int, int]] = []

    # Seed with every valid cell on the border or touching nodata.
    for r in range(rows):
        for c in range(cols):
            if closed[r, c]:
                continue
            edge = r in (0, rows - 1) or c in (0, cols - 1)
            if not edge:
                edge = any(
                    nodata_mask[r + dr, c + dc]
                    for dr, dc in _NB
                    if 0 <= r + dr < rows and 0 <= c + dc < cols
                )
            if edge:
                heapq.heappush(heap, (float(filled[r, c]), r, c))
                closed[r, c] = True

    while heap:
        z, r, c = heapq.heappop(heap)
        for dr, dc in _NB:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols) or closed[nr, nc]:
                continue
            closed[nr, nc] = True
            if filled[nr, nc] <= z:
                filled[nr, nc] = z + _EPS
            heapq.heappush(heap, (float(filled[nr, nc]), nr, nc))

    return filled


def flow_direction(filled: np.ndarray, nodata_mask: np.ndarray,
                   dx_m: float, dy_m: float) -> np.ndarray:
    """D8 steepest descent. Returns a flat downstream index, -1 for sinks."""
    rows, cols = filled.shape
    down = np.full(rows * cols, -1, dtype="int64")
    dist = {
        (dr, dc): float(np.hypot(dc * dx_m, dr * dy_m)) for dr, dc in _NB
    }

    for r in range(rows):
        for c in range(cols):
            if nodata_mask[r, c]:
                continue
            z = filled[r, c]
            best, best_slope = -1, 0.0
            for dr, dc in _NB:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < rows and 0 <= nc < cols) or nodata_mask[nr, nc]:
                    continue
                drop = z - filled[nr, nc]
                if drop <= 0:
                    continue
                slope = drop / dist[(dr, dc)]
                if slope > best_slope:
                    best_slope, best = slope, nr * cols + nc
            down[r * cols + c] = best
    return down


def accumulation(down: np.ndarray, filled: np.ndarray,
                 nodata_mask: np.ndarray) -> np.ndarray:
    """Upstream cell count, by draining in order of descending elevation."""
    rows, cols = filled.shape
    acc = np.zeros(rows * cols, dtype="int64")
    valid = ~nodata_mask.ravel()
    acc[valid] = 1

    z = filled.ravel().copy()
    z[~valid] = -np.inf
    order = np.argsort(-z, kind="stable")      # highest first

    for idx in order:
        if not valid[idx]:
            continue
        d = down[idx]
        if d >= 0:
            acc[d] += acc[idx]
    return acc.reshape(rows, cols)


def hand(filled: np.ndarray, down: np.ndarray, channels: np.ndarray,
         nodata_mask: np.ndarray) -> np.ndarray:
    """Height Above Nearest Drainage.

    Each cell walks downstream to the first channel cell and records the
    elevation difference. The D8 network is a forest, so an explicit stack with
    memoisation visits every cell once.
    """
    rows, cols = filled.shape
    n = rows * cols
    flat_z = filled.ravel()
    flat_ch = channels.ravel()
    flat_nd = nodata_mask.ravel()

    outlet_z = np.full(n, np.nan)              # elevation of the receiving channel
    for idx in range(n):
        if flat_nd[idx] or not np.isnan(outlet_z[idx]):
            continue

        path: list[int] = []
        cur = idx
        while True:
            if flat_nd[cur]:
                resolved = np.nan
                break
            if flat_ch[cur]:
                resolved = flat_z[cur]
                break
            if not np.isnan(outlet_z[cur]):
                resolved = outlet_z[cur]
                break
            path.append(cur)
            nxt = down[cur]
            if nxt < 0:                        # drains off-grid: no channel found
                resolved = np.nan
                break
            cur = nxt

        for p in path:
            outlet_z[p] = resolved

    h = flat_z - outlet_z
    h[flat_ch] = 0.0
    h[flat_nd] = np.nan
    return np.maximum(h, 0.0).reshape(rows, cols)


def cell_size_m(transform, mean_lat_deg: float) -> tuple[float, float]:
    """Degrees -> metres for a geographic raster at this latitude."""
    deg_lat_m = 111_320.0
    deg_lon_m = 111_320.0 * float(np.cos(np.radians(mean_lat_deg)))
    return abs(transform.a) * deg_lon_m, abs(transform.e) * deg_lat_m
