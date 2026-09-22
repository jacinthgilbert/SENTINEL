"""Flood nowcast at +30/60/90/120 min, with calibrated bands and exact
Shapley attributions.

Pure function of a rolling history. No DB, no clock, no network — so scenario
and live mode produce forecasts through identical code.

On explainability: the `shap` package depends on numba, which has no wheel on
every platform a teammate might use. With only 10 features we can enumerate
all 2^10 coalitions directly, which yields EXACT Shapley values under the
interventional (marginal) expectation — the same quantity TreeSHAP estimates,
computed by definition rather than by approximation.
"""

from __future__ import annotations

import functools
import logging
import math
import pickle
from collections import deque
from itertools import combinations

import numpy as np

import paths
from adapters import BASE_STAGE

log = logging.getLogger("sentinel.nowcast")

STEP_MIN = 5
STEP_S = STEP_MIN * 60
HORIZONS_MIN = (30, 60, 90, 120)
MAX_HISTORY = 24 * 60 // STEP_MIN          # 288 buckets = 24 h
N_BACKGROUND = 32                          # coalitions x background per explain

MODELS_PKL = paths.DATA / "nowcast" / "models.pkl"
REPORT_JSON = paths.DATA / "nowcast" / "report.json"

# Human labels for the explanation sentence.
LABELS = {
    "rain_now": "rainfall now",
    "rain_1h": "rain over the last hour",
    "rain_3h": "rain over the last 3 hours",
    "rain_24h": "rain over the last 24 hours",
    "stage_cm": "current water level",
    "d_stage_30m": "rise over the last 30 min",
    "d_stage_60m": "rise over the last hour",
    "rain_fc_30m": "forecast rain, next 30 min",
    "rain_fc_60m": "forecast rain, next hour",
    "rain_fc_120m": "forecast rain, next 2 hours",
}
UNITS = {
    "rain_now": "mm/hr", "rain_1h": "mm/hr", "rain_3h": "mm/hr", "rain_24h": "mm/hr",
    "stage_cm": "cm", "d_stage_30m": "cm", "d_stage_60m": "cm",
    "rain_fc_30m": "mm/hr", "rain_fc_60m": "mm/hr", "rain_fc_120m": "mm/hr",
}


@functools.lru_cache(maxsize=1)
def _bundle():
    if not MODELS_PKL.exists():
        raise FileNotFoundError(
            f"{MODELS_PKL} missing — run: .venv/bin/python prep/train_nowcast.py"
        )
    with open(MODELS_PKL, "rb") as fh:
        b = pickle.load(fh)
    log.info("nowcast models loaded (%d features)", len(b["features"]))
    return b


