"""Citizen report trust scoring.

    trust = 0.40·cv_confidence
          + 0.30·reporter_history
          + 0.20·spatial_corroboration
          + 0.10·metadata_plausibility

Reports below MIN_TRUST are shown as "unverified" and never reach zone risk.

Spatial corroboration is the term that makes this defensible against a judge
asking "how do you stop false reports?". A lone report in an otherwise dry
zone scores low; three independent reports within 300 m of each other, in a
zone the model already flags as rising, score high. Cheap to compute, and it
means a single bad actor cannot move the map.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

W_CV = 0.40
W_HISTORY = 0.30
W_CORROBORATION = 0.20
W_METADATA = 0.10
assert abs(W_CV + W_HISTORY + W_CORROBORATION + W_METADATA - 1.0) < 1e-9

MIN_TRUST = 0.50
# A report may vouch for a neighbour if its REPORTER is not discredited.
# Requiring the neighbour to already be trusted deadlocks: everyone starts
# untrusted, so nobody can ever corroborate anybody and no report is ever
# verified. Standing is independent of the report being scored, which breaks
# the circularity.
MIN_HISTORY_TO_VOUCH = 0.30
CORROBORATION_RADIUS_M = 300.0
CORROBORATION_WINDOW_MIN = 30
CORROBORATION_SATURATES_AT = 3          # 3 nearby reports = full marks

NEW_REPORTER_HISTORY = 0.5              # unknown reporters start neutral
HISTORY_STEP = 0.08


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def corroboration(report, others, now: datetime,
                  history_of=None) -> tuple[float, int]:
    history_of = history_of or {}
    cutoff = now - timedelta(minutes=CORROBORATION_WINDOW_MIN)
    seen: set[str] = set()
    n = 0
    for o in others:
        if o is report or o["reporter"] == report["reporter"]:
            continue                                    # cannot vouch for yourself
        if o["reporter"] in seen:
            continue                                    # one vote per reporter
        if o["created_at"] < cutoff:
            continue
        if history_of.get(o["reporter"], NEW_REPORTER_HISTORY) < MIN_HISTORY_TO_VOUCH:
            continue                                    # discredited reporters do not count
        if haversine_m(report["lat"], report["lon"], o["lat"], o["lon"]) <= CORROBORATION_RADIUS_M:
            seen.add(o["reporter"])
            n += 1
    return min(1.0, n / CORROBORATION_SATURATES_AT), n


def metadata_plausibility(report) -> float:
    """Cheap sanity checks. Not security — just friction against junk."""
    score = 1.0
    d = report.get("depth_cm")
    if d is None:
        score -= 0.3
    elif not (0 <= d <= 400):
        score -= 0.6
    if not report.get("has_photo"):
        score -= 0.3
    return max(0.0, score)


def score(report, others, history: float, now: datetime,
          history_of=None) -> dict:
    corr, n_near = corroboration(report, others, now, history_of)
    meta = metadata_plausibility(report)
    has_photo = bool(report.get("has_photo"))
    cv_conf = float(report.get("cv_conf") or 0.0)

    # Renormalise over the components actually present. Scoring a photo-less
    # report as CV = 0 is not "no evidence", it is "evidence against" — and it
    # caps such a report at 0.6 no matter how many neighbours confirm it. A
    # missing signal should widen the others' share, not act as a penalty.
    parts = [(W_HISTORY, history), (W_CORROBORATION, corr), (W_METADATA, meta)]
    if has_photo:
        parts.append((W_CV, cv_conf))
    total_w = sum(w for w, _ in parts)
    t = sum(w * v for w, v in parts) / total_w

    return {
        "trust": round(min(1.0, max(0.0, t)), 3),
        "verified": t >= MIN_TRUST,
        "photo_submitted": has_photo,
        "components": {
            "cv_confidence": (round(cv_conf, 3) if has_photo else None),
            "reporter_history": round(history, 3),
            "spatial_corroboration": round(corr, 3),
            "metadata_plausibility": round(meta, 3),
        },
        "nearby_supporting_reports": n_near,
    }


def update_history(history: float, agreed: bool) -> float:
    """Nudge a reporter's standing after the model agrees or disagrees.

    Deliberately slow and bounded: one report should never make or break a
    reporter, and nobody can farm their way to unlimited influence.
    """
    step = HISTORY_STEP if agreed else -HISTORY_STEP * 1.5
    return float(min(0.95, max(0.05, history + step)))
