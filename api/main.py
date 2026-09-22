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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import adapters
from loop import TickLoop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("sentinel.api")

TICK_INTERVAL_S = float(os.getenv("TICK_INTERVAL_S", "1.0"))
ADAPTER_NAME = os.getenv("ADAPTER", "synthetic")
DATABASE_URL = os.getenv("DATABASE_URL", "")

HEARTBEAT_S = 15.0          # keeps proxies from closing an idle SSE stream

loop: TickLoop


@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = TickLoop(adapters.build(ADAPTER_NAME), interval_s=TICK_INTERVAL_S)
    loop.start()
    log.info("adapter=%s tick=%.2fs", ADAPTER_NAME, TICK_INTERVAL_S)
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
