"""Parity lock: the batch and streaming candle builders must agree exactly.

The streaming :class:`~strategy_core.candles.streaming.CandleEngine` (event-at-a-time,
the live/replay path) and the vectorized
:func:`~strategy_core.candles.batch.build_tick_bars_from_frame` (research / warm-up
path) are two implementations of the same N-trade tick bar. Any drift between them
means a strategy trained on the batch bars would execute on subtly different live
bars -- the exact failure this package exists to prevent. This test feeds the SAME
deterministic synthetic trade stream through both and asserts the resulting
:class:`~strategy_core.types.Bar` lists are field-for-field identical.

All timestamps are fixed, timezone-aware UTC datetimes (never ``now()``/random) so the
test is fully deterministic. The stream deliberately spans the 18:00 ET trading-day
boundary so the day-rollover ``END_OF_DAY`` behavior is exercised, and a second case
runs under ``TRADE_LAB_CT_SESSION_SCHEME`` so the closed-window drop path is shown to
be parity-safe too.
"""

from __future__ import annotations

from dataclasses import astuple
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from strategy_core.candles.batch import build_tick_bars_from_frame
from strategy_core.candles.streaming import CandleEngine
from strategy_core.constants import (
    DEFAULT_TICK_SIZE,
    RESEARCH_SESSION_SCHEME,
    TRADE_LAB_CT_SESSION_SCHEME,
)
from strategy_core.types import Bar, SessionScheme, Trade

UTC = timezone.utc

# Timeframes chosen small so a few hundred trades fill several complete bars per day
# plus a trailing partial (END_OF_DAY) on each day, for both timeframes.
TIMEFRAMES = (3, 5)


def _synthetic_trades() -> list[Trade]:
    """A deterministic trade stream spanning the 18:00 ET trading-day boundary.

    Starts at 13:30:00 UTC (09:30 ET, RTH open) and emits one trade every 150
    seconds for 300 trades, ending at 13:30 + 299*150s = 01:57:30 UTC the next
    calendar day. The span therefore crosses:

    * 22:00:00 UTC (18:00 ET) -- rolls ET trading day 2025-06-02 -> 2025-06-03,
      exercising the streaming engine's mid-stream END_OF_DAY freeze and the
      batch builder's daily trailing-partial END_OF_DAY bar.
    * 21:00-23:00 UTC (16:00-18:00 CT) -- the ``TRADE_LAB_CT_SESSION_SCHEME``
      closed window, so the CT case exercises both drop mechanisms.
    * 23:00:00 UTC (18:00 CT) -- the CT trading-day rollover.

    Prices walk a fixed integer-tick zig-zag (no float ambiguity) so high/low/open/
    close aggregation is non-trivial and order-sensitive.
    """
    base = datetime(2025, 6, 2, 13, 30, 0, tzinfo=UTC)
    trades: list[Trade] = []
    price_ticks = 80_000  # e.g. 20000.00 points at 0.25 tick size
    for i in range(300):
        # Deterministic zig-zag: rises 7, dips 3, rises 2, repeats. Gives real
        # intrabar highs/lows that differ from open and close.
        step = (7, -3, 2, -5, 4)[i % 5]
        price_ticks += step
        trades.append(
            Trade(
                event_ts_utc=base + timedelta(seconds=150 * i),
                price_ticks=price_ticks,
                size=1 + (i % 4),  # 1..4, so volume != trade_count
            )
        )
    return trades


def _trades_to_frame(trades: list[Trade], *, tick_size: float) -> pd.DataFrame:
    """Render the trade stream as the batch builder's input DataFrame.

    ``price`` is the points value (ticks * tick_size); the builder rounds it back
    to integer ticks, mirroring how the streaming engine already carries ticks.
    """
    return pd.DataFrame(
        {
            "ts_event": [t.event_ts_utc for t in trades],
            "price": [t.price_ticks * tick_size for t in trades],
            "size": [t.size for t in trades],
        }
    )


def _streaming_bars(
    trades: list[Trade], timeframes: tuple[int, ...], scheme: SessionScheme
) -> list[Bar]:
    """All bars from the streaming engine: completed bars in stream order plus the
    final ``finalize_trading_day`` END_OF_DAY partials."""
    engine = CandleEngine(timeframes, scheme=scheme)
    bars: list[Bar] = []
    for trade in trades:
        update = engine.process_trade(trade)
        bars.extend(update.completed)
    bars.extend(engine.finalize_trading_day())
    return bars


