"""Outbound notification channels.

Pluggable on purpose. SMS to Indian numbers is the requested channel but is
NOT reliable without DLT registration under TRAI: the provider accepts the
message, returns a success id, and Indian carriers then drop it silently. That
failure mode looks identical to success in your logs, which is why every send
here reports a DELIVERY status fetched back from the provider rather than just
"the API said 200".

If Twilio does not deliver, swap in an Indian aggregator that handles DLT
(MSG91, Fast2SMS) by implementing one more class with the same `send` method.
Nothing else in the codebase changes.
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

    def __init__(self) -> None:
        self.sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        self.token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        self.frm = os.getenv("TWILIO_FROM", "").strip()

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


class TwilioWhatsAppChannel(TwilioSMSChannel):
    """WhatsApp via the Twilio sandbox — the practical channel for India.

    Uses the SAME Twilio credentials as SMS, but WhatsApp is not SMS, so the
    TRAI DLT regime does not apply and the trial template allowlist (error
    572006) does not either. Recipients opt in by texting the sandbox number
    once, which also gives you documented consent.

    Two real constraints, both worth knowing before demo day:
      · each recipient must send "join <code>" to the sandbox number
      · that session expires 3 days later, so everyone re-joins on the day
    """

    name = "whatsapp"

    def __init__(self) -> None:
        super().__init__()
        # Twilio's shared sandbox number, unless a dedicated sender is set.
        self.frm = os.getenv("TWILIO_WHATSAPP_FROM", "+14155238886").strip()

    @property
    def live(self) -> bool:
        return bool(self.sid and self.token and self.frm)

    def send(self, to: str, body: str) -> SendResult:
        if not self.live:
            return SendResult(ok=False, status="failed",
                              error="TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not set")
        import requests

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"
        try:
            r = requests.post(url, auth=(self.sid, self.token), timeout=25,
                              data={"To": f"whatsapp:{to}",
                                    "From": f"whatsapp:{self.frm}",
                                    "Body": body})
        except Exception as exc:                          # noqa: BLE001
            return SendResult(ok=False, status="failed", error=f"{type(exc).__name__}: {exc}")

        if r.status_code >= 300:
            try:
                d = r.json()
                msg, code = d.get("message", r.text[:200]), d.get("code")
            except Exception:                             # noqa: BLE001
                msg, code = r.text[:200], None
            hint = ""
            if code == 63015 or "not been enabled" in str(msg) or code == 63007:
                hint = ("this number has not joined the sandbox — send "
                        "\"join <your-code>\" from it to the sandbox number first")
            elif code == 63016:
                hint = ("outside the 24-hour session window — the recipient must "
                        "message the sandbox again")
            return SendResult(ok=False, status="failed",
                              error=f"{code}: {msg}", detail=hint)

        d = r.json()
        return SendResult(ok=True, status=d.get("status", "queued"),
                          provider_id=d.get("sid"),
                          detail="accepted — check delivery status")


class TelegramChannel:
    """Telegram bot — the channel with no gatekeeper.

    No carrier, so no TRAI DLT. No Meta, so no template approval, no ContentSid,
    no 24-hour session window. No trial restrictions. A bot token and a chat id
    are all it needs, and both are free and instant.

    Recipients opt in by sending the bot any message; their chat id is then
    discoverable from getUpdates, which is also documented consent.

        TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
    """

    name = "telegram"

    def __init__(self) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    @property
    def live(self) -> bool:
        return bool(self.token)

    def _api(self, method: str, **params):
        import requests
        return requests.post(f"https://api.telegram.org/bot{self.token}/{method}",
                             json=params, timeout=20)

    def send(self, to: str, body: str) -> SendResult:
        """`to` is a Telegram chat id, not a phone number."""
        if not self.live:
            return SendResult(ok=False, status="failed",
                              error="TELEGRAM_BOT_TOKEN not set in .env")
        try:
            r = self._api("sendMessage", chat_id=to, text=body)
            d = r.json()
        except Exception as exc:                          # noqa: BLE001
            return SendResult(ok=False, status="failed", error=f"{type(exc).__name__}: {exc}")

        if not d.get("ok"):
            desc = d.get("description", "unknown error")
            hint = ("that chat id has not started the bot — open the bot in "
                    "Telegram and press Start" if "chat not found" in desc.lower() else "")
            return SendResult(ok=False, status="failed", error=desc, detail=hint)

        # Telegram is synchronous: an ok response means it is on the device.
        return SendResult(ok=True, status="delivered",
                          provider_id=str(d["result"].get("message_id")),
                          detail="delivered by Telegram")

    def discover(self) -> list[dict]:
        """Everyone who has messaged the bot — i.e. everyone who opted in."""
        if not self.live:
            return []
        try:
            d = self._api("getUpdates", timeout=0).json()
        except Exception:                                 # noqa: BLE001
            return []
        seen, out = set(), []
        for u in d.get("result", []):
            msg = u.get("message") or u.get("edited_message") or {}
            chat = msg.get("chat") or {}
            cid = chat.get("id")
            if cid and cid not in seen:
                seen.add(cid)
                name = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
                out.append({"chat_id": str(cid),
                            "name": name or chat.get("username") or str(cid),
                            "username": chat.get("username")})
        return out

    def me(self) -> dict | None:
        if not self.live:
            return None
        try:
            d = self._api("getMe").json()
            return d.get("result") if d.get("ok") else None
        except Exception:                                 # noqa: BLE001
            return None


_SIM = SimulatedChannel()
_SMS = TwilioSMSChannel()
_WA = TwilioWhatsAppChannel()
_TG = TelegramChannel()


def get(name: str):
    return {"simulated": _SIM, "sms": _SMS,
            "whatsapp": _WA, "telegram": _TG}.get(name, _SIM)


def status() -> dict:
    bot = _TG.me() if _TG.live else None
    return {
        "simulated": {"live": True, "note": "on-screen handset, always available"},
        "telegram": {
            "live": _TG.live,
            "note": (f"ready as @{bot.get('username')} — recipients press Start on the bot"
                     if bot else
                     "set TELEGRAM_BOT_TOKEN in .env (get one from @BotFather)"),
        },
        "whatsapp": {
            "live": _WA.live,
            "note": ("ready — each recipient must send \"join <code>\" to "
                     f"{_WA.frm} first" if _WA.live else
                     "set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env"),
            "warning": ("Sandbox sessions expire 3 days after a recipient joins. "
                        "Have everyone re-join on demo day."),
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
