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
from strategy_core.strategies.ifvg_smc.reducer import (
    IfvgReducer,
    IfvgReducerConfig,
    IfvgReducerSnapshot,
    IfvgSetupSnapshot,
    IfvgStepInput,
    REDUCER_SNAPSHOT_SCHEMA_VERSION,
)
from strategy_core.strategies.ifvg_smc.section import default_ifvg_smc_section, ifvg_profile_hash
from strategy_core.structures.fvg import Fvg, GapDirection
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
    assert timeout.label == "eod_timeout" and timeout.bars_to_resolution == -1

    # r=2: +21 ticks is short of the +40 target but the stop never hits.
    r2 = resolve_ifvg_outcome(
        entry_ticks=10000,
        stop_ticks=9980,
        direction=Direction.LONG,
        forward_bars_1m=[_bar(1, 10005, 10021, 9990, 10018)],
        tick_size=_TICK,
        r_multiple=2.0,
    )
    assert r2.label == "eod_timeout"


def test_both_breach_bar_is_the_loss_on_both_paths() -> None:
    """One bar spans stop AND target: the kernel resolves it as the loss
    (MAE-first) and the reducer's in-trade walk must agree."""
    both = _bar(1, 10000, 10025, 9979, 10010)  # entry 10000, stop 9980, tp 10020

    kernel = resolve_ifvg_outcome(
        entry_ticks=10000,
        stop_ticks=9980,
        direction=Direction.LONG,
        forward_bars_1m=[both],
        tick_size=_TICK,
    )
    assert kernel.label == "loss"

    section = default_ifvg_smc_section()
    cfg = IfvgReducerConfig.from_section(
        section, tick_size=_TICK, strategy_id="ifvg_smc", strategy_version="1"
    )
    dummy_gap = Fvg(
        fvg_id="3600s:bullish:x",
        timeframe_seconds=3600,
        direction=GapDirection.BULLISH,
        gap_low_ticks=9990,
        gap_high_ticks=10005,
        size_ticks=15,
        a_bar_id="a",
        c_bar_id="c",
        a_open_ts_utc=_T0 - timedelta(hours=3),
        confirmed_ts_utc=_T0 - timedelta(hours=2),
        trading_day=_DAY,
    )
    in_trade = IfvgReducerSnapshot(
        schema_version=REDUCER_SNAPSHOT_SCHEMA_VERSION,
        profile_hash=ifvg_profile_hash(section),
        ordinal=10,
        seq_day=_DAY,
        seq=1,
        setup=IfvgSetupSnapshot(
            setup_id="ifvg:2026-01-06:0001",
            phase="S5",
            direction=Direction.LONG,
            htf=dummy_gap,
            tap_ts_utc=_T0,
            tap_ordinal=1,
            parent=None,
            parent_selected_ordinal=None,
            lock_ts_utc=None,
            lock_ordinal=None,
            swing_min_low=9981,
            swing_max_high=10010,
            sweep=None,
            opposing=None,
            armed_ts_utc=None,
            armed_ordinal=None,
            inversion_ts_utc=_T0 + timedelta(minutes=5),
            inversion_ordinal=6,
            sweep_result=None,
            entry_family="fresh_fvg_continuation",
            entry_ticks=10000,
            stop_ticks=9980,
            tp_ticks=10020,
            entry_ts_utc=_T0 + timedelta(minutes=9),
            entry_ordinal=10,
            mfe_ticks=0,
            mae_ticks=0,
        ),
    )
    reducer = IfvgReducer.from_snapshot(in_trade, cfg)
    emissions = reducer.step(
        IfvgStepInput(
            bar_1m=both,
            tf_bars_closed={},
            new_fvgs={},
            fill_events=(),
            htf_live=(),
            levels=(),
            recent_swing_highs=(),
            recent_swing_lows=(),
            session_engine="ny",
            session_doc="ny",
        )
    )
    res = [e.record for e in emissions if e.kind == "resolution"]
    assert len(res) == 1 and res[0].resolution == "resolved_sl"


def test_risk_floor_fails_loud() -> None:
    with pytest.raises(ValueError):
        resolve_ifvg_outcome(
            entry_ticks=10000,
            stop_ticks=10000,
            direction=Direction.LONG,
            forward_bars_1m=[],
            tick_size=_TICK,
        )
