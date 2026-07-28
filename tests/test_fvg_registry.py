"""FvgRegistry fill-tracking tests (``structures/fvg.py``).

Pins the census fill semantics (wick touch, running-extreme traversal fill),
the strict-after participation rule (zero lookahead: a gap's own C bar never
touches it), memory-bound evictions as counted events, and the snapshot
round-trip that the cross-day seed chain depends on.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from strategy_core.candles._ids import make_bar_id
from strategy_core.structures.fvg import (
    FvgRegistry,
    detect_fvgs_over_bars,
)
from strategy_core.types import Bar, BarKind, CloseReason

_DAY = date(2026, 1, 5)
_T0 = datetime(2026, 1, 4, 23, 0, tzinfo=UTC)


def _bar(
    index: int,
    o: int,
    h: int,
    l: int,  # noqa: E741 - mirrors OHLC naming
    c: int,
    *,
    tf: int = 60,
    day: date = _DAY,
) -> Bar:
    open_ts = _T0 + timedelta(days=(day - _DAY).days, seconds=tf * index)
    return Bar(
        timeframe_ticks=tf,
        trading_day=day,
        bar_index=index,
        bar_id=make_bar_id(tf, day, index, BarKind.TIME),
        open_ts_utc=open_ts,
        close_ts_utc=open_ts + timedelta(seconds=tf - 1),
        open_ticks=o,
        high_ticks=h,
        low_ticks=l,
        close_ticks=c,
        volume=10,
        trade_count=5,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
        kind=BarKind.TIME,
    )


def _bullish_gap():
    """Bullish [102, 105] confirmed at bar 2's close."""
    bars = [_bar(0, 100, 102, 99, 101), _bar(1, 101, 104, 100, 104), _bar(2, 105, 108, 105, 107)]
    return detect_fvgs_over_bars(bars, timeframe_seconds=60)[0]


def test_own_confirming_bar_never_participates() -> None:
    """A bar closing AT the confirmation instant is skipped (strict-after)."""
    gap = _bullish_gap()
    reg = FvgRegistry(timeframe_seconds=60)
    reg.add(gap)
    same_instant = _bar(2, 105, 108, 101, 107)  # range would touch, instant forbids
    assert reg.on_execution_bar(same_instant) == ()
    assert reg.live()[0].first_touch_ts_utc is None


def test_first_touch_once_then_fill_on_traversal() -> None:
    gap = _bullish_gap()
    reg = FvgRegistry(timeframe_seconds=60)
    reg.add(gap)
    touch1 = _bar(3, 106, 107, 104, 106)  # 1 tick in
    touch2 = _bar(4, 106, 107, 103, 106)  # deeper, no second first_touch
    fill = _bar(5, 106, 107, 102, 106)  # low == far boundary -> traversed
    ev1 = reg.on_execution_bar(touch1)
    assert [e.kind for e in ev1] == ["first_touch"]
    state = reg.live()[0]
    assert state.penetration_so_far_ticks() == 1
    assert abs(state.remaining_fraction() - 2 / 3) < 1e-12
    ev2 = reg.on_execution_bar(touch2)
    assert ev2 == ()
    assert reg.live()[0].penetration_so_far_ticks() == 2
    ev3 = reg.on_execution_bar(fill)
    assert [e.kind for e in ev3] == ["filled"]
    assert reg.live() == ()  # filled gaps are dead context


def test_untouched_gap_stays_live_and_full_fraction() -> None:
    gap = _bullish_gap()
    reg = FvgRegistry(timeframe_seconds=60)
    reg.add(gap)
    away = _bar(3, 107, 109, 106, 108)
    assert reg.on_execution_bar(away) == ()
    state = reg.live()[0]
    assert state.first_touch_ts_utc is None
    assert state.remaining_fraction() == 1.0


def test_cap_eviction_is_oldest_first_and_counted() -> None:
    reg = FvgRegistry(timeframe_seconds=60, max_live=1)
    g1 = _bullish_gap()
    bars2 = [
        _bar(10, 200, 202, 199, 201),
        _bar(11, 201, 204, 200, 204),
        _bar(12, 205, 208, 205, 207),
    ]
    g2 = detect_fvgs_over_bars(bars2, timeframe_seconds=60)[0]
    assert reg.add(g1) == ()
    events = reg.add(g2)
    assert [e.kind for e in events] == ["evicted_cap"]
    assert events[0].fvg_id == g1.fvg_id
    assert [s.fvg.fvg_id for s in reg.live()] == [g2.fvg_id]


def test_age_eviction_counted() -> None:
    gap = _bullish_gap()
    reg = FvgRegistry(timeframe_seconds=60, max_age_days=2)
    reg.add(gap)
    later = _bar(0, 300, 301, 299, 300, day=_DAY + timedelta(days=3))
    events = reg.on_execution_bar(later)
    assert [e.kind for e in events] == ["evicted_age"]
    assert reg.live() == ()


def test_snapshot_roundtrip_preserves_tracking_state() -> None:
    gap = _bullish_gap()
    reg = FvgRegistry(timeframe_seconds=60, max_live=8, max_age_days=15)
    reg.add(gap)
    reg.on_execution_bar(_bar(3, 106, 107, 104, 106))  # first touch, 1 tick in
    tail = (_bar(8, 110, 112, 109, 111), _bar(9, 111, 113, 110, 112))
    snap = reg.snapshot(detector_tail=tail, min_gap_ticks=1)
    restored = FvgRegistry.from_snapshot(snap)
    assert restored.max_live == 8 and restored.max_age_days == 15
    orig, back = reg.live()[0], restored.live()[0]
    assert back.fvg == orig.fvg
    assert back.first_touch_ts_utc == orig.first_touch_ts_utc
    assert back.reached_ticks == orig.reached_ticks
    assert snap.detector_tail == tail
    fill = _bar(5, 106, 107, 102, 106)
    assert [e.kind for e in restored.on_execution_bar(fill)] == ["filled"]
