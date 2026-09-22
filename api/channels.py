"""Outbound notification channels.

Pluggable on purpose. SMS to Indian numbers is the requested channel but is
NOT reliable without DLT registration under TRAI: the provider accepts the
message, returns a success id, and Indian carriers then drop it silently. That
failure mode looks identical to success in your logs, which is why every send
here reports a DELIVERY status fetched back from the provider rather than just
"the API said 200".

Two things block SMS from this app on a Twilio TRIAL account, both verified
by testing rather than assumed:

  · error 572006 rejects ANY body, including the exact text of a template that
    had already been delivered to the handset from the Console. The Console
    has a privileged path the API does not.
  · SMS delivery itself is fine — 3 of 3 reached an Indian handset with no
    error, so the TRAI DLT regime is not what is stopping this.

Upgrading the Twilio account to Full removes the restriction. If DLT ever does
bite, swap in an Indian aggregator (MSG91, Fast2SMS) with the same `send`
method; nothing else in the codebase changes.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

log = logging.getLogger("sentinel.channels")


@dataclass
class SendResult:
    ok: bool
    status: str              # queued | sent | delivered | undelivered | failed | simulated
    provider_id: str | None = None
    error: str | None = None
    detail: str = ""


class SimulatedChannel:
    """Always available. Drives the on-screen handset; never leaves the machine."""

    name = "simulated"
    live = True

    def send(self, to: str, body: str) -> SendResult:
        return SendResult(ok=True, status="simulated",
                          detail="shown in the on-screen handset only")


class TwilioSMSChannel:
    """Real SMS via Twilio.

    Credentials come from the environment, never from the browser and never
    from a file in git:

        TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM
    """

    name = "sms"

    # Read lazily, NOT in __init__. These objects are constructed at import
    # time, which happens before .env is loaded, so anything captured in the
    # constructor is permanently empty — the channel then reports itself as
    # unconfigured with a correctly filled .env sitting right there.
    @property
    def sid(self) -> str:
        return os.getenv("TWILIO_ACCOUNT_SID", "").strip()

    @property
    def token(self) -> str:
        return os.getenv("TWILIO_AUTH_TOKEN", "").strip()

    @property
    def frm(self) -> str:
        return os.getenv("TWILIO_FROM", "").strip()

    @property
    def live(self) -> bool:
        return bool(self.sid and self.token and self.frm)

    def send(self, to: str, body: str) -> SendResult:
        if not self.live:
            return SendResult(ok=False, status="failed",
                              error="TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM not set")
        import requests

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"
        try:
            r = requests.post(url, auth=(self.sid, self.token), timeout=25,
                              data={"To": to, "From": self.frm, "Body": body})
        except Exception as exc:                          # noqa: BLE001
            return SendResult(ok=False, status="failed", error=f"{type(exc).__name__}: {exc}")

        if r.status_code >= 300:
            try:
                msg = r.json().get("message", r.text[:200])
            except Exception:                             # noqa: BLE001
                msg = r.text[:200]
            return SendResult(ok=False, status="failed", error=f"HTTP {r.status_code}: {msg}")

        body_json = r.json()
        return SendResult(ok=True, status=body_json.get("status", "queued"),
                          provider_id=body_json.get("sid"),
                          detail="accepted by Twilio — NOT yet proof of delivery")

    def delivery_status(self, provider_id: str) -> SendResult:
        """Fetch the real outcome. This is the number that matters.

        'delivered' means a handset got it. 'undelivered' or 'failed' with
        error 30034 / 30007 is the DLT block, and no amount of retrying fixes
        it — you need a DLT-registered sender.
        """
        if not self.live or not provider_id:
            return SendResult(ok=False, status="failed", error="not configured")
        import requests

        url = (f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}"
               f"/Messages/{provider_id}.json")
        try:
            r = requests.get(url, auth=(self.sid, self.token), timeout=25)
            d = r.json()
        except Exception as exc:                          # noqa: BLE001
            return SendResult(ok=False, status="failed", error=str(exc))

        status = d.get("status", "unknown")
        code = d.get("error_code")
        hint = ""
        if code in (30034, 30032, 30007, 30008):
            hint = (f"error {code} — this is the India DLT block. The message was "
                    f"accepted then dropped by the carrier. A DLT-registered "
                    f"sender is required; retrying will not help.")
        return SendResult(ok=status == "delivered", status=status,
                          provider_id=provider_id,
                          error=(str(code) if code else None), detail=hint)


_SIM = SimulatedChannel()
_SMS = TwilioSMSChannel()


def get(name: str):
    return {"simulated": _SIM, "sms": _SMS}.get(name, _SIM)


def status() -> dict:
    return {
        "simulated": {"live": True, "note": "on-screen handset, always available"},
        "sms": {
            "live": _SMS.live,
            "note": ("ready" if _SMS.live else
                     "set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM in .env"),
            "warning": ("Delivery to Indian numbers requires DLT registration under "
                        "TRAI. Twilio will accept the message and the carrier may "
                        "drop it. Always check delivery status, never the send call."),
        },
    }
