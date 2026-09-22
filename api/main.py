"""The Sentinel — API surface (plan §3.3).

Step 1 ships three endpoints: /health, /state, /events.
The other eight land with their features.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import adapters
import alerts as alerts_mod
import facilities as facilities_mod
import hazards as hazards_mod
import inundation
import nowcast
import cv as cv_mod
import dispatch as dispatch_mod
import channels as channels_mod
import i18n
import notify as notify_mod
import recipients as rec_mod
import reports as reports_mod
import risk as risk_mod
import routing as routing_mod
import zones as zones_mod
from loop import TickLoop

def _load_dotenv() -> None:
    """Read .env into the environment at import time.

    Without this the API only sees credentials that happen to be exported in
    the shell that launched it, so Twilio would silently read as "not
    configured" even with a correctly filled .env — which is exactly the kind
    of thing you discover on stage.
    """
    from pathlib import Path

    for candidate in (Path(".env"), Path(__file__).resolve().parent.parent / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        break


_load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("sentinel.api")

TICK_INTERVAL_S = float(os.getenv("TICK_INTERVAL_S", "1.0"))
ADAPTER_NAME = os.getenv("ADAPTER", "synthetic")
DATABASE_URL = os.getenv("DATABASE_URL", "")

HEARTBEAT_S = 15.0          # keeps proxies from closing an idle SSE stream

# 10x is the demo default: the reservoir's ~170 s lag becomes ~17 s of real
# time — long enough for judges to SEE rain lead water, short enough to hold
# a room. 60x compresses a two-hour event into two minutes.
SPEEDS = (1, 10, 60)
DEFAULT_SCENARIO_SPEED = 10.0
MAX_RAIN_MM_HR = 150.0
PRESETS = {
    "calm": 0.0,
    "steady": 20.0,
    "heavy": 60.0,
    "cloudburst": 120.0,
}

loop: TickLoop


@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = TickLoop(adapters.build(ADAPTER_NAME), interval_s=TICK_INTERVAL_S)
    loop.start()
    log.info("adapter=%s tick=%.2fs", ADAPTER_NAME, TICK_INTERVAL_S)
    # Off the event loop so startup is not blocked by raster work.
    await asyncio.to_thread(inundation.prewarm)

    def _tick_hook(world_s: float) -> None:
        if world_s - _last_alert_eval["world_s"] < ALERT_EVERY_WORLD_S:
            return
        _last_alert_eval["world_s"] = world_s
        try:
            _run_alert_cycle()
        except Exception:                                # noqa: BLE001
            log.exception("alert cycle failed")

    loop.on_tick = _tick_hook
    yield
    await loop.stop()


app = FastAPI(title="The Sentinel", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Liveness + DB reachability. Step 1 DoD depends on this."""
    db_ok = False
    detail = "not configured"
    if DATABASE_URL:
        try:
            import psycopg

            with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
                row = conn.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                ).fetchone()
                db_ok = True
                detail = f"{row[0]} tables"
        except Exception as exc:                      # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
    return {"status": "ok", "adapter": ADAPTER_NAME, "db": db_ok, "db_detail": detail}


@app.get("/state")
def get_state() -> dict:
    """Current WorldState snapshot."""
    return loop.state.to_dict()


@app.get("/events")
async def events() -> StreamingResponse:
    """SSE stream of WorldState deltas — the spine of every live view."""

    async def gen():
        q = loop.subscribe()
        # Tell the browser how fast to retry if we die. Drives the offline ladder.
        yield "retry: 2000\n\n"
        try:
            while True:
                try:
                    state = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_S)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(state.to_dict())}\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            loop.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Step 3: inundation ───────────────────────────────────────────────────
@app.get("/inundation")
def get_inundation(
    stage_m: float = Query(..., ge=0.0, le=inundation.MAX_STAGE_M),
    geometry: bool = Query(True, description="false returns stats only"),
) -> dict:
    """Flooded extent at a given stage. The slider hits this."""
    try:
        if not geometry:
            return inundation.stats(stage_m)
        # cache on whole cm so a slider drag replays instead of recomputing
        return inundation.extent(int(round(stage_m * 100)))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/inundation/current")