def _sort_key(bar: Bar) -> tuple[int, str, int]:
    return (bar.timeframe_ticks, bar.trading_day.isoformat(), bar.bar_index)


def _assert_bars_equal(streaming: list[Bar], batch: list[Bar]) -> None:
    """Both lists sorted by (timeframe, trading_day, bar_index), then every field
    of every bar compared exactly."""
    assert len(streaming) == len(batch), (
        f"bar count differs: streaming={len(streaming)} batch={len(batch)}"
    )
    s_sorted = sorted(streaming, key=_sort_key)
    b_sorted = sorted(batch, key=_sort_key)
    for s, b in zip(s_sorted, b_sorted, strict=True):
        # astuple compares EVERY field (ohlc ticks, volume, trade_count,
        # is_complete, is_partial, close_reason, bar_id, timestamps, ...).
        assert astuple(s) == astuple(b), f"bar mismatch:\n streaming={s}\n    batch={b}"


def test_batch_streaming_parity_research_scheme() -> None:
    """Under RESEARCH_SESSION_SCHEME (ET, no closed window) the two builders agree
    bar-for-bar, including the day-rollover END_OF_DAY bars at the 18:00 ET boundary."""
    trades = _synthetic_trades()
    frame = _trades_to_frame(trades, tick_size=DEFAULT_TICK_SIZE)

    streaming = _streaming_bars(trades, TIMEFRAMES, RESEARCH_SESSION_SCHEME)
    batch = build_tick_bars_from_frame(
        frame, TIMEFRAMES, scheme=RESEARCH_SESSION_SCHEME, tick_size=DEFAULT_TICK_SIZE
    )

    _assert_bars_equal(streaming, batch)

    # Sanity: the stream really does straddle the 18:00 ET boundary -> two trading
    # days -> at least one END_OF_DAY bar per timeframe (the first day's partial).
    trading_days = {b.trading_day for b in streaming}
    assert len(trading_days) == 2, f"expected the stream to span 2 ET trading days, got {trading_days}"
    end_of_day = [b for b in streaming if b.close_reason and b.close_reason.value == "end_of_day"]
    assert end_of_day, "expected at least one END_OF_DAY bar from the day rollover"
    assert all(b.is_partial and not b.is_complete for b in end_of_day)


def test_batch_streaming_parity_ct_scheme_closed_window() -> None:
    """Under TRADE_LAB_CT_SESSION_SCHEME the closed-window drop (16:00-18:00 CT) and
    the 18:00 CT rollover are both parity-safe: batch == streaming.

    The batch builder drops closed-window rows explicitly; the streaming engine drops
    them because ``trading_day_for`` returns ``None`` there. Equal output proves the
    two drop mechanisms are equivalent.
    """
    trades = _synthetic_trades()
    frame = _trades_to_frame(trades, tick_size=DEFAULT_TICK_SIZE)

    streaming = _streaming_bars(trades, TIMEFRAMES, TRADE_LAB_CT_SESSION_SCHEME)
    batch = build_tick_bars_from_frame(
        frame, TIMEFRAMES, scheme=TRADE_LAB_CT_SESSION_SCHEME, tick_size=DEFAULT_TICK_SIZE
    )

    _assert_bars_equal(streaming, batch)

    # Sanity: trades land in the 16:00-18:00 CT closed window (21:00-23:00 UTC), so
    # the dropped trades mean fewer total trades aggregated than the raw stream.
    total_trade_count = sum(b.trade_count for b in streaming if b.timeframe_ticks == TIMEFRAMES[0])
    assert total_trade_count < len(trades), (
        "expected some trades dropped in the CT closed window; "
        f"aggregated {total_trade_count} of {len(trades)}"
    )


def test_empty_frame_returns_no_bars() -> None:
    """Empty input yields ``[]`` (seed.py:56-57 empty-case), matching a stream with
    no trades through the streaming engine."""
    empty = pd.DataFrame({"ts_event": [], "price": [], "size": []})
    assert build_tick_bars_from_frame(empty, TIMEFRAMES) == []
