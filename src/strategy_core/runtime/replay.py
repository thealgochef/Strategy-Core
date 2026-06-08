"""Strategy-Core replay controller over neutral runtime sources."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from strategy_core.data.events import DataQualityWarning, safe_text
from strategy_core.runtime.state import RuntimeUpdate, StrategyRuntime
from strategy_core.types import Quote, Trade

__all__ = ["ReplayConfig", "ReplayRuntime", "ReplayState", "ReplayStatus"]


class ReplayState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class ReplayConfig:
    speed: float = 0.0
    max_events: int | None = None


@dataclass(frozen=True, slots=True)
class ReplayStatus:
    state: ReplayState
    events_processed: int
    warnings_recorded: int
    last_event_ts_utc: datetime | None = None
    last_error: str | None = None
    last_message: str = ""
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None
    failed_at_utc: datetime | None = None


ProcessItem = Callable[[Any], Any]
Predicate = Callable[[Any], bool]
TimestampGetter = Callable[[Any], datetime | None]
UpdateCallback = Callable[[Any], Awaitable[None] | None]
RegressionCallback = Callable[[Any, datetime], Any]
_REPLAY_DONE = object()


def _next_or_done(iterator: Any) -> Any:
    return next(iterator, _REPLAY_DONE)


class ReplayRuntime:
    def __init__(
        self,
        runtime: StrategyRuntime | None,
        source: Any,
        *,
        process_item: ProcessItem | None = None,
        on_update: UpdateCallback | None = None,
        is_event: Predicate | None = None,
        is_warning: Predicate | None = None,
        event_timestamp: TimestampGetter | None = None,
        on_timestamp_regression: RegressionCallback | None = None,
    ) -> None:
        if runtime is None and process_item is None:
            raise ValueError("runtime or process_item is required")
        self.runtime = runtime
        self.source = source
        self.updates: list[Any] = []
        self._process_item = process_item or self._default_process_item
        self._on_update = on_update
        self._is_event = is_event or _default_is_event
        self._is_warning = is_warning or _default_is_warning
        self._event_timestamp = event_timestamp or _default_event_timestamp
        self._on_timestamp_regression = on_timestamp_regression
        self._state = ReplayState.IDLE
        self._events_processed = 0
        self._warnings_recorded = 0
        self._last_event_ts_utc: datetime | None = None
        self._last_error: str | None = None
        self._last_message = ""
        self._started_at_utc: datetime | None = None
        self._completed_at_utc: datetime | None = None
        self._failed_at_utc: datetime | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._stop_requested = False

    def status(self) -> ReplayStatus:
        return ReplayStatus(
            state=self._state,
            events_processed=self._events_processed,
            warnings_recorded=self._warnings_recorded,
            last_event_ts_utc=self._last_event_ts_utc,
            last_error=self._last_error,
            last_message=self._last_message,
            started_at_utc=self._started_at_utc,
            completed_at_utc=self._completed_at_utc,
            failed_at_utc=self._failed_at_utc,
        )

    async def start(self, config: ReplayConfig | None = None) -> None:
        config = config or ReplayConfig()
        self._state = ReplayState.RUNNING
        self._events_processed = 0
        self._warnings_recorded = 0
        # audit N7: clear accumulated updates so each run starts clean; otherwise
        # _record_update appends across every replay and self.updates grows unbounded.
        self.updates = []
        self._last_event_ts_utc = None
        self._last_error = None
        self._last_message = "historical replay running"
        self._started_at_utc = datetime.now(UTC)
        self._completed_at_utc = None
        self._failed_at_utc = None
        self._stop_requested = False
        self._pause_event.set()
        previous_ts: datetime | None = None
        items_processed = 0
        try:
            iterator = iter(self.source.events())
            while True:
                if config.max_events is not None and items_processed >= config.max_events:
                    break
                item = await asyncio.to_thread(_next_or_done, iterator)
                if item is _REPLAY_DONE:
                    break
                await self._pause_event.wait()
                if self._stop_requested:
                    self._state = ReplayState.STOPPED
                    self._completed_at_utc = datetime.now(UTC)
                    self._last_message = "historical replay stopped"
                    return
                item_ts = self._event_timestamp(item)
                if previous_ts is not None and config.speed > 0 and item_ts is not None:
                    delay = max((item_ts - previous_ts).total_seconds(), 0) / config.speed
                    await asyncio.sleep(min(delay, 0.25))
                await self._pause_event.wait()
                if self._stop_requested:
                    self._state = ReplayState.STOPPED
                    self._completed_at_utc = datetime.now(UTC)
                    self._last_message = "historical replay stopped"
                    return
                if item_ts is not None and previous_ts is not None and item_ts < previous_ts:
                    callback = self._on_timestamp_regression
                    if callback is not None:
                        update = callback(item, previous_ts)
                        self._warnings_recorded += 1
                        items_processed += 1
                        await self._record_update(update)
                        await asyncio.sleep(0)
                        continue
                update = self._process_item(item)
                if self._is_warning(item):
                    self._warnings_recorded += 1
                if self._is_event(item):
                    self._events_processed += 1
                    if item_ts is not None:
                        self._last_event_ts_utc = item_ts
                        previous_ts = item_ts
                items_processed += 1
                await self._record_update(update)
                await asyncio.sleep(0)
            self._state = ReplayState.COMPLETED
            self._completed_at_utc = datetime.now(UTC)
            self._last_message = "historical replay completed"
        except Exception as exc:
            self._state = ReplayState.FAILED
            self._last_error = type(exc).__name__
            self._last_message = safe_text(str(exc)) or type(exc).__name__
            self._failed_at_utc = datetime.now(UTC)

    async def pause(self) -> None:
        if self._state == ReplayState.RUNNING:
            self._state = ReplayState.PAUSED
            self._pause_event.clear()

    async def resume(self) -> None:
        if self._state == ReplayState.PAUSED:
            self._state = ReplayState.RUNNING
            self._pause_event.set()

    async def stop(self) -> None:
        self._stop_requested = True
        self._pause_event.set()

    async def _record_update(self, update: Any) -> None:
        if not _has_deltas(update):
            return
        self.updates.append(update)
        if self._on_update is not None:
            result = self._on_update(update)
            if result is not None:
                await result

    def _default_process_item(self, item: Any) -> RuntimeUpdate:
        if self.runtime is None:  # pragma: no cover - guarded by __init__
            raise RuntimeError("runtime is not configured")
        return self.runtime.process_event(item)


def _default_is_warning(item: Any) -> bool:
    return isinstance(item, DataQualityWarning) or item.__class__.__name__ == "DataQualityWarning"


def _default_is_event(item: Any) -> bool:
    return isinstance(item, Trade | Quote) or (
        _default_event_timestamp(item) is not None and not _default_is_warning(item)
    )


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
