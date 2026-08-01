"""Own-timeframe parent reaction clock invariants."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from strategy_core.candles._ids import make_bar_id
from strategy_core.strategies.ifvg_smc.reducer import (
    IfvgReducer,
    IfvgReducerConfig,
    IfvgStepInput,
)
from strategy_core.strategies.ifvg_smc.section import (
    IFVG_STRATEGY_VERSION,
    default_ifvg_smc_section,
)
from strategy_core.structures.fvg import Fvg, FvgState, GapDirection
from strategy_core.types import Bar, BarKind, CloseReason

DAY = date(2026, 1, 13)
T0 = datetime(2026, 1, 12, 23, 0, tzinfo=UTC)


def _bar(index: int, *, tf: int = 60) -> Bar:
    opened = T0 + timedelta(minutes=index)
    return Bar(
        timeframe_ticks=tf,
        trading_day=DAY,
        bar_index=index,
        bar_id=make_bar_id(tf, DAY, index, BarKind.TIME),
        open_ts_utc=opened,
        close_ts_utc=opened + timedelta(seconds=59),
        open_ticks=110,
        high_ticks=115,
        low_ticks=105,
        close_ticks=110,
        volume=1,
        trade_count=1,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
        kind=BarKind.TIME,
    )


def _gap(tf: int, ident: str, confirmed: datetime) -> Fvg:
    return Fvg(
        fvg_id=f"{tf}s:bullish:{ident}",
        timeframe_seconds=tf,
        direction=GapDirection.BULLISH,
        gap_low_ticks=100,
        gap_high_ticks=108,
        size_ticks=8,
        a_bar_id=f"{ident}:a",
        c_bar_id=f"{ident}:c",
        a_open_ts_utc=confirmed - timedelta(seconds=3 * tf),
        confirmed_ts_utc=confirmed,
        trading_day=DAY,
    )


def _step(index: int, *, closed=(), gaps=()) -> IfvgStepInput:
    bar = _bar(index)
    return IfvgStepInput(
        bar_1m=bar,
        tf_bars_closed={tf: _bar(index, tf=tf) for tf in closed},
        new_fvgs={
            gap.timeframe_seconds: (gap,)
            for gap in gaps
        },
        fill_events=(),
        htf_live=(),
        levels=(),
        recent_swing_highs=(),
        recent_swing_lows=(),
        session_engine="ny",
        session_doc="ny",
        tf_bar_close_counts={tf: 1 for tf in closed},
    )


def _reducer() -> IfvgReducer:
    section = default_ifvg_smc_section()
    return IfvgReducer(
        IfvgReducerConfig.from_section(
            section,
            tick_size=0.25,
            strategy_id="ifvg_smc",
            strategy_version=IFVG_STRATEGY_VERSION,
        )
    )


def _activate(reducer: IfvgReducer) -> None:
    htf = _gap(3600, "htf", T0 - timedelta(hours=2))
    bar = _bar(0)
    reducer.step(
        IfvgStepInput(
            bar_1m=bar,
            tf_bars_closed={},
            new_fvgs={},
            fill_events=(),
            htf_live=(FvgState(fvg=htf),),
            levels=(),
            recent_swing_highs=(),
            recent_swing_lows=(),
            session_engine="ny",
            session_doc="ny",
        )
    )
    assert reducer.phase == "S1"


def test_one_timeframe_expiring_does_not_expire_all_parent_windows() -> None:
    reducer = _reducer()
    _activate(reducer)
    for index in range(1, 42):
        reducer.step(_step(index, closed=(180,)))
    assert reducer.phase == "S1"
    assert reducer.funnel_counters()["parentless_window_live"] == 42


def test_deadline_parent_bar_is_inclusive() -> None:
    reducer = _reducer()
    _activate(reducer)
    for index in range(1, 40):
        reducer.step(_step(index, closed=(180,)))
    deadline = _bar(40)
    parent = _gap(180, "parent", deadline.close_ts_utc)
    emissions = reducer.step(_step(40, closed=(180,), gaps=(parent,)))
    records = [e.record for e in emissions if e.kind == "parent_candidate"]
    assert len(records) == 1
    assert records[0].elapsed_parent_bars_since_tap == 40
    assert records[0].selected is True
