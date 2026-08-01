"""Characterization gates for the IFVG v1 -> v2 correctness repair.

These tests intentionally describe the repaired contract rather than preserving
the v1 candidate-as-trade behavior.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, date, datetime, timedelta

import pytest

from strategy_core.candles._ids import make_bar_id
from strategy_core.strategies.ifvg_smc.labels import resolve_ifvg_outcome
from strategy_core.strategies.ifvg_smc.records import (
    IFVG_RECORD_SCHEMA_VERSION,
    EligibleDecisionRecord,
    EntryCandidateRecord,
    ExecutedTradeRecord,
    make_candidate_id,
    make_decision_id,
    make_setup_id,
    make_trade_id,
)
from strategy_core.strategies.ifvg_smc.reducer import (
    IfvgReducer,
    IfvgReducerConfig,
    IfvgStepInput,
)
from strategy_core.strategies.ifvg_smc.section import (
    IFVG_STRATEGY_VERSION,
    QualificationMode,
    RetestTrigger,
    default_ifvg_smc_section,
)
from strategy_core.structures.fvg import Fvg, FvgState, GapDirection
from strategy_core.types import Bar, BarKind, CloseReason, Direction

_DAY = date(2026, 1, 13)
_T0 = datetime(2026, 1, 12, 23, 0, tzinfo=UTC)


def _bar(index: int, o: int, h: int, low: int, c: int) -> Bar:
    logical_open = _T0 + timedelta(minutes=index)
    logical_close = logical_open + timedelta(minutes=1)
    return Bar(
        timeframe_ticks=60,
        trading_day=_DAY,
        bar_index=index,
        bar_id=make_bar_id(60, _DAY, index, BarKind.TIME),
        open_ts_utc=logical_open + timedelta(seconds=3),
        close_ts_utc=logical_close - timedelta(seconds=2),
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
        logical_open_ts_utc=logical_open,
        logical_close_ts_utc=logical_close,
    )


def _fvg(
    tf: int,
    direction: GapDirection,
    lo: int,
    hi: int,
    *,
    confirmed: datetime,
    ident: str,
) -> Fvg:
    return Fvg(
        fvg_id=f"{tf}s:{direction}:{ident}",
        timeframe_seconds=tf,
        direction=direction,
        gap_low_ticks=lo,
        gap_high_ticks=hi,
        size_ticks=hi - lo,
        a_bar_id=f"{ident}:a",
        c_bar_id=f"{ident}:c",
        a_open_ts_utc=confirmed - timedelta(seconds=tf * 3),
        confirmed_ts_utc=confirmed,
        trading_day=_DAY,
    )


def _step(bar: Bar, **kwargs) -> IfvgStepInput:
    return IfvgStepInput(
        bar_1m=bar,
        tf_bars_closed=kwargs.get("tf_bars_closed", {}),
        new_fvgs=kwargs.get("new_fvgs", {}),
        fill_events=kwargs.get("fill_events", ()),
        htf_live=kwargs.get("htf_live", ()),
        levels=(),
        recent_swing_highs=(),
        recent_swing_lows=(),
        session_engine=kwargs.get("session_engine", "ny"),
        session_doc=kwargs.get("session_doc", "ny"),
    )


def _cfg(*, both_directions: bool = False) -> IfvgReducerConfig:
    section = default_ifvg_smc_section()
    if both_directions:
        section = section.model_copy(update={"enable_shorts": True})
    return IfvgReducerConfig.from_section(
        section,
        tick_size=0.25,
        strategy_id="ifvg_smc",
        strategy_version=IFVG_STRATEGY_VERSION,
    )


def _drive_to_inversion(reducer: IfvgReducer) -> tuple[Fvg, Fvg, Fvg]:
    htf = _fvg(
        3600,
        GapDirection.BULLISH,
        10000,
        10020,
        confirmed=_T0 - timedelta(hours=2),
        ident="htf",
    )
    reducer.step(
        _step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(FvgState(fvg=htf),))
    )
    parent_bar = _bar(1, 10028, 10031, 10022, 10029)
    parent = _fvg(
        300,
        GapDirection.BULLISH,
        10010,
        10018,
        confirmed=parent_bar.logical_close_ts_utc,
        ident="parent",
    )
    reducer.step(
        _step(
            parent_bar,
            new_fvgs={300: (parent,)},
            tf_bars_closed={300: parent_bar},
        )
    )
    reducer.step(_step(_bar(2, 10024, 10026, 10016, 10022)))
    opposing_bar = _bar(3, 10020, 10021, 9992, 9995)
    opposing = _fvg(
        60,
        GapDirection.BEARISH,
        10008,
        10012,
        confirmed=opposing_bar.logical_close_ts_utc,
        ident="opposing",
    )
    reducer.step(_step(opposing_bar, new_fvgs={60: (opposing,)}))
    reducer.step(_step(_bar(4, 10000, 10016, 9998, 10014)))
    assert reducer.phase == "S4"
    return htf, parent, opposing


def test_v2_contract_separates_candidate_decision_and_trade() -> None:
    assert IFVG_STRATEGY_VERSION == "2"
    assert IFVG_RECORD_SCHEMA_VERSION == 2
    assert "selected" not in {field.name for field in fields(EntryCandidateRecord)}
    assert EligibleDecisionRecord is not EntryCandidateRecord
    assert ExecutedTradeRecord is not EligibleDecisionRecord


def test_doc_default_profile_is_explicit_and_runnable() -> None:
    section = default_ifvg_smc_section()
    assert section.profile_name == "ifvg_v2_doc_default_fresh_static_1r"
    assert section.qualification_mode is QualificationMode.DOC_DEFAULT
    assert section.runnable is True
    assert section.enable_longs is True
    assert section.enable_shorts is False
    assert section.max_executed_trades_per_day is None


def test_uuidv5_identity_chain_is_stable_and_family_specific() -> None:
    setup = make_setup_id("profile-hash", "htf-1", "tap-cursor")
    assert setup == make_setup_id("profile-hash", "htf-1", "tap-cursor")
    fresh = make_candidate_id(setup, "fresh_fvg_continuation", "gap:e1")
    retest = make_candidate_id(setup, "ifvg_retest", "touch:e1")
    assert fresh != retest
    decision = make_decision_id(fresh, "execution-profile-hash")
    trade = make_trade_id(decision, "entry-cursor")
    assert len({setup, fresh, retest, decision, trade}) == 5


def test_retest_candidate_is_one_shot_after_inversion() -> None:
    section = default_ifvg_smc_section().model_copy(
        update={
            "entry_family": "ifvg_retest",
            "retest_trigger": RetestTrigger.FIRST_TOUCH,
            "runnable": False,
            "non_runnable_reason": "trigger semantics unratified",
        }
    )
    reducer = IfvgReducer(
        IfvgReducerConfig.from_section(
            section,
            tick_size=0.25,
            strategy_id="ifvg_smc",
            strategy_version=IFVG_STRATEGY_VERSION,
        )
    )
    _drive_to_inversion(reducer)
    first = reducer.step(_step(_bar(5, 10013, 10014, 10009, 10011)))
    second = reducer.step(_step(_bar(6, 10012, 10015, 10008, 10010)))
    assert len([e for e in first if e.kind == "entry_candidate"]) == 1
    assert len([e for e in second if e.kind == "entry_candidate"]) == 0


def test_structural_stop_includes_entry_candle_extreme() -> None:
    reducer = IfvgReducer(_cfg())
    _drive_to_inversion(reducer)
    entry_bar = _bar(5, 10015, 10019, 9985, 10016)
    fresh = _fvg(
        60,
        GapDirection.BULLISH,
        10014,
        10015,
        confirmed=entry_bar.logical_close_ts_utc,
        ident="entry",
    )
    emissions = reducer.step(_step(entry_bar, new_fvgs={60: (fresh,)}))
    candidates = [
        e.record
        for e in emissions
        if e.kind == "entry_candidate"
        and e.record.entry_family == "fresh_fvg_continuation"
    ]
    assert len(candidates) == 1
    assert candidates[0].stop_ticks == 9984
    decisions = [e.record for e in emissions if e.kind == "eligible_decision"]
    assert len(decisions) == 1
    assert decisions[0].direction is Direction.LONG
    assert decisions[0].risk_ticks == 32


def test_ifvg_resolution_is_one_based_and_entry_bar_is_excluded() -> None:
    entry_bar = _bar(0, 10000, 10030, 9970, 10000)
    first_forward = _bar(1, 10000, 10021, 9990, 10018)
    outcome = resolve_ifvg_outcome(
        entry_ticks=10000,
        stop_ticks=9980,
        direction=Direction.LONG,
        entry_bar=entry_bar,
        forward_bars_1m=(entry_bar, first_forward),
        tick_size=0.25,
    )
    assert outcome.label == "win"
    assert outcome.bars_after_entry_to_resolution == 1
    assert outcome.bars_to_resolution == 0  # generic compatibility field


@pytest.mark.parametrize(
    ("direction", "entry", "stop", "r_multiple", "expected"),
    [
        (Direction.LONG, 100, 97, 1.5, 105),
        (Direction.SHORT, 100, 103, 1.5, 95),
    ],
)
def test_target_rounds_away_from_entry(
    direction: Direction,
    entry: int,
    stop: int,
    r_multiple: float,
    expected: int,
) -> None:
    from strategy_core.strategies.ifvg_smc.labels import target_ticks_for_r

    assert target_ticks_for_r(entry, stop, direction, r_multiple) == expected
