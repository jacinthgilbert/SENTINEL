"""Authority-authorised dispatch of real warnings.

Two rules, both deliberate:

  1. ARMED, NOT AUTOMATIC. The send only becomes available once the forecast
     crosses a severity threshold, and a human still has to press it. Real
     warning systems work this way: an officer authorises before a city is
     messaged. Auto-blasting is how false alarms get sent and how people learn
     to ignore you.

  2. CONSENT FIRST. Only recipients with opted_in reach the channel. That is
     filtered in recipients.active(), once, so no send path can bypass it.

Every attempt is logged with its DELIVERY status, not just whether the API
call succeeded — the two differ, and for Indian SMS they differ silently.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone

import channels
import i18n
import recipients as rec_mod

log = logging.getLogger("sentinel.notify")

ARM_AT = "watch"                 # advisory < watch < warning
RANK = {"advisory": 1, "watch": 2, "warning": 3}
LOG_MAX = 200
audit: deque[dict] = deque(maxlen=LOG_MAX)


def armed(worst_severity: str | None) -> bool:
    return RANK.get(worst_severity or "", 0) >= RANK[ARM_AT]


def preview(severity: str, zone_label: str, lead_min: int) -> list[dict]:
    """Exactly what each person would receive, before anything is sent."""
    out = []
    for r in rec_mod.active():
        out.append({
            "id": r["id"],
            "name": r["name"],
            "phone": rec_mod.masked(r)["phone"],
            "lang": r["lang"],
            "text": i18n.sms_text(severity, r["lang"], zone=zone_label, mins=lead_min),
        })
    return out


def send(severity: str, zone_label: str, lead_min: int,
         channel: str = "sms", dry_run: bool = False) -> dict:
    ch = channels.get(channel)
    people = rec_mod.active()
    now = datetime.now(timezone.utc).isoformat()
    results = []

    for r in people:
        text = i18n.sms_text(severity, r["lang"], zone=zone_label, mins=lead_min)
        if dry_run:
            res = channels.SendResult(ok=True, status="dry_run", detail="not sent")
        else:
            res = ch.send(r["phone"], text)
            rec_mod.record_send(r["id"], res.status, res.provider_id)

        results.append({
            "id": r["id"], "name": r["name"], "lang": r["lang"],
            "phone": rec_mod.masked(r)["phone"],
            "ok": res.ok, "status": res.status,
            "provider_id": res.provider_id,
            "error": res.error, "detail": res.detail,
            "chars": len(text),
        })

    entry = {
        "at": now, "channel": channel, "severity": severity,
        "zone": zone_label, "lead_min": lead_min,
        "dry_run": dry_run,
        "recipients": len(people),
        "accepted": sum(1 for x in results if x["ok"]),
        "results": results,
    }
    audit.appendleft(entry)
    log.info("notify channel=%s severity=%s people=%d accepted=%d dry_run=%s",
             channel, severity, len(people), entry["accepted"], dry_run)
    return entry


def refresh_delivery() -> dict:
    """Re-fetch delivery outcomes for the most recent send.

    Run this a few seconds after sending. 'accepted' is not 'delivered', and
    on Indian SMS routes the gap between them is where the whole thing fails.
    """
    sms = channels.get("sms")
    if not hasattr(sms, "delivery_status"):
        return {"updated": 0, "note": "channel does not report delivery"}

    updated = 0
    for entry in list(audit)[:1]:
        for row in entry["results"]:
            pid = row.get("provider_id")
            if not pid:
                continue
            res = sms.delivery_status(pid)
            row["status"] = res.status
            row["ok"] = res.ok
            row["detail"] = res.detail or row.get("detail", "")
            if res.error:
                row["error"] = res.error
            rec_mod.record_send(row["id"], res.status, pid)
            updated += 1
        entry["delivered"] = sum(1 for r in entry["results"] if r["status"] == "delivered")
    return {"updated": updated,
            "delivered": (audit[0].get("delivered") if audit else 0),
            "entry": audit[0] if audit else None}
