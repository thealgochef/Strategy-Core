"""Terminal-path unit coverage for the D1a StreamingHonestResolver (post-review).

Gate A (validation/test_d1_streaming_vs_batch_parity.py) proved streaming == batch
on the 9 real store days, but that window only exercised resolutions + flatten
drops. These synthetic tests pin the unexercised arms: registration cutoff (incl.
the non-strict boundary), the exact flatten boundary, no_fill, no_forward via
flush, no_resolution via flush AND via an at/after-cutoff bar close (whose range
must NOT contribute), and the StrategyRuntime trade-ring lookback/eviction edges.

The resolution-path test additionally pins ``StreamResolution.resolved_ts_utc``
(the resolving bar's close instant) — the one envelope field gate A can NEVER
check against batch, because the kernel ``OutcomeResult`` deliberately carries no
timestamp (see the ``StreamResolution`` docstring).
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from strategy_core.decisions.streaming import (
    StreamDrop,
    StreamingHonestResolver,
    StreamResolution,
)
from strategy_core.runtime.state import StrategyRuntime
from strategy_core.types import Bar, Trade

_ET = ZoneInfo("US/Eastern")
_DAY = date(2025, 7, 15)  # a Tuesday
_TICK = 0.25


def _et(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2025, 7, 15, hour, minute, second, tzinfo=_ET).astimezone(UTC)


def _resolver(*, trade_price_at=lambda ts: 23000.0, flatten_time=None) -> StreamingHonestResolver:
    kwargs = {}
    if flatten_time is not None:
        kwargs["flatten_time"] = flatten_time
    return StreamingHonestResolver(
        forward_timeframe_ticks=147,
        tick_size=_TICK,
        tp_points=15.0,
        sl_points=30.0,
        trap_mfe_min=5.0,
        trade_price_at=trade_price_at,
        available_timeframes=(147,),
        **kwargs,
    )


def _bar(close_ts: datetime, high_pts: float, low_pts: float) -> Bar:
    high_ticks = round(high_pts / _TICK)
    low_ticks = round(low_pts / _TICK)
    return Bar(
        timeframe_ticks=147,
        trading_day=_DAY,
        bar_index=0,
        bar_id="147t:test:0",
        open_ts_utc=close_ts - timedelta(seconds=30),
        close_ts_utc=close_ts,
        open_ticks=low_ticks,
        high_ticks=high_ticks,
        low_ticks=low_ticks,
        close_ticks=high_ticks,
        volume=147,
        trade_count=147,
        is_complete=True,
        is_partial=False,
    )


def test_registration_cutoff_drop_is_non_strict_at_1700_et() -> None:
    # flatten pushed past the cutoff so the cutoff arm is reachable (mirrors
    # tests/test_honest_entry.py::test_cutoff_drop).
    resolver = _resolver(flatten_time=time(23, 0))
    drop = resolver.register(
        "k", touch_bar_ts_utc=_et(16, 55), trading_day=_DAY, direction="long"
    )
    # decision = 16:55 + 5m = EXACTLY 17:00 ET -> dropped non-strict (>= cutoff).
    assert isinstance(drop, StreamDrop) and drop.reason == "cutoff"
    assert drop.decision_ts_utc == _et(17, 0)
    assert resolver.open_count == 0


def test_registration_flatten_drop_at_exact_1640_et_boundary() -> None:
    resolver = _resolver()
    drop = resolver.register(
        "k", touch_bar_ts_utc=_et(16, 35), trading_day=_DAY, direction="long"
    )
    # decision = EXACTLY 16:40:00 ET -> flatten is non-strict (>=).
    assert isinstance(drop, StreamDrop) and drop.reason == "flatten"
    assert drop.decision_ts_utc == _et(16, 40)


def test_registration_evening_touch_of_next_trading_day_not_flattened() -> None:
    """W1 P2a: flatten is anchored to the setup's trading day. A 20:00 ET touch the
    prior evening (trading day _DAY, which rolls at 18:00 ET) registers live and
    resolves against _DAY's cutoff."""
    resolver = _resolver()
    prev_evening = datetime(2025, 7, 14, 20, 0, tzinfo=_ET).astimezone(UTC)
    assert (
        resolver.register(
            "k", touch_bar_ts_utc=prev_evening, trading_day=_DAY, direction="long"
        )
        is None
    )
    assert resolver.open_count == 1
    # A next-morning bar (inside _DAY's RTH, before the 17:00 ET cutoff) advances the
    # setup: +16 pts off the 23000.0 entry -> TP for the long.
    emitted = resolver.on_bar(_bar(_et(10, 0), 23016.0, 23000.0))
    assert len(emitted) == 1
    assert isinstance(emitted[0], StreamResolution)
    assert resolver.open_count == 0


def test_registration_no_fill_when_no_qualifying_print() -> None:
    resolver = _resolver(trade_price_at=lambda ts: None)
    drop = resolver.register(
        "k", touch_bar_ts_utc=_et(10, 0), trading_day=_DAY, direction="long"
    )
    assert isinstance(drop, StreamDrop) and drop.reason == "no_fill"
    assert drop.entry_price is None
    assert resolver.open_count == 0


