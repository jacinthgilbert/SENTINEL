"""Source adapters. Step 1 ships the synthetic one only.

LiveAdapter arrives in Step 5 (Open-Meteo + sensor ingest).
ScenarioAdapter arrives in Step 4 (replay file + rainfall slider).
Both must satisfy the same Adapter protocol, so nothing downstream changes.
"""

from __future__ import annotations

import math
from datetime import timedelta

from world import Adapter, Mode, WorldState

# A single fake gauge so the loop has something to move.
GAUGE = "SYNTH-01"

# Linear-reservoir constants (placeholder physics; real model lands in Step 5).
#
# Calibrated so the gauge stays in a plausible band rather than exploding:
# at a sustained 60 mm/hr the equilibrium rise is K_IN/K_OUT * 60 = 120 cm,
# i.e. the gauge tops out near 160 cm (1.2 m above the channel datum).
# Drainage time constant 1/K_OUT is about 170 s, so the reservoir visibly lags
# the rain instead of tracking it instantly — which is the whole point of
# forecasting 30-120 minutes ahead.
_K_IN = 0.012      # cm of stage per (mm/hr) per second
_K_OUT = 0.006     # drainage, fraction of stage above datum per second
_BASE_STAGE = 40.0


class SyntheticAdapter:
    """Sine-wave rainfall driving a linear reservoir.

    Exists purely so the tick loop has observable motion before any real data.
    Deleted-or-kept as a test fixture once LiveAdapter lands.
    """

    mode: Mode = "live"

    def __init__(self, period_s: float = 240.0, peak_mm_hr: float = 60.0) -> None:
        self.period_s = period_s
        self.peak_mm_hr = peak_mm_hr

    def initial(self) -> WorldState:
        return WorldState.empty(mode=self.mode).evolve(
            stages={GAUGE: _BASE_STAGE},
        )

    def step(self, prev: WorldState, dt_s: float) -> WorldState:
        tick = prev.tick + 1
        phase = (tick * dt_s / self.period_s) * 2 * math.pi

        # half-wave rectified sine: dry spells between bursts, like real rain
        rain = max(0.0, math.sin(phase)) * self.peak_mm_hr

        stage = prev.stages.get(GAUGE, _BASE_STAGE)
        stage += (_K_IN * rain - _K_OUT * (stage - _BASE_STAGE)) * dt_s
        stage = max(_BASE_STAGE, stage)

        return prev.evolve(
            t=prev.t + timedelta(seconds=dt_s),
            tick=tick,
            rainfall_mm_hr=rain,
            stages={GAUGE: stage},
        )


class LiveAdapter:
    """Step 5. Open-Meteo minutely_15 + POST /ingest sensor readings."""

    mode: Mode = "live"

    def initial(self) -> WorldState:
        raise NotImplementedError("LiveAdapter lands in Step 5")

    def step(self, prev: WorldState, dt_s: float) -> WorldState:
        raise NotImplementedError("LiveAdapter lands in Step 5")


class ScenarioAdapter:
    """Step 4. Replay a recorded event, scaled by the rainfall slider."""

    mode: Mode = "scenario"

    def initial(self) -> WorldState:
        raise NotImplementedError("ScenarioAdapter lands in Step 4")

    def step(self, prev: WorldState, dt_s: float) -> WorldState:
        raise NotImplementedError("ScenarioAdapter lands in Step 4")


_ADAPTERS: dict[str, type] = {
    "synthetic": SyntheticAdapter,
    "live": LiveAdapter,
    "scenario": ScenarioAdapter,
}


def build(name: str) -> Adapter:
    try:
        return _ADAPTERS[name]()
    except KeyError:
        raise ValueError(f"unknown adapter {name!r}; have {sorted(_ADAPTERS)}") from None
