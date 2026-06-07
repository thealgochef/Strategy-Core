"""Fidelity tests for the interaction + approach feature formulas.

Every expected value is hand-computed against the canonical research math in
``dashboard_utility_builder.py:446-538`` and ``experiment/features.py``. All inputs
use fixed timezone-aware UTC datetimes -- no ``now()``/``random`` -- so the suite is
deterministic. ``tick_size`` here is the canonical ``0.25`` unless a test needs a
round number to keep the hand arithmetic transparent.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from strategy_core.constants import (
    LARGE_TRADE_THRESHOLD,
    LEVEL_PROXIMITY_PTS,
    MAX_DWELL_GAP_SECONDS,
    WITHIN_BAND_PTS,
)
from strategy_core.decisions.features import (
    app_avg_trade_size,
    app_large_trade_vol_pct,
    app_max_spread,
    int_absorption_ratio,
    int_time_beyond_level,
    int_time_within_2pts,
)
from strategy_core.types import Direction, Quote, Trade

# A fixed UTC anchor for every timestamp in the suite.
T0 = datetime(2025, 6, 2, 13, 30, tzinfo=timezone.utc)


def _t(seconds: float) -> datetime:
    """T0 offset by ``seconds`` (kept tz-aware)."""
    return T0 + timedelta(seconds=seconds)


def _trade(seconds: float, price_ticks: int, size: int = 1) -> Trade:
    return Trade(event_ts_utc=_t(seconds), price_ticks=price_ticks, size=size)


# ── int_time_beyond_level ─────────────────────────────────────────────────────


def test_int_time_beyond_level_long_hand_computed() -> None:
    """LONG: dwell counts gaps whose *start* price is below the level.

    tick_size 1.0 so price_ticks == price_points. Level at 100.0 points.
    Trades (ts offset s, price): (0,99) (10,101) (40,98) (70,100).
    Gaps attributed to the *earlier* trade's price:
      [0->10]   dt=10, m=99  < 100 -> counts  (+10)
      [10->40]  dt=30, m=101 not < 100 -> skip
      [40->70]  dt=30, m=98  < 100 -> counts  (+30)
    Total = 40.0 seconds.
    """
    trades = [
        _trade(0, 99),
        _trade(10, 101),
        _trade(40, 98),
        _trade(70, 100),
    ]
    assert int_time_beyond_level(trades, 100.0, Direction.LONG, 1.0) == 40.0


def test_int_time_beyond_level_short_hand_computed() -> None:
    """SHORT: dwell counts gaps whose start price is *above* the level.

    Same trade list / level. Predicate m > 100:
      [0->10]   m=99  -> skip
      [10->40]  m=101 -> counts (+30)
      [40->70]  m=98  -> skip
    Total = 30.0 seconds.
    """
    trades = [
        _trade(0, 99),
        _trade(10, 101),
        _trade(40, 98),
        _trade(70, 100),
    ]
    assert int_time_beyond_level(trades, 100.0, Direction.SHORT, 1.0) == 30.0


def test_int_time_beyond_level_skips_gap_over_600s() -> None:
    """A gap > MAX_DWELL_GAP_SECONDS is a data gap, not dwell, and is skipped.

    LONG, level 100, tick_size 1.0. Trades all below the level so each gap would
    otherwise count:
      [0->10]    dt=10  <= 600 -> counts (+10)
      [10->710]  dt=700 > 600  -> SKIP
      [710->715] dt=5   <= 600 -> counts (+5)
    Total = 15.0; the 700s gap is excluded.
    """
    trades = [
        _trade(0, 99),
        _trade(10, 98),
        _trade(710, 97),
        _trade(715, 96),
    ]
    assert int_time_beyond_level(trades, 100.0, Direction.LONG, 1.0) == 15.0
    # Boundary: exactly MAX_DWELL_GAP_SECONDS is kept (loop skips only `> max`).
    boundary = [
        _trade(0, 99),
        _trade(MAX_DWELL_GAP_SECONDS, 98),
    ]
    assert int_time_beyond_level(boundary, 100.0, Direction.LONG, 1.0) == round(
        MAX_DWELL_GAP_SECONDS, 4
    )


def test_int_time_beyond_level_negative_gap_skipped_via_stable_sort() -> None:
    """Out-of-order input is stably sorted ascending before the dwell loop.

    Supplied reversed; after sort the order/result match the LONG hand case (40.0).
    """
    trades = [
        _trade(70, 100),
        _trade(40, 98),
        _trade(10, 101),
        _trade(0, 99),
    ]
    assert int_time_beyond_level(trades, 100.0, Direction.LONG, 1.0) == 40.0


def test_int_time_beyond_level_uses_trade_price_not_quote_mid() -> None:
    """tick_size 0.25: price_points = price_ticks * 0.25 (the TRADE price).

    Level 25.0 points. Trades (offset, ticks): (0, 96)->24.0pts, (5, 104)->26.0pts.
    LONG predicate m < 25 on the first gap's start price 24.0 -> counts dt=5.
    """
    trades = [_trade(0, 96), _trade(5, 104)]
    assert int_time_beyond_level(trades, 25.0, Direction.LONG, 0.25) == 5.0


def test_int_time_beyond_level_empty_and_single() -> None:
    assert int_time_beyond_level([], 100.0, Direction.LONG, 1.0) == 0.0
    assert int_time_beyond_level([_trade(0, 99)], 100.0, Direction.LONG, 1.0) == 0.0


# ── int_time_within_2pts ──────────────────────────────────────────────────────


def test_int_time_within_2pts_hand_computed() -> None:
    """Within-band dwell uses abs(m - level) <= 2.0 (the hardcoded band).

    Level 100.0, tick_size 1.0. Trades (offset, price):
      (0, 101)  -> |1|   <= 2  start of gap [0->10]  dt=10 counts (+10)
      (10, 103) -> |3|   > 2   start of gap [10->25] dt=15 skip
      (25, 98)  -> |2|   <= 2  start of gap [25->40] dt=15 counts (+15)
      (40, 100) -> last trade, no gap starts here
    Total = 25.0 seconds.
    """
    trades = [
        _trade(0, 101),
        _trade(10, 103),
        _trade(25, 98),
        _trade(40, 100),
    ]
    assert int_time_within_2pts(trades, 100.0, 1.0) == 25.0


def test_int_time_within_2pts_band_boundary_inclusive() -> None:
    """The band edge is inclusive: |m - level| == 2.0 counts (<=, not <)."""
    trades = [_trade(0, 102), _trade(7, 100)]  # |102-100| == 2.0 exactly
    assert int_time_within_2pts(trades, 100.0, 1.0) == 7.0
    assert WITHIN_BAND_PTS == 2.0


def test_int_time_within_2pts_empty_and_single() -> None:
    assert int_time_within_2pts([], 100.0, 1.0) == 0.0
    assert int_time_within_2pts([_trade(0, 100)], 100.0, 1.0) == 0.0


# ── int_absorption_ratio ──────────────────────────────────────────────────────


def test_int_absorption_ratio_hand_computed_long() -> None:
    """at_level vs through volume with known sizes, LONG.

    tick_size 1.0, level 100.0, proximity 0.5 -> band [99.5, 100.5].
      price 100, size 30 -> in band      -> at_level += 30
      price 100, size 10 -> in band      -> at_level += 10  (at_level = 40)
      price  98, size 20 -> < 100, LONG  -> through  += 20
      price  97, size 20 -> < 100, LONG  -> through  += 20  (through = 40)
      price 105, size 99 -> > 100, LONG  -> neither (not adverse, not in band)
    ratio = 40 / (40 + 40) = 0.5 exactly. round(.,6) == 0.5.
    """
    trades = [
        _trade(0, 100, size=30),
        _trade(1, 100, size=10),
        _trade(2, 98, size=20),
        _trade(3, 97, size=20),
        _trade(4, 105, size=99),
    ]
    assert int_absorption_ratio(trades, 100.0, Direction.LONG, 1.0) == 0.5


def test_int_absorption_ratio_rounds_to_six_decimals() -> None:
    """1/3 ratio exercises the 6-decimal rounding (builder:537)."""
    trades = [
        _trade(0, 100, size=10),  # at level
        _trade(1, 98, size=20),  # through (LONG, < 100)
    ]
    # 10 / 30 = 0.333333... -> round(.,6) = 0.333333
    assert int_absorption_ratio(trades, 100.0, Direction.LONG, 1.0) == round(10 / 30, 6)
    assert int_absorption_ratio(trades, 100.0, Direction.LONG, 1.0) == 0.333333


def test_int_absorption_ratio_short_direction() -> None:
    """SHORT: through volume is the adverse-direction (> level) prints.

    Level 100, band [99.5,100.5].
      price 100, size 25 -> at_level (25)
      price 102, size 75 -> > 100, SHORT -> through (75)
      price  90, size 99 -> < 100, SHORT -> neither
    ratio = 25 / 100 = 0.25.
    """
    trades = [
        _trade(0, 100, size=25),
        _trade(1, 102, size=75),
        _trade(2, 90, size=99),
    ]
    assert int_absorption_ratio(trades, 100.0, Direction.SHORT, 1.0) == 0.25


def test_int_absorption_ratio_band_uses_proximity_default() -> None:
    """The default band half-width is LEVEL_PROXIMITY_PTS (0.50), inclusive.

    tick_size 0.25: price_ticks 401 -> 100.25 pts is within +/-0.5 of 100.0.
    """
    assert LEVEL_PROXIMITY_PTS == 0.50
    trades = [_trade(0, 401, size=5)]  # 401 * 0.25 = 100.25, in [99.5, 100.5]
    assert int_absorption_ratio(trades, 100.0, Direction.LONG, 0.25) == 1.0


def test_int_absorption_ratio_zero_total_returns_zero() -> None:
    """No at-level and no adverse-through volume -> total <= 0 -> 0.0."""
    # LONG, level 100: a single print far ABOVE the level is neither in-band nor
    # adverse, so both volumes stay zero.
    trades = [_trade(0, 110, size=50)]
    assert int_absorption_ratio(trades, 100.0, Direction.LONG, 1.0) == 0.0


def test_int_absorption_ratio_empty() -> None:
    assert int_absorption_ratio([], 100.0, Direction.LONG, 1.0) == 0.0


# ── app_large_trade_vol_pct ───────────────────────────────────────────────────


def test_app_large_trade_vol_pct_hand_computed() -> None:
    """Large share = sum(size for size>=10) / sum(size). Threshold is >=.

    Sizes: 5, 10, 12, 3.  large = 10 + 12 = 22 (size==10 counts: >=).
    total = 5 + 10 + 12 + 3 = 30.  pct = 22 / 30.
    """
    trades = [
        _trade(0, 100, size=5),
        _trade(1, 100, size=10),
        _trade(2, 100, size=12),
        _trade(3, 100, size=3),
    ]
    assert app_large_trade_vol_pct(trades) == 22 / 30
    assert LARGE_TRADE_THRESHOLD == 10


def test_app_large_trade_vol_pct_no_large_is_zero() -> None:
    trades = [_trade(0, 100, size=1), _trade(1, 100, size=9)]
    assert app_large_trade_vol_pct(trades) == 0.0


def test_app_large_trade_vol_pct_empty_is_nan() -> None:
    assert math.isnan(app_large_trade_vol_pct([]))


# ── app_avg_trade_size ────────────────────────────────────────────────────────


def test_app_avg_trade_size_hand_computed() -> None:
    """Mean size = (4 + 8 + 18) / 3 = 10.0."""
    trades = [
        _trade(0, 100, size=4),
        _trade(1, 100, size=8),
        _trade(2, 100, size=18),
    ]
    assert app_avg_trade_size(trades) == 10.0


def test_app_avg_trade_size_empty_is_nan() -> None:
    assert math.isnan(app_avg_trade_size([]))


# ── app_max_spread ────────────────────────────────────────────────────────────


def _quote(seconds: float, bid_ticks: int, ask_ticks: int) -> Quote:
    return Quote(
        event_ts_utc=_t(seconds),
        bid_price_ticks=bid_ticks,
        ask_price_ticks=ask_ticks,
    )


def test_app_max_spread_hand_computed() -> None:
    """Widest (ask-bid) over quotes, in points.

    tick_size 0.25. Spreads in ticks: (101-100)=1, (104-100)=4, (102-100)=2.
    max ticks = 4 -> 4 * 0.25 = 1.0 points.
    """
    quotes = [
        _quote(0, 100, 101),
        _quote(1, 100, 104),
        _quote(2, 100, 102),
    ]
    assert app_max_spread(quotes, 0.25) == 1.0


def test_app_max_spread_empty_is_nan() -> None:
    assert math.isnan(app_max_spread([], 0.25))
