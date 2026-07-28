"""Unit tests for the Phase-F time-bar RULES themselves (not parity).

Covers, per the architect's spec: bucket anchoring at the trading-day boundary; a
trade landing exactly on a bucket edge; the DST 23-hour and 25-hour trading days;
``bar_id`` format for both kinds; ``kind`` defaulting to TICK on every existing
construction path; and dense ``bar_index`` across skipped buckets. All timestamps
are fixed aware datetimes — no files, no ``now()``, no RNG.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from strategy_core.candles._buckets import trading_day_start_utc
from strategy_core.candles._ids import make_bar_id
from strategy_core.candles.batch import build_tick_bars_from_frame
from strategy_core.candles.streaming import CandleEngine
from strategy_core.candles.time_streaming import TimeBarEngine
from strategy_core.constants import DEFAULT_TICK_SIZE, RESEARCH_SESSION_SCHEME
from strategy_core.types import Bar, BarKind, Trade

UTC = timezone.utc


def _trade(ts: datetime, price_ticks: int = 80_000, size: int = 1) -> Trade:
    return Trade(event_ts_utc=ts, price_ticks=price_ticks, size=size)


def _all_bars(engine: TimeBarEngine, trades: list[Trade]) -> list[Bar]:
    bars: list[Bar] = []
    for trade in trades:
        bars.extend(engine.process_trade(trade).completed)
    bars.extend(engine.finalize_trading_day())
    return bars


# ── boundary anchoring ────────────────────────────────────────────────────────
def test_day_anchor_is_prior_calendar_day_boundary_in_scheme_tz() -> None:
    """Trading day D opens at 18:00 ET on calendar day D-1, expressed in UTC (EDT
    in June -> 22:00 UTC; EST in January -> 23:00 UTC)."""
    assert trading_day_start_utc(date(2025, 6, 3), RESEARCH_SESSION_SCHEME) == datetime(
        2025, 6, 2, 22, 0, tzinfo=UTC
    )
    assert trading_day_start_utc(date(2025, 1, 7), RESEARCH_SESSION_SCHEME) == datetime(
        2025, 1, 6, 23, 0, tzinfo=UTC
    )


def test_buckets_anchor_at_day_open() -> None:
    """The first second of the trading day is bucket 0 for every timeframe: a trade
    AT the 18:00 ET open lands in 60s bar 0 and 4H bar 0."""
    day_open = datetime(2025, 6, 2, 22, 0, 0, tzinfo=UTC)  # 18:00 EDT
    engine = TimeBarEngine((60, 14400))
    bars = _all_bars(engine, [_trade(day_open), _trade(day_open + timedelta(seconds=59))])
    assert [b.bar_id for b in bars] == ["60s:2025-06-03:0", "14400s:2025-06-03:0"]
    assert all(b.trade_count == 2 for b in bars)  # both trades in bucket 0


# ── exact bucket edge ─────────────────────────────────────────────────────────
def test_trade_exactly_on_bucket_edge_opens_the_later_bar() -> None:
    """Buckets are half-open [edge, next_edge): a trade at exactly +60.000000s
    belongs to bucket 1, closing bucket 0's bar COMPLETE — identically in both
    builders (integer-us streaming vs integer-ns batch arithmetic)."""
    day_open = datetime(2025, 6, 2, 22, 0, 0, tzinfo=UTC)
    trades = [
        _trade(day_open + timedelta(seconds=1), price_ticks=80_000),
        _trade(day_open + timedelta(seconds=60), price_ticks=80_004),  # exact edge
    ]
    streaming = _all_bars(TimeBarEngine((60,)), trades)
    assert [b.bar_id for b in streaming] == ["60s:2025-06-03:0", "60s:2025-06-03:1"]
    assert streaming[0].trade_count == 1 and streaming[0].is_complete
    assert streaming[1].trade_count == 1 and streaming[1].is_partial

    from strategy_core.candles.time_batch import build_time_bars_from_frame

    frame = pd.DataFrame(
        {
            "ts_event": [t.event_ts_utc for t in trades],
            "price": [t.price_ticks * DEFAULT_TICK_SIZE for t in trades],
            "size": [t.size for t in trades],
        }
    )
    batch = build_time_bars_from_frame(frame, (60,))
    assert [b.bar_id for b in batch] == ["60s:2025-06-03:0", "60s:2025-06-03:1"]


# ── DST day lengths ───────────────────────────────────────────────────────────
def test_dst_spring_forward_day_has_23_hours_of_buckets() -> None:
    """Trading day 2025-03-09 (spring forward) spans 23 real hours: a trade one
    second before the Sun 18:00 EDT close lands in 60s wall-bucket 1379 (23h*60-1),
    NOT 1439 — and the next second rolls the trading day."""
    day_open = datetime(2025, 3, 8, 23, 0, 0, tzinfo=UTC)  # Sat 18:00 EST
    engine = TimeBarEngine((60,))
    last_in_day = day_open + timedelta(hours=23, seconds=-1)
    bars = _all_bars(engine, [_trade(day_open), _trade(last_in_day)])
    assert [b.trading_day.isoformat() for b in bars] == ["2025-03-09", "2025-03-09"]
    # Dense indexes 0 and 1, but the WALL buckets are 0 and 1379: the second bar
    # opened 22:59:59 after the anchor.
    elapsed = bars[1].open_ts_utc - trading_day_start_utc(date(2025, 3, 9), RESEARCH_SESSION_SCHEME)
    assert int(elapsed.total_seconds()) // 60 == 23 * 60 - 1
    # One second later is the next trading day (18:00 EDT boundary).
    rolled = engine.process_trade(_trade(day_open + timedelta(hours=23)))
    assert not rolled.completed  # prior bars were already finalized above
    assert rolled.current[0].trading_day.isoformat() == "2025-03-10"


def test_dst_fall_back_day_has_25_hours_of_buckets() -> None:
    """Trading day 2025-11-02 (fall back) spans 25 real hours: one second before the
    Sun 18:00 EST close is 60s wall-bucket 1499 (25h*60-1), and the repeated
    01:00-02:00 ET wall hour maps to two DISTINCT bucket ranges."""
    day_open = datetime(2025, 11, 1, 22, 0, 0, tzinfo=UTC)  # Sat 18:00 EDT
    anchor = trading_day_start_utc(date(2025, 11, 2), RESEARCH_SESSION_SCHEME)
    assert anchor == day_open
    last_in_day = day_open + timedelta(hours=25, seconds=-1)
    engine = TimeBarEngine((60,))
    bars = _all_bars(engine, [_trade(day_open), _trade(last_in_day)])
    assert [b.trading_day.isoformat() for b in bars] == ["2025-11-02", "2025-11-02"]
    assert int((bars[1].open_ts_utc - anchor).total_seconds()) // 60 == 25 * 60 - 1
    # The repeated wall hour: 01:30 EDT (05:30 UTC) and 01:30 EST (06:30 UTC) are
    # the same local label but 60 buckets apart — elapsed time disambiguates them.
    first_0130 = datetime(2025, 11, 2, 5, 30, 0, tzinfo=UTC)
    second_0130 = datetime(2025, 11, 2, 6, 30, 0, tzinfo=UTC)
    b1 = int((first_0130 - anchor).total_seconds()) // 60
    b2 = int((second_0130 - anchor).total_seconds()) // 60
    assert b2 - b1 == 60


# ── bar_id format, both kinds ─────────────────────────────────────────────────
def test_bar_id_format_for_both_kinds() -> None:
    day = date(2026, 1, 5)
    assert make_bar_id(147, day, 3) == "147t:2026-01-05:3"
    assert make_bar_id(147, day, 3, BarKind.TICK) == "147t:2026-01-05:3"
    assert make_bar_id(3600, day, 0, BarKind.TIME) == "3600s:2026-01-05:0"


# ── kind defaults to TICK on every existing construction path ─────────────────
def test_kind_defaults_to_tick_everywhere() -> None:
    """Direct construction (positional and keyword), the streaming tick engine, and
    the batch tick builder all yield ``kind=TICK`` untouched."""
    ts = datetime(2025, 6, 2, 14, 0, 0, tzinfo=UTC)
    positional = Bar(147, date(2025, 6, 2), 0, "147t:2025-06-02:0", ts, ts, 1, 1, 1, 1, 1, 1, True, False)
    assert positional.kind is BarKind.TICK
    keyword = Bar(
        timeframe_ticks=147, trading_day=date(2025, 6, 2), bar_index=0,
        bar_id="147t:2025-06-02:0", open_ts_utc=ts, close_ts_utc=ts,
        open_ticks=1, high_ticks=1, low_ticks=1, close_ticks=1,
        volume=1, trade_count=1, is_complete=True, is_partial=False,
    )
    assert keyword.kind is BarKind.TICK

    trades = [_trade(ts + timedelta(seconds=i), price_ticks=80_000 + i) for i in range(5)]
    engine = CandleEngine((2,))
    tick_bars = []
    for t in trades:
        tick_bars.extend(engine.process_trade(t).completed)
    tick_bars.extend(engine.finalize_trading_day())
    assert tick_bars and all(b.kind is BarKind.TICK for b in tick_bars)
    assert all(b.bar_id.startswith("2t:") for b in tick_bars)

    frame = pd.DataFrame(
        {
            "ts_event": [t.event_ts_utc for t in trades],
            "price": [t.price_ticks * DEFAULT_TICK_SIZE for t in trades],
            "size": [t.size for t in trades],
        }
    )
    batch_bars = build_tick_bars_from_frame(frame, (2,))
    assert batch_bars and all(b.kind is BarKind.TICK for b in batch_bars)


# ── dense bar_index across skipped buckets ────────────────────────────────────
def test_bar_index_dense_across_skipped_buckets() -> None:
    """Trades in minutes 0, 7 and 30 of the day: three 60s bars with indexes
    0, 1, 2 (not 0, 7, 30) — the index is over EMITTED bars, not wall buckets."""
    day_open = datetime(2025, 6, 2, 22, 0, 0, tzinfo=UTC)
    trades = [
        _trade(day_open + timedelta(minutes=0, seconds=5)),
        _trade(day_open + timedelta(minutes=7, seconds=5)),
        _trade(day_open + timedelta(minutes=30, seconds=5)),
    ]
    bars = _all_bars(TimeBarEngine((60,)), trades)
    assert [b.bar_index for b in bars] == [0, 1, 2]
    assert [b.bar_id for b in bars] == [
        "60s:2025-06-03:0",
        "60s:2025-06-03:1",
        "60s:2025-06-03:2",
    ]
    # First two closed COMPLETE (a later bucket produced a bar), last is EOD.
    assert [b.is_complete for b in bars] == [True, True, False]


# ── ns-extraction unit guard (version-independent) ────────────────────────────
@pytest.mark.parametrize("unit", ["us", "ms", "s"])
def test_ns_extraction_does_not_inherit_dtype_unit(unit: str) -> None:
    """The batch path's datetime->integer helpers must return NANOSECONDS no matter
    what resolution the datetime dtype carries.

    This is the version-independent form of the pandas-3 cold-runner red (SC ci run
    30331205481 on tip 8ec6906): pandas 3 preserves a source datetime unit through
    DataFrame construction, and ``.asi8`` / ``.value`` return integers in the
    dtype's OWN unit — so a nanosecond assumption collapses every bucket index. A
    prior reproduction through the PUBLIC input passed on pandas 2 because the
    module's internal ``to_numpy()`` -> DataFrame round-trip renormalizes to ns
    there; this guard therefore targets the extraction helpers DIRECTLY with a
    ``DatetimeIndex.as_unit(...)``-forced non-ns index, which survives to the
    helper on either pandas major.

    Whole-second timestamps so every parameterized unit represents them exactly;
    a 60-second separation must yield exactly 60_000_000_000.
    """
    from strategy_core.candles.time_batch import _index_to_ns, _timestamp_to_ns

    base = datetime(2025, 6, 2, 22, 0, 0, tzinfo=UTC)
    later = base + timedelta(seconds=60)

    idx = pd.DatetimeIndex([base, later]).as_unit(unit)
    assert str(idx.dtype) == f"datetime64[{unit}, UTC]"  # the forced non-ns dtype
    out = _index_to_ns(idx)
    assert str(out.dtype) == "int64"
    assert int(out[1]) - int(out[0]) == 60_000_000_000, (
        f"_index_to_ns returned unit-{unit} integers, not nanoseconds: "
        f"delta={int(out[1]) - int(out[0])}"
    )

    t0 = pd.Timestamp(base).as_unit(unit)
    t1 = pd.Timestamp(later).as_unit(unit)
    assert t0.unit == unit
    delta = _timestamp_to_ns(t1) - _timestamp_to_ns(t0)
    assert delta == 60_000_000_000, (
        f"_timestamp_to_ns returned unit-{unit} integers, not nanoseconds: delta={delta}"
    )


# ── construction guards ───────────────────────────────────────────────────────
def test_non_multiple_of_60_rejected() -> None:
    with pytest.raises(ValueError):
        TimeBarEngine((90,))
    with pytest.raises(ValueError):
        TimeBarEngine((0,))
    from strategy_core.candles.time_batch import build_time_bars_from_frame

    with pytest.raises(ValueError):
        build_time_bars_from_frame(pd.DataFrame({"ts_event": [], "price": [], "size": []}), (30,))
