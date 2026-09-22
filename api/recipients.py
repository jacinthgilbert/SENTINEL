"""Recipient registry for real outbound warnings.

Stored in data/recipients.json, which is GITIGNORED: it holds phone numbers,
which are personal data. Do not commit it, and do not put real numbers in any
file that goes to GitHub.

Consent is explicit and recorded. A person is only messaged if `opted_in` is
true, because a flood warning arriving unannounced from an unknown number is
indistinguishable from spam — and in a demo, messaging someone who did not
agree is simply not on.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import paths

STORE = paths.DATA / "recipients.json"
E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def _load() -> list[dict]:
    if not STORE.exists():
        return []
    try:
        return json.loads(STORE.read_text())
    except Exception:                                    # noqa: BLE001
        return []


def _save(rows: list[dict]) -> None:
    STORE.parent.mkdir(exist_ok=True)
    STORE.write_text(json.dumps(rows, indent=2))


def all_recipients() -> list[dict]:
    return _load()


def active() -> list[dict]:
    """Only people who consented. Everything else is filtered out here, once."""
    return [r for r in _load() if r.get("opted_in") and E164.match(r.get("phone", ""))]


def add(*, name: str, phone: str, lang: str = "te", zone: str | None = None,
        opted_in: bool = False, note: str = "") -> dict:
    phone = phone.strip().replace(" ", "")
    if not E164.match(phone):
        raise ValueError(
            f"phone must be E.164, e.g. +919876543210 (got {phone!r})"
        )
    rows = _load()
    if any(r["phone"] == phone for r in rows):
        raise ValueError(f"{phone} is already registered")

    rec = {
        "id": max([r["id"] for r in rows], default=0) + 1,
        "name": name.strip() or "unnamed",
        "phone": phone,
        "lang": lang if lang in ("te", "hi", "en") else "te",
        "zone": zone,
        "opted_in": bool(opted_in),
        "opted_in_at": datetime.now(timezone.utc).isoformat() if opted_in else None,
        "note": note,
        "last_sent": None,
        "last_status": None,
    }
    rows.append(rec)
    _save(rows)
    return rec


def set_opt_in(rid: int, value: bool) -> dict | None:
    rows = _load()
    for r in rows:
        if r["id"] == rid:
            r["opted_in"] = bool(value)
            r["opted_in_at"] = datetime.now(timezone.utc).isoformat() if value else None
            _save(rows)
            return r
    return None


def remove(rid: int) -> bool:
    rows = _load()
    kept = [r for r in rows if r["id"] != rid]
    if len(kept) == len(rows):
        return False
    _save(kept)
    return True


def record_send(rid: int, status: str, sid: str | None = None) -> None:
    rows = _load()
    for r in rows:
        if r["id"] == rid:
            r["last_sent"] = datetime.now(timezone.utc).isoformat()
            r["last_status"] = status
            if sid:
                r["last_sid"] = sid
    _save(rows)


def masked(r: dict) -> dict:
    """Never return a full number to the browser."""
    p = r.get("phone", "")
    return {**r, "phone": (p[:3] + "•" * max(0, len(p) - 6) + p[-3:]) if len(p) > 6 else "•••"}