def get_inundation_current() -> dict:
    """Extent implied by the live gauge. Keeps the stage->depth physics server-side."""
    st = loop.state
    level_cm = next(iter(st.stages.values()), inundation.GAUGE_DATUM_CM)
    stage_m = inundation.stage_from_gauge(level_cm)
    try:
        out = dict(inundation.extent(int(round(stage_m * 100))))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    out["properties"] = {**out["properties"], "gauge_cm": round(level_cm, 1), "tick": st.tick}
    return out


@app.get("/zones")
def get_zones() -> dict:
    """Static H3 zone layer."""
    try:
        return zones_mod.geojson()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/zones/flooded")
def get_zones_flooded(
    stage_m: float = Query(..., ge=0.0, le=inundation.MAX_STAGE_M),
) -> dict:
    """Per-zone flooded fraction + exposed population."""
    try:
        return {
            "summary": zones_mod.summary(stage_m),
            "zones": zones_mod.flooded_fraction(stage_m),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/facilities")
def get_facilities() -> dict:
    try:
        return zones_mod.facilities()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


# ── Step 4: the digital twin console ─────────────────────────────────────
def _sim_state() -> dict:
    ad = loop.adapter
    st = loop.state
    return {
        "mode": st.mode,
        "playing": loop.playing,
        "speed": loop.speed,
        "speeds": list(SPEEDS),
        "rain_mm_hr": round(getattr(ad, "rain_mm_hr", st.rainfall_mm_hr), 1),
        "max_rain_mm_hr": MAX_RAIN_MM_HR,
        "presets": PRESETS,
        "tick": st.tick,
        "world_t": st.t.isoformat(),
        "gauge_cm": round(next(iter(st.stages.values()), 0.0), 1),
        "tick_interval_s": TICK_INTERVAL_S,
    }


@app.get("/sim")
def get_sim() -> dict:
    return _sim_state()


@app.post("/sim/control")
def post_sim_control(body: dict = Body(default={})) -> dict:
    """Drive the twin: switch mode, set rainfall, change speed, pause, reset.

    Rainfall is the ONLY forcing exposed. Water level is never settable —
    it is always the reservoir's answer to the rain, which is what keeps the
    demo honest about the model it is showing off.
    """
    mode = body.get("mode")
    if mode in ("scenario", "live"):
        want = "scenario" if mode == "scenario" else ADAPTER_NAME
        if loop.state.mode != mode:
            speed = DEFAULT_SCENARIO_SPEED if mode == "scenario" else 1.0
            loop.set_adapter(adapters.build(want), speed=speed)

    if (rain := body.get("rain_mm_hr")) is not None:
        ad = loop.adapter
        if not hasattr(ad, "rain_mm_hr"):
            raise HTTPException(409, "rainfall is only settable in scenario mode")
        try:
            ad.rain_mm_hr = max(0.0, min(float(rain), MAX_RAIN_MM_HR))
        except (TypeError, ValueError):
            raise HTTPException(422, "rain_mm_hr must be a number") from None

    if (speed := body.get("speed")) is not None:
        try:
            loop.speed = max(0.1, min(float(speed), 120.0))
        except (TypeError, ValueError):
            raise HTTPException(422, "speed must be a number") from None

    if (playing := body.get("playing")) is not None:
        loop.playing = bool(playing)

    if body.get("reset"):
        loop.reset()

    return _sim_state()


# ── Step 5: AI nowcasting ────────────────────────────────────────────────
def _forecast_rain() -> float:
    """Rainfall forecast fed to the model.

    Scenario mode: the operator's slider IS the future, so this is exact.
    Live mode (Step 5b): Open-Meteo minutely_15, which carries real forecast
    error — the skill numbers in data/nowcast/report.json reflect that case.
    """
    return float(getattr(loop.adapter, "rain_mm_hr", loop.state.rainfall_mm_hr))


@app.get("/nowcast")
def get_nowcast() -> dict:
    try:
        out = nowcast.predict(loop.history, _forecast_rain())
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from None
    out["mode"] = loop.state.mode
    out["forecast_rain_mm_hr"] = round(_forecast_rain(), 1)
    return out


@app.get("/nowcast/explain")
def get_nowcast_explain(
    horizon_min: int = Query(60, description="one of 30, 60, 90, 120"),
) -> dict:
    if horizon_min not in nowcast.HORIZONS_MIN:
        raise HTTPException(422, f"horizon_min must be one of {nowcast.HORIZONS_MIN}")
    try:
        return nowcast.explain(loop.history, _forecast_rain(), horizon_min)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from None


@app.get("/nowcast/skill")
def get_nowcast_skill() -> dict:
    """The held-out evaluation. Shown in the UI so the claim is checkable."""
    import json as _json
    if not nowcast.REPORT_JSON.exists():
        raise HTTPException(503, "no training report — run prep/train_nowcast.py")
    return _json.loads(nowcast.REPORT_JSON.read_text())


# ── Step 6: risk fusion, exposure, critical infrastructure ───────────────
def _stage_now_m() -> float:
    level_cm = next(iter(loop.state.stages.values()), inundation.GAUGE_DATUM_CM)
    return inundation.stage_from_gauge(level_cm)


def _forecast_stage_m(horizon_min: int) -> float | None:
    """Stage the nowcast expects at `horizon_min`, or None if not ready."""
    try:
        nc = nowcast.predict(loop.history, _forecast_rain())
    except FileNotFoundError:
        return None
    if not nc.get("ready"):
        return None
    for h in nc["horizons"]:
        if h["horizon_min"] == horizon_min:
            return inundation.stage_from_gauge(h["stage_p50_cm"])
    return None


@app.get("/risk")
def get_risk(
    horizon_min: int = Query(60, description="forecast horizon for the second view"),
    zones: bool = Query(True, description="false returns the summary only"),
) -> dict:
    try:
        out = risk_mod.assess(
            stage_m=_stage_now_m(),
            rain_mm_hr=loop.state.rainfall_mm_hr,
            forecast_stage_m=_forecast_stage_m(horizon_min),
            reports_by_zone=reports_mod.store.by_zone(),
        )
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from None
    out["summary"]["horizon_min"] = horizon_min
    if not zones:
        out.pop("zones", None)
    return out


@app.get("/facilities/at-risk")
def get_facilities_at_risk(horizon_min: int = Query(60)) -> dict:
    try:
        r = risk_mod.assess(
            stage_m=_stage_now_m(),
            rain_mm_hr=loop.state.rainfall_mm_hr,
            forecast_stage_m=_forecast_stage_m(horizon_min),
        )
        return facilities_mod.assess(
            stage_m=_stage_now_m(),
            forecast_stage_m=_forecast_stage_m(horizon_min),
            exposed_population=r["summary"]["population_exposed"],
        )
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from None


# ── Step 7: dynamic evacuation routing ───────────────────────────────────
@app.post("/route")
def post_route(body: dict = Body(...)) -> dict:
    """Route from a point to its nearest USABLE shelter, avoiding flooded roads."""
    try:
        lat = float(body["lat"]); lon = float(body["lon"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "body must be {lat, lon}") from None
    try:
        return routing_mod.route(lat, lon, _stage_now_m())
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from None


@app.get("/routes/coverage")
def get_route_coverage() -> dict:
    """How much of the city can still reach a shelter."""
    try:
        return routing_mod.coverage(_stage_now_m())
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from None


@app.get("/routes/priority")
def get_priority_routes(limit: int = Query(8, ge=1, le=25)) -> dict:
    """Evacuation routes out of at-risk critical facilities, hospitals first."""
    try:
        return routing_mod.priority_routes(_stage_now_m(), limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from None


# ── Step 8: alerting ─────────────────────────────────────────────────────
ALERT_EVERY_WORLD_S = 300.0        # evaluate every 5 world-minutes
_last_alert_eval = {"world_s": -1e9}


def _alert_lead_min() -> int:
    return 60


def _run_alert_cycle() -> list[dict]:
    """Evaluate and dispatch. Called on a world-time cadence, not every tick."""
    stage = _stage_now_m()
    fc = _forecast_stage_m(_alert_lead_min())
    r = risk_mod.assess(stage_m=stage, rain_mm_hr=loop.state.rainfall_mm_hr,
                        forecast_stage_m=fc,
                        reports_by_zone=reports_mod.store.by_zone())
    # Close the loop: reporters whose zone the model independently rates as
    # risky gain standing; those who cried wolf lose it.
    reports_mod.store.feedback({z["h3"]: z["risk"] for z in r["zones"]})

    # Confidence from the nowcast's own interval: a tight band is a confident
    # forecast. This is the number that becomes CAP <certainty>.
    conf = 0.5
    cap_certainty = "Possible"
    try:
        nc = nowcast.predict(loop.history, _forecast_rain())
        if nc.get("ready"):
            h = next((x for x in nc["horizons"]
                      if x["horizon_min"] == _alert_lead_min()), None)
            if h:
                # Band width is the CONFIDENCE shown to a human.
                conf = max(0.05, min(1.0, 1.0 - (h["band_width_cm"] / 200.0)))
                # Whether the event happens is a different question — CAP
                # certainty comes from the quantiles, not the band width.
                cap_certainty = alerts_mod.certainty_from_quantiles(
                    nc["stage_now_cm"], h["stage_p10_cm"], h["stage_p50_cm"]
                )
    except FileNotFoundError:
        pass

    reason = []
    try:
        ex = nowcast.explain(loop.history, _forecast_rain(), _alert_lead_min())
        if ex.get("ready"):
            reason = ex["contributions"][:3]
    except FileNotFoundError:
        pass

    return alerts_mod.dispatcher.evaluate(
        r["zones"], lead_min=_alert_lead_min(), confidence=conf,
        cap_certainty=cap_certainty,
        exercise=(loop.state.mode == "scenario"), reason=reason,
    )


@app.get("/alerts")
def get_alerts(limit: int = Query(20, ge=1, le=100)) -> dict:
    d = alerts_mod.dispatcher
    items = sorted(d.alerts.values(), key=lambda a: a.get("seq", 0), reverse=True)[:limit]
    return {"count": len(d.alerts), "channels": d.channels(),
            "rate_limited_last_cycle": d.suppressed,
            "max_per_cycle": alerts_mod.MAX_PER_CYCLE,
            "languages": i18n.LANGUAGES, "alerts": items}


@app.get("/alerts/outbox")
def get_outbox(lang: str | None = Query(None), limit: int = Query(30, ge=1, le=60)) -> dict:
    msgs = list(alerts_mod.dispatcher.outbox)
    if lang:
        msgs = [m for m in msgs if m["language"] == lang]
    return {"messages": msgs[:limit], "languages": i18n.LANGUAGES}


@app.get("/alerts/{alert_id}.xml")
def get_alert_cap(alert_id: str):
    from fastapi.responses import Response
    a = alerts_mod.dispatcher.alerts.get(alert_id)
    if not a:
        raise HTTPException(404, "no such alert")
    return Response(content=alerts_mod.dispatcher.cap_xml(a),
                    media_type="application/cap+xml")


@app.post("/alerts/evaluate")
def post_alert_evaluate() -> dict:
    """Force an evaluation now (the loop also does this every 5 world-minutes)."""
    try:
        fired = _run_alert_cycle()
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from None
    return {"fired": len(fired),
            "rate_limited": alerts_mod.dispatcher.suppressed,
            "alerts": fired}


@app.post("/alerts/reset")
def post_alert_reset() -> dict:
    alerts_mod.dispatcher.reset()
    return {"ok": True}


# ── Step 9: crowdsourced verification ────────────────────────────────────
@app.post("/reports")
async def post_report(
    lat: float = Form(...),
    lon: float = Form(...),
    depth_cm: int | None = Form(None),
    reporter: str = Form("anon"),
    photo: UploadFile | None = File(None),
) -> dict:
    """Submit a geotagged citizen report, optionally with a photo."""
    cv_result = None
    if photo is not None:
        data = await photo.read()
        if data:
            cv_result = cv_mod.classify(data)

    rec = reports_mod.store.add(reporter=reporter, lat=lat, lon=lon,
                                depth_cm=depth_cm, cv=cv_result)
    return {
        "id": rec["id"], "h3": rec["h3"],
        "trust": rec["trust"], "verified": rec.get("verified", False),
        "components": rec.get("trust_components", {}),
        "nearby_supporting_reports": rec.get("nearby", 0),
        "cv": cv_result or {"note": "no photo submitted"},
        "min_trust_to_count": trust_threshold(),
    }


def trust_threshold() -> float:
    import trust as t
    return t.MIN_TRUST


@app.get("/reports")
def get_reports() -> dict:
    gj = reports_mod.store.geojson()
    verified = sum(1 for f in gj["features"] if f["properties"]["verified"])
    return {
        "geojson": gj,
        "total": len(gj["features"]),
        "verified": verified,
        "unverified": len(gj["features"]) - verified,
        "zones_influenced": len(reports_mod.store.by_zone()),
        "cv_model": cv_mod.MODEL_ID,
        "cv_trained": False,
        "min_trust": trust_threshold(),
    }


@app.post("/reports/reset")
def post_reports_reset() -> dict:
    reports_mod.store.reset()
    return {"ok": True}


# ── Step 10: authority dashboard ─────────────────────────────────────────
@app.get("/dispatch")
def get_dispatch(teams: int = Query(6, ge=1, le=40),
                 limit: int = Query(12, ge=1, le=60),
                 horizon_min: int = Query(60)) -> dict:
    """Ranked response priorities with team assignments."""
    try:
        return dispatch_mod.plan(
            stage_m=_stage_now_m(),
            forecast_stage_m=_forecast_stage_m(horizon_min),
            rain_mm_hr=loop.state.rainfall_mm_hr,
            reports_by_zone=reports_mod.store.by_zone(),
            teams=teams, limit=limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from None


@app.get("/situation")
def get_situation(horizon_min: int = Query(60)) -> dict:
    """Everything an operations officer needs, in one call.

    The dashboard polls this instead of five endpoints: a single consistent
    snapshot, so the population figure and the shelter figure can never come
    from different moments of the simulation.
    """
    stage = _stage_now_m()
    fc = _forecast_stage_m(horizon_min)
    try:
        r = risk_mod.assess(stage_m=stage, rain_mm_hr=loop.state.rainfall_mm_hr,
                            forecast_stage_m=fc,
                            reports_by_zone=reports_mod.store.by_zone())
        fa = facilities_mod.assess(stage_m=stage, forecast_stage_m=fc,
                                   exposed_population=r["summary"]["population_exposed"])
        cov = routing_mod.coverage(stage)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from None

    r["summary"]["horizon_min"] = horizon_min      # /risk stamps this; /situation must too
    rep = reports_mod.store.geojson()
    d = alerts_mod.dispatcher
    return {
        "world": {"t": loop.state.t.isoformat(), "tick": loop.state.tick,
                  "mode": loop.state.mode, "rain_mm_hr": round(loop.state.rainfall_mm_hr, 1),
                  "gauge_cm": round(next(iter(loop.state.stages.values()), 0.0), 1)},
        "risk": r["summary"],
        "facilities": fa["summary"],
        "routing": cov,
        "reports": {"total": len(rep["features"]),
                    "verified": sum(1 for f in rep["features"]
                                    if f["properties"]["verified"])},
        "alerts": {"total": len(d.alerts),
                   "rate_limited": d.suppressed,
                   "recent": sorted(d.alerts.values(),
                                    key=lambda a: a.get("seq", 0), reverse=True)[:5]},
    }


# ── Step 12: demo control ────────────────────────────────────────────────
DEMO_SPEED = 10.0
DEMO_CALM_MM_HR = 8.0


@app.get("/hazards")
def get_hazards() -> dict:
    """What generalises beyond flood, and what would still need building."""
    return hazards_mod.summary()


@app.post("/demo/reset")
def post_demo_reset() -> dict:
    """One call to a known-good starting state. Used by `make demo`.

    On stage you do not want to be hunting for three different reset buttons
    while a room waits, and a half-reset state (alerts from the last run,
    reports from the run before) is worse than no reset at all.
    """
    alerts_mod.dispatcher.reset()
    reports_mod.store.reset()
    _last_alert_eval["world_s"] = -1e9
    loop.set_adapter(adapters.build("scenario"), speed=DEMO_SPEED)
    loop.adapter.rain_mm_hr = DEMO_CALM_MM_HR
    loop.playing = True
    loop.reset()
    return {
        "ok": True,
        "mode": loop.state.mode,
        "speed": loop.speed,
        "rain_mm_hr": DEMO_CALM_MM_HR,
        "alerts_cleared": True,
        "reports_cleared": True,
        "note": "calm start — drag rainfall or hit a preset to begin the event",
    }


# ── Step 13: real outbound warnings (authority only) ─────────────────────
def _worst_forecast_severity() -> str | None:
    """Highest FORECAST severity across all zones — what arms the send."""
    r = risk_mod.assess(
        stage_m=_stage_now_m(),
        rain_mm_hr=loop.state.rainfall_mm_hr,
        forecast_stage_m=_forecast_stage_m(_alert_lead_min()),
        reports_by_zone=reports_mod.store.by_zone(),
    )
    worst, best_rank = None, 0
    for z in r["zones"]:
        sev = z.get("severity_forecast") or z.get("severity")
        if notify_mod.RANK.get(sev or "", 0) > best_rank:
            best_rank, worst = notify_mod.RANK[sev], sev
    return worst


@app.get("/recipients")
def get_recipients() -> dict:
    rows = [rec_mod.masked(r) for r in rec_mod.all_recipients()]
    return {
        "recipients": rows,
        "active": len(rec_mod.active()),
        "channels": channels_mod.status(),
    }


@app.post("/recipients")
def post_recipient(body: dict = Body(...)) -> dict:
    try:
        r = rec_mod.add(
            name=str(body.get("name", "")),
            phone=str(body.get("phone", "")),
            lang=str(body.get("lang", "te")),
            zone=body.get("zone"),
            opted_in=bool(body.get("opted_in", False)),
            note=str(body.get("note", "")),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return rec_mod.masked(r)


@app.post("/recipients/{rid}/opt-in")
def post_opt_in(rid: int, body: dict = Body(default={})) -> dict:
    r = rec_mod.set_opt_in(rid, bool(body.get("opted_in", True)))
    if not r:
        raise HTTPException(404, "no such recipient")
    return rec_mod.masked(r)


@app.delete("/recipients/{rid}")
def delete_recipient(rid: int) -> dict:
    if not rec_mod.remove(rid):
        raise HTTPException(404, "no such recipient")
    return {"ok": True}


@app.get("/notify/state")
def get_notify_state() -> dict:
    """Is the send armed, who would receive it, and what would it say."""
    worst = _worst_forecast_severity()
    sev = worst or "advisory"
    zone = "Visakhapatnam"
    return {
        "armed": notify_mod.armed(worst),
        "arm_threshold": notify_mod.ARM_AT,
        "worst_forecast_severity": worst,
        "lead_min": _alert_lead_min(),
        "channels": channels_mod.status(),
        "recipients_active": len(rec_mod.active()),
        "preview": notify_mod.preview(sev, zone, _alert_lead_min()),
        "exercise": loop.state.mode == "scenario",
    }


@app.post("/notify/send")
def post_notify_send(body: dict = Body(default={})) -> dict:
    """Send for real. Requires the forecast to have armed it."""
    worst = _worst_forecast_severity()
    if not notify_mod.armed(worst) and not body.get("force"):
        raise HTTPException(
            409,
            f"not armed: worst forecast severity is {worst or 'none'}, "
            f"need {notify_mod.ARM_AT} or higher. Raise the rainfall first.",
        )
    if not rec_mod.active():
        raise HTTPException(409, "no opted-in recipients")

    return notify_mod.send(
        severity=worst or "watch",
        zone_label=str(body.get("zone", "Visakhapatnam")),
        lead_min=_alert_lead_min(),
        channel=str(body.get("channel", "sms")),
        dry_run=bool(body.get("dry_run", False)),
    )


@app.post("/notify/refresh")
def post_notify_refresh() -> dict:
    """Re-check delivery. 'accepted' is not 'delivered'."""
    return notify_mod.refresh_delivery()


@app.get("/notify/probe")
def get_notify_probe() -> dict:
    """Is the Android phone reachable? Check this before the demo, not during."""
    ch = channels_mod.get("phone")
    if not hasattr(ch, "probe"):
        return {"ok": False, "status": "n/a"}
    r = ch.probe()
    return {"ok": r.ok, "status": r.status, "error": r.error, "detail": r.detail,
            "url": getattr(ch, "base", "")}


@app.get("/notify/log")
def get_notify_log(limit: int = Query(10, ge=1, le=50)) -> dict:
    return {"entries": list(notify_mod.audit)[:limit]}
