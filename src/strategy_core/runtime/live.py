"""Generic live-feed lifecycle controller for Strategy-Core runtime integrations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from strategy_core.data.events import safe_text

__all__ = ["LiveRuntime", "LiveState", "LiveStatus"]


class LiveState(StrEnum):
    IDLE = "idle"
    CONNECTING = "connecting"
    RUNNING = "running"
    STOPPED = "stopped"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class LiveStatus:
    state: LiveState
    events_processed: int
    warnings_recorded: int
    last_event_ts_utc: datetime | None = None
    last_error: str | None = None
    last_message: str = ""
    started_at_utc: datetime | None = None
    stopped_at_utc: datetime | None = None
    failed_at_utc: datetime | None = None


ProcessItem = Callable[[Any], Any]
Predicate = Callable[[Any], bool]
TimestampGetter = Callable[[Any], datetime | None]
UpdateCallback = Callable[[Any], Awaitable[None] | None]


class LiveRuntime:
    """Small async live-source controller with no provider-specific dependencies.

    The source only needs ``start()``, ``stop()``, and async ``events()`` methods.
    Integrations provide ``process_item`` to map provider/domain items into their
    runtime update shape. This keeps live lifecycle state in Strategy-Core while
    allowing Trade-Lab to keep API/WebSocket DTOs at its boundary.
    """

    def __init__(
        self,
        source: Any,
        *,
        process_item: ProcessItem,
        on_update: UpdateCallback | None = None,
        is_event: Predicate | None = None,
        is_warning: Predicate | None = None,
        event_timestamp: TimestampGetter | None = None,
    ) -> None:
        self.source = source
        self._process_item = process_item
        self._on_update = on_update
        self._is_event = is_event or _default_is_event
        self._is_warning = is_warning or _default_is_warning
        self._event_timestamp = event_timestamp or _default_event_timestamp
        self._state = LiveState.IDLE
        self._events_processed = 0
        self._warnings_recorded = 0
        self._last_event_ts_utc: datetime | None = None
        self._last_error: str | None = None
        self._last_message = ""
        self._started_at_utc: datetime | None = None
        self._stopped_at_utc: datetime | None = None
        self._failed_at_utc: datetime | None = None
        self._task: asyncio.Task[None] | None = None

    def status(self) -> LiveStatus:
        return LiveStatus(
            state=self._state,
            events_processed=self._events_processed,
            warnings_recorded=self._warnings_recorded,
            last_event_ts_utc=self._last_event_ts_utc,
            last_error=self._last_error,
            last_message=self._last_message,
            started_at_utc=self._started_at_utc,
            stopped_at_utc=self._stopped_at_utc,
            failed_at_utc=self._failed_at_utc,
        )

    async def start(self) -> None:
        if self._state in {LiveState.CONNECTING, LiveState.RUNNING} or (
            self._task is not None and not self._task.done()
        ):
            raise RuntimeError("live source is already running")
        self._state = LiveState.CONNECTING
        self._events_processed = 0
        self._warnings_recorded = 0
        self._last_event_ts_utc = None
        self._last_error = None
        self._last_message = "live source connecting"
        self._started_at_utc = datetime.now(UTC)
        self._stopped_at_utc = None
        self._failed_at_utc = None
        try:
            await self.source.start()
        except Exception as exc:
            self._state = LiveState.FAILED
            self._last_error = type(exc).__name__
            self._last_message = safe_text(str(exc)) or type(exc).__name__
            self._failed_at_utc = datetime.now(UTC)
            with suppress(Exception):
                await self.source.stop()
            raise
        self._state = LiveState.RUNNING
        self._last_message = "live source running"
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await self.source.stop()
        self._state = LiveState.STOPPED
        self._stopped_at_utc = datetime.now(UTC)
        self._last_message = "live source stopped"

    async def wait_finished(self) -> None:
        task = self._task
        if task is not None:
            await task

    async def _run(self) -> None:
        try:
            async for item in self.source.events():
                update = self._process_item(item)
                if self._is_warning(item):
                    self._warnings_recorded += 1
                if self._is_event(item):
                    self._events_processed += 1
                    ts = self._event_timestamp(item)
                    if ts is not None:
                        self._last_event_ts_utc = ts
                if _has_deltas(update) and self._on_update is not None:
                    result = self._on_update(update)
                    if result is not None:
                        await result
                await asyncio.sleep(0)
            if self._state == LiveState.RUNNING:
                self._state = LiveState.DISCONNECTED
                self._stopped_at_utc = datetime.now(UTC)
                self._last_message = "live source disconnected"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._state = LiveState.FAILED
            self._last_error = type(exc).__name__
            self._last_message = safe_text(str(exc)) or type(exc).__name__
            self._failed_at_utc = datetime.now(UTC)


def _default_is_event(item: Any) -> bool:
    return _default_event_timestamp(item) is not None and not _default_is_warning(item)


def _default_is_warning(item: Any) -> bool:
    return item.__class__.__name__ == "DataQualityWarning"


def _default_event_timestamp(item: Any) -> datetime | None:
    ts = getattr(item, "event_ts_utc", None)
    if isinstance(ts, datetime):
        return ts.astimezone(UTC) if ts.tzinfo is not None else ts
    return None


def _has_deltas(update: Any) -> bool:
    if update is None:
        return False
    has_deltas = getattr(update, "has_deltas", None)
    if callable(has_deltas):
        return bool(has_deltas())
    return True
