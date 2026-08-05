"""IFVG FSM audit channel tests (``strategies/ifvg_smc``).

The audit channel is opt-in, per-step drained, and behavior-neutral: core
emissions are byte-identical with the channel on or off, and every audit
record carries the cross-channel ordering stamp. These tests pin the D-1/D-2
characterizations (documented as OPEN decisions — no behavior change), the
slot-death/window/causality evidence, the locked parentless-step semantics,
and the drain-boundary discipline.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from strategy_core.candles._ids import make_bar_id
from strategy_core.strategies.ifvg_smc.records import (
    AUDIT_SUBSTEP_CANDIDATE_INTAKE,
    AUDIT_SUBSTEP_FSM_TRANSITION,
    AUDIT_SUBSTEP_PRETRADE_INVALIDATION,
    AUDIT_SUBSTEP_RESOLUTION,
)
from strategy_core.strategies.ifvg_smc.reducer import (
    IfvgReducer,
    IfvgReducerConfig,
    IfvgStepInput,
)
from strategy_core.strategies.ifvg_smc.section import (
    IFVG_STRATEGY_VERSION,
    default_ifvg_smc_section,
)
from strategy_core.structures.fvg import Fvg, FvgFillEvent, FvgState, GapDirection
from strategy_core.types import Bar, BarKind, CloseReason, Level, Side

_DAY = date(2026, 1, 6)
_T0 = datetime(2026, 1, 5, 23, 0, tzinfo=UTC)
_TICK = 0.25


def _cfg() -> IfvgReducerConfig:
    return IfvgReducerConfig.from_section(
        default_ifvg_smc_section(),
        tick_size=_TICK,
        strategy_id="ifvg_smc",
        strategy_version=IFVG_STRATEGY_VERSION,
    )


def _audit_reducer() -> IfvgReducer:
    return IfvgReducer(_cfg(), audit_capture_mode="fsm_audit_v1")


def _bar(index: int, o: int, h: int, low: int, c: int, *, day: date = _DAY) -> Bar:
    open_ts = _T0 + timedelta(days=(day - _DAY).days, seconds=60 * index)
    return Bar(
        timeframe_ticks=60,
        trading_day=day,
        bar_index=index,
        bar_id=make_bar_id(60, day, index, BarKind.TIME),
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
        tf_bar_close_counts=kw.get("tf_bar_close_counts", {}),
    )


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


def _parent_fill_event(parent: Fvg, ts: datetime) -> FvgFillEvent:
    return FvgFillEvent(
        fvg_id=parent.fvg_id,
        kind="filled",
        ts_utc=ts,
        fvg=parent,
        prior_reached_ticks=10014,
        new_reached_ticks=10010,
        prior_penetration_ticks=4,
        new_penetration_ticks=8,
        remaining_fraction_after=0.0,
        wick_crossed_far_boundary=True,
        body_closed_through_far_boundary=False,
        age_seconds=300,
        age_trading_days=0,
        registry_live_count_after=0,
    )


def _drain_kinds(reducer: IfvgReducer):
    drained = reducer.drain_audit()
    return drained, [e.kind for e in drained]


def _full_pass_inputs() -> list[IfvgStepInput]:
    """The proven tap→parent→lock→arm→invert→enter→target walk."""
    htf = _htf_bullish()
    pdl = Level("pdl", 9990 * _TICK, Side.LOW, _T0 - timedelta(hours=1))
    bar1 = _bar(1, 10028, 10031, 10022, 10029)
    parent = _fvg(300, GapDirection.BULLISH, 10010, 10018, confirmed_ts=bar1.close_ts_utc, ident="p1")
    bar3 = _bar(3, 10020, 10021, 9988, 9995)
    opposing = _fvg(60, GapDirection.BEARISH, 10008, 10012, confirmed_ts=bar3.close_ts_utc, ident="o1")
    bar5 = _bar(5, 10015, 10018, 10010, 10016)
    entry_gap = _fvg(60, GapDirection.BULLISH, 10014, 10015, confirmed_ts=bar5.close_ts_utc, ident="e1")
    return [
        _step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,), levels=(pdl,)),
        _step(bar1, new_fvgs={300: (parent,)}, levels=(pdl,)),
        _step(_bar(2, 10024, 10026, 10016, 10022), levels=(pdl,)),
        _step(bar3, new_fvgs={60: (opposing,)}, levels=(pdl,)),
        _step(_bar(4, 10000, 10016, 9998, 10014), levels=(pdl,)),
        _step(bar5, new_fvgs={60: (entry_gap,)}, levels=(pdl,)),
        _step(_bar(6, 10020, 10050, 10015, 10046), levels=(pdl,)),
    ]


def test_audit_mode_validation() -> None:
    with pytest.raises(ValueError):
        IfvgReducer(_cfg(), audit_capture_mode="bogus")


def test_disabled_mode_emits_nothing() -> None:
    reducer = IfvgReducer(_cfg())
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(_htf_bullish(),)))
    assert reducer.drain_audit() == ()


def test_core_emissions_identical_with_audit_enabled() -> None:
    inputs = _full_pass_inputs()
    plain = IfvgReducer(_cfg())
    audited = _audit_reducer()
    for inp in inputs:
        a = plain.step(inp)
        b = audited.step(inp)
        audited.drain_audit()
        assert len(a) == len(b)
        for x, y in zip(a, b):
            assert x.kind == y.kind and x.record == y.record


def test_full_pass_audit_stream_and_ordering() -> None:
    audited = _audit_reducer()
    audit = []
    core = []
    for inp in _full_pass_inputs():
        core.extend(audited.step(inp))
        audit.extend(audited.drain_audit())
    kinds = [e.kind for e in audit]

    # channel separation: audit kinds never enter the core stream and vice versa.
    assert set(kinds).isdisjoint({e.kind for e in core})

    opened = [e.record for e in audit if e.kind == "parent_window_event" and e.record.event_kind == "opened"]
    assert len(opened) == 1
    assert opened[0].stamp.reducer_substep == AUDIT_SUBSTEP_FSM_TRANSITION
    assert opened[0].parent_fvg_id is None and opened[0].open_window_timeframes

    selected = [e.record for e in audit if e.kind == "parent_window_event" and e.record.event_kind == "parent_selected"]
    assert len(selected) == 1
    assert selected[0].stamp.reducer_substep == AUDIT_SUBSTEP_CANDIDATE_INTAKE
    assert selected[0].prior_parent_fvg_id is None
    assert selected[0].parent_fvg_id.startswith("300s:")

    causality = [e.record for e in audit if e.kind == "entry_joint_causality"]
    candidates = [e.record for e in core if e.kind == "entry_candidate"]
    assert causality and len(causality) == len(candidates)
    candidate_ids = {c.candidate_id for c in candidates}
    for record in causality:
        assert record.candidate_id in candidate_ids  # exact join
    fresh = [r for r in causality if r.entry_family == "fresh_fvg_continuation"]
    assert fresh and fresh[0].confirmed_after is True and fresh[0].satisfied is True
    assert fresh[0].entry_fvg_id is not None and fresh[0].trigger_ts_utc is not None

    deaths = [e.record for e in audit if e.kind == "parent_slot_death"]
    assert len(deaths) == 1
    death = deaths[0]
    assert death.death_reason == "slot_freed" and death.setup_terminated
    assert death.phase == "S5"
    assert death.stamp.reducer_substep == AUDIT_SUBSTEP_RESOLUTION
    assert death.lifecycle_event_id is not None

    # ordering contract: audit_seq monotone per day, no substep-key ties.
    seqs = [e.record.stamp.audit_seq for e in audit]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    keys = [
        (
            e.record.stamp.source_step_ordinal,
            e.record.stamp.reducer_substep,
            e.record.stamp.reducer_substep_ordinal,
        )
        for e in audit
    ]
    assert len(set(keys)) == len(keys)
    for e in audit:
        stamp = e.record.stamp
        assert stamp.core_trace_ordinal_after == stamp.core_trace_ordinal_before + 1
        assert stamp.source_bar_id and stamp.source_bar_cursor


def test_d1_same_tf_conflict_unreachable_at_cap_1() -> None:
    """D-1 characterization: with htf_selection_max_per_timeframe == 1 (the
    document profile), retention keeps one gap per TF, so the same-TF
    bull+bear conflict rule can never fire and ``taps_conflicted`` never
    increments. OPEN decision — no behavior change."""
    cfg = _cfg()
    assert cfg.htf_selection_max_per_timeframe == 1
    reducer = _audit_reducer()
    bull = FvgState(
        fvg=_fvg(3600, GapDirection.BULLISH, 10000, 10020, confirmed_ts=_T0 - timedelta(hours=2), ident="b")
    )
    bear = FvgState(
        fvg=_fvg(3600, GapDirection.BEARISH, 10025, 10040, confirmed_ts=_T0 - timedelta(hours=1), ident="s")
    )
    e = reducer.step(_step(_bar(0, 10030, 10035, 10015, 10028), htf_live=(bull, bear)))
    reducer.drain_audit()
    taps = [x.record for x in e if x.kind == "htf_tap"]
    assert len(taps) == 2
    assert not any(t.conflicted for t in taps)
    assert reducer.funnel_counters().get("taps_conflicted", 0) == 0
    # The retained (newer) gap is the bearish one; shorts are disabled in the
    # document profile, so it drops direction_disabled; the bull gap was never
    # in the retained view.
    by_id = {t.fvg.fvg_id: t for t in taps}
    assert by_id[bear.fvg.fvg_id].drop_reason == "direction_disabled"
    assert by_id[bull.fvg.fvg_id].drop_reason == "retention_not_selected"
    assert reducer.phase == "S0"


def test_d2_direction_disabled_winner_no_fallback() -> None:
    """D-2 characterization: a bearish top-TF winner with shorts disabled
    yields direction_disabled on the winner and outranked on the bullish
    lower-TF runner-up — no setup is born, no ranked fallback."""
    reducer = _audit_reducer()
    bear_4h = FvgState(
        fvg=_fvg(14400, GapDirection.BEARISH, 10025, 10040, confirmed_ts=_T0 - timedelta(hours=5), ident="b4")
    )
    bull_1h = FvgState(
        fvg=_fvg(3600, GapDirection.BULLISH, 10000, 10020, confirmed_ts=_T0 - timedelta(hours=2), ident="b1")
    )
    e = reducer.step(_step(_bar(0, 10030, 10035, 10015, 10028), htf_live=(bear_4h, bull_1h)))
    reducer.drain_audit()
    taps = {x.record.fvg.fvg_id: x.record for x in e if x.kind == "htf_tap"}
    assert taps[bear_4h.fvg.fvg_id].drop_reason == "direction_disabled"
    assert taps[bull_1h.fvg.fvg_id].drop_reason == "outranked"
    assert reducer.phase == "S0"
    assert reducer.funnel_counters().get("setups_born", 0) == 0


def _setup_with_parent(reducer: IfvgReducer):
    """Tap on bar 0, select a 5m parent on bar 1. Returns the parent gap."""
    htf = _htf_bullish()
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,)))
    reducer.drain_audit()
    bar1 = _bar(1, 10028, 10031, 10022, 10029)
    parent = _fvg(300, GapDirection.BULLISH, 10010, 10018, confirmed_ts=bar1.close_ts_utc, ident="p1")
    reducer.step(_step(bar1, new_fvgs={300: (parent,)}))
    reducer.drain_audit()
    return parent


def test_s1_parent_death_evidence_and_clock_math() -> None:
    reducer = _audit_reducer()
    parent = _setup_with_parent(reducer)

    # bar 2 ticks the 5m clock twice (no parent-death yet).
    reducer.step(_step(_bar(2, 10024, 10026, 10020, 10022), tf_bar_close_counts={300: 2}))
    reducer.drain_audit()

    # bar 3: the parent gap fills -> S1 provisional death, setup survives.
    bar3 = _bar(3, 10016, 10018, 10008, 10012)
    fill = _parent_fill_event(parent, bar3.close_ts_utc)
    reducer.audit_observe_fill_events((fill,), bar3)
    core = reducer.step(_step(bar3, fill_events=(fill,)))
    audit, kinds = _drain_kinds(reducer)

    assert "setup_resolution" not in [e.kind for e in core]  # setup survives
    assert kinds[0] == "fvg_fill_event"  # maintenance evidence first
    assert "fvg_invalidation_event" in kinds and "parent_slot_death" in kinds
    assert "parent_window_event" in kinds

    invalidation = [e.record for e in audit if e.kind == "fvg_invalidation_event"][0]
    assert invalidation.invalidation_kind == "physical_full_fill"
    assert invalidation.parent_fvg_id == parent.fvg_id
    assert invalidation.boundary_ticks == parent.far_boundary_ticks
    assert invalidation.stamp.reducer_substep == AUDIT_SUBSTEP_PRETRADE_INVALIDATION

    death = [e.record for e in audit if e.kind == "parent_slot_death"][0]
    assert not death.setup_terminated and death.phase == "S1"
    assert death.death_reason == "parent_filled"
    assert death.parent_fvg_id == parent.fvg_id == death.died_fvg_id
    assert death.physical_fill and not death.structural_close
    assert death.prior_reached_ticks == 10014 and death.new_reached_ticks == 10010
    assert death.fill_depth_ticks == 8
    # clock math: the 5m clock ticked twice on bar 2; window = 40 parent bars.
    clocks = dict(death.parent_clocks)
    assert clocks[300] == 2
    remaining = dict(death.remaining_window_bars_by_tf)
    assert remaining[300] == 38 and remaining[180] == 40
    assert set(death.open_window_timeframes) == set(clocks)
    assert death.parentless_interval_started

    cleared = [
        e.record
        for e in audit
        if e.kind == "parent_window_event" and e.record.event_kind == "parent_cleared"
    ][0]
    assert cleared.prior_parent_fvg_id == parent.fvg_id and cleared.parent_fvg_id is None

    fill_record = [e.record for e in audit if e.kind == "fvg_fill_event"][0]
    assert fill_record.fvg_role == "parent" and fill_record.selected_for_setup
    assert fill_record.setup_phase_before == "S1" and fill_record.setup_phase_after == "S1"
    assert fill_record.linked_slot_death_event_id == death.event_id
    assert fill_record.linked_setup_resolution_event_id == death.lifecycle_event_id


def test_terminal_parent_death_after_lock() -> None:
    reducer = _audit_reducer()
    parent = _setup_with_parent(reducer)
    # bar 2 locks the parent (wick retest).
    reducer.step(_step(_bar(2, 10024, 10026, 10016, 10022)))
    reducer.drain_audit()
    assert reducer.phase == "S2"
    # bar 3: parent fills while locked -> terminal death.
    bar3 = _bar(3, 10016, 10018, 10008, 10012)
    fill = _parent_fill_event(parent, bar3.close_ts_utc)
    reducer.audit_observe_fill_events((fill,), bar3)
    core = reducer.step(_step(bar3, fill_events=(fill,)))
    audit, kinds = _drain_kinds(reducer)
    assert "setup_resolution" in [e.kind for e in core]
    death = [e.record for e in audit if e.kind == "parent_slot_death"][0]
    assert death.setup_terminated and death.phase == "S2"
    assert death.death_reason == "invalidated_parent_filled"
    assert death.physical_fill and death.died_fvg_id == parent.fvg_id
    fill_record = [e.record for e in audit if e.kind == "fvg_fill_event"][0]
    assert fill_record.linked_slot_death_event_id == death.event_id
    assert fill_record.setup_phase_after == "S0"
    assert reducer.phase == "S0"


def test_parentless_step_semantics() -> None:
    """The locked parentless predicate, mirrored 1:1 with the funnel counter:
    counted on post-intake S1-parentless bars with an open window; NOT counted
    on the death step, the successor-selection step, the expiry step, or the
    HTF-fill step."""
    reducer = _audit_reducer()
    htf = _htf_bullish()

    # tap bar: S1, no parent, window open -> counted.
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,)))
    audit0, kinds0 = _drain_kinds(reducer)
    assert kinds0.count("parentless_step") == 1
    step0 = [e.record for e in audit0 if e.kind == "parentless_step"][0]
    assert set(step0.open_window_timeframes) == set(dict(step0.parent_clocks))

    # parent selected on this intake step -> bar does NOT count.
    bar1 = _bar(1, 10028, 10031, 10022, 10029)
    parent = _fvg(300, GapDirection.BULLISH, 10010, 10018, confirmed_ts=bar1.close_ts_utc, ident="p1")
    reducer.step(_step(bar1, new_fvgs={300: (parent,)}))
    _, kinds1 = _drain_kinds(reducer)
    assert kinds1.count("parentless_step") == 0

    # parent dies on bar 2: the POST-INTAKE state is already parentless again,
    # so the death step itself counts — exactly mirroring the funnel counter
    # (S1 provisional death does not early-return the step).
    bar2 = _bar(2, 10016, 10018, 10008, 10012)
    fill = _parent_fill_event(parent, bar2.close_ts_utc)
    reducer.audit_observe_fill_events((fill,), bar2)
    reducer.step(_step(bar2, fill_events=(fill,)))
    audit2, kinds2 = _drain_kinds(reducer)
    assert kinds2.count("parentless_step") == 1
    death2 = [e.record for e in audit2 if e.kind == "parent_slot_death"][0]
    assert death2.parentless_interval_started

    # the interval continues on the next plain bar.
    reducer.step(_step(_bar(3, 10024, 10026, 10020, 10022)))
    _, kinds3 = _drain_kinds(reducer)
    assert kinds3.count("parentless_step") == 1

    # counted steps reconcile exactly with the funnel counter so far.
    assert reducer.funnel_counters()["parentless_window_live"] == 3

    # all-windows-expired: the expiry step terminates and does not count.
    reducer.step(
        _step(
            _bar(4, 10024, 10026, 10020, 10022),
            tf_bar_close_counts={tf: 41 for tf in dict(step0.parent_clocks)},
        )
    )
    audit4, kinds4 = _drain_kinds(reducer)
    assert kinds4.count("parentless_step") == 0
    death = [e.record for e in audit4 if e.kind == "parent_slot_death"][0]
    assert death.death_reason == "expired_parent_search" and death.setup_terminated
    assert death.open_window_timeframes == ()
    assert reducer.phase == "S0"
    assert reducer.funnel_counters()["parentless_window_live"] == 3


def test_parentless_ends_on_htf_fill_and_survives_seed_resume() -> None:
    reducer = _audit_reducer()
    htf = _htf_bullish()
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,)))
    reducer.drain_audit()

    # mid-parentless snapshot/resume: the seed shape is frozen, so the audit
    # channel reconstructs from snapshotted state only; step records continue
    # under the same setup identity.
    snap = reducer.snapshot()
    resumed = IfvgReducer.from_snapshot(snap, _cfg(), audit_capture_mode="fsm_audit_v1")
    resumed.step(_step(_bar(1, 10028, 10031, 10022, 10029)))
    audit1, kinds1 = _drain_kinds(resumed)
    assert kinds1.count("parentless_step") == 1
    resumed_step = [e.record for e in audit1 if e.kind == "parentless_step"][0]
    assert resumed_step.setup_id == snap.setup.setup_id

    # HTF fill terminates: the death step does not count.
    bar2 = _bar(2, 10010, 10012, 9995, 9999)
    htf_fill = FvgFillEvent(
        fvg_id=htf.fvg.fvg_id,
        kind="filled",
        ts_utc=bar2.close_ts_utc,
        fvg=htf.fvg,
        prior_reached_ticks=None,
        new_reached_ticks=10000,
        prior_penetration_ticks=0,
        new_penetration_ticks=20,
        remaining_fraction_after=0.0,
        wick_crossed_far_boundary=True,
        body_closed_through_far_boundary=True,
        age_seconds=7200,
        age_trading_days=0,
        registry_live_count_after=0,
    )
    resumed.audit_observe_fill_events((htf_fill,), bar2)
    resumed.step(_step(bar2, fill_events=(htf_fill,)))
    audit2, kinds2 = _drain_kinds(resumed)
    assert kinds2.count("parentless_step") == 0
    death = [e.record for e in audit2 if e.kind == "parent_slot_death"][0]
    assert death.death_reason == "invalidated_htf_filled" and death.setup_terminated
    assert death.died_fvg_id == htf.fvg.fvg_id and death.parent_fvg_id is None
    fill_record = [e.record for e in audit2 if e.kind == "fvg_fill_event"][0]
    assert fill_record.fvg_role == "htf" and fill_record.selected_for_setup
    assert fill_record.linked_slot_death_event_id == death.event_id


def test_parentless_steps_cross_trading_day_boundary() -> None:
    """Consecutive counted steps span the 18:00 roll; the day-local audit_seq
    restarts but the setup identity and step stream continue, so QL derives
    ONE interval crossing the boundary."""
    reducer = _audit_reducer()
    htf = _htf_bullish()
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,)))
    audit0, _ = _drain_kinds(reducer)
    day0_seq = [e.record.stamp.audit_seq for e in audit0]
    next_day = _DAY + timedelta(days=1)
    reducer.step(_step(_bar(0, 10028, 10031, 10022, 10029, day=next_day)))
    audit1, kinds1 = _drain_kinds(reducer)
    assert kinds1.count("parentless_step") == 1
    step1 = [e.record for e in audit1 if e.kind == "parentless_step"][0]
    assert step1.envelope.trading_day == next_day
    assert step1.stamp.audit_seq == 0  # day-local counters reset at the roll
    assert day0_seq[0] == 0


def test_dataset_exhaustion_death_record() -> None:
    reducer = _audit_reducer()
    htf = _htf_bullish()
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(htf,)))
    reducer.drain_audit()
    out = reducer.finalize_dataset(last_ts_utc=_T0 + timedelta(minutes=5), trading_day=_DAY)
    assert [e.kind for e in out] == ["setup_lifecycle_event"]
    audit, kinds = _drain_kinds(reducer)
    assert kinds == ["parent_slot_death"]
    death = audit[0].record
    assert death.death_reason == "dataset_exhaustion_pre_entry"
    assert death.setup_terminated and death.bar is None
    assert death.event_cursor.startswith("dataset_exhaustion|")
    assert death.stamp.reducer_substep == AUDIT_SUBSTEP_RESOLUTION


def test_drain_discipline_enforced() -> None:
    """An undrained audit buffer at the next bar is a hard error — the buffer
    provably never spans a step boundary."""
    reducer = _audit_reducer()
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(_htf_bullish(),)))
    with pytest.raises(RuntimeError, match="not drained"):
        reducer.step(_step(_bar(1, 10028, 10031, 10022, 10029)))


def test_drain_is_idempotent_when_empty() -> None:
    reducer = _audit_reducer()
    reducer.step(_step(_bar(0, 10030, 10032, 10015, 10028), htf_live=(_htf_bullish(),)))
    assert reducer.drain_audit() != ()
    assert reducer.drain_audit() == ()
