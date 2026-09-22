"""Fetch the Copernicus COP30 DEM for the AOI. Exactly one API call."""

from __future__ import annotations

import requests

import config as C


def run() -> None:
    if C.DEM_TIF.exists():
        print(f"  dem.tif exists ({C.DEM_TIF.stat().st_size/1e6:.1f} MB) — skipping")
        return

    C.DATA.mkdir(exist_ok=True)
    params = {
        "demtype": C.DEM_TYPE,
        **C.BBOX,
        "outputFormat": "GTiff",
        "API_Key": C.api_key(),
    }
    print(f"  requesting {C.DEM_TYPE} for {C.CITY} …")
    r = requests.get(C.OPENTOPO_URL, params=params, timeout=180)

    if r.status_code != 200 or r.content[:2] not in (b"II", b"MM"):
        raise SystemExit(
            f"OpenTopography returned {r.status_code}: {r.text[:300]}\n"
            "Check the key and the 200-call/24h quota."
        )

    C.DEM_TIF.write_bytes(r.content)
    print(f"  wrote {C.DEM_TIF.name}  {len(r.content)/1e6:.2f} MB")


if __name__ == "__main__":
    run()
