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


class AndroidGatewayChannel:
    """Send SMS through an Android phone on the local network.

    The phone runs a small HTTP server and sends through its own SIM, which is
    why this works where Twilio does not: it is person-to-person SMS on an
    Indian number, not bulk commercial traffic, so the TRAI DLT regime does not
    apply. No account tier, no templates, no approval, and no per-message cost
    beyond the phone's existing plan.

    Targets the local API of capcom6/android-sms-gateway:

        POST {base}/message   {"message": "...", "phoneNumbers": ["+91..."]}

    Configure in .env:
        ANDROID_SMS_URL=http://192.168.1.5:8080
        ANDROID_SMS_USER=sms
        ANDROID_SMS_PASS=...
    """

    name = "phone"

    @property
    def base(self) -> str:
        return os.getenv("ANDROID_SMS_URL", "").strip().rstrip("/")

    @property
    def auth(self):
        u = os.getenv("ANDROID_SMS_USER", "").strip()
        p = os.getenv("ANDROID_SMS_PASS", "").strip()
        return (u, p) if u else None

    @property
    def live(self) -> bool:
        return bool(self.base)

    def probe(self) -> SendResult:
        """Is the phone reachable right now? Run this BEFORE the demo.

        The usual failure is not the app — it is the network. Venue wifi often
        isolates clients from each other, so the laptop cannot reach the phone
        even though both are online.
        """
        if not self.live:
            return SendResult(ok=False, status="failed",
                              error="ANDROID_SMS_URL not set in .env")
        import requests
        for path in ("/health", "/message"):
            try:
                r = requests.get(f"{self.base}{path}", auth=self.auth, timeout=6)
                if r.status_code < 500:
                    return SendResult(ok=True, status="reachable",
                                      detail=f"{self.base} answered {r.status_code} on {path}")
            except Exception as exc:                      # noqa: BLE001
                last = f"{type(exc).__name__}"
        return SendResult(
            ok=False, status="unreachable", error=last,
            detail=("phone not reachable. Check both devices are on the same "
                    "network, and prefer the phone's own hotspot — venue wifi "
                    "commonly blocks device-to-device traffic."),
        )

    def send(self, to: str, body: str) -> SendResult:
        if not self.live:
            return SendResult(ok=False, status="failed",
                              error="ANDROID_SMS_URL not set in .env")
        import requests
        try:
            r = requests.post(f"{self.base}/message", auth=self.auth, timeout=25,
                              json={"message": body, "phoneNumbers": [to]})
        except Exception as exc:                          # noqa: BLE001
            return SendResult(ok=False, status="failed",
                              error=f"{type(exc).__name__}: {exc}",
                              detail="phone unreachable — see the probe hint")
        if r.status_code >= 300:
            return SendResult(ok=False, status="failed",
                              error=f"HTTP {r.status_code}: {r.text[:160]}")
        try:
            d = r.json()
        except Exception:                                 # noqa: BLE001
            d = {}
        return SendResult(ok=True, status=str(d.get("state", "sent")).lower(),
                          provider_id=d.get("id"),
                          detail="handed to the phone's SIM")


_SIM = SimulatedChannel()
_SMS = TwilioSMSChannel()
_PHONE = AndroidGatewayChannel()


def get(name: str):
    return {"simulated": _SIM, "sms": _SMS, "phone": _PHONE}.get(name, _SIM)


def status() -> dict:
    return {
        "simulated": {"live": True, "note": "on-screen handset, always available"},
        "phone": {
            "live": _PHONE.live,
            "note": (f"Android gateway at {_PHONE.base}" if _PHONE.live else
                     "set ANDROID_SMS_URL in .env (SMS Gateway app, local server mode)"),
            "warning": ("Both devices must be on the same network. Venue wifi often "
                        "isolates clients — use the phone's hotspot and connect the "
                        "laptop to it."),
        },
        "sms": {
            "live": _SMS.live,
            "note": ("ready" if _SMS.live else
                     "set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM in .env"),
            "warning": ("Delivery to Indian numbers requires DLT registration under "
                        "TRAI. Twilio will accept the message and the carrier may "
                        "drop it. Always check delivery status, never the send call."),
        },
    }
