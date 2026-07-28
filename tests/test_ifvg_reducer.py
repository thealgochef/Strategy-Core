"""IFVG reducer FSM tests (``strategies/ifvg_smc/reducer.py``).

Scripted step sequences pin every transition, the hard invariants (strict-after
usability, no entry on the inversion candle, MAE-first in-trade walk), the
dropped-candidate emissions, WIDE-bound expiries, and the mid-flight snapshot
round-trip. Inputs are hand-assembled ``IfvgStepInput``s — the orchestration
conventions (registry maintenance first, intake after transitions) are the
caller's contract and are exercised end-to-end by the replay-parity tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from strategy_core.candles._ids import make_bar_id
from strategy_core.strategies.ifvg_smc.reducer import (
    IfvgReducer,
    IfvgReducerConfig,
    IfvgStepInput,
)
from strategy_core.strategies.ifvg_smc.section import default_ifvg_smc_section
from strategy_core.structures.fvg import Fvg, FvgFillEvent, FvgState, GapDirection
from strategy_core.types import Bar, BarKind, CloseReason, Direction, Level, Side

_DAY = date(2026, 1, 6)
_T0 = datetime(2026, 1, 5, 23, 0, tzinfo=UTC)
_TICK = 0.25


def _cfg() -> IfvgReducerConfig:
    return IfvgReducerConfig.from_section(
        default_ifvg_smc_section(), tick_size=_TICK, strategy_id="ifvg_smc", strategy_version="1"
    )


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


def _fvg(
    tf: int,
    direction: GapDirection,
    lo: int,
    hi: int,
    *,
    confirmed_ts: datetime,
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
        a_open_ts_utc=confirmed_ts - timedelta(seconds=3 * tf),
        confirmed_ts_utc=confirmed_ts,
        trading_day=_DAY,
    )


def _step(bar: Bar, **kw) -> IfvgStepInput:
    return IfvgStepInput(
        bar_1m=bar,
        tf_bars_closed=kw.get("tf_bars_closed", {}),
        new_fvgs=kw.get("new_fvgs", {}),
        fill_events=kw.get("fill_events", ()),
        htf_live=kw.get("htf_live", ()),
        levels=kw.get("levels", ()),
        recent_swing_highs=kw.get("recent_swing_highs", ()),
        recent_swing_lows=kw.get("recent_swing_lows", ()),
        session_engine=kw.get("session_engine", "ny"),
        session_doc=kw.get("session_doc", "ny"),
    )


def _kinds(emissions) -> list[str]:
    return [e.kind for e in emissions]


def _htf_bullish() -> FvgState:
    gap = _fvg(
        3600,
        GapDirection.BULLISH,
        10000,
        10020,
        confirmed_ts=_T0 - timedelta(hours=2),
        ident="htf1",
    )
    return FvgState(fvg=gap)


def test_full_long_pass_tap_to_tp() -> None:
    reducer = IfvgReducer(_cfg())
    htf = _htf_bullish()
    pdl = Level("pdl", 9990 * _TICK, Side.LOW, _T0 - timedelta(hours=1))

    # bar 0: wick taps the HTF gap -> setup born (S1).
    e0 = reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,), levels=(pdl,)))
    assert _kinds(e0) == ["htf_tap"]
    tap = e0[0].record
    assert tap.selected and tap.direction is Direction.LONG and not tap.conflicted
    assert tap.envelope.setup_id == "ifvg:2026-01-06:0001"
    assert tap.nearest_level_kind == "pdl"
    assert reducer.phase == "S1"

    # bar 1: a same-direction 5m parent confirms near the HTF zone.
    bar1 = _bar(1, 10028, 10031, 10022, 10029)
    parent = _fvg(300, GapDirection.BULLISH, 10010, 10018, confirmed_ts=bar1.close_ts_utc, ident="p1")
    e1 = reducer.step(_step(bar1, new_fvgs={300: (parent,)}, levels=(pdl,)))
    assert _kinds(e1) == ["parent_candidate"]
    assert e1[0].record.selected and e1[0].record.confirmed_after

    # bar 2: 1m retest of the parent locks it (S2); sweep tracker arms.
    e2 = reducer.step(_step(_bar(2, 10024, 10026, 10016, 10022), levels=(pdl,)))
    assert _kinds(e2) == ["parent_lock"]
    assert reducer.phase == "S2"

    # bar 3: counter-direction 1m gap arms the manipulation slot (S3); the bar
    # also presses down through the pdl pool (9988 < 9990 -> raid).
    bar3 = _bar(3, 10020, 10021, 9988, 9995)
    opposing = _fvg(60, GapDirection.BEARISH, 10008, 10012, confirmed_ts=bar3.close_ts_utc, ident="o1")
    e3 = reducer.step(_step(bar3, new_fvgs={60: (opposing,)}, levels=(pdl,)))
    assert _kinds(e3) == ["opposing"]
    assert e3[0].record.selected
    assert reducer.phase == "S3"

    # bar 4: 1m BODY close back through the opposing gap's far boundary (S4).
    e4 = reducer.step(_step(_bar(4, 10000, 10016, 9998, 10014), levels=(pdl,)))
    assert _kinds(e4) == ["inversion"]
    inv = e4[0].record
    assert inv.close_through_margin_ticks == 2
    assert inv.sweep.sweep_confirmed and inv.sweep.swept_kinds == ("pdl",)
    assert reducer.phase == "S4"

    # bar 5: a fresh same-direction 1m gap confirms -> entry at ITS close.
    bar5 = _bar(5, 10015, 10018, 10010, 10016)
    entry_gap = _fvg(60, GapDirection.BULLISH, 10014, 10015, confirmed_ts=bar5.close_ts_utc, ident="e1")
    e5 = reducer.step(_step(bar5, new_fvgs={60: (entry_gap,)}, levels=(pdl,)))
    kinds5 = _kinds(e5)
    assert "entry_candidate" in kinds5
    selected5 = [e.record for e in e5 if e.kind == "entry_candidate" and e.record.selected]
    assert len(selected5) == 1
    entry = selected5[0]
    assert entry.entry_family == "fresh_fvg_continuation"
    # swing min low over lock..inversion bars = 9988; stop = 9988 - 1 buffer.
    assert entry.stop_ticks == 9987
    assert entry.entry_ticks == 10016 and entry.risk_ticks == 29 and entry.tp_ticks == 10045
    assert reducer.phase == "S5"

    # bar 6: runs to the target -> resolved_tp with the full stage chain.
    e6 = reducer.step(_step(_bar(6, 10020, 10050, 10015, 10046), levels=(pdl,)))
    assert _kinds(e6) == ["resolution"]
    res = e6[0].record
    assert res.resolution == "resolved_tp"
    assert res.htf_fvg_id == htf.fvg.fvg_id
    assert res.parent_fvg_id == parent.fvg_id and res.opposing_fvg_id == opposing.fvg_id
    assert res.entry_ts_utc == bar5.close_ts_utc
    assert res.mfe_ticks == 10050 - 10016 and res.mae_ticks == 10016 - 10015
    assert reducer.phase == "S0"

    funnel = reducer.funnel_counters()
    assert funnel["htf_taps"] == 1
    assert funnel["setups_born"] == 1
    assert funnel["parents_locked"] == 1
    assert funnel["opposing_armed"] == 1
    assert funnel["inversions"] == 1
    assert funnel["entries_selected"] == 1
    assert funnel["resolved_tp"] == 1


def test_no_entry_on_the_inversion_candle() -> None:
    """A same-direction gap confirming ON the inversion bar cannot enter (the
    entry watch requires inversion_ordinal < ordinal)."""
    reducer = IfvgReducer(_cfg())
    htf = _htf_bullish()
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,)))
    bar1 = _bar(1, 10028, 10031, 10022, 10029)
    parent = _fvg(300, GapDirection.BULLISH, 10010, 10018, confirmed_ts=bar1.close_ts_utc, ident="p1")
    reducer.step(_step(bar1, new_fvgs={300: (parent,)}))
    reducer.step(_step(_bar(2, 10024, 10026, 10016, 10022)))
    bar3 = _bar(3, 10020, 10021, 9992, 9995)
    opposing = _fvg(60, GapDirection.BEARISH, 10008, 10012, confirmed_ts=bar3.close_ts_utc, ident="o1")
    reducer.step(_step(bar3, new_fvgs={60: (opposing,)}))
    # bar 4 inverts AND completes a fresh bullish gap at the same close.
    bar4 = _bar(4, 10000, 10016, 9998, 10014)
    fresh = _fvg(60, GapDirection.BULLISH, 10012, 10013, confirmed_ts=bar4.close_ts_utc, ident="e1")
    e4 = reducer.step(_step(bar4, new_fvgs={60: (fresh,)}))
    assert _kinds(e4) == ["inversion"]
    assert reducer.phase == "S4"


def test_conflicted_taps_do_not_activate() -> None:
    reducer = IfvgReducer(_cfg())
    bull = FvgState(
        fvg=_fvg(3600, GapDirection.BULLISH, 10000, 10020, confirmed_ts=_T0 - timedelta(hours=2), ident="b")
    )
    bear = FvgState(
        fvg=_fvg(3600, GapDirection.BEARISH, 10025, 10040, confirmed_ts=_T0 - timedelta(hours=1), ident="s")
    )
    e = reducer.step(_step(_bar(0, 10030, 10035, 10015, 10028), htf_live=(bull, bear)))
    assert _kinds(e) == ["htf_tap", "htf_tap"]
    assert all(r.record.conflicted and not r.record.selected for r in e)
    assert all(r.record.drop_reason == "conflicted" for r in e)
    assert reducer.phase == "S0"
    assert reducer.funnel_counters()["taps_conflicted"] == 2


def test_tap_while_slot_occupied_is_recorded() -> None:
    reducer = IfvgReducer(_cfg())
    htf = _htf_bullish()
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,)))
    assert reducer.phase == "S1"
    e1 = reducer.step(_step(_bar(1, 10028, 10031, 10015, 10029), htf_live=(htf,)))
    taps = [e.record for e in e1 if e.kind == "htf_tap"]
    assert len(taps) == 1
    assert taps[0].drop_reason == "slot_occupied" and taps[0].envelope.setup_id == ""
    assert reducer.funnel_counters()["taps_slot_occupied"] == 1


def test_htf_fill_invalidates_pre_entry() -> None:
    reducer = IfvgReducer(_cfg())
    htf = _htf_bullish()
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,)))
    fill = FvgFillEvent(fvg_id=htf.fvg.fvg_id, kind="filled", ts_utc=_T0 + timedelta(minutes=2))
    e1 = reducer.step(_step(_bar(1, 10010, 10012, 9995, 9999), fill_events=(fill,)))
    assert _kinds(e1) == ["resolution"]
    assert e1[0].record.resolution == "invalidated_htf_filled"
    assert reducer.phase == "S0"


def test_parent_search_expires_at_wide_bound() -> None:
    section = default_ifvg_smc_section().model_copy(
        update={"parent_reaction_window_1m_bars_max": 3}
    )
    cfg = IfvgReducerConfig.from_section(
        section, tick_size=_TICK, strategy_id="ifvg_smc", strategy_version="1"
    )
    reducer = IfvgReducer(cfg)
    htf = _htf_bullish()
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,)))
    out: list = []
    for i in range(1, 6):
        out.extend(reducer.step(_step(_bar(i, 10030, 10031, 10029, 10030))))
    kinds = [e.kind for e in out]
    assert kinds == ["resolution"]
    assert out[0].record.resolution == "expired_parent_search"


def test_snapshot_roundtrip_mid_flight_matches_continuous() -> None:
    def drive(reducer: IfvgReducer, steps) -> list:
        collected = []
        for s in steps:
            collected.extend(reducer.step(s))
        return collected

    htf = _htf_bullish()
    pdl = Level("pdl", 9990 * _TICK, Side.LOW, _T0 - timedelta(hours=1))
    bar1 = _bar(1, 10028, 10031, 10022, 10029)
    parent = _fvg(300, GapDirection.BULLISH, 10010, 10018, confirmed_ts=bar1.close_ts_utc, ident="p1")
    bar3 = _bar(3, 10020, 10021, 9988, 9995)
    opposing = _fvg(60, GapDirection.BEARISH, 10008, 10012, confirmed_ts=bar3.close_ts_utc, ident="o1")
    bar5 = _bar(5, 10015, 10018, 10010, 10016)
    entry_gap = _fvg(60, GapDirection.BULLISH, 10014, 10015, confirmed_ts=bar5.close_ts_utc, ident="e1")

    prefix = [
        _step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,), levels=(pdl,)),
        _step(bar1, new_fvgs={300: (parent,)}, levels=(pdl,)),
        _step(_bar(2, 10024, 10026, 10016, 10022), levels=(pdl,)),
        _step(bar3, new_fvgs={60: (opposing,)}, levels=(pdl,)),
    ]
    suffix = [
        _step(_bar(4, 10000, 10016, 9998, 10014), levels=(pdl,)),
        _step(bar5, new_fvgs={60: (entry_gap,)}, levels=(pdl,)),
        _step(_bar(6, 10020, 10050, 10015, 10046), levels=(pdl,)),
    ]

    cont = IfvgReducer(_cfg())
    drive(cont, prefix)
    cont_rest = drive(cont, suffix)

    part = IfvgReducer(_cfg())
    drive(part, prefix)
    resumed = IfvgReducer.from_snapshot(part.snapshot(), _cfg())
    resumed_rest = drive(resumed, suffix)

    assert [e.kind for e in resumed_rest] == [e.kind for e in cont_rest]
    assert [type(e.record).__name__ for e in resumed_rest] == [
        type(e.record).__name__ for e in cont_rest
    ]
    cont_res = [e.record for e in cont_rest if e.kind == "resolution"][0]
    res_res = [e.record for e in resumed_rest if e.kind == "resolution"][0]
    assert cont_res == res_res
