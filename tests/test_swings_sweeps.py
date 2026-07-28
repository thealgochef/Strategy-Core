"""Swing-confirmation lag + sweep semantics (``structures/swings.py`` / ``sweeps.py``).

Pins: strict fractal pivots with ties producing no pivot; confirmation exactly
``strength`` bars after the pivot (the availability instant); snapshot resume ==
continuous; sweeps are STRICT trades-through on the stop side with availability
and side filtering at arm time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from strategy_core.candles._ids import make_bar_id
from strategy_core.structures.sweeps import LevelPool, SweepTracker
from strategy_core.structures.swings import SwingTracker
from strategy_core.types import Bar, BarKind, CloseReason, Direction, Side

_DAY = date(2026, 1, 5)
_T0 = datetime(2026, 1, 4, 23, 0, tzinfo=UTC)


def _bar(index: int, h: int, low: int) -> Bar:
    open_ts = _T0 + timedelta(seconds=60 * index)
    return Bar(
        timeframe_ticks=60,
        trading_day=_DAY,
        bar_index=index,
        bar_id=make_bar_id(60, _DAY, index, BarKind.TIME),
        open_ts_utc=open_ts,
        close_ts_utc=open_ts + timedelta(seconds=59),
        open_ticks=(h + low) // 2,
        high_ticks=h,
        low_ticks=low,
        close_ticks=(h + low) // 2,
        volume=1,
        trade_count=1,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
        kind=BarKind.TIME,
    )


def test_pivot_confirms_strength_bars_later() -> None:
    """Highs 100,101,105,102,101: bar 2 is a strength-2 HIGH pivot, confirmed
    only at bar 4's close."""
    tracker = SwingTracker(strength=2)
    bars = [_bar(0, 100, 90), _bar(1, 101, 91), _bar(2, 105, 95), _bar(3, 102, 92)]
    for bar in bars:
        assert tracker.on_bar_closed(bar) == ()
    confirming = _bar(4, 101, 91)
    points = tracker.on_bar_closed(confirming)
    assert [(p.side, p.price_ticks) for p in points] == [(Side.HIGH, 105)]
    assert points[0].pivot_bar_id == bars[2].bar_id
    assert points[0].confirmed_ts_utc == confirming.close_ts_utc


def test_tie_produces_no_pivot() -> None:
    """An equal high inside the window kills the pivot (strict comparison)."""
    tracker = SwingTracker(strength=2)
    for bar in [_bar(0, 100, 90), _bar(1, 105, 91), _bar(2, 105, 95), _bar(3, 102, 92), _bar(4, 101, 91)]:
        points = tracker.on_bar_closed(bar)
        assert all(p.side is not Side.HIGH for p in points)


def test_low_pivot_and_recent_filtering() -> None:
    tracker = SwingTracker(strength=1)
    bars = [_bar(0, 100, 95), _bar(1, 99, 90), _bar(2, 100, 94)]
    tracker.on_bar_closed(bars[0])
    tracker.on_bar_closed(bars[1])
    points = tracker.on_bar_closed(bars[2])
    assert [(p.side, p.price_ticks) for p in points] == [(Side.LOW, 90)]
    confirmed_at = points[0].confirmed_ts_utc
    assert tracker.recent(side=Side.LOW, before=confirmed_at, limit=8) == points
    # Not yet available one microsecond before confirmation.
    assert tracker.recent(side=Side.LOW, before=confirmed_at - timedelta(microseconds=1), limit=8) == ()


def test_snapshot_resume_equals_continuous() -> None:
    import random

    rng = random.Random(11)
    highs = [100]
    for _ in range(120):
        highs.append(highs[-1] + rng.choice((-4, -1, 0, 1, 4)))
    bars = [_bar(i, h, h - 6) for i, h in enumerate(highs)]

    cont = SwingTracker(strength=3, max_kept=16)
    cont_points = [p for b in bars for p in cont.on_bar_closed(b)]

    part = SwingTracker(strength=3, max_kept=16)
    resumed_points = []
    for b in bars[:60]:
        resumed_points.extend(part.on_bar_closed(b))
    resumed = SwingTracker.from_snapshot(part.snapshot())
    for b in bars[60:]:
        resumed_points.extend(resumed.on_bar_closed(b))

    assert resumed_points == cont_points
    assert resumed.snapshot() == cont.snapshot()
    assert cont_points, "walk must confirm at least one pivot"


def test_sweep_strictly_through_low_pool_for_long() -> None:
    """LONG setup: counter-leg down. AT the pool is a touch, not a raid; one
    tick through confirms, with penetration and first-sweep instant recorded."""
    armed = _T0 + timedelta(hours=1)
    pools = (
        LevelPool("pdl", 100, Side.LOW, None),
        LevelPool("asia_low", 95, Side.LOW, None),
        LevelPool("pdh", 130, Side.HIGH, None),  # off-side: excluded at arm
    )
    tracker = SweepTracker(direction=Direction.LONG, pools=pools, armed_ts=armed)
    assert [p.kind for p in tracker.pools] == ["pdl", "asia_low"]

    tracker.on_bar(_bar(61, 108, 100))  # touches pdl exactly -> not swept
    r = tracker.result()
    assert not r.sweep_confirmed and r.leg_extreme_ticks == 100
    assert r.nearest_unswept_distance_ticks == 0  # sitting ON the nearest pool

    sweep_bar = _bar(62, 106, 98)  # strictly through pdl, not asia_low
    tracker.on_bar(sweep_bar)
    r = tracker.result()
    assert r.sweep_confirmed and r.swept_kinds == ("pdl",)
    assert r.max_penetration_ticks == 2
    assert r.nearest_unswept_distance_ticks == 3  # asia_low 95 vs extreme 98
    assert r.sweep_ts_utc == sweep_bar.close_ts_utc


def test_sweep_availability_filter_at_arm() -> None:
    armed = _T0 + timedelta(hours=1)
    pools = (
        LevelPool("ny_low", 90, Side.LOW, available_from=armed + timedelta(hours=5)),
        LevelPool("pdl", 100, Side.LOW, available_from=armed - timedelta(hours=5)),
    )
    tracker = SweepTracker(direction=Direction.LONG, pools=pools, armed_ts=armed)
    assert [p.kind for p in tracker.pools] == ["pdl"]


def test_sweep_short_direction_high_pools() -> None:
    armed = _T0 + timedelta(hours=1)
    pools = (LevelPool("prev_ny_high", 120, Side.HIGH, None),)
    tracker = SweepTracker(direction=Direction.SHORT, pools=pools, armed_ts=armed)
    tracker.on_bar(_bar(61, 121, 110))
    r = tracker.result()
    assert r.sweep_confirmed and r.swept_kinds == ("prev_ny_high",)
    assert r.max_penetration_ticks == 1 and r.leg_extreme_ticks == 121
