"""Verify the D8/HAND implementation against terrain with a known answer.

Run:  python prep/tests/test_hydrology.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hydrology as H  # noqa: E402

N = 60
AXIS = 30
WALL_SLOPE = 0.8        # m of rise per cell away from the valley axis
DOWN_SLOPE = 0.05       # m of fall per cell going south


def valley() -> np.ndarray:
    r, c = np.meshgrid(np.arange(N), np.arange(N), indexing="ij")
    return 50.0 + WALL_SLOPE * np.abs(c - AXIS) + DOWN_SLOPE * (N - r)


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")
    return cond


def main() -> int:
    ok = True
    nd = np.zeros((N, N), dtype=bool)

    # ── 1. depression filling removes a pit ──────────────────────────────
    dem = valley()
    dem[40, AXIS] -= 12.0                       # carve a 12 m pit in the channel
    filled = H.fill_depressions(dem, nd)
    ok &= check(
        "pit is filled",
        filled[40, AXIS] > dem[40, AXIS] + 10,
        f"{dem[40, AXIS]:.2f} -> {filled[40, AXIS]:.2f} m",
    )
    ok &= check(
        "filling never lowers terrain",
        bool((filled >= dem - 1e-9).all()),
    )

    # ── 2. flow routing on the clean valley ──────────────────────────────
    dem = valley()
    filled = H.fill_depressions(dem, nd)
    down = H.flow_direction(filled, nd, 30.0, 30.0)

    interior = np.ones((N, N), dtype=bool)
    interior[0, :] = interior[-1, :] = interior[:, 0] = interior[:, -1] = False
    ok &= check(
        "every interior cell has a downstream neighbour",
        bool((down.reshape(N, N)[interior] >= 0).all()),
    )

    acc = H.accumulation(down, filled, nd)
    axis_share = acc[:, AXIS].sum() / acc.sum()
    ok &= check(
        "flow concentrates on the valley axis",
        axis_share > 0.20,
        f"{axis_share:.0%} of accumulation on 1 of {N} columns",
    )

    # ── 3. HAND ──────────────────────────────────────────────────────────
    channels = (acc > 200) & ~nd
    ok &= check("a drainage network forms", channels.sum() > 0,
                f"{channels.sum()} channel cells")

    hand = H.hand(filled, down, channels, nd)

    ok &= check("HAND is zero on channel cells",
                bool(np.allclose(hand[channels], 0.0)))
    ok &= check("HAND is never negative",
                bool(np.nanmin(hand) >= 0.0), f"min={np.nanmin(hand):.3f}")

    mid = slice(20, 40)                          # avoid top/bottom edge effects
    for k in (3, 5, 8):
        got = float(np.nanmean(hand[mid, AXIS + k]))
        want = WALL_SLOPE * k
        ok &= check(
            f"HAND at {k} cells up the valley wall ~ {want:.1f} m",
            abs(got - want) < max(1.0, 0.35 * want),
            f"got {got:.2f} m",
        )

    rising = [float(np.nanmean(hand[mid, AXIS + k])) for k in range(1, 12)]
    ok &= check("HAND increases monotonically away from the channel",
                all(b >= a - 1e-6 for a, b in zip(rising, rising[1:])))

    print("\n" + ("all checks passed" if ok else "FAILURES — do not trust hand.tif"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
