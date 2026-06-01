"""Streaming, event-at-a-time tick-bar builder.

Promoted from Trade-Lab's ``CandleEngine`` /  ``_MutableCandle``
(``Trade-Lab/backend/src/trade_lab/domain/candles.py:35-196``) and generalized so
the trading-day calendar is supplied by a :class:`~strategy_core.types.SessionScheme`
instead of the hardcoded Chicago ``SessionClassifier``. The bar *mechanics* --
per-timeframe current bar, freeze-and-restart on a trading-day change as
``END_OF_DAY`` (incomplete), accumulate high/low/close/volume/trade_count, freeze
``COMPLETE`` when ``trade_count == timeframe``, and the ``timeframe == 1`` emit-now
special case -- are reproduced exactly. The batch builder in ``candles/batch.py``
produces an identical :class:`~strategy_core.types.Bar` sequence; the parity test
(``tests/test_candle_parity.py``) locks the two paths together.

Emits :class:`strategy_core.types.Bar` (not Trade-Lab's ``Candle``) and uses
:class:`strategy_core.types.CloseReason`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from strategy_core.constants import RESEARCH_SESSION_SCHEME
from strategy_core.decisions.sessions import trading_day_for
from strategy_core.candles._ids import make_bar_id
from strategy_core.types import Bar, CloseReason, SessionScheme, Trade

__all__ = ["CandleEngine", "CandleUpdate"]


@dataclass(slots=True)
class _MutableCandle:
    """Mutable in-progress bar accumulator.

    Mirrors Trade-Lab's ``_MutableCandle`` (``candles.py:35-94``) field-for-field;
    ``freeze`` materializes an immutable :class:`~strategy_core.types.Bar`.
    """

    timeframe_ticks: int
    trading_day: date
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
        """Materialize an immutable :class:`Bar`. Mirrors ``_MutableCandle.freeze``
        (``candles.py:77-94``): ``is_partial`` is exactly ``not complete``."""
        return Bar(
            timeframe_ticks=self.timeframe_ticks,
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
        )


@dataclass(frozen=True, slots=True)
class CandleUpdate:
    """Per-trade result: bars that just closed and a snapshot of in-progress bars.

    Mirrors Trade-Lab's ``CandleUpdate`` (``candles.py:97-100``). ``current`` bars
    are frozen with ``is_complete=False`` and ``close_reason=None``.
    """

    completed: tuple[Bar, ...]
    current: tuple[Bar, ...]


class CandleEngine:
    """Build all configured tick bars concurrently from a stream of trades.

    Generalized port of Trade-Lab's ``CandleEngine`` (``candles.py:103-192``).
    Only :class:`~strategy_core.types.Trade` events are accepted because quotes /
    status do not represent prints; this keeps live and replay bar semantics
    identical. The trading day for each trade comes from
    :func:`strategy_core.decisions.sessions.trading_day_for` under ``scheme``
    (replacing Trade-Lab's hardcoded Chicago ``SessionClassifier.classify``);
    trades whose timestamp has no trading day (``None`` -- a closed window) are
    skipped, exactly as the original returned an empty update for ``trading_day
    is None``.
    """

    def __init__(
        self,
        timeframes: tuple[int, ...] = (147, 987, 2000),
        *,
        scheme: SessionScheme = RESEARCH_SESSION_SCHEME,
    ) -> None:
        # candles.py:111-112 -- positive timeframes only.
        if not timeframes or any(size <= 0 for size in timeframes):
            raise ValueError("tick timeframes must be positive")
        # candles.py:113 -- dedup + ascending order so iteration is deterministic.
        self.timeframes = tuple(sorted(set(timeframes)))
        self._scheme = scheme
        self._current: dict[int, _MutableCandle] = {}
        self._next_index: dict[tuple[int, date], int] = {}

    def process_trade(self, trade: Trade) -> CandleUpdate:
        """Fold one trade into every timeframe's current bar.

        Exact port of ``CandleEngine.process_trade`` (``candles.py:123-172``):

        * Classify the trade's trading day via ``trading_day_for``; if ``None``
          (closed window) return an empty-completed snapshot, skipping the trade.
        * For each timeframe, if the open bar belongs to an earlier trading day,
          freeze it ``END_OF_DAY`` (incomplete) and start fresh.
        * Opening a bar: ``timeframe == 1`` emits it immediately as ``COMPLETE``;
          otherwise it becomes the current bar.
        * Otherwise accumulate (close ts/price, high/low via ``>``/``<``, volume,
          trade_count) and freeze ``COMPLETE`` once ``trade_count == timeframe``.
        """
        # candles.py:124-126 -- trades with no trading day (closed window) are skipped.
        trading_day = trading_day_for(trade.event_ts_utc, self._scheme)
        if trading_day is None:
            return self.snapshot_update(())

        completed: list[Bar] = []
        current = self._current
        price_ticks = trade.price_ticks
        event_ts_utc = trade.event_ts_utc
        size = trade.size
        for timeframe in self.timeframes:
            candle = current.get(timeframe)
            # candles.py:135-137 -- trading-day rollover: freeze the open bar as
            # END_OF_DAY (incomplete) and reopen on the new day.
            if candle is not None and candle.trading_day != trading_day:
                completed.append(candle.freeze(complete=False, reason=CloseReason.END_OF_DAY))
                candle = None
            if candle is None:
                # candles.py:138-159 -- open a fresh bar seeded by this trade.
                bar_index = self._allocate_bar_index(timeframe, trading_day)
                new_candle = _MutableCandle(
                    timeframe_ticks=timeframe,
                    trading_day=trading_day,
                    bar_index=bar_index,
                    bar_id=make_bar_id(timeframe, trading_day, bar_index),
                    open_ts_utc=event_ts_utc,
                    close_ts_utc=event_ts_utc,
                    open_ticks=price_ticks,
                    high_ticks=price_ticks,
                    low_ticks=price_ticks,
                    close_ticks=price_ticks,
                    volume=size,
                    trade_count=1,
                )
                # candles.py:154-159 -- 1-tick bars close on their seeding trade.
                if timeframe == 1:
                    completed.append(
                        new_candle.freeze(complete=True, reason=CloseReason.COMPLETE)
                    )
                else:
                    current[timeframe] = new_candle
                continue
            # candles.py:161-168 -- accumulate into the open bar. High/low use
            # strict comparisons so equal prices leave them untouched.
            candle.close_ts_utc = event_ts_utc
            candle.close_ticks = price_ticks
            if price_ticks > candle.high_ticks:
                candle.high_ticks = price_ticks
            if price_ticks < candle.low_ticks:
                candle.low_ticks = price_ticks
            candle.volume += size
            candle.trade_count += 1
            # candles.py:169-171 -- exact fill closes the bar COMPLETE and clears it.
            if candle.trade_count == timeframe:
                completed.append(candle.freeze(complete=True, reason=CloseReason.COMPLETE))
                del current[timeframe]
        return self.snapshot_update(tuple(completed))

    def snapshot_update(self, completed: tuple[Bar, ...]) -> CandleUpdate:
        """Pair ``completed`` with a snapshot of every in-progress bar.

        Mirrors ``CandleEngine.snapshot_update`` (``candles.py:174-176``): the
        ``current`` bars are frozen incomplete with ``close_reason=None``.
        """
        current = tuple(c.freeze(complete=False, reason=None) for c in self._current.values())
        return CandleUpdate(completed=completed, current=current)

    def finalize_trading_day(self) -> tuple[Bar, ...]:
        """Explicitly close every incomplete bar at its last trade as END_OF_DAY.

        Exact port of ``CandleEngine.finalize_trading_day`` (``candles.py:178-186``):
        each open bar is frozen incomplete with ``END_OF_DAY`` and the current map
        is cleared. Returns the freshly-closed bars in current-dict (ascending
        timeframe) order.
        """
        completed = tuple(
            c.freeze(complete=False, reason=CloseReason.END_OF_DAY)
            for c in self._current.values()
        )
        self._current.clear()
        return completed

    def _allocate_bar_index(self, timeframe: int, trading_day: date) -> int:
        """Hand out a monotonic per-``(timeframe, trading_day)`` index from 0.

        Exact port of ``CandleEngine._allocate_bar_index`` (``candles.py:188-192``).
        """
        key = (timeframe, trading_day)
        bar_index = self._next_index.get(key, 0)
        self._next_index[key] = bar_index + 1
        return bar_index
