"""Parity lock: the batch and streaming TIME-bar builders must agree exactly.

The streaming :class:`~strategy_core.candles.time_streaming.TimeBarEngine`
(event-at-a-time, the live/replay path) and the vectorized
:func:`~strategy_core.candles.time_batch.build_time_bars_from_frame` (research /
warm-up path) are two implementations of the same day-anchored time bar. This test
feeds the SAME deterministic synthetic trade streams through both and asserts the
resulting :class:`~strategy_core.types.Bar` lists are field-for-field identical —
the exact ``tests/test_candle_parity.py`` harness applied to the time path.

All timestamps are fixed, timezone-aware UTC datetimes (never ``now()``/random).
Coverage, per the architect's spec: all eight ratified timeframes; a stream crossing
the 18:00 ET trading-day boundary; stretches containing empty buckets (sparse
spacing AND a multi-hour dead-time jump); a truncated final bucket; and both DST
transition days in the scheme timezone (the 23-hour spring-forward and 25-hour
fall-back trading days).
"""

from __future__ import annotations

from dataclasses import astuple
from datetime import datetime, timedelta, timezone

import pandas as pd

from strategy_core.candles.time_batch import build_time_bars_from_frame
from strategy_core.candles.time_streaming import DEFAULT_TIME_TIMEFRAMES, TimeBarEngine
from strategy_core.constants import DEFAULT_TICK_SIZE, RESEARCH_SESSION_SCHEME
from strategy_core.types import Bar, BarKind, SessionScheme, Trade

UTC = timezone.utc

TIMEFRAMES = DEFAULT_TIME_TIMEFRAMES  # all eight: 1m 3m 5m 10m 15m 30m 1H 4H


def _zigzag_trades(start: datetime, count: int, spacing: timedelta) -> list[Trade]:
    """Deterministic zig-zag price walk (rises 7, dips 3, rises 2, ...) with sizes
    cycling 1..4, one trade per ``spacing`` — the tick parity test's generator shape."""
    trades: list[Trade] = []
    price_ticks = 80_000
    for i in range(count):
        price_ticks += (7, -3, 2, -5, 4)[i % 5]
        trades.append(
            Trade(event_ts_utc=start + spacing * i, price_ticks=price_ticks, size=1 + (i % 4))
        )
    return trades


def _main_stream() -> list[Trade]:
    """The headline stream: three stitched segments.

    * A — 300 trades every 150s from 2025-06-02 13:30 UTC. Sparser than a minute, so
      empty 60s buckets occur throughout; crosses 22:00 UTC (18:00 ET), exercising the
      mid-stream trading-day roll.
    * B — a 200-trade burst every 7s (+123456 us so sub-second offsets are exercised)
      starting 41s after A ends, i.e. dense multi-trade minutes.
    * C — after a 5-hour dead-time jump (empty buckets at EVERY timeframe, including
      whole empty 1H buckets), 50 trades every 90s. Ends mid-bucket at every
      timeframe — the truncated final bucket.
    """
    a_start = datetime(2025, 6, 2, 13, 30, 0, tzinfo=UTC)
    trades = _zigzag_trades(a_start, 300, timedelta(seconds=150))
    b_start = trades[-1].event_ts_utc + timedelta(seconds=41, microseconds=123_456)
    trades += _zigzag_trades(b_start, 200, timedelta(seconds=7))
    c_start = trades[-1].event_ts_utc + timedelta(hours=5)
    trades += _zigzag_trades(c_start, 50, timedelta(seconds=90))
    return trades


def _trades_to_frame(trades: list[Trade], *, tick_size: float) -> pd.DataFrame:
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
    engine = TimeBarEngine(timeframes, scheme=scheme)
    bars: list[Bar] = []
    for trade in trades:
        bars.extend(engine.process_trade(trade).completed)
    bars.extend(engine.finalize_trading_day())
    return bars


def _sort_key(bar: Bar) -> tuple[int, str, int]:
    return (bar.timeframe_ticks, bar.trading_day.isoformat(), bar.bar_index)


def _assert_bars_equal(streaming: list[Bar], batch: list[Bar]) -> None:
    assert len(streaming) == len(batch), (
        f"bar count differs: streaming={len(streaming)} batch={len(batch)}"
    )
    s_sorted = sorted(streaming, key=_sort_key)
    b_sorted = sorted(batch, key=_sort_key)
    for s, b in zip(s_sorted, b_sorted, strict=True):
        assert astuple(s) == astuple(b), f"bar mismatch:\n streaming={s}\n    batch={b}"


def _run_parity(trades: list[Trade]) -> list[Bar]:
    """Drive both builders over ``trades`` across all eight timeframes, assert
    field-for-field equality, and return the (streaming) bars for extra checks."""
    frame = _trades_to_frame(trades, tick_size=DEFAULT_TICK_SIZE)
    streaming = _streaming_bars(trades, TIMEFRAMES, RESEARCH_SESSION_SCHEME)
    batch = build_time_bars_from_frame(
        frame, TIMEFRAMES, scheme=RESEARCH_SESSION_SCHEME, tick_size=DEFAULT_TICK_SIZE
    )
    _assert_bars_equal(streaming, batch)
    return streaming