def test_no_forward_via_flush_carries_the_entry() -> None:
    resolver = _resolver(trade_price_at=lambda ts: 23000.0)
    assert resolver.register(
        "k", touch_bar_ts_utc=_et(10, 0), trading_day=_DAY, direction="long"
    ) is None
    assert resolver.open_count == 1
    emitted = resolver.flush(_et(18, 0))  # cutoff (17:00 ET) has passed; zero bars seen
    assert len(emitted) == 1
    drop = emitted[0]
    assert isinstance(drop, StreamDrop) and drop.reason == "no_forward"
    assert drop.entry_price == 23000.0
    assert drop.max_mfe is None and drop.bars_to_resolution is None
    assert resolver.open_count == 0


def test_no_resolution_via_flush_carries_4dp_extremes_and_bars_sentinel() -> None:
    resolver = _resolver(trade_price_at=lambda ts: 23000.0)
    resolver.register("k", touch_bar_ts_utc=_et(10, 0), trading_day=_DAY, direction="long")
    # Two in-window bars, neither barrier reached (long: MFE 3.0, MAE 2.0).
    assert resolver.on_bar(_bar(_et(10, 10), 23003.0, 22999.0)) == ()
    assert resolver.on_bar(_bar(_et(10, 20), 23002.0, 22998.0)) == ()
    emitted = resolver.flush(_et(18, 0))
    assert len(emitted) == 1
    drop = emitted[0]
    assert isinstance(drop, StreamDrop) and drop.reason == "no_resolution"
    assert (drop.max_mfe, drop.max_mae) == (3.0, 2.0)
    assert drop.bars_to_resolution == -1
    assert drop.entry_price == 23000.0


def test_resolution_carries_the_resolving_bars_close_instant() -> None:
    # The resolution path: one in-window bar trips TP (long: MFE 16 >= 15, MAE 1 < 30).
    resolver = _resolver(trade_price_at=lambda ts: 23000.0)
    resolver.register("k", touch_bar_ts_utc=_et(10, 0), trading_day=_DAY, direction="long")
    assert resolver.on_bar(_bar(_et(10, 10), 23003.0, 22999.0)) == ()  # no barrier yet
    resolving_close = _et(10, 20)
    emitted = resolver.on_bar(_bar(resolving_close, 23016.0, 22999.0))
    assert len(emitted) == 1
    resolution = emitted[0]
    assert isinstance(resolution, StreamResolution)
    assert resolution.result.label == "tradeable_reversal"
    assert resolution.entry_price == 23000.0
    assert resolution.decision_ts_utc == _et(10, 5)
    # PIN: resolved_ts_utc is the RESOLVING bar's close_ts_utc — the timestamp the
    # batch OutcomeResult deliberately omits, so gate A cannot arbitrate it.
    assert resolution.resolved_ts_utc == resolving_close
    # ZERO-BASED: the second in-window bar resolves at index 1.
    assert resolution.result.bars_to_resolution == 1
    assert resolver.open_count == 0


def test_no_resolution_via_on_bar_excludes_the_cutoff_straddling_bars_range() -> None:
    resolver = _resolver(trade_price_at=lambda ts: 23000.0)
    resolver.register("k", touch_bar_ts_utc=_et(10, 0), trading_day=_DAY, direction="long")
    assert resolver.on_bar(_bar(_et(10, 10), 23003.0, 22999.0)) == ()
    # The finalizing bar closes AT the cutoff with a range that would trip BOTH
    # barriers if counted; the strict close < cutoff window excludes it.
    emitted = resolver.on_bar(_bar(_et(17, 0), 23100.0, 22900.0))
    assert len(emitted) == 1
    drop = emitted[0]
    assert isinstance(drop, StreamDrop) and drop.reason == "no_resolution"
    assert (drop.max_mfe, drop.max_mae) == (3.0, 1.0)  # the 10:10 bar only
    assert drop.bars_to_resolution == -1
    assert not isinstance(drop, StreamResolution)


def test_trade_ring_lookback_bound_and_retention_eviction() -> None:
    runtime = StrategyRuntime(timeframes=(147,), decision_timeframe=147)
    t0 = _et(10, 0)
    runtime.process_event(Trade(event_ts_utc=t0, price_ticks=92000, size=1))
    # (g1) inside the 30-min lookback -> the print; just past it -> None.
    assert runtime.trade_price_at(t0 + timedelta(minutes=29)) == 92000 * _TICK
    assert runtime.trade_price_at(t0 + timedelta(minutes=31)) is None
    # (g2) a print 61 minutes later evicts t0 beyond the 60-min retention: a query
    # at t0+25m would have matched t0 inside its own 30-min window, but the entry
    # is gone from the ring entirely.
    runtime.process_event(
        Trade(event_ts_utc=t0 + timedelta(minutes=61), price_ticks=92400, size=1)
    )
    assert runtime.trade_price_at(t0 + timedelta(minutes=25)) is None
    # The fresh print serves at-or-before queries normally.
    assert runtime.trade_price_at(t0 + timedelta(minutes=62)) == 92400 * _TICK
