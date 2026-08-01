"""Synthetic IFVG v2 FSM goldens across both directions and guard paths."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from random import Random

import pytest

from strategy_core.candles._ids import make_bar_id
from strategy_core.strategies.ifvg_smc.reducer import (
    IfvgReducer,
    IfvgReducerConfig,
    IfvgStepInput,
)
from strategy_core.strategies.ifvg_smc.section import (
    IFVG_STRATEGY_VERSION,
    RetestTrigger,
    default_ifvg_smc_section,
)
from strategy_core.structures.fvg import (
    Fvg,
    FvgFillEvent,
    FvgState,
    GapDirection,
)
from strategy_core.types import Bar, BarKind, CloseReason, Direction

_DAY = date(2026, 1, 14)
_T0 = datetime(2026, 1, 13, 23, 0, tzinfo=UTC)


def _bar(index: int, o: int, h: int, low: int, c: int) -> Bar:
    logical_open = _T0 + timedelta(minutes=index)
    logical_close = logical_open + timedelta(minutes=1)
    return Bar(
        timeframe_ticks=60,
        trading_day=_DAY,
        bar_index=index,
        bar_id=make_bar_id(60, _DAY, index, BarKind.TIME),
        open_ts_utc=logical_open + timedelta(seconds=2),
        close_ts_utc=logical_close - timedelta(seconds=1),
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
        fvg_id=f"{tf}s:{direction.value}:{ident}",
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


def _step(
    bar: Bar,
    *,
    new_fvgs: dict[int, tuple[Fvg, ...]] | None = None,
    fill_events: tuple[FvgFillEvent, ...] = (),
    htf_live: tuple[FvgState, ...] = (),
    session_doc: str = "ny",
) -> IfvgStepInput:
    return IfvgStepInput(
        bar_1m=bar,
        tf_bars_closed={},
        new_fvgs=new_fvgs or {},
        fill_events=fill_events,
        htf_live=htf_live,
        levels=(),
        recent_swing_highs=(),
        recent_swing_lows=(),
        session_engine=session_doc,
        session_doc=session_doc,
    )


def _reducer(
    direction: Direction,
    *,
    retest_only: bool = False,
) -> IfvgReducer:
    section = default_ifvg_smc_section()
    if direction is Direction.SHORT:
        section = section.model_copy(update={"enable_shorts": True})
    if retest_only:
        section = section.model_copy(
            update={
                "profile_name": "synthetic_unratified_retest",
                "entry_family": "ifvg_retest",
                "retest_trigger": RetestTrigger.FIRST_TOUCH,
                "runnable": False,
                "non_runnable_reason": "pure retest trigger is unratified",
                "execution_enabled": False,
            }
        )
    return IfvgReducer(
        IfvgReducerConfig.from_section(
            section,
            tick_size=0.25,
            strategy_id="ifvg_smc",
            strategy_version=IFVG_STRATEGY_VERSION,
        )
    )


def _drive_to_entry(
    direction: Direction,
    *,
    entry_session: str = "ny",
    retest_only: bool = False,
) -> tuple[IfvgReducer, Fvg, Fvg, Fvg, tuple]:
    reducer = _reducer(direction, retest_only=retest_only)
    if direction is Direction.LONG:
        htf = _fvg(
            3600,
            GapDirection.BULLISH,
            10000,
            10020,
            confirmed=_T0 - timedelta(hours=2),
            ident="long-htf",
        )
        parent = _fvg(
            300,
            GapDirection.BULLISH,
            10010,
            10018,
            confirmed=_bar(1, 10028, 10031, 10022, 10029).availability_ts_utc,
            ident="long-parent",
        )
        opposing = _fvg(
            60,
            GapDirection.BEARISH,
            10008,
            10012,
            confirmed=_bar(3, 10020, 10021, 9992, 9995).availability_ts_utc,
            ident="long-opposing",
        )
        entry = _fvg(
            60,
            GapDirection.BULLISH,
            10014,
            10015,
            confirmed=_bar(5, 10015, 10018, 10010, 10016).availability_ts_utc,
            ident="long-entry",
        )
        scripted = (
            _step(
                _bar(0, 10030, 10032, 10015, 10028),
                htf_live=(FvgState(fvg=htf),),
            ),
            _step(
                _bar(1, 10028, 10031, 10022, 10029),
                new_fvgs={300: (parent,)},
            ),
            _step(_bar(2, 10024, 10026, 10016, 10022)),
            _step(
                _bar(3, 10020, 10021, 9992, 9995),
                new_fvgs={60: (opposing,)},
            ),
            _step(_bar(4, 10000, 10016, 9998, 10014)),
            _step(
                _bar(5, 10015, 10018, 10010, 10016),
                new_fvgs={60: (entry,)},
                session_doc=entry_session,
            ),
        )
    else:
        htf = _fvg(
            3600,
            GapDirection.BEARISH,
            10000,
            10020,
            confirmed=_T0 - timedelta(hours=2),
            ident="short-htf",
        )
        parent = _fvg(
            300,
            GapDirection.BEARISH,
            10002,
            10010,
            confirmed=_bar(1, 9993, 9998, 9989, 9992).availability_ts_utc,
            ident="short-parent",
        )
        opposing = _fvg(
            60,
            GapDirection.BULLISH,
            9998,
            10002,
            confirmed=_bar(3, 9998, 10025, 9994, 10015).availability_ts_utc,
            ident="short-opposing",
        )
        entry = _fvg(
            60,
            GapDirection.BEARISH,
            9996,
            9997,
            confirmed=_bar(5, 9995, 10005, 9990, 9994).availability_ts_utc,
            ident="short-entry",
        )
        scripted = (
            _step(
                _bar(0, 9992, 10005, 9988, 9993),
                htf_live=(FvgState(fvg=htf),),
            ),
            _step(
                _bar(1, 9993, 9998, 9989, 9992),
                new_fvgs={300: (parent,)},
            ),
            _step(_bar(2, 9995, 10006, 9990, 9994)),
            _step(
                _bar(3, 9998, 10025, 9994, 10015),
                new_fvgs={60: (opposing,)},
            ),
            _step(_bar(4, 10010, 10014, 9990, 9996)),
            _step(
                _bar(5, 9995, 10005, 9990, 9994),
                new_fvgs={60: (entry,)},
                session_doc=entry_session,
            ),
        )
    emissions: tuple = ()
    for item in scripted:
        emissions = reducer.step(item)
    return reducer, htf, parent, opposing, emissions


@pytest.mark.parametrize(
    ("direction", "resolution"),
    [
        (Direction.LONG, "target"),
        (Direction.LONG, "stop"),
        (Direction.SHORT, "target"),
        (Direction.SHORT, "stop"),
    ],
)
def test_fresh_trade_directional_win_and_loss_goldens(
    direction: Direction,
    resolution: str,
) -> None:
    reducer, htf, parent, opposing, entry_emissions = _drive_to_entry(direction)
    decisions = [
        emission.record
        for emission in entry_emissions
        if emission.kind == "eligible_decision"
    ]
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.direction is direction
    assert decision.risk_ticks > 0
    assert (
        decision.stop_ticks < decision.entry_ticks
        if direction is Direction.LONG
        else decision.stop_ticks > decision.entry_ticks
    )
    if direction is Direction.LONG:
        resolution_bar = (
            _bar(6, 10020, decision.target_ticks + 2, decision.entry_ticks - 1, 10030)
            if resolution == "target"
            else _bar(6, 10000, decision.entry_ticks + 2, decision.stop_ticks - 1, 9995)
        )
    else:
        resolution_bar = (
            _bar(6, 9990, decision.entry_ticks + 1, decision.target_ticks - 2, 9970)
            if resolution == "target"
            else _bar(6, 10000, decision.stop_ticks + 1, decision.entry_ticks - 2, 10020)
        )
    resolved = [
        emission.record
        for emission in reducer.step(_step(resolution_bar))
        if emission.kind == "executed_trade"
    ]
    assert len(resolved) == 1
    trade = resolved[0]
    assert trade.resolution == resolution
    assert trade.direction is direction
    assert trade.bars_after_entry_to_resolution == 1
    assert trade.envelope.entry_session == "ny"
    assert trade.geometry.htf.fvg_id == htf.fvg_id
    assert trade.geometry.parent.fvg_id == parent.fvg_id
    assert trade.geometry.opposing.fvg_id == opposing.fvg_id
    assert reducer.active_setup_count == reducer.active_trade_count == 0


def test_fresh_candidate_while_trade_open_is_blocked_and_cannot_overlap() -> None:
    reducer, _, _, _, entry_emissions = _drive_to_entry(Direction.LONG)
    decision = next(
        emission.record
        for emission in entry_emissions
        if emission.kind == "eligible_decision"
    )
    fresh = _fvg(
        60,
        GapDirection.BULLISH,
        10018,
        10019,
        confirmed=_bar(6, 10017, 10025, 10000, 10020).availability_ts_utc,
        ident="occupied-fresh",
    )
    occupied = reducer.step(
        _step(
            _bar(6, 10017, 10025, 10000, 10020),
            new_fvgs={60: (fresh,)},
        )
    )
    candidates = [
        emission.record
        for emission in occupied
        if emission.kind == "entry_candidate"
        and emission.record.trigger_evidence_id == fresh.fvg_id
    ]
    assert len(candidates) == 1
    assert candidates[0].block_reasons == ("already_in_trade",)
    assert not [e for e in occupied if e.kind == "eligible_decision"]
    assert not [e for e in occupied if e.kind == "executed_trade"]
    assert reducer.active_setup_count == reducer.active_trade_count == 1

    closed = reducer.step(
        _step(
            _bar(
                7,
                10020,
                decision.target_ticks + 1,
                decision.entry_ticks,
                decision.target_ticks,
            )
        )
    )
    assert len([e for e in closed if e.kind == "executed_trade"]) == 1
    assert reducer.active_setup_count == reducer.active_trade_count == 0


def test_seeded_counterfactual_stream_preserves_single_slot_invariants() -> None:
    reducer, _, _, _, entry_emissions = _drive_to_entry(Direction.LONG)
    decision = next(
        emission.record
        for emission in entry_emissions
        if emission.kind == "eligible_decision"
    )
    rng = Random(20260114)
    observed_candidate_ids: set[str] = set()
    for index in range(6, 31):
        close = rng.randint(decision.stop_ticks + 2, decision.target_ticks - 2)
        low = rng.randint(decision.stop_ticks + 1, close)
        high = rng.randint(close, decision.target_ticks - 1)
        bar = _bar(index, close, high, low, close)
        fresh = _fvg(
            60,
            GapDirection.BULLISH,
            max(decision.stop_ticks + 1, close - 2),
            max(decision.stop_ticks + 2, close - 1),
            confirmed=bar.availability_ts_utc,
            ident=f"generated-{index}",
        )
        emissions = reducer.step(_step(bar, new_fvgs={60: (fresh,)}))
        assert reducer.active_setup_count <= 1
        assert reducer.active_trade_count <= 1
        assert not [e for e in emissions if e.kind == "eligible_decision"]
        assert not [e for e in emissions if e.kind == "executed_trade"]
        candidates = [
            e.record
            for e in emissions
            if e.kind == "entry_candidate"
            and e.record.trigger_evidence_id == fresh.fvg_id
        ]
        assert len(candidates) == 1
        assert candidates[0].direction is Direction.LONG
        assert candidates[0].risk_ticks > 0
        assert candidates[0].block_reasons == ("already_in_trade",)
        assert candidates[0].candidate_id not in observed_candidate_ids
        observed_candidate_ids.add(candidates[0].candidate_id)

    resolution_bar = _bar(
        31,
        decision.entry_ticks,
        decision.target_ticks + 1,
        decision.stop_ticks + 1,
        decision.target_ticks,
    )
    resolved = [
        e.record
        for e in reducer.step(_step(resolution_bar))
        if e.kind == "executed_trade"
    ]
    assert len(resolved) == 1
    assert resolved[0].entry_ts_utc < resolved[0].resolution_ts_utc
    assert resolved[0].bars_after_entry_to_resolution == 26


@pytest.mark.parametrize("direction", [Direction.LONG, Direction.SHORT])
def test_dual_family_collision_creates_one_decision_only(
    direction: Direction,
) -> None:
    reducer, _, _, _, emissions = _drive_to_entry(direction)
    candidates = [
        emission.record
        for emission in emissions
        if emission.kind == "entry_candidate"
    ]
    by_family = {candidate.entry_family: candidate for candidate in candidates}
    assert set(by_family) == {"fresh_fvg_continuation", "ifvg_retest"}
    assert by_family["fresh_fvg_continuation"].block_reasons == ()
    assert by_family["ifvg_retest"].block_reasons == (
        "entry_family_not_profile",
        "already_in_trade",
        "retest_trigger_unratified",
    )
    assert (
        by_family["fresh_fvg_continuation"].candidate_id
        != by_family["ifvg_retest"].candidate_id
    )
    assert len([e for e in emissions if e.kind == "eligible_decision"]) == 1
    assert reducer.active_setup_count == reducer.active_trade_count == 1


@pytest.mark.parametrize("direction", [Direction.LONG, Direction.SHORT])
def test_same_bar_stop_and_target_resolves_stop_first(
    direction: Direction,
) -> None:
    reducer, _, _, _, emissions = _drive_to_entry(direction)
    decision = next(
        emission.record
        for emission in emissions
        if emission.kind == "eligible_decision"
    )
    both = _bar(
        6,
        decision.entry_ticks,
        max(decision.stop_ticks, decision.target_ticks) + 1,
        min(decision.stop_ticks, decision.target_ticks) - 1,
        decision.entry_ticks,
    )
    resolved = [
        emission.record
        for emission in reducer.step(_step(both))
        if emission.kind == "executed_trade"
    ]
    assert len(resolved) == 1
    assert resolved[0].resolution == "stop"
    assert resolved[0].realized_r == -1.0


def test_day_roll_carries_trade_and_dataset_exhaustion_leaves_it_unresolved() -> None:
    reducer, _, _, _, emissions = _drive_to_entry(Direction.LONG)
    decision = next(
        emission.record
        for emission in emissions
        if emission.kind == "eligible_decision"
    )
    assert reducer.finalize_day(
        last_ts_utc=_bar(5, 10015, 10018, 10010, 10016).availability_ts_utc,
        trading_day=_DAY,
    ) == ()
    assert reducer.phase == "S5"

    exhausted = reducer.finalize_dataset(
        last_ts_utc=_bar(6, 10016, 10020, 10012, 10018).availability_ts_utc,
        trading_day=_DAY,
    )
    trade = next(
        emission.record
        for emission in exhausted
        if emission.kind == "executed_trade"
    )
    assert trade.trade_id
    assert trade.status == "open_unresolved"
    assert trade.resolution == "dataset_exhaustion"
    assert trade.resolution_cursor is None
    assert trade.bars_after_entry_to_resolution is None
    assert trade.realized_ticks is trade.realized_r is None
    assert trade.entry_ticks == decision.entry_ticks
    assert trade.envelope.entry_session == "ny"
    assert reducer.active_setup_count == reducer.active_trade_count == 0


def test_locked_parent_fill_invalidates_before_entry() -> None:
    reducer = _reducer(Direction.LONG)
    htf = _fvg(
        3600,
        GapDirection.BULLISH,
        10000,
        10020,
        confirmed=_T0 - timedelta(hours=2),
        ident="invalid-htf",
    )
    parent_bar = _bar(1, 10028, 10031, 10022, 10029)
    parent = _fvg(
        300,
        GapDirection.BULLISH,
        10010,
        10018,
        confirmed=parent_bar.availability_ts_utc,
        ident="invalid-parent",
    )
    reducer.step(
        _step(
            _bar(0, 10030, 10032, 10015, 10028),
            htf_live=(FvgState(fvg=htf),),
        )
    )
    reducer.step(_step(parent_bar, new_fvgs={300: (parent,)}))
    reducer.step(_step(_bar(2, 10024, 10026, 10016, 10022)))
    assert reducer.phase == "S2"
    fill = FvgFillEvent(
        fvg_id=parent.fvg_id,
        kind="filled",
        ts_utc=_bar(3, 10010, 10012, 10000, 10005).availability_ts_utc,
    )
    emissions = reducer.step(
        _step(
            _bar(3, 10010, 10012, 10000, 10005),
            fill_events=(fill,),
        )
    )
    resolution = next(
        emission.record
        for emission in emissions
        if emission.kind == "setup_resolution"
    )
    assert resolution.resolution == "invalidated_parent_filled"
    assert reducer.active_setup_count == 0


def test_higher_priority_parent_replaces_and_does_not_fallback_after_fill() -> None:
    reducer = _reducer(Direction.LONG)
    htf = _fvg(
        3600,
        GapDirection.BULLISH,
        10000,
        10020,
        confirmed=_T0 - timedelta(hours=2),
        ident="replace-htf",
    )
    old = _fvg(
        300,
        GapDirection.BULLISH,
        10010,
        10018,
        confirmed=_bar(1, 10030, 10032, 10025, 10029).availability_ts_utc,
        ident="old-5m",
    )
    newer = _fvg(
        900,
        GapDirection.BULLISH,
        10012,
        10019,
        confirmed=_bar(2, 10030, 10033, 10024, 10029).availability_ts_utc,
        ident="new-15m",
    )
    reducer.step(
        _step(
            _bar(0, 10030, 10032, 10015, 10028),
            htf_live=(FvgState(fvg=htf),),
        )
    )
    first = reducer.step(
        _step(
            _bar(1, 10030, 10032, 10025, 10029),
            new_fvgs={300: (old,)},
        )
    )
    assert next(e.record for e in first if e.kind == "parent_candidate").selected
    replaced = reducer.step(
        _step(
            _bar(2, 10030, 10033, 10024, 10029),
            new_fvgs={900: (newer,)},
        )
    )
    assert next(
        e.record for e in replaced if e.kind == "parent_candidate"
    ).selected
    fill = FvgFillEvent(
        fvg_id=newer.fvg_id,
        kind="filled",
        ts_utc=_bar(3, 10030, 10031, 10025, 10029).availability_ts_utc,
    )
    reducer.step(
        _step(
            _bar(3, 10030, 10031, 10025, 10029),
            fill_events=(fill,),
        )
    )
    attempted_old_retest = reducer.step(
        _step(_bar(4, 10024, 10026, 10015, 10022))
    )
    assert not [e for e in attempted_old_retest if e.kind == "parent_lock"]
    assert reducer.phase == "S1"


def test_htf_view_keeps_freshest_per_timeframe_and_4h_wins_same_tap() -> None:
    reducer = _reducer(Direction.LONG)
    old_1h = FvgState(
        fvg=_fvg(
            3600,
            GapDirection.BULLISH,
            10000,
            10020,
            confirmed=_T0 - timedelta(hours=4),
            ident="old-1h",
        )
    )
    fresh_1h = FvgState(
        fvg=_fvg(
            3600,
            GapDirection.BULLISH,
            10002,
            10022,
            confirmed=_T0 - timedelta(hours=2),
            ident="fresh-1h",
        )
    )
    four_hour = FvgState(
        fvg=_fvg(
            14400,
            GapDirection.BULLISH,
            10004,
            10024,
            confirmed=_T0 - timedelta(hours=3),
            ident="4h",
        )
    )
    emissions = reducer.step(
        _step(
            _bar(0, 10030, 10032, 10015, 10028),
            htf_live=(old_1h, fresh_1h, four_hour),
        )
    )
    taps = {
        emission.record.fvg.fvg_id: emission.record
        for emission in emissions
        if emission.kind == "htf_tap"
    }
    assert taps[old_1h.fvg.fvg_id].drop_reason == "retention_not_selected"
    assert taps[fresh_1h.fvg.fvg_id].drop_reason == "outranked"
    assert taps[four_hour.fvg.fvg_id].selected is True
    assert reducer.phase == "S1"


def test_out_of_session_candidate_waits_for_later_eligible_fresh_gap() -> None:
    reducer, _, _, _, emissions = _drive_to_entry(
        Direction.LONG,
        entry_session="none",
    )
    fresh = next(
        emission.record
        for emission in emissions
        if emission.kind == "entry_candidate"
        and emission.record.entry_family == "fresh_fvg_continuation"
    )
    assert "out_of_session" in fresh.block_reasons
    assert not [e for e in emissions if e.kind == "eligible_decision"]
    assert reducer.phase == "S4"

    later_bar = _bar(6, 10017, 10022, 10009, 10019)
    later = _fvg(
        60,
        GapDirection.BULLISH,
        10016,
        10017,
        confirmed=later_bar.availability_ts_utc,
        ident="in-session-entry",
    )
    eligible = reducer.step(
        _step(later_bar, new_fvgs={60: (later,)}, session_doc="ny")
    )
    assert len([e for e in eligible if e.kind == "eligible_decision"]) == 1
    assert reducer.phase == "S5"


@pytest.mark.parametrize("direction", [Direction.LONG, Direction.SHORT])
def test_unratified_retest_paths_are_one_shot_and_never_executable(
    direction: Direction,
) -> None:
    reducer, _, _, _, emissions = _drive_to_entry(
        direction,
        retest_only=True,
    )
    retests = [
        emission.record
        for emission in emissions
        if emission.kind == "entry_candidate"
        and emission.record.entry_family == "ifvg_retest"
    ]
    assert len(retests) == 1
    assert retests[0].block_reasons == (
        "profile_not_runnable",
        "execution_disabled",
        "retest_trigger_unratified",
    )
    assert not [e for e in emissions if e.kind == "eligible_decision"]
    assert reducer.phase == "S4"

    later = (
        _bar(6, 10013, 10015, 10009, 10011)
        if direction is Direction.LONG
        else _bar(6, 9997, 10004, 9995, 10000)
    )
    repeated = reducer.step(_step(later))
    assert not [
        e
        for e in repeated
        if e.kind == "entry_candidate"
        and e.record.entry_family == "ifvg_retest"
    ]


def test_wick_through_does_not_invert_and_old_opposing_inverts_before_replacement() -> None:
    reducer = _reducer(Direction.LONG)
    htf = _fvg(
        3600,
        GapDirection.BULLISH,
        10000,
        10020,
        confirmed=_T0 - timedelta(hours=2),
        ident="order-htf",
    )
    parent_bar = _bar(1, 10028, 10031, 10022, 10029)
    parent = _fvg(
        300,
        GapDirection.BULLISH,
        10010,
        10018,
        confirmed=parent_bar.availability_ts_utc,
        ident="order-parent",
    )
    old = _fvg(
        60,
        GapDirection.BEARISH,
        10008,
        10012,
        confirmed=_bar(3, 10020, 10021, 9992, 9995).availability_ts_utc,
        ident="old-opposing",
    )
    reducer.step(
        _step(
            _bar(0, 10030, 10032, 10015, 10028),
            htf_live=(FvgState(fvg=htf),),
        )
    )
    reducer.step(_step(parent_bar, new_fvgs={300: (parent,)}))
    reducer.step(_step(_bar(2, 10024, 10026, 10016, 10022)))
    reducer.step(
        _step(
            _bar(3, 10020, 10021, 9992, 9995),
            new_fvgs={60: (old,)},
        )
    )
    wick_only = reducer.step(_step(_bar(4, 10000, 10020, 9998, 10012)))
    assert not [e for e in wick_only if e.kind == "inversion"]
    assert reducer.phase == "S3"

    replacement_bar = _bar(5, 10010, 10018, 10000, 10014)
    replacement = _fvg(
        60,
        GapDirection.BEARISH,
        10011,
        10015,
        confirmed=replacement_bar.availability_ts_utc,
        ident="replacement-opposing",
    )
    emissions = reducer.step(
        _step(replacement_bar, new_fvgs={60: (replacement,)})
    )
    inversion = next(
        emission.record
        for emission in emissions
        if emission.kind == "inversion"
    )
    assert inversion.opposing_fvg_id == old.fvg_id
    assert not [e for e in emissions if e.kind == "opposing"]
    assert reducer.phase == "S4"
