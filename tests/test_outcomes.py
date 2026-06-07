"""Tests for the MAE-first outcome labeler (``decisions/outcomes.py``).

Fidelity target: ``dashboard_utility_labeling.py:44-108`` (``label_touch_event``)
and the aligned streaming ``outcome_tracker.py:160-191`` (``_classify``). The
load-bearing case is the MAE-first guard: a single bar breaching both the stop and
the target must resolve to the LOSS, not the win.

All timestamps are fixed, timezone-aware UTC -- never ``now()`` / ``random``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from strategy_core.constants import (
    AGGRESSIVE_BLOWTHROUGH,
    NO_RESOLUTION,
    TRADEABLE_REVERSAL,
    TRAP_REVERSAL,
)
from strategy_core.decisions.outcomes import (
    OutcomeResult,
    classify_mae_first,
    resolve_outcome,
)
from strategy_core.types import Bar, CloseReason, Direction

# ── Fixtures / helpers ───────────────────────────────────────────────────────

TICK_SIZE = 0.25
TP_POINTS = 15.0
SL_POINTS = 30.0
TRAP_MFE_MIN = 5.0

# A fixed, timezone-aware UTC anchor; bars are spaced by an arbitrary fixed delta.
_T0 = datetime(2025, 6, 2, 13, 30, tzinfo=timezone.utc)
_TRADING_DAY = date(2025, 6, 2)


def _bar(index: int, *, high_pts: float, low_pts: float) -> Bar:
    """Build a forward Bar whose high/low (in points) round-trip through ticks.

    Points are converted to integer ticks (``points / TICK_SIZE``) so the resolver's
    ``ticks * tick_size`` reproduces the intended points exactly. open/close are
    pinned at the low; they are unused by the resolver.
    """
    high_ticks = round(high_pts / TICK_SIZE)
    low_ticks = round(low_pts / TICK_SIZE)
    open_ts = _T0.replace(minute=30 + index)
    return Bar(
        timeframe_ticks=0,
        trading_day=_TRADING_DAY,
        bar_index=index,
        bar_id=f"bar-{index}",
        open_ts_utc=open_ts,
        close_ts_utc=open_ts,
        open_ticks=low_ticks,
        high_ticks=high_ticks,
        low_ticks=low_ticks,
        close_ticks=low_ticks,
        volume=1,
        trade_count=1,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
    )


def _resolve(entry: float, direction: Direction, bars: list[Bar]) -> OutcomeResult:
    return resolve_outcome(
        entry,
        direction,
        bars,
        TICK_SIZE,
        tp_points=TP_POINTS,
        sl_points=SL_POINTS,
        trap_mfe_min=TRAP_MFE_MIN,
    )


# ── classify_mae_first kernel ────────────────────────────────────────────────


def _classify(max_mfe: float, max_mae: float, *, forced: bool = False) -> str | None:
    return classify_mae_first(
        max_mfe,
        max_mae,
        tp_points=TP_POINTS,
        sl_points=SL_POINTS,
        trap_mfe_min=TRAP_MFE_MIN,
        forced=forced,
    )


def test_kernel_mae_first_both_breached_is_loss_not_win() -> None:
    """MFE >= TP and MAE >= SL together -> LOSS (MAE checked first), never the win."""
    # trap: favorable enough to count as a trap.
    assert _classify(max_mfe=20.0, max_mae=30.0) == TRAP_REVERSAL
    # blowthrough: MFE below trap_mfe_min even though TP was nominally exceeded.
    assert _classify(max_mfe=4.0, max_mae=30.0) == AGGRESSIVE_BLOWTHROUGH


def test_kernel_trap_vs_blowthrough_boundary() -> None:
    """MFE >= trap_mfe_min -> trap; strictly below -> blowthrough (>= boundary)."""
    assert _classify(max_mfe=TRAP_MFE_MIN, max_mae=SL_POINTS) == TRAP_REVERSAL
    assert _classify(max_mfe=TRAP_MFE_MIN - 0.0001, max_mae=SL_POINTS) == AGGRESSIVE_BLOWTHROUGH


def test_kernel_tp_only_is_tradeable() -> None:
    assert _classify(max_mfe=TP_POINTS, max_mae=0.0) == TRADEABLE_REVERSAL
    assert _classify(max_mfe=TP_POINTS - 0.0001, max_mae=0.0) is None


def test_kernel_unresolved_returns_none() -> None:
    assert _classify(max_mfe=1.0, max_mae=1.0) is None


def test_kernel_forced_splits_trap_blowthrough() -> None:
    """Forced (RTH cutoff) resolves with no threshold hit, same trap/blowthrough split."""
    assert _classify(max_mfe=TRAP_MFE_MIN, max_mae=1.0, forced=True) == TRAP_REVERSAL
    assert _classify(max_mfe=1.0, max_mae=1.0, forced=True) == AGGRESSIVE_BLOWTHROUGH
    # forced does not override the SL branch nor the TP branch.
    assert _classify(max_mfe=TP_POINTS, max_mae=0.0, forced=True) == TRADEABLE_REVERSAL


# ── resolve_outcome: LONG ────────────────────────────────────────────────────


def test_long_hits_tp_before_sl_tradeable_at_right_index() -> None:
    """LONG: TP reached on bar index 2 (no SL) -> tradeable_reversal, bars=2."""
    entry = 100.0
    bars = [
        _bar(0, high_pts=105.0, low_pts=98.0),  # mfe 5, mae 2
        _bar(1, high_pts=110.0, low_pts=99.0),  # mfe 10, mae 1
        _bar(2, high_pts=116.0, low_pts=99.0),  # mfe 16 >= TP -> resolve
    ]
    res = _resolve(entry, Direction.LONG, bars)
    assert res.label == TRADEABLE_REVERSAL
    assert res.label_encoded == 0
    assert res.bars_to_resolution == 2
    assert res.max_mfe == 16.0
    assert res.max_mae == 2.0


def test_long_single_bar_breaches_both_resolves_to_loss_not_win() -> None:
    """MAE-FIRST GUARD: one bar breaches SL and TP -> LOSS, not the win. Explicit."""
    entry = 100.0
    # high 120 -> mfe 20 (>= TP 15); low 69 -> mae 31 (>= SL 30). Both on bar 0.
    bars = [_bar(0, high_pts=120.0, low_pts=69.0)]
    res = _resolve(entry, Direction.LONG, bars)
    assert res.label != TRADEABLE_REVERSAL  # the guard: NOT the win
    assert res.label == TRAP_REVERSAL  # mfe 20 >= trap_mfe_min -> trap
    assert res.label_encoded == 1
    assert res.bars_to_resolution == 0
    assert res.max_mfe == 20.0
    assert res.max_mae == 31.0


def test_long_sl_with_mfe_at_or_above_trap_min_is_trap() -> None:
    entry = 100.0
    # bar0 gives mfe 5 (>= trap_mfe_min) and no SL; bar1 breaches SL.
    bars = [
        _bar(0, high_pts=105.0, low_pts=99.0),  # mfe 5, mae 1
        _bar(1, high_pts=101.0, low_pts=69.0),  # mae 31 >= SL; running mfe stays 5
    ]
    res = _resolve(entry, Direction.LONG, bars)
    assert res.label == TRAP_REVERSAL
    assert res.label_encoded == 1
    assert res.bars_to_resolution == 1
    assert res.max_mfe == 5.0
    assert res.max_mae == 31.0


def test_long_sl_with_mfe_below_trap_min_is_blowthrough() -> None:
    entry = 100.0
    # never reaches trap_mfe_min favorable; SL breached on bar 0.
    bars = [_bar(0, high_pts=102.0, low_pts=69.0)]  # mfe 2 < 5, mae 31 >= SL
    res = _resolve(entry, Direction.LONG, bars)
    assert res.label == AGGRESSIVE_BLOWTHROUGH
    assert res.label_encoded == 2
    assert res.bars_to_resolution == 0
    assert res.max_mfe == 2.0
    assert res.max_mae == 31.0


def test_never_resolved_is_no_resolution() -> None:
    entry = 100.0
    bars = [
        _bar(0, high_pts=103.0, low_pts=98.0),
        _bar(1, high_pts=104.0, low_pts=97.0),
    ]
    res = _resolve(entry, Direction.LONG, bars)
    assert res.label == NO_RESOLUTION
    assert res.label_encoded is None  # absent from LABEL_ENCODING
    assert res.bars_to_resolution == -1
    assert res.max_mfe == 4.0  # max(high-entry) = 104-100
    assert res.max_mae == 3.0  # max(entry-low)  = 100-97


def test_empty_forward_bars_is_no_resolution_zero_extremes() -> None:
    res = _resolve(100.0, Direction.LONG, [])
    assert res.label == NO_RESOLUTION
    assert res.label_encoded is None
    assert res.bars_to_resolution == -1
    assert res.max_mfe == 0.0
    assert res.max_mae == 0.0


# ── resolve_outcome: SHORT (mirrored) ────────────────────────────────────────


def test_short_hits_tp_before_sl_tradeable() -> None:
    """SHORT: favorable = entry - low. TP reached when price drops 15 below entry."""
    entry = 100.0
    bars = [
        _bar(0, high_pts=102.0, low_pts=95.0),  # mfe 5, mae 2
        _bar(1, high_pts=101.0, low_pts=84.0),  # mfe 16 >= TP -> resolve
    ]
    res = _resolve(entry, Direction.SHORT, bars)
    assert res.label == TRADEABLE_REVERSAL
    assert res.label_encoded == 0
    assert res.bars_to_resolution == 1
    assert res.max_mfe == 16.0  # entry - low = 100 - 84
    assert res.max_mae == 2.0  # high - entry = 102 - 100


def test_short_single_bar_breaches_both_resolves_to_loss() -> None:
    """SHORT mirror of the MAE-first guard: both breached -> LOSS, not win."""
    entry = 100.0
    # mfe = entry - low = 100 - 80 = 20 (>= TP); mae = high - entry = 131 - 100 = 31 (>= SL).
    bars = [_bar(0, high_pts=131.0, low_pts=80.0)]
    res = _resolve(entry, Direction.SHORT, bars)
    assert res.label != TRADEABLE_REVERSAL
    assert res.label == TRAP_REVERSAL
    assert res.label_encoded == 1
    assert res.bars_to_resolution == 0
    assert res.max_mfe == 20.0
    assert res.max_mae == 31.0


def test_short_sl_blowthrough() -> None:
    entry = 100.0
    # mfe = entry - low = 100 - 98 = 2 (< trap_min); mae = high - entry = 131 - 100 = 31.
    bars = [_bar(0, high_pts=131.0, low_pts=98.0)]
    res = _resolve(entry, Direction.SHORT, bars)
    assert res.label == AGGRESSIVE_BLOWTHROUGH
    assert res.label_encoded == 2
    assert res.bars_to_resolution == 0
    assert res.max_mfe == 2.0
    assert res.max_mae == 31.0


def test_rounding_to_four_decimals() -> None:
    """max_mfe / max_mae are rounded to 4 decimals (labeler:104-105)."""
    entry = 100.0
    # 0.1 pts -> not representable as exact ticks at 0.25, but choose a value that
    # exercises rounding via tick math: 100.375 high -> 401.5 ticks rounds to 402.
    # Instead use a clean fractional difference that needs rounding only at display.
    bars = [_bar(0, high_pts=100.25, low_pts=99.75)]  # mfe 0.25, mae 0.25
    res = _resolve(entry, Direction.LONG, bars)
    assert res.max_mfe == pytest.approx(0.25)
    assert res.max_mae == pytest.approx(0.25)
