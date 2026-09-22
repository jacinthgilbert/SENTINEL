"""Tick scheduler + subscriber fan-out.

Runs every TICK_INTERVAL_S in live mode. In scenario mode (Step 4) the same
loop runs faster and multiplies world-time per tick — the downstream code
cannot tell the difference, which is the whole point.
"""

from __future__ import annotations

import asyncio
import logging

from world import Adapter, WorldState

log = logging.getLogger("sentinel.loop")

_QUEUE_MAX = 8      # a slow client drops frames rather than stalling the loop


class TickLoop:
    def __init__(self, adapter: Adapter, interval_s: float = 1.0) -> None:
        self._adapter = adapter
        self._interval_s = interval_s
        self._state: WorldState = adapter.initial()
        self._subscribers: set[asyncio.Queue[WorldState]] = set()
        self._task: asyncio.Task | None = None

    # ── state ────────────────────────────────────────────────────────────
    @property
    def state(self) -> WorldState:
        return self._state

    # ── pub/sub ──────────────────────────────────────────────────────────
    def subscribe(self) -> asyncio.Queue[WorldState]:
        q: asyncio.Queue[WorldState] = asyncio.Queue(maxsize=_QUEUE_MAX)
        q.put_nowait(self._state)          # new client gets current state at once
        self._subscribers.add(q)
        log.info("subscriber joined (%d total)", len(self._subscribers))
        return q

    def unsubscribe(self, q: asyncio.Queue[WorldState]) -> None:
        self._subscribers.discard(q)
        log.info("subscriber left (%d total)", len(self._subscribers))

    def _publish(self, state: WorldState) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(state)
            except asyncio.QueueFull:
                # Drop the frame. A stalled browser tab must not slow the world.
                pass

    # ── lifecycle ────────────────────────────────────────────────────────
    async def _run(self) -> None:
        log.info("tick loop started (interval=%.2fs)", self._interval_s)
        while True:
            await asyncio.sleep(self._interval_s)
            try:
                self._state = self._adapter.step(self._state, self._interval_s)
                self._publish(self._state)
            except Exception:
                log.exception("tick failed; holding last good state")

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
