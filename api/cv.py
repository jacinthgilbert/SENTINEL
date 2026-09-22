"""Flood-photo classifier.

THIS IS A HEURISTIC BASELINE, NOT A TRAINED MODEL — and it says so in every
response it returns. The intended model is a ResNet/EfficientNet fine-tuned on
FloodNet-Supervised v1.0, which is a Colab job with real labels behind it.
Until those weights exist, shipping a random number dressed up as a classifier
would be worse than shipping nothing, because it would silently drive the
trust score and therefore zone risk.

So this looks at the actual pixels and applies three properties that flood
water in a ground-level photo genuinely has:

  1. It sits in the LOWER part of the frame.
  2. It is desaturated and brown/grey — silt-laden water is never vivid.
  3. It is SMOOTH relative to dry ground: standing water has far less
     high-frequency texture than tarmac, rubble or vegetation.

Confidence is capped well below 1.0. A heuristic must not be able to out-vote
the other trust components on its own.
"""

from __future__ import annotations

import io
import logging

import numpy as np

log = logging.getLogger("sentinel.cv")

MODEL_ID = "heuristic-v1"
CONFIDENCE_CAP = 0.75
MAX_PIXELS = 240            # downscale; we need statistics, not detail


def classify(image_bytes: bytes) -> dict:
    """Return {flood_confidence, model, features, trained}."""
    try:
        from PIL import Image
    except ImportError:
        return {"flood_confidence": 0.5, "model": "unavailable", "trained": False,
                "note": "Pillow not installed"}

    try:
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:                                  # noqa: BLE001
        return {"flood_confidence": 0.0, "model": MODEL_ID, "trained": False,
                "note": f"unreadable image ({type(exc).__name__})"}

    im.thumbnail((MAX_PIXELS, MAX_PIXELS))
    a = np.asarray(im, dtype="float32") / 255.0
    h, w, _ = a.shape
    if h < 8 or w < 8:
        return {"flood_confidence": 0.0, "model": MODEL_ID, "trained": False,
                "note": "image too small"}

    lower = a[int(h * 0.55):, :, :]          # where standing water would be
    upper = a[: int(h * 0.45), :, :]

    mx = lower.max(axis=2)
    mn = lower.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    val = mx

    r, g, b = lower[..., 0], lower[..., 1], lower[..., 2]
    brownish = (r >= g - 0.02) & (g >= b - 0.02)              # r >= g >= b
    muted = (sat < 0.38) & (val > 0.12) & (val < 0.92)
    water_like = float((brownish & muted).mean())

    # Smoothness: mean absolute gradient, lower half vs upper half.
    def rough(x: np.ndarray) -> float:
        gray = x.mean(axis=2)
        return float(np.abs(np.diff(gray, axis=0)).mean()
                     + np.abs(np.diff(gray, axis=1)).mean())

    r_low, r_up = rough(lower), rough(upper)
    smoothness = float(np.clip(1.0 - (r_low / max(r_up, 1e-4)), 0.0, 1.0))

    score = 0.55 * water_like + 0.45 * smoothness
    confidence = float(np.clip(score, 0.0, 1.0) * CONFIDENCE_CAP)

    return {
        "flood_confidence": round(confidence, 3),
        "model": MODEL_ID,
        "trained": False,
        "note": "colour/texture heuristic — replace with a FloodNet fine-tune",
        "features": {
            "water_like_fraction": round(water_like, 3),
            "lower_vs_upper_smoothness": round(smoothness, 3),
        },
    }
