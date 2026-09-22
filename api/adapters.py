"""Source adapters. Live and Scenario are interchangeable by construction.

Both drive the SAME reservoir physics, so the only difference between "real
rain" and "the judge dragged a slider" is where rainfall_mm_hr comes from.
That is the claim the digital twin makes, and it is enforced here rather than
merely asserted in a slide.
"""

from __future__ import annotations

import math
from datetime import timedelta

from world import Adapter, Mode, WorldState

GAUGE = "SYNTH-01"

# ── shared reservoir physics ─────────────────────────────────────────────
#
# Calibrated so the gauge stays in a plausible band: at a sustained 60 mm/hr
# the equilibrium rise is K_IN/K_OUT * 60 = 120 cm, i.e. the gauge tops out
# near 160 cm (1.2 m above the channel datum). The drainage time constant
# 1/K_OUT is about 170 s, so the reservoir visibly LAGS the rain instead of
# tracking it. That lag is the whole reason a 30-120 minute forecast is
# possible, so the demo must show it, not hide it.
_K_IN = 0.012      # cm of stage per (mm/hr) per second
_K_OUT = 0.006     # drainage, fraction of stage above datum per second
BASE_STAGE = 40.0


def advance_reservoir(stage_cm: float, rain_mm_hr: float, dt_s: float) -> float:
    """One linear-reservoir step. Pure."""
    stage = stage_cm + (_K_IN * rain_mm_hr - _K_OUT * (stage_cm - BASE_STAGE)) * dt_s
    return max(BASE_STAGE, stage)


# ── live-ish synthetic source ────────────────────────────────────────────
class SyntheticAdapter:
    """Half-wave rectified sine rainfall: bursts with dry spells between.

    Stands in for LiveAdapter until Open-Meteo lands in Step 5.
    """

    mode: Mode = "live"

    def __init__(self, period_s: float = 240.0, peak_mm_hr: float = 60.0) -> None:
        self.period_s = period_s
        self.peak_mm_hr = peak_mm_hr
        self._elapsed = 0.0

    def initial(self) -> WorldState:
        self._elapsed = 0.0
        return WorldState.empty(mode=self.mode).evolve(stages={GAUGE: BASE_STAGE})

    def step(self, prev: WorldState, dt_s: float) -> WorldState:
        self._elapsed += dt_s
        phase = (self._elapsed / self.period_s) * 2 * math.pi
        rain = max(0.0, math.sin(phase)) * self.peak_mm_hr
        stage = advance_reservoir(prev.stages.get(GAUGE, BASE_STAGE), rain, dt_s)
        return prev.evolve(
            t=prev.t + timedelta(seconds=dt_s),
            tick=prev.tick + 1,
            rainfall_mm_hr=rain,
            stages={GAUGE: stage},
        )


# ── operator-driven scenario ─────────────────────────────────────────────
class ScenarioAdapter:
    """Rainfall is set by the operator; the reservoir decides the water.

    Deliberately NOT a water-level slider. Dragging stage directly would skip
    the rainfall -> runoff -> stage chain that the nowcast model exists to
    predict, which is precisely the thing being judged.
    """

    mode: Mode = "scenario"

    def __init__(self, rain_mm_hr: float = 0.0) -> None:
        self.rain_mm_hr = float(rain_mm_hr)

    def initial(self) -> WorldState:
        return WorldState.empty(mode=self.mode).evolve(stages={GAUGE: BASE_STAGE})

    def step(self, prev: WorldState, dt_s: float) -> WorldState:
        stage = advance_reservoir(prev.stages.get(GAUGE, BASE_STAGE),
                                  self.rain_mm_hr, dt_s)
        return prev.evolve(
            t=prev.t + timedelta(seconds=dt_s),
            tick=prev.tick + 1,
            rainfall_mm_hr=self.rain_mm_hr,
            stages={GAUGE: stage},
        )


class LiveAdapter:
    """Step 5. Open-Meteo minutely_15 + POST /ingest sensor readings."""

    mode: Mode = "live"

    def initial(self) -> WorldState:
        raise NotImplementedError("LiveAdapter lands in Step 5")

    def step(self, prev: WorldState, dt_s: float) -> WorldState:
        raise NotImplementedError("LiveAdapter lands in Step 5")


_ADAPTERS: dict[str, type] = {
    "synthetic": SyntheticAdapter,
    "scenario": ScenarioAdapter,
    "live": LiveAdapter,
}


def build(name: str) -> Adapter:
    try:
        return _ADAPTERS[name]()
    except KeyError:
        raise ValueError(f"unknown adapter {name!r}; have {sorted(_ADAPTERS)}") from None
