"""IFVG label kernel-reuse tests (``strategies/ifvg_smc/labels.py``).

Pins the r-relative mapping onto the shared MAE-first kernel and the
reducer-walk <-> kernel agreement (both-breach resolves to the loss on both
paths — the single-source-of-truth guarantee).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from strategy_core.candles._ids import make_bar_id
from strategy_core.strategies.ifvg_smc.labels import resolve_ifvg_outcome
from strategy_core.types import Bar, BarKind, CloseReason, Direction

_DAY = date(2026, 1, 6)
_T0 = datetime(2026, 1, 5, 23, 0, tzinfo=UTC)
_TICK = 0.25


def _bar(index: int, o: int, h: int, low: int, c: int) -> Bar:
    open_ts = _T0 + timedelta(seconds=60 * index)
    return Bar(
        timeframe_ticks=60,
        trading_day=_DAY,
        bar_index=index,
        bar_id=make_bar_id(60, _DAY, index, BarKind.TIME),
        open_ts_utc=open_ts,
        close_ts_utc=open_ts + timedelta(seconds=59),
        open_ticks=o,
        high_ticks=h,
        low_ticks=low,
        close_ticks=c,
        volume=1,
        trade_count=1,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
        kind=BarKind.TIME,
    )


def test_win_loss_timeout_and_r_multiples() -> None:
    # entry 10000, stop 9980 -> risk 20 ticks = 5.0 points.
    win = resolve_ifvg_outcome(
        entry_ticks=10000,
        stop_ticks=9980,
        direction=Direction.LONG,
        forward_bars_1m=[_bar(1, 10005, 10021, 9990, 10018)],  # +21 ticks > +20 target
        tick_size=_TICK,
    )
    assert win.label == "win" and win.bars_to_resolution == 0  # kernel: 0-indexed slice position
    assert win.risk_points == 5.0 and win.mfe_r == pytest.approx(21 / 20)

    loss = resolve_ifvg_outcome(
        entry_ticks=10000,
        stop_ticks=9980,
        direction=Direction.LONG,
        forward_bars_1m=[_bar(1, 9998, 10005, 9979, 9985)],
        tick_size=_TICK,
    )
    assert loss.label == "loss"

    timeout = resolve_ifvg_outcome(
        entry_ticks=10000,
        stop_ticks=9980,
        direction=Direction.LONG,
        forward_bars_1m=[_bar(1, 10001, 10010, 9991, 10005)],
        tick_size=_TICK,
    )
    assert timeout.label == "censored" and timeout.bars_to_resolution == -1
    assert timeout.bars_after_entry_to_resolution is None

    # r=2: +21 ticks is short of the +40 target but the stop never hits.
    r2 = resolve_ifvg_outcome(
        entry_ticks=10000,
        stop_ticks=9980,
        direction=Direction.LONG,
        forward_bars_1m=[_bar(1, 10005, 10021, 9990, 10018)],
        tick_size=_TICK,
        r_multiple=2.0,
    )
    assert r2.label == "censored"


def test_both_breach_bar_is_the_loss_in_shared_kernel() -> None:
    """One bar spans stop AND target: the shared kernel resolves it as a loss."""
    both = _bar(1, 10000, 10025, 9979, 10010)  # entry 10000, stop 9980, tp 10020

    kernel = resolve_ifvg_outcome(
        entry_ticks=10000,
        stop_ticks=9980,
        direction=Direction.LONG,
        forward_bars_1m=[both],
        tick_size=_TICK,
    )
    assert kernel.label == "loss"



def test_risk_floor_fails_loud() -> None:
    with pytest.raises(ValueError):
        resolve_ifvg_outcome(
            entry_ticks=10000,
            stop_ticks=10000,
            direction=Direction.LONG,
            forward_bars_1m=[],
            tick_size=_TICK,
        )
