"""The Sentinel — the contract.

WorldState is the ONLY mutable thing in the system. Every downstream module
(nowcast, inundation, risk, routing, alerts) is a pure function of it:
no DB reads, no HTTP calls, no clock access.

That is what makes scenario replay behave identically to live mode.

FROZEN AFTER STEP 1. Changing these fields means coordinating every track.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Literal, Mapping, Protocol

Mode = Literal["live", "scenario"]


@dataclass(frozen=True, slots=True)
class Report:
    """A citizen report, already scored by trust.py."""

    id: int
    lat: float
    lon: float
    depth_cm: int | None
    trust: float                     # 0..1 — below 0.5 never feeds risk
    created_at: datetime

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lat": self.lat,
            "lon": self.lon,
            "depth_cm": self.depth_cm,
            "trust": round(self.trust, 3),
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class WorldState:
    t: datetime                      # sim clock in scenario mode, wall clock in live
    tick: int
    rainfall_mm_hr: float
    stages: Mapping[str, float]      # gauge_id -> level_cm   (treat as read-only)
    blocked_roads: frozenset[int]    # OSM way ids
    reports: tuple[Report, ...]
    mode: Mode

    # ── construction ─────────────────────────────────────────────────────
    @classmethod
    def empty(cls, mode: Mode = "live") -> "WorldState":
        return cls(
            t=datetime.now(timezone.utc),
            tick=0,
            rainfall_mm_hr=0.0,
            stages={},
            blocked_roads=frozenset(),
            reports=(),
            mode=mode,
        )

    def evolve(self, **changes) -> "WorldState":
        """Return a new state. Never mutate in place."""
        return replace(self, **changes)

    # ── serialisation (the SSE + /state payload) ─────────────────────────
    def to_dict(self) -> dict:
        return {
            "t": self.t.isoformat(),
            "tick": self.tick,
            "rainfall_mm_hr": round(self.rainfall_mm_hr, 2),
            "stages": {k: round(v, 1) for k, v in self.stages.items()},
            "blocked_roads": sorted(self.blocked_roads),
            "reports": [r.to_dict() for r in self.reports],
            "mode": self.mode,
        }


class Adapter(Protocol):
    """Source of truth for a WorldState. Live and Scenario are interchangeable."""

    mode: Mode

    def initial(self) -> WorldState:
        """The world at t=0."""
        ...

    def step(self, prev: WorldState, dt_s: float) -> WorldState:
        """Advance by dt_s seconds of *world* time and return the new state."""
        ...
