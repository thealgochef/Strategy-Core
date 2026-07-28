"""FVG detection + predicate/measurement tests (``structures/fvg.py``).

Pins the census-canonical geometry: strict inequalities, three-bar triplets
with B irrelevant, confirmation at the C bar's close, cross-day triplet
continuity via the detector tail, and the integer-tick predicate semantics
(strict body-close-through, doubled-tick CE, closed-interval wick overlap).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from strategy_core.candles._ids import make_bar_id
from strategy_core.structures.fvg import (
    FvgDetector,
    GapDirection,
    body_closes_through,
    ce_reached,
    close_through_margin_ticks,
    detect_fvgs_over_bars,
    interval_distance_ticks,
    penetration_ticks,
    wick_overlaps,
)
from strategy_core.types import Bar, BarKind, CloseReason, Side

_DAY = date(2026, 1, 5)
_T0 = datetime(2026, 1, 4, 23, 0, tzinfo=UTC)  # 18:00 ET day start


def _bar(
    index: int,
    o: int,
    h: int,
    l: int,  # noqa: E741 - mirrors OHLC naming
    c: int,
    *,
    tf: int = 60,
    day: date = _DAY,
    complete: bool = True,
) -> Bar:
    open_ts = _T0 + timedelta(seconds=tf * index)
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
        is_complete=complete,
        is_partial=not complete,
        close_reason=CloseReason.COMPLETE if complete else CloseReason.END_OF_DAY,
        kind=BarKind.TIME,
    )


def test_bullish_gap_detected_with_exact_interval() -> None:
    """A.high(102) < C.low(105) -> bullish [102, 105], size 3, confirmed at C close."""
    a, b, c = _bar(0, 100, 102, 99, 101), _bar(1, 101, 104, 100, 104), _bar(2, 105, 108, 105, 107)
    det = FvgDetector(60)
    assert det.on_bar_closed(a) is None
    assert det.on_bar_closed(b) is None
    gap = det.on_bar_closed(c)
    assert gap is not None
    assert gap.direction is GapDirection.BULLISH
    assert (gap.gap_low_ticks, gap.gap_high_ticks, gap.size_ticks) == (102, 105, 3)
    assert gap.confirmed_ts_utc == c.close_ts_utc
    assert gap.a_open_ts_utc == a.open_ts_utc
    assert gap.fvg_id == f"60s:bullish:{c.bar_id}"
    assert gap.far_boundary_ticks == 102 and gap.near_boundary_ticks == 105


def test_bearish_gap_detected() -> None:
    """A.low(105) > C.high(102) -> bearish [102, 105]."""
    a, b, c = _bar(0, 107, 108, 105, 106), _bar(1, 105, 106, 103, 103), _bar(2, 101, 102, 99, 100)
    gaps = detect_fvgs_over_bars([a, b, c], timeframe_seconds=60)
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.direction is GapDirection.BEARISH
    assert (gap.gap_low_ticks, gap.gap_high_ticks, gap.size_ticks) == (102, 105, 3)
    assert gap.far_boundary_ticks == 105 and gap.near_boundary_ticks == 102


def test_touching_edges_is_not_a_gap() -> None:
    """Strict inequality: A.high == C.low leaves no gap (census convention)."""
    bars = [_bar(0, 100, 103, 99, 102), _bar(1, 102, 104, 101, 104), _bar(2, 103, 106, 103, 105)]
    assert detect_fvgs_over_bars(bars, timeframe_seconds=60) == []


def test_min_gap_ticks_floor_is_a_capture_bound() -> None:
    """size 3 passes floor 3 but not floor 4."""
    bars = [_bar(0, 100, 102, 99, 101), _bar(1, 101, 104, 100, 104), _bar(2, 105, 108, 105, 107)]
    assert len(detect_fvgs_over_bars(bars, timeframe_seconds=60, min_gap_ticks=3)) == 1
    assert detect_fvgs_over_bars(bars, timeframe_seconds=60, min_gap_ticks=4) == []


def test_window_rolls_and_overlapping_triplets_each_detect() -> None:
    """The window rolls one bar at a time: triplets (0,1,2) and (1,2,3) each
    satisfy the strict-inequality geometry here and each yields its own gap."""
    bars = [
        _bar(0, 100, 102, 99, 101),
        _bar(1, 101, 104, 100, 104),
        _bar(2, 105, 108, 105, 107),  # A.high 102 < C.low 105
        _bar(3, 107, 110, 106, 109),  # A.high 104 < C.low 106
    ]
    gaps = detect_fvgs_over_bars(bars, timeframe_seconds=60)
    assert [g.c_bar_id for g in gaps] == [bars[2].bar_id, bars[3].bar_id]


def test_cross_day_triplet_via_tail() -> None:
    """A batch run seeded with the prior day's tail detects the boundary triplet."""
    day2 = date(2026, 1, 6)
    a = _bar(40, 100, 102, 99, 101)
    b = _bar(41, 101, 104, 100, 104, complete=False)  # END_OF_DAY bars participate
    c = _bar(0, 105, 108, 105, 107, day=day2)
    continuous = detect_fvgs_over_bars([a, b, c], timeframe_seconds=60)
    seeded = detect_fvgs_over_bars([c], timeframe_seconds=60, tail=(a, b))
    assert continuous == seeded
    assert len(seeded) == 1 and seeded[0].trading_day == day2


