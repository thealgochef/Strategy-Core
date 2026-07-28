"""Streaming, event-at-a-time TIME-bar builder (Phase F).

Mirrors :class:`~strategy_core.candles.streaming.CandleEngine`'s shape — per-timeframe
current bar, freeze-and-restart on a trading-day change as ``END_OF_DAY`` (incomplete),
a ``finalize_trading_day`` twin, and the same :class:`CandleUpdate` result type — with
the TIME close trigger instead of the trade-count one. The batch builder in
``candles/time_batch.py`` produces an identical :class:`~strategy_core.types.Bar`
sequence; the parity test (``tests/test_time_bar_parity.py``) locks the two together.

Architect-ratified design:

* A TIME bar carries ``kind=BarKind.TIME`` and ``timeframe_ticks = interval SECONDS``
  (the ``BarSpec.size`` convention; 0 is an existing "unspecified" sentinel and is
  unavailable). ``bar_id`` is ``f"{seconds}s:{trading_day}:{bar_index}"``.
* BUCKETING is anchored at the trading-day boundary INSTANT:
  ``bucket = floor((ts_utc - day_start_utc) / interval)`` with ``day_start_utc`` from
  :func:`~strategy_core.candles._buckets.trading_day_start_utc` — DST-correct because
  elapsed time from an absolute instant is used, never wall-clock labels.
* NO EMPTY BARS: a bucket with no trades produces no bar. ``bar_index`` is DENSE over
  EMITTED bars per ``(timeframe, trading_day)`` starting at 0 (the tick allocator's
  rule), not the wall-clock bucket ordinal.
* DERIVE ONCE, AGGREGATE UPWARD: trades fold into the 60s accumulator only; each
  CLOSED 60s bar feeds the higher-timeframe accumulators (every interval is an
  integer multiple of 60). Higher OHLC = first open / max high / min low / last
  close over constituent 60s bars; volume / trade_count are sums over the 60s bars
  that EXIST.
* COMPLETENESS: a bar is ``COMPLETE`` iff a LATER bucket in the same trading day and
  timeframe produced a bar (observable: a later bar OPENED); otherwise it freezes
  ``END_OF_DAY`` incomplete at the day roll / ``finalize_trading_day``. Bars are
  emitted when a later bucket opens, never on a wall clock.

Producers deliver trades in wire order (``TRADE_BAR_ORDER``); like the tick engine,
this engine never sorts. A late out-of-order trade would fold into the currently open
bar rather than its true bucket, exactly as it would join the wrong tick bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from strategy_core.candles._buckets import trading_day_start_utc
from strategy_core.candles._ids import make_bar_id
from strategy_core.candles.streaming import CandleUpdate
from strategy_core.constants import RESEARCH_SESSION_SCHEME
from strategy_core.decisions.sessions import trading_day_for
from strategy_core.types import Bar, BarKind, CloseReason, SessionScheme, Trade

__all__ = ["TimeBarEngine", "BASE_INTERVAL_SECONDS", "DEFAULT_TIME_TIMEFRAMES"]

#: The base derivation interval: trades aggregate into 60s bars once; every higher
#: timeframe aggregates those (never a second pass over the trade stream).
BASE_INTERVAL_SECONDS = 60
#: The ratified timeframe set, in seconds: 1m 3m 5m 10m 15m 30m 1H 4H.
DEFAULT_TIME_TIMEFRAMES = (60, 180, 300, 600, 900, 1800, 3600, 14400)

_US_PER_SECOND = 1_000_000


@dataclass(slots=True)
class _MutableTimeBar:
    """Mutable in-progress TIME bar. Mirrors ``streaming._MutableCandle`` plus the
    wall-clock ``bucket`` it occupies (the close trigger; NOT the emitted index)."""

    interval_seconds: int
    trading_day: date
    bucket: int
    bar_index: int
    bar_id: str
    open_ts_utc: datetime
    close_ts_utc: datetime
    open_ticks: int
    high_ticks: int
    low_ticks: int
    close_ticks: int
    volume: int
    trade_count: int

    def freeze(self, *, complete: bool, reason: CloseReason | None) -> Bar:
        """Materialize an immutable TIME :class:`Bar`; ``is_partial == not complete``."""
        return Bar(
            timeframe_ticks=self.interval_seconds,
            trading_day=self.trading_day,
            bar_index=self.bar_index,
            bar_id=self.bar_id,
            open_ts_utc=self.open_ts_utc,
            close_ts_utc=self.close_ts_utc,
            open_ticks=self.open_ticks,
            high_ticks=self.high_ticks,
            low_ticks=self.low_ticks,
            close_ticks=self.close_ticks,
            volume=self.volume,
            trade_count=self.trade_count,
            is_complete=complete,
            is_partial=not complete,
            close_reason=reason,
            kind=BarKind.TIME,
        )


class TimeBarEngine:
    """Build all configured TIME bars concurrently from a stream of trades.

    Only :class:`~strategy_core.types.Trade` events are accepted (quotes/status are
    not prints), and the trading day comes from
    :func:`strategy_core.decisions.sessions.trading_day_for` under ``scheme`` —
    both exactly as :class:`~strategy_core.candles.streaming.CandleEngine`.
    """

    def __init__(
        self,
        timeframes_seconds: tuple[int, ...] = DEFAULT_TIME_TIMEFRAMES,
        *,
        scheme: SessionScheme = RESEARCH_SESSION_SCHEME,
    ) -> None:
        if not timeframes_seconds:
            raise ValueError("time timeframes must be non-empty")
        for seconds in timeframes_seconds:
            if seconds < BASE_INTERVAL_SECONDS or seconds % BASE_INTERVAL_SECONDS:
                raise ValueError(
                    "time timeframes must be positive multiples of "
                    f"{BASE_INTERVAL_SECONDS}s (got {seconds})"
                )
        self.timeframes = tuple(sorted(set(timeframes_seconds)))
        self._scheme = scheme
        # The 60s accumulator always runs (it is the derivation base); its bars are
        # only EMITTED when 60 was actually requested.
        self._emit_base = BASE_INTERVAL_SECONDS in self.timeframes
        self._higher = tuple(tf for tf in self.timeframes if tf != BASE_INTERVAL_SECONDS)
        self._trading_day: date | None = None
        self._day_start_utc: datetime | None = None
        self._minute: _MutableTimeBar | None = None
        self._current: dict[int, _MutableTimeBar] = {}
        self._next_index: dict[tuple[int, date], int] = {}

    # ── public API (CandleEngine mirror) ──────────────────────────────────────
    def process_trade(self, trade: Trade) -> CandleUpdate:
        """Fold one trade into the 60s accumulator; cascade closed 60s bars upward."""
        trading_day = trading_day_for(trade.event_ts_utc, self._scheme)
        if trading_day is None:  # closed window -> skipped, like the tick engine
            return self.snapshot_update(())
        completed: list[Bar] = []
        if self._trading_day is not None and trading_day != self._trading_day:
            # Trading-day rollover: freeze every open bar END_OF_DAY (incomplete)
            # and start fresh on the new day.
            completed.extend(self._roll_day())
        if self._trading_day != trading_day:
            self._trading_day = trading_day
            self._day_start_utc = trading_day_start_utc(trading_day, self._scheme)
        # Integer-microsecond arithmetic so a trade landing EXACTLY on a bucket edge
        # buckets identically to the batch builder's integer-nanosecond floor-divide.
        delta = trade.event_ts_utc - self._day_start_utc  # type: ignore[operator]
        elapsed_us = (delta.days * 86_400 + delta.seconds) * _US_PER_SECOND + delta.microseconds
        bucket = elapsed_us // (BASE_INTERVAL_SECONDS * _US_PER_SECOND)
        minute = self._minute
        if minute is not None and bucket > minute.bucket:
            # A later bucket produced a bar -> the open 60s bar closes COMPLETE.
            completed.extend(self._close_minute(complete=True))
            minute = None
        if minute is None:
            self._minute = _MutableTimeBar(
                interval_seconds=BASE_INTERVAL_SECONDS,
                trading_day=trading_day,
                bucket=bucket,
                bar_index=(idx := self._allocate_bar_index(BASE_INTERVAL_SECONDS, trading_day)),
                bar_id=make_bar_id(BASE_INTERVAL_SECONDS, trading_day, idx, BarKind.TIME),
                open_ts_utc=trade.event_ts_utc,
                close_ts_utc=trade.event_ts_utc,
                open_ticks=trade.price_ticks,
                high_ticks=trade.price_ticks,
                low_ticks=trade.price_ticks,
                close_ticks=trade.price_ticks,
                volume=trade.size,
                trade_count=1,
            )
        else:
            minute.close_ts_utc = trade.event_ts_utc
            minute.close_ticks = trade.price_ticks
            if trade.price_ticks > minute.high_ticks:
                minute.high_ticks = trade.price_ticks
            if trade.price_ticks < minute.low_ticks:
                minute.low_ticks = trade.price_ticks
            minute.volume += trade.size
            minute.trade_count += 1
        return self.snapshot_update(tuple(completed))

    def snapshot_update(self, completed: tuple[Bar, ...]) -> CandleUpdate:
        """Pair ``completed`` with every in-progress bar frozen incomplete
        (``close_reason=None``), ascending timeframe — the CandleEngine mirror."""
        current: list[Bar] = []
        if self._emit_base and self._minute is not None:
            current.append(self._minute.freeze(complete=False, reason=None))
        for tf in self._higher:
            open_bar = self._current.get(tf)
            if open_bar is not None:
                current.append(open_bar.freeze(complete=False, reason=None))
        return CandleUpdate(completed=completed, current=tuple(current))

    def finalize_trading_day(self) -> tuple[Bar, ...]:
        """Explicitly close every open bar END_OF_DAY (incomplete) — the
        ``CandleEngine.finalize_trading_day`` twin. The trailing partial 60s bar
        still folds into its higher-timeframe bars first, exactly as the batch
        builder counts it as a constituent of the day's final higher bars."""
        return tuple(self._roll_day())

    # ── internals ─────────────────────────────────────────────────────────────
    def _close_minute(self, *, complete: bool) -> list[Bar]:
        """Freeze the open 60s bar and cascade it into the higher timeframes.

        The cascade can itself close a higher bar COMPLETE (the 60s bar landed in a
        later higher-timeframe bucket of the same day). Emission order is the closed
        higher bars (ascending timeframe) after the 60s bar itself; order is
        irrelevant to parity, which sorts by (timeframe, day, index).
        """
        minute = self._minute
        assert minute is not None
        self._minute = None
        reason = CloseReason.COMPLETE if complete else CloseReason.END_OF_DAY
        out: list[Bar] = []
        if self._emit_base:
            out.append(minute.freeze(complete=complete, reason=reason))
        for tf in self._higher:
            hbucket = minute.bucket * BASE_INTERVAL_SECONDS // tf
            open_bar = self._current.get(tf)
            if open_bar is not None and hbucket > open_bar.bucket:
                out.append(open_bar.freeze(complete=True, reason=CloseReason.COMPLETE))
                open_bar = None
            if open_bar is None:
                idx = self._allocate_bar_index(tf, minute.trading_day)
                self._current[tf] = _MutableTimeBar(
                    interval_seconds=tf,
                    trading_day=minute.trading_day,
                    bucket=hbucket,
                    bar_index=idx,
                    bar_id=make_bar_id(tf, minute.trading_day, idx, BarKind.TIME),
                    open_ts_utc=minute.open_ts_utc,
                    close_ts_utc=minute.close_ts_utc,
                    open_ticks=minute.open_ticks,
                    high_ticks=minute.high_ticks,
                    low_ticks=minute.low_ticks,
                    close_ticks=minute.close_ticks,
                    volume=minute.volume,
                    trade_count=minute.trade_count,
                )
            else:
                open_bar.close_ts_utc = minute.close_ts_utc
                open_bar.close_ticks = minute.close_ticks
                if minute.high_ticks > open_bar.high_ticks:
                    open_bar.high_ticks = minute.high_ticks
                if minute.low_ticks < open_bar.low_ticks:
                    open_bar.low_ticks = minute.low_ticks
                open_bar.volume += minute.volume
                open_bar.trade_count += minute.trade_count
        return out

    def _roll_day(self) -> list[Bar]:
        """Freeze everything open as END_OF_DAY: the partial 60s bar first (still
        cascading into its higher bars), then every open higher bar."""
        out: list[Bar] = []
        if self._minute is not None:
            out.extend(self._close_minute(complete=False))
        for tf in self._higher:
            open_bar = self._current.pop(tf, None)
            if open_bar is not None:
                out.append(open_bar.freeze(complete=False, reason=CloseReason.END_OF_DAY))
        return out

    def _allocate_bar_index(self, timeframe: int, trading_day: date) -> int:
        """Dense monotonic per-``(timeframe, trading_day)`` index from 0 — the tick
        allocator's rule, so skipped empty buckets never leave index holes."""
        key = (timeframe, trading_day)
        bar_index = self._next_index.get(key, 0)
        self._next_index[key] = bar_index + 1
        return bar_index