def test_parity_main_stream_all_timeframes() -> None:
    """Sparse + burst + dead-time stream over all eight timeframes, crossing the
    18:00 ET boundary, with empty buckets and a truncated final bucket."""
    bars = _run_parity(_main_stream())

    # The stream really crosses the boundary -> two ET trading days.
    trading_days = {b.trading_day for b in bars}
    assert len(trading_days) == 2, f"expected 2 ET trading days, got {trading_days}"

    # Every timeframe emitted, all TIME-kind, seconds-suffixed ids.
    per_tf = {tf: [b for b in bars if b.timeframe_ticks == tf] for tf in TIMEFRAMES}
    assert all(per_tf.values()), "every timeframe must emit at least one bar"
    assert all(b.kind is BarKind.TIME for b in bars)
    assert all(b.bar_id.startswith(f"{b.timeframe_ticks}s:") for b in bars)

    # No empty bars, ever.
    assert all(b.trade_count > 0 for b in bars)

    # Empty 60s buckets exist (150s spacing + the 5h jump) yet bar_index stays
    # dense: per (timeframe, day) the indexes are exactly 0..n-1.
    for tf in TIMEFRAMES:
        for day in trading_days:
            idx = sorted(b.bar_index for b in per_tf[tf] if b.trading_day == day)
            assert idx == list(range(len(idx))), f"bar_index not dense for {tf}s {day}"

    # The 5h dead-time jump left whole 1H wall-buckets empty on the second day:
    # fewer 3600s bars than spanned wall hours proves buckets were skipped.
    h1 = per_tf[3600]
    spanned_hours = (
        max(b.close_ts_utc for b in h1) - min(b.open_ts_utc for b in h1)
    ).total_seconds() / 3600
    assert len(h1) < spanned_hours, "expected skipped (empty) 1H buckets"

    # Truncated final bucket: per timeframe the last bar of the last day is the
    # END_OF_DAY partial; every non-final bar is COMPLETE.
    last_day = max(trading_days)
    for tf in TIMEFRAMES:
        day_bars = sorted(
            (b for b in per_tf[tf] if b.trading_day == last_day), key=_sort_key
        )
        assert day_bars[-1].is_partial and day_bars[-1].close_reason.value == "end_of_day"
        assert all(b.is_complete and b.close_reason.value == "complete" for b in day_bars[:-1])

    # Aggregate-upward conservation: per day, volume/trade_count sums agree across
    # every timeframe (skipped empty minutes contribute nothing at any level).
    for day in trading_days:
        sums = {
            tf: (
                sum(b.volume for b in per_tf[tf] if b.trading_day == day),
                sum(b.trade_count for b in per_tf[tf] if b.trading_day == day),
            )
            for tf in TIMEFRAMES
        }
        assert len(set(sums.values())) == 1, f"volume/trade_count not conserved: {sums}"


def test_parity_dst_spring_forward_23h_day() -> None:
    """The 2025-03-09 spring-forward trading day (Sat 18:00 EST -> Sun 18:00 EDT,
    23 real hours). Trades every 20 minutes span the whole day including the 02:00 ET
    jump; parity must hold and the day must fit inside 23 hours of buckets."""
    start = datetime(2025, 3, 8, 23, 0, 0, tzinfo=UTC)  # Sat 18:00 EST == day open
    trades = _zigzag_trades(start, 69, timedelta(minutes=20))  # 68*20min = 22h40m span
    bars = _run_parity(trades)
    day_bars = [b for b in bars if b.timeframe_ticks == 60]
    assert {b.trading_day.isoformat() for b in bars} == {"2025-03-09"}
    assert len(day_bars) == 69  # 20-min spacing -> every trade its own 60s bar


def test_parity_dst_fall_back_25h_day() -> None:
    """The 2025-11-02 fall-back trading day (Sat 18:00 EDT -> Sun 18:00 EST, 25 real
    hours). The repeated 01:00-02:00 ET wall-clock hour buckets correctly because
    bucketing counts elapsed time from the absolute day-open instant."""
    start = datetime(2025, 11, 1, 22, 0, 0, tzinfo=UTC)  # Sat 18:00 EDT == day open
    trades = _zigzag_trades(start, 75, timedelta(minutes=20))  # 74*20min = 24h40m span
    bars = _run_parity(trades)
    assert {b.trading_day.isoformat() for b in bars} == {"2025-11-02"}
    h4 = [b for b in bars if b.timeframe_ticks == 14400]
    assert len(h4) == 7  # 25 elapsed hours -> 4H buckets 0..6 all populated


def test_empty_frame_returns_no_bars() -> None:
    empty = pd.DataFrame({"ts_event": [], "price": [], "size": []})
    assert build_time_bars_from_frame(empty, TIMEFRAMES) == []