def test_detector_tail_snapshot_roundtrip() -> None:
    """from_tail(snapshot_tail()) continues the stream identically."""
    bars = [_bar(i, 100 + i, 102 + i, 99 + i, 101 + i) for i in range(2)]
    det = FvgDetector(60)
    for bar in bars:
        det.on_bar_closed(bar)
    resumed = FvgDetector.from_tail(60, det.snapshot_tail())
    c = _bar(2, 110, 112, 108, 111)
    assert resumed.on_bar_closed(c) == FvgDetector.from_tail(60, tuple(bars)).on_bar_closed(c)


def test_wick_overlap_closed_interval() -> None:
    bar = _bar(0, 100, 105, 100, 104)
    assert wick_overlaps(bar, 105, 108)  # high == lo edge -> touch
    assert wick_overlaps(bar, 98, 100)  # low == hi edge -> touch
    assert not wick_overlaps(bar, 106, 108)
    assert not wick_overlaps(bar, 95, 99)


def test_body_close_through_is_strict_with_margin() -> None:
    bar = _bar(0, 100, 106, 99, 105)
    assert not body_closes_through(bar, boundary_ticks=105, beyond=Side.HIGH)  # AT != through
    assert body_closes_through(bar, boundary_ticks=104, beyond=Side.HIGH)
    assert close_through_margin_ticks(bar, boundary_ticks=104, beyond=Side.HIGH) == 1
    assert close_through_margin_ticks(bar, boundary_ticks=106, beyond=Side.HIGH) == -1
    assert body_closes_through(bar, boundary_ticks=106, beyond=Side.LOW)
    assert close_through_margin_ticks(bar, boundary_ticks=106, beyond=Side.LOW) == 1


def test_penetration_and_ce_measurements() -> None:
    bars = [_bar(0, 100, 102, 99, 101), _bar(1, 101, 104, 100, 104), _bar(2, 105, 108, 105, 107)]
    gap = detect_fvgs_over_bars(bars, timeframe_seconds=60)[0]  # bullish [102,105], ce_x2 = 207
    probe_shallow = _bar(3, 106, 107, 104, 106)  # low 104 -> 1 tick in, above CE (103.5)
    probe_ce = _bar(4, 106, 107, 103, 106)  # low 103 -> 2 ticks in, through CE
    probe_traverse = _bar(5, 106, 107, 101, 106)  # low 101 -> capped at size 3
    assert penetration_ticks(probe_shallow, gap) == 1
    assert not ce_reached(probe_shallow, gap)
    assert ce_reached(probe_ce, gap)
    assert penetration_ticks(probe_traverse, gap) == 3
    assert penetration_ticks(_bar(6, 106, 107, 106, 106), gap) == 0


def test_interval_distance() -> None:
    assert interval_distance_ticks(100, 105, 103, 110) == 0  # overlap
    assert interval_distance_ticks(100, 105, 105, 110) == 0  # shared edge
    assert interval_distance_ticks(100, 105, 108, 110) == 3
    assert interval_distance_ticks(108, 110, 100, 105) == 3
