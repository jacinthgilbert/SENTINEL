"""Alert generation and dispatch.

Produces CAP 1.2 documents with one <info> block per language, then fans out to
channels. The simulated channel is always on so the demo cannot be broken by a
carrier, an expired sandbox or conference wifi; Twilio activates automatically
when credentials are present, through the same code path.

Two details that matter more than they look:

  · DEBOUNCE. A zone must hold a severity for two consecutive evaluations
    before it fires. Without it, dragging the rainfall slider back and forth
    sends dozens of alerts and a judge's phone melts.
  · CAP status Exercise. In scenario mode every document is marked
    <status>Exercise</status>, which is the field CAP provides for drills.
    Emitting Actual from a simulation would be indefensible.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

import i18n
import zones as zones_mod

log = logging.getLogger("sentinel.alerts")

SENDER = "sentinel@vizag.local"
DEBOUNCE_TICKS = 2
OUTBOX_MAX = 60
RESEND_AFTER_S = 900            # do not re-alert the same zone inside 15 min

# A cloudburst can push 200+ hexes over threshold in one cycle. Sending a
# message per hex is operationally wrong — it floods the channel, burns the
# Twilio quota and trains people to ignore alerts. Highest severity first,
# the rest are counted and reported rather than silently dropped. Production
# would aggregate contiguous hexes into wards instead.
MAX_PER_CYCLE = 25

SEVERITY_CAP = {"warning": "Severe", "watch": "Moderate", "advisory": "Minor"}
URGENCY_CAP = {"warning": "Immediate", "watch": "Expected", "advisory": "Future"}
RANK = {"advisory": 1, "watch": 2, "warning": 3}


def certainty_from_quantiles(stage_now_cm: float, p10_cm: float, p50_cm: float) -> str:
    """CAP <certainty> from the forecast quantiles.

    Certainty in CAP is about whether the EVENT happens, not how precisely its
    magnitude is known. Deriving it from interval WIDTH produced the absurd
    combination <severity>Severe</severity><certainty>Unlikely</certainty>
    during a cloudburst, because heavy rain widens the band.

    The quantiles answer the right question directly: if even the pessimistic
    low end of the interval is still above the current level, the rise is
    robust to forecast error and the event is Likely. If only the median is,
    it is Possible.
    """
    if p10_cm > stage_now_cm:
        return "Likely"
    if p50_cm > stage_now_cm:
        return "Possible"
    return "Unlikely"


def zone_certainty(already_flooded: bool, forecast_certainty: str) -> str:
    """CAP <certainty> for one zone.

    A zone that ALREADY meets its threshold is not an uncertain prediction —
    it is an observation, and CAP has a value for exactly that. Without this
    case a flooded zone was labelled <severity>Severe</severity> with
    <certainty>Unlikely</certainty>, because the forecast said the water would
    not rise FURTHER. Correct about the future, nonsense as a warning.
    """
    return "Observed" if already_flooded else forecast_certainty


class Dispatcher:
    def __init__(self) -> None:
        self.outbox: deque[dict] = deque(maxlen=OUTBOX_MAX)
        self.alerts: dict[str, dict] = {}
        self._pending: dict[str, tuple[str, int]] = {}    # zone -> (sev, count)
        self._last_sent: dict[str, datetime] = {}
        self._zone_coords: dict[str, list] | None = None
        self.suppressed = 0

    # ── channels ─────────────────────────────────────────────────────────
    @staticmethod
    def channels() -> dict:
        sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        tok = os.getenv("TWILIO_AUTH_TOKEN", "")
        return {
            "simulated": {"live": True, "note": "always on; drives the demo panel"},
            "sms": {"live": bool(sid and tok),
                    "note": "set TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM"},
            "voice": {"live": False,
                      "note": "browser speech in the panel; Piper + Twilio <Play> in production"},
        }

    # ── geometry ─────────────────────────────────────────────────────────
    def _coords(self, h3: str) -> list | None:
        if self._zone_coords is None:
            self._zone_coords = {}
            for f in zones_mod.geojson()["features"]:
                g = f.get("geometry") or {}
                if g.get("type") == "Polygon":
                    self._zone_coords[f["properties"]["h3"]] = g["coordinates"][0]
        return self._zone_coords.get(h3)

    def cap_xml(self, alert: dict) -> str:
        """CAP 1.2 with one <info> per language."""
        poly = ""
        coords = self._coords(alert["zone"])
        if coords:
            pts = " ".join(f"{lat:.5f},{lon:.5f}" for lon, lat in coords)
            poly = f"<polygon>{pts}</polygon>"

        infos = []
        for block in alert["messages"]:
            lang = next(l for l in i18n.LANGUAGES if l["code"] == block["language"])
            infos.append(f"""  <info>
    <language>{lang['cap']}</language>
    <category>Met</category>
    <event>Flood</event>
    <urgency>{URGENCY_CAP[alert['severity']]}</urgency>
    <severity>{SEVERITY_CAP[alert['severity']]}</severity>
    <certainty>{alert['certainty']}</certainty>
    <onset>{alert['onset']}</onset>
    <headline>{escape(block['headline'])}</headline>
    <description>{escape(block['body'])}</description>
    <instruction>{escape(block['instruction'])}</instruction>
    <area>
      <areaDesc>{escape(alert['zone'])}</areaDesc>
      {poly}
    </area>
  </info>""")

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>{alert['id']}</identifier>
  <sender>{SENDER}</sender>
  <sent>{alert['sent']}</sent>
  <status>{alert['status']}</status>
  <msgType>Alert</msgType>
  <scope>Public</scope>
{chr(10).join(infos)}
</alert>
"""

    # ── evaluation ───────────────────────────────────────────────────────
    def evaluate(self, zone_rows: list[dict], *, lead_min: int, confidence: float,
                 cap_certainty: str = "Possible", exercise: bool = True,
                 reason: list[dict] | None = None,
                 now: datetime | None = None) -> list[dict]:
        now = now or datetime.now(timezone.utc)
        fired: list[dict] = []

        # Alert on the FORECAST severity, not the current one. Warning people
        # about water they can already see is not early warning.
        candidates = {
            r["h3"]: (
                (r.get("severity_forecast") or r.get("severity")),
                bool(r.get("severity")),          # already at threshold now?
            )
            for r in zone_rows
            if (r.get("severity_forecast") or r.get("severity"))
        }

        ready: list[tuple[str, str, bool]] = []
        for h3, (sev, observed) in candidates.items():
            prev_sev, count = self._pending.get(h3, (None, 0))
            count = count + 1 if prev_sev == sev else 1
            self._pending[h3] = (sev, count)
            if count < DEBOUNCE_TICKS:
                continue
            last = self._last_sent.get(h3)
            if last and (now - last).total_seconds() < RESEND_AFTER_S:
                continue
            ready.append((h3, sev, observed))

        # Escalating zones FIRST, then by severity.
        #
        # Sorting by severity alone spent the whole alert budget on zones that
        # were already underwater — where a warning is useless, because the
        # people there need rescue, not notice. A zone that is still dry but
        # forecast to flood is the only place an alert can change what
        # someone does, so it outranks a worse-but-already-flooded zone.
        ready.sort(key=lambda p: (p[2], -RANK.get(p[1], 0)))
        self.suppressed = max(0, len(ready) - MAX_PER_CYCLE)
        for h3, sev, observed in ready[:MAX_PER_CYCLE]:
            fired.append(self._emit(h3, sev, lead_min, confidence,
                                    zone_certainty(observed, cap_certainty),
                                    exercise, reason, now))

        for h3 in list(self._pending):
            if h3 not in candidates:
                del self._pending[h3]
        return fired

    def _emit(self, h3: str, sev: str, lead_min: int, confidence: float,
              cap_certainty: str, exercise: bool, reason, now: datetime) -> dict:
        label = f"Zone {h3[-6:]}"
        messages = i18n.render_all(sev, zone=label, mins=lead_min)

        # Every alert in a cycle shares `sent`, so sorting on it alone is
        # unstable: the alert list and the handset outbox could disagree about
        # which alert is newest, which reads as a bug on stage.
        self._seq += 1
        alert = {
            "seq": self._seq,
            "id": f"sentinel-{uuid.uuid4().hex[:12]}",
            "zone": h3,
            "zone_label": label,
            "severity": sev,
            "certainty": cap_certainty,
            "confidence": round(confidence, 3),
            "lead_min": lead_min,
            "sent": now.isoformat(),
            "onset": (now + timedelta(minutes=lead_min)).isoformat(),
            "status": "Exercise" if exercise else "Actual",
            "messages": messages,
            "reason": reason or [],
        }
        self.alerts[alert["id"]] = alert
        self._last_sent[h3] = now

        for lang in i18n.LANGUAGES:
            self.outbox.appendleft({
                "alert_id": alert["id"],
                "zone_label": label,
                "severity": sev,
                "status": alert["status"],
                "language": lang["code"],
                "language_name": lang["name"],
                "channel": "sms",
                "text": i18n.sms_text(sev, lang["code"], zone=label, mins=lead_min),
                "sent": alert["sent"],
            })

        log.info("alert %s zone=%s sev=%s lead=%dmin status=%s",
                 alert["id"], h3, sev, lead_min, alert["status"])
        return alert

    def reset(self) -> None:
        self.outbox.clear()
        self.alerts.clear()
        self._pending.clear()
        self._last_sent.clear()
        self.suppressed = 0
        self._seq = 0


dispatcher = Dispatcher()