class History:
    """Resamples the tick stream into 5-minute world-time buckets.

    The model was trained at STEP_MIN resolution, so the runtime must present
    features at exactly that resolution regardless of tick rate or sim speed.
    """

    def __init__(self) -> None:
        self.buckets: deque[tuple[float, float]] = deque(maxlen=MAX_HISTORY)  # (rain, stage)
        self._acc_s = 0.0
        self._acc_rain = 0.0
        self._last_stage = 0.0
        self._last_rain = 0.0

    def reset(self, stage_cm: float = BASE_STAGE) -> None:
        """Warm-start with a dry antecedent day.

        Without this the model needs 13 five-minute buckets before it will
        answer — 6.5 real minutes at 10x speed, which no demo and no operator
        restart can afford. Pre-filling the full 24 h window with "it was dry
        and the channel was at datum" is both the realistic pre-storm state
        and exactly how training sequences begin, so the feature windows are
        in-distribution from the first tick instead of being computed over a
        handful of samples.
        """
        self.buckets.clear()
        for _ in range(MAX_HISTORY):
            self.buckets.append((0.0, stage_cm))
        self._acc_s = 0.0
        self._acc_rain = 0.0

    def observe(self, rain_mm_hr: float, stage_cm: float, dt_world_s: float) -> None:
        self._acc_rain += rain_mm_hr * dt_world_s
        self._acc_s += dt_world_s
        self._last_stage = stage_cm
        self._last_rain = rain_mm_hr
        while self._acc_s >= STEP_S:
            self.buckets.append((self._acc_rain / self._acc_s, stage_cm))
            self._acc_rain = 0.0
            self._acc_s = 0.0

    @property
    def ready(self) -> bool:
        return len(self.buckets) >= 60 // STEP_MIN + 1        # need >= 1 h

    def _partial(self) -> tuple[float, float] | None:
        """The bucket currently filling, as (mean rain, stage).

        Serving only completed buckets stalls the model for up to STEP_MIN of
        world time after conditions change — 60 real seconds at 5x speed, which
        is precisely the moment a warning is most valuable. The in-progress
        observation is the freshest truth available, so it is used.
        """
        if self._acc_s <= 0.0:
            return None
        return self._acc_rain / self._acc_s, self._last_stage

    def _series(self) -> list[tuple[float, float]]:
        b = list(self.buckets)
        p = self._partial()
        return b + [p] if p else b

    def _back_mean_rain(self, minutes: int) -> float:
        n = max(1, minutes // STEP_MIN)
        vals = [r for r, _ in self._series()[-n:]]
        return float(np.mean(vals)) if vals else 0.0

    def _delta_stage(self, minutes: int) -> float:
        n = max(1, minutes // STEP_MIN)
        b = self._series()
        if len(b) < 2:
            return 0.0
        return float(b[-1][1] - b[max(0, len(b) - 1 - n)][1])

    def features(self, rain_forecast_mm_hr: float) -> np.ndarray:
        """Feature vector in the trained order.

        `rain_forecast_mm_hr` stands in for a rainfall forecast. In scenario
        mode the operator's slider IS the future, so this is exact — the model
        will therefore look better in a demo than the test metrics imply. In
        live mode it comes from Open-Meteo and carries real forecast error,
        which is what the reported skill reflects.
        """
        series = self._series()
        stage = series[-1][1] if series else 0.0
        return np.asarray([[
            series[-1][0] if series else 0.0,
            self._back_mean_rain(60),
            self._back_mean_rain(180),
            self._back_mean_rain(1440),
            stage,
            self._delta_stage(30),
            self._delta_stage(60),
            rain_forecast_mm_hr,
            rain_forecast_mm_hr,
            rain_forecast_mm_hr,
        ]], dtype="float32")


# ── exact Shapley over all coalitions ────────────────────────────────────
def _shapley(model, x: np.ndarray, background: np.ndarray) -> np.ndarray:
    n = x.shape[1]
    bg = background[:N_BACKGROUND]
    masks = list(range(1 << n))

    # One batched predict for every (coalition, background row) pair.
    rows = np.repeat(bg[None, :, :], len(masks), axis=0)          # (2^n, B, n)
    for mi, m in enumerate(masks):
        idx = [i for i in range(n) if m & (1 << i)]
        if idx:
            rows[mi][:, idx] = x[0, idx]
    preds = model.predict(rows.reshape(-1, n)).reshape(len(masks), len(bg))
    v = preds.mean(axis=1)                                         # v(S) per coalition

    fact = [math.factorial(k) for k in range(n + 1)]
    phi = np.zeros(n)
    for i in range(n):
        others = [j for j in range(n) if j != i]
        for k in range(n):
            w = fact[k] * fact[n - k - 1] / fact[n]
            for comb in combinations(others, k):
                s = 0
                for j in comb:
                    s |= 1 << j
                phi[i] += w * (v[s | (1 << i)] - v[s])
    return phi


def predict(history: History, rain_forecast_mm_hr: float) -> dict:
    b = _bundle()
    models, feats, calib = b["models"], b["features"], b["calibration"]

    if not history.ready:
        return {"ready": False, "reason": "need at least 1 h of history",
                "buckets": len(history.buckets)}

    x = history.features(rain_forecast_mm_hr)
    stage_now = float(x[0, feats.index("stage_cm")])

    out = []
    clamped = False
    for h in HORIZONS_MIN:
        p50 = float(models[(h, 0.5)].predict(x)[0])
        lam = float(calib[h])
        p10 = p50 - lam * (p50 - float(models[(h, 0.1)].predict(x)[0]))
        p90 = p50 + lam * (float(models[(h, 0.9)].predict(x)[0]) - p50)

        # The channel bed is a hard floor: the gauge cannot read below its
        # datum. A model is free to be wrong, but it is not free to be
        # physically impossible, and a negative depth on screen destroys
        # credibility faster than a wide band ever would.
        lo, mid, hi = (max(BASE_STAGE, stage_now + d) for d in (p10, p50, p90))
        if min(stage_now + p10, stage_now + p50) < BASE_STAGE:
            clamped = True

        out.append({
            "horizon_min": h,
            "delta_p50_cm": round(mid - stage_now, 1),
            "stage_p10_cm": round(lo, 1),
            "stage_p50_cm": round(mid, 1),
            "stage_p90_cm": round(hi, 1),
            "band_width_cm": round(hi - lo, 1),
        })

    return {"ready": True, "stage_now_cm": round(stage_now, 1), "horizons": out,
            "clamped_to_channel_bed": clamped,
            "features": {k: round(float(v), 2) for k, v in zip(feats, x[0])}}


def explain(history: History, rain_forecast_mm_hr: float, horizon_min: int = 60) -> dict:
    """Exact Shapley attribution for the median forecast at one horizon."""
    b = _bundle()
    models, feats = b["models"], b["features"]
    if not history.ready:
        return {"ready": False}

    x = history.features(rain_forecast_mm_hr)
    model = models[(horizon_min, 0.5)]
    phi = _shapley(model, x, b["background"])
    base = float(model.predict(b["background"][:N_BACKGROUND]).mean())
    total = float(np.abs(phi).sum()) or 1.0

    contribs = sorted(
        (
            {
                "feature": f,
                "label": LABELS.get(f, f),
                "value": round(float(x[0, i]), 1),
                "unit": UNITS.get(f, ""),
                "phi_cm": round(float(phi[i]), 2),
                "share": round(float(abs(phi[i]) / total), 3),
            }
            for i, f in enumerate(feats)
        ),
        key=lambda d: -abs(d["phi_cm"]),
    )
    return {
        "ready": True,
        "horizon_min": horizon_min,
        "baseline_cm": round(base, 2),
        "prediction_cm": round(base + float(phi.sum()), 2),
        "contributions": contribs,
        "method": "exact Shapley, all 2^10 coalitions, 32-sample background",
    }
