"""Deterministic IFVG v2 one-setup/one-trade reducer."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Mapping

from strategy_core.structures.fvg import (
    Fvg,
    FvgFillEvent,
    FvgState,
    GapDirection,
    body_closes_through,
    ce_reached,
    close_through_margin_ticks,
    interval_distance_ticks,
    penetration_ticks,
    wick_overlaps,
)
from strategy_core.structures.sweeps import (
    LevelPool,
    SweepResult,
    SweepTracker,
    SweepTrackerSnapshot,
)
from strategy_core.structures.swings import SwingPoint
from strategy_core.types import Bar, Direction, Level, Side

from .records import (
    AUDIT_SUBSTEP_CANDIDATE_INTAKE,
    AUDIT_SUBSTEP_CONTEXT_FILL,
    AUDIT_SUBSTEP_FSM_TRANSITION,
    AUDIT_SUBSTEP_PARENTLESS,
    AUDIT_SUBSTEP_PRETRADE_INVALIDATION,
    AUDIT_SUBSTEP_RESOLUTION,
    IFVG_AUDIT_RECORD_SCHEMA_VERSION,
    IFVG_RECORD_SCHEMA_VERSION,
    AuditStamp,
    EligibleDecisionRecord,
    EntryCandidateRecord,
    EntryCausalityRecord,
    ExecutedTradeRecord,
    FvgFillEventRecord,
    FvgInvalidationEventRecord,
    GeometryDossierRecord,
    GeometryEvidence,
    HtfTapRecord,
    IfvgEmission,
    InversionRecord,
    OpposingGapRecord,
    ParentCandidateRecord,
    ParentLockRecord,
    ParentSlotDeathRecord,
    ParentWindowEventRecord,
    ParentlessStepRecord,
    QuarantineRecord,
    RecordEnvelope,
    SetupLifecycleEventRecord,
    SetupResolutionRecord,
    bar_cursor,
    bar_evidence,
    make_audit_event_id,
    make_candidate_id,
    make_decision_id,
    make_lifecycle_event_id,
    make_setup_id,
    make_trade_id,
)
from .section import (
    CausalityPolicy,
    IfvgSmcSection,
    OutsideSessionPolicy,
    RetestTrigger,
    ifvg_profile_hash,
)

__all__ = [
    "IfvgReducerConfig",
    "IfvgStepInput",
    "IfvgReducer",
    "IfvgReducerSnapshot",
    "IfvgSetupSnapshot",
    "REDUCER_SNAPSHOT_SCHEMA_VERSION",
]

REDUCER_SNAPSHOT_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class IfvgReducerConfig:
    strategy_id: str
    strategy_version: str
    profile_hash: str
    profile_name: str
    qualification_mode: str
    runnable: bool
    execution_enabled: bool
    tick_size: float
    htf_tf_seconds: tuple[int, ...]
    parent_tf_seconds: tuple[int, ...]
    enable_longs: bool
    enable_shorts: bool
    parent_reaction_window_parent_bars: int
    parent_reaction_window_1m_bars_max: int | None
    parent_retest_timeout_1m_bars: int | None
    opposing_timeout_1m_bars: int | None
    inversion_timeout_1m_bars: int | None
    post_inversion_expiry_1m_bars_max: int
    parent_htf_distance_ticks_max: int
    opposing_parent_distance_ticks_max: int
    entry_near_parent: bool
    entry_parent_distance_ticks_max: int | None
    htf_selection_max_per_timeframe: int
    sl_buffer_ticks: int
    tp_r_multiple: float
    entry_families: tuple[str, ...]
    entry_family: str
    retest_trigger: str
    label_family: str
    causality_parent: str
    causality_opposing: str
    causality_entry: str
    enabled_entry_sessions: tuple[str, ...]
    outside_session_policy: str
    anchor_policy: str
    resolver_policy: str
    parent_full_fill_invalidation: bool
    parent_structural_invalidation: bool
    max_executed_trades_per_day: int | None

    @classmethod
    def from_section(
        cls,
        section: IfvgSmcSection,
        *,
        tick_size: float,
        strategy_id: str,
        strategy_version: str,
    ) -> "IfvgReducerConfig":
        from strategy_core.constants import TIME_TF_SECONDS

        return cls(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            profile_hash=ifvg_profile_hash(section),
            profile_name=section.profile_name,
            qualification_mode=getattr(
                section.qualification_mode,
                "value",
                str(section.qualification_mode),
            ),
            runnable=section.runnable,
            execution_enabled=section.execution_enabled,
            tick_size=tick_size,
            htf_tf_seconds=tuple(
                sorted(
                    (TIME_TF_SECONDS[label] for label in section.htf_timeframes),
                    reverse=True,
                )
            ),
            parent_tf_seconds=tuple(
                sorted(
                    (TIME_TF_SECONDS[label] for label in section.parent_timeframes),
                    reverse=True,
                )
            ),
            enable_longs=section.enable_longs,
            enable_shorts=section.enable_shorts,
            parent_reaction_window_parent_bars=(
                section.parent_reaction_window_parent_bars
            ),
            parent_reaction_window_1m_bars_max=(
                section.parent_reaction_window_1m_bars_max
            ),
            parent_retest_timeout_1m_bars=section.parent_retest_timeout_1m_bars,
            opposing_timeout_1m_bars=section.opposing_timeout_1m_bars,
            inversion_timeout_1m_bars=section.inversion_timeout_1m_bars,
            post_inversion_expiry_1m_bars_max=(
                section.post_inversion_expiry_1m_bars_max
            ),
            parent_htf_distance_ticks_max=section.parent_htf_distance_ticks_max,
            opposing_parent_distance_ticks_max=(
                section.opposing_parent_distance_ticks_max
            ),
            entry_near_parent=section.entry_near_parent,
            entry_parent_distance_ticks_max=section.entry_parent_distance_ticks_max,
            htf_selection_max_per_timeframe=(
                section.htf_selection_max_per_timeframe
            ),
            sl_buffer_ticks=section.sl_buffer_ticks,
            tp_r_multiple=section.tp_r_multiple,
            entry_families=section.entry_families,
            entry_family=section.entry_family,
            retest_trigger=getattr(
                section.retest_trigger, "value", str(section.retest_trigger)
            ),
            label_family=section.label_family,
            causality_parent=getattr(
                section.causality_parent, "value", str(section.causality_parent)
            ),
            causality_opposing=getattr(
                section.causality_opposing,
                "value",
                str(section.causality_opposing),
            ),
            causality_entry=getattr(
                section.causality_entry, "value", str(section.causality_entry)
            ),
            enabled_entry_sessions=section.enabled_entry_sessions,
            outside_session_policy=getattr(
                section.outside_session_policy,
                "value",
                str(section.outside_session_policy),
            ),
            anchor_policy=section.anchor_policy,
            resolver_policy=getattr(
                section.resolver_policy, "value", str(section.resolver_policy)
            ),
            parent_full_fill_invalidation=section.parent_full_fill_invalidation,
            parent_structural_invalidation=section.parent_structural_invalidation,
            max_executed_trades_per_day=section.max_executed_trades_per_day,
        )

    @property
    def timeout_policy(self) -> str:
        return json.dumps(
            {
                "parent_retest_1m": self.parent_retest_timeout_1m_bars,
                "opposing_1m": self.opposing_timeout_1m_bars,
                "inversion_1m": self.inversion_timeout_1m_bars,
                "post_inversion_1m": self.post_inversion_expiry_1m_bars_max,
                "parent_reaction_own_tf": self.parent_reaction_window_parent_bars,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class IfvgStepInput:
    bar_1m: Bar
    tf_bars_closed: Mapping[int, Bar]
    new_fvgs: Mapping[int, tuple[Fvg, ...]]
    fill_events: tuple[FvgFillEvent, ...]
    htf_live: tuple[FvgState, ...]
    levels: tuple[Level, ...]
    recent_swing_highs: tuple[SwingPoint, ...]
    recent_swing_lows: tuple[SwingPoint, ...]
    session_engine: str
    session_doc: str
    tf_bar_close_counts: Mapping[int, int] = field(default_factory=dict)


@dataclass(slots=True)
class _Setup:
    setup_id: str
    phase: str
    direction: Direction
    htf: Fvg
    tap_ts_utc: datetime
    tap_ordinal: int
    tap_bar: Bar
    parent_clocks: dict[int, int]
    parent: Fvg | None = None
    parent_selected_ordinal: int | None = None
    lock_ts_utc: datetime | None = None
    lock_ordinal: int | None = None
    lock_bar: Bar | None = None
    swing_min_low: int | None = None
    swing_max_high: int | None = None
    sweep: SweepTracker | None = None
    opposing: Fvg | None = None
    armed_ts_utc: datetime | None = None
    armed_ordinal: int | None = None
    inversion_ts_utc: datetime | None = None
    inversion_ordinal: int | None = None
    inversion_bar: Bar | None = None
    sweep_result: SweepResult | None = None
    retest_latched: bool = False
    retest_touch_seen: bool = False
    entry_family: str | None = None
    candidate_id: str | None = None
    decision_id: str | None = None
    trade_id: str | None = None
    entry_ticks: int | None = None
    stop_ticks: int | None = None
    tp_ticks: int | None = None
    entry_ts_utc: datetime | None = None
    entry_session: str | None = None
    entry_ordinal: int | None = None
    entry_bar: Bar | None = None
    geometry: GeometryEvidence | None = None
    mfe_ticks: int = 0
    mae_ticks: int = 0


@dataclass(frozen=True, slots=True)
class IfvgSetupSnapshot:
    # V1 fields remain first so old snapshot construction fails only on schema,
    # not by shape, and migration tooling can inspect it.
    setup_id: str
    phase: str
    direction: Direction
    htf: Fvg
    tap_ts_utc: datetime
    tap_ordinal: int
    parent: Fvg | None
    parent_selected_ordinal: int | None
    lock_ts_utc: datetime | None
    lock_ordinal: int | None
    swing_min_low: int | None
    swing_max_high: int | None
    sweep: SweepTrackerSnapshot | None
    opposing: Fvg | None
    armed_ts_utc: datetime | None
    armed_ordinal: int | None
    inversion_ts_utc: datetime | None
    inversion_ordinal: int | None
    sweep_result: SweepResult | None
    entry_family: str | None
    entry_ticks: int | None
    stop_ticks: int | None
    tp_ticks: int | None
    entry_ts_utc: datetime | None
    entry_ordinal: int | None
    mfe_ticks: int
    mae_ticks: int
    tap_bar: Bar | None = None
    parent_clocks: tuple[tuple[int, int], ...] = ()
    lock_bar: Bar | None = None
    inversion_bar: Bar | None = None
    retest_latched: bool = False
    retest_touch_seen: bool = False
    candidate_id: str | None = None
    decision_id: str | None = None
    trade_id: str | None = None
    entry_bar: Bar | None = None
    geometry: GeometryEvidence | None = None
    entry_session: str | None = None


@dataclass(frozen=True, slots=True)
class IfvgReducerSnapshot:
    schema_version: int
    profile_hash: str
    ordinal: int
    seq_day: date | None
    seq: int
    setup: IfvgSetupSnapshot | None
    executions_by_day: tuple[tuple[date, int], ...] = ()


#: Valid values for the opt-in audit channel. NEVER a section/profile field —
#: the profile hash is untouched and ``disabled`` short-circuits all audit work.
AUDIT_CAPTURE_MODES = ("disabled", "fsm_audit_v1")


class IfvgReducer:
    def __init__(
        self,
        config: IfvgReducerConfig,
        *,
        audit_capture_mode: str = "disabled",
    ) -> None:
        if audit_capture_mode not in AUDIT_CAPTURE_MODES:
            raise ValueError(
                f"audit_capture_mode must be one of {AUDIT_CAPTURE_MODES} "
                f"(got {audit_capture_mode!r})"
            )
        self._cfg = config
        self._ordinal = 0
        self._setup: _Setup | None = None
        self._seq_day: date | None = None
        self._seq = 0
        self._funnel: dict[str, int] = {}
        self._executions_by_day: dict[date, int] = {}
        # ── audit channel state: NEVER snapshotted (seed identity is frozen).
        # Day-local counters reset on the first bar of a new trading day, so
        # chained (fresh reducer per day) and continuous drives stamp
        # identically. Buffers are drained after EVERY step — they never span
        # any externally observable boundary.
        self.audit_capture_mode = audit_capture_mode
        self._audit_enabled = audit_capture_mode == "fsm_audit_v1"
        self._audit_day: date | None = None
        self._audit_bar_id: str | None = None
        self._audit_seq_day = 0
        self._core_emitted_day = 0
        self._audit_step_base = 0
        self._last_step_core_len = 0
        self._audit_substep = AUDIT_SUBSTEP_FSM_TRANSITION
        self._audit_substep_counts: dict[str, int] = {}
        self._audit_step_records: list[IfvgEmission] = []
        self._audit_pending_fills_pre: list[tuple] = []
        self._audit_pending_fills_post: list[tuple] = []
        self._step_bar: Bar | None = None
        self._step_filled_events: dict[str, FvgFillEvent] = {}

    @property
    def phase(self) -> str:
        return self._setup.phase if self._setup is not None else "S0"

    @property
    def active_setup_count(self) -> int:
        return int(self._setup is not None)

    @property
    def active_trade_count(self) -> int:
        return int(self._setup is not None and self._setup.phase == "S5")

    def funnel_counters(self) -> dict[str, int]:
        return dict(self._funnel)

    def reset_funnel(self) -> None:
        self._funnel = {}

    # ------------------------------------------------------------------
    # FSM audit channel (opt-in; "disabled" short-circuits everything)

    def _audit_on_bar(self, bar: Bar) -> None:
        """Per-bar audit bookkeeping — idempotent per bar; resets the day-local
        counters on the first bar of a new trading day so chained and
        continuous drives stamp identically."""
        if self._audit_bar_id == bar.bar_id:
            return
        if (
            self._audit_step_records
            or self._audit_pending_fills_pre
            or self._audit_pending_fills_post
        ):
            raise RuntimeError("IFVG audit buffer was not drained before the next step")
        if self._audit_day != bar.trading_day:
            self._audit_day = bar.trading_day
            self._audit_seq_day = 0
            self._core_emitted_day = 0
        self._audit_bar_id = bar.bar_id
        self._audit_step_base = self._core_emitted_day
        self._audit_substep_counts = {}

    def _audit_stamp(
        self,
        *,
        substep: str,
        out_len: int,
        bar_id: str,
        cursor: str,
        step_ordinal: int,
        base: int | None = None,
    ) -> AuditStamp:
        ordinal = self._audit_substep_counts.get(substep, 0)
        self._audit_substep_counts[substep] = ordinal + 1
        core_base = self._audit_step_base if base is None else base
        return AuditStamp(
            audit_schema_version=IFVG_AUDIT_RECORD_SCHEMA_VERSION,
            source_step_ordinal=step_ordinal,
            source_bar_id=bar_id,
            source_bar_cursor=cursor,
            reducer_substep=substep,
            reducer_substep_ordinal=ordinal,
            core_trace_ordinal_before=core_base + out_len - 1,
            core_trace_ordinal_after=core_base + out_len,
            audit_seq=-1,  # assigned once, in final order, at drain
        )

    def _audit_emit(self, kind: str, record: object) -> None:
        self._audit_step_records.append(IfvgEmission(kind=kind, record=record))

    def _audit_fill_linkage(self, fvg_id: str) -> tuple[str | None, str, bool, str]:
        s = self._setup
        if s is None:
            return None, "registry_only", False, "S0"
        role = "registry_only"
        if s.htf.fvg_id == fvg_id:
            role = "htf"
        elif s.parent is not None and s.parent.fvg_id == fvg_id:
            role = "parent"
        elif s.opposing is not None and s.opposing.fvg_id == fvg_id:
            role = "opposing"
        elif (
            s.geometry is not None
            and s.geometry.entry_fvg is not None
            and s.geometry.entry_fvg.fvg_id == fvg_id
        ):
            role = "entry"
        if role == "registry_only":
            return None, role, False, s.phase
        return s.setup_id, role, True, s.phase

    def _audit_window_snapshot(
        self, s: _Setup
    ) -> tuple[
        tuple[tuple[int, int], ...],
        tuple[tuple[int, int], ...],
        tuple[int, ...],
    ]:
        window = self._cfg.parent_reaction_window_parent_bars
        clocks = tuple(sorted(s.parent_clocks.items()))
        remaining = tuple((tf, max(0, window - clock)) for tf, clock in clocks)
        open_tfs = tuple(tf for tf, clock in clocks if clock <= window)
        return clocks, remaining, open_tfs

    def audit_observe_fill_events(
        self, events: tuple[FvgFillEvent, ...], bar: Bar
    ) -> None:
        """Registry maintenance outcomes for this 1m bar, observed BEFORE the
        step so linkage reflects the entering setup state; records are
        finalized (phase_after, death links) at drain."""
        if not self._audit_enabled or not events:
            return
        self._audit_on_bar(bar)
        cursor = bar_cursor(bar)
        for event in events:
            stamp = self._audit_stamp(
                substep=AUDIT_SUBSTEP_CONTEXT_FILL,
                out_len=0,
                bar_id=bar.bar_id,
                cursor=cursor,
                step_ordinal=self._ordinal + 1,
            )
            setup_id, role, selected, phase = self._audit_fill_linkage(event.fvg_id)
            self._audit_pending_fills_pre.append(
                (stamp, event, bar, setup_id, role, selected, phase)
            )

    def audit_observe_intake_events(
        self, events: tuple[FvgFillEvent, ...], bar: Bar
    ) -> None:
        """Cap-eviction outcomes from the post-step registry intake."""
        if not self._audit_enabled or not events:
            return
        cursor = bar_cursor(bar)
        for event in events:
            stamp = self._audit_stamp(
                substep=AUDIT_SUBSTEP_CONTEXT_FILL,
                out_len=self._last_step_core_len,
                bar_id=bar.bar_id,
                cursor=cursor,
                step_ordinal=self._ordinal,
            )
            setup_id, role, selected, phase = self._audit_fill_linkage(event.fvg_id)
            self._audit_pending_fills_post.append(
                (stamp, event, bar, setup_id, role, selected, phase)
            )

    def _audit_fill_record(
        self, spec: tuple, phase_after: str, deaths: list
    ) -> IfvgEmission:
        stamp, event, bar, setup_id, role, selected, phase_before = spec
        if event.fvg is None:
            raise ValueError("audit fill event lacks gap evidence")
        death_id = None
        lifecycle_id = None
        for death in deaths:
            if death.died_fvg_id == event.fvg_id:
                death_id = death.event_id
                lifecycle_id = death.lifecycle_event_id
                break
        prior_pen = event.prior_penetration_ticks
        new_pen = event.new_penetration_ticks
        record = FvgFillEventRecord(
            envelope=self._env(bar, setup_id or ""),
            stamp=stamp,
            event_kind=event.kind,
            fvg=event.fvg,
            bar=bar_evidence(bar),
            prior_reached_ticks=event.prior_reached_ticks,
            new_reached_ticks=event.new_reached_ticks,
            prior_penetration_ticks=prior_pen if prior_pen is not None else 0,
            new_penetration_ticks=new_pen if new_pen is not None else 0,
            far_boundary_ticks=event.fvg.far_boundary_ticks,
            fill_depth_ticks=new_pen if new_pen is not None else 0,
            remaining_fraction_after=(
                event.remaining_fraction_after
                if event.remaining_fraction_after is not None
                else 1.0
            ),
            wick_crossed_far_boundary=event.wick_crossed_far_boundary,
            body_closed_through_far_boundary=event.body_closed_through_far_boundary,
            age_seconds=event.age_seconds if event.age_seconds is not None else 0,
            age_trading_days=(
                event.age_trading_days if event.age_trading_days is not None else 0
            ),
            registry_live_count_after=(
                event.registry_live_count_after
                if event.registry_live_count_after is not None
                else 0
            ),
            setup_id=setup_id,
            fvg_role=role,
            selected_for_setup=selected,
            setup_phase_before=phase_before,
            setup_phase_after=phase_after,
            linked_slot_death_event_id=death_id,
            linked_setup_resolution_event_id=lifecycle_id,
        )
        return IfvgEmission(kind="fvg_fill_event", record=record)

    def drain_audit(self) -> tuple[IfvgEmission, ...]:
        """This step's audit emissions in canonical order; clears the buffer.

        Called after EVERY step (and after ``finalize_dataset``), so the
        buffer never spans an externally observable boundary."""
        if not self._audit_enabled:
            return ()
        if not (
            self._audit_step_records
            or self._audit_pending_fills_pre
            or self._audit_pending_fills_post
        ):
            return ()
        phase_after = self.phase
        deaths = [
            emission.record
            for emission in self._audit_step_records
            if emission.kind == "parent_slot_death"
        ]
        ordered: list[IfvgEmission] = []
        for spec in self._audit_pending_fills_pre:
            ordered.append(self._audit_fill_record(spec, phase_after, deaths))
        ordered.extend(self._audit_step_records)
        for spec in self._audit_pending_fills_post:
            ordered.append(self._audit_fill_record(spec, phase_after, deaths))
        self._audit_step_records = []
        self._audit_pending_fills_pre = []
        self._audit_pending_fills_post = []
        stamped: list[IfvgEmission] = []
        for emission in ordered:
            seq = self._audit_seq_day
            self._audit_seq_day += 1
            record = emission.record
            stamped.append(
                IfvgEmission(
                    kind=emission.kind,
                    record=replace(
                        record, stamp=replace(record.stamp, audit_seq=seq)
                    ),
                )
            )
        return tuple(stamped)

    def _audit_slot_death(
        self,
        s: _Setup,
        *,
        reason: str,
        bar: Bar | None,
        cursor: str,
        ts_utc: datetime,
        trading_day: date,
        terminated: bool,
        lifecycle_transition: str,
        lifecycle_reason: str | None = None,
        died_fvg_id: str | None = None,
        structural: bool = False,
        out_len: int,
    ) -> None:
        clocks, remaining, open_tfs = self._audit_window_snapshot(s)
        fill = (
            self._step_filled_events.get(died_fvg_id)
            if died_fvg_id is not None and not structural
            else None
        )
        self._audit_emit(
            "parent_slot_death",
            ParentSlotDeathRecord(
                envelope=self._env_at(
                    ts_utc,
                    trading_day,
                    s.setup_id,
                    entry_session=s.entry_session or "none",
                ),
                stamp=self._audit_stamp(
                    substep=self._audit_substep,
                    out_len=out_len,
                    bar_id=bar.bar_id if bar is not None else "",
                    cursor=cursor,
                    step_ordinal=self._ordinal,
                    base=None if bar is not None else self._core_emitted_day,
                ),
                event_id=make_audit_event_id(
                    "parent_slot_death", s.setup_id, reason, cursor
                ),
                setup_id=s.setup_id,
                phase=s.phase,
                death_reason=reason,
                death_ts_utc=ts_utc,
                parent_fvg_id=s.parent.fvg_id if s.parent is not None else None,
                died_fvg_id=died_fvg_id,
                setup_terminated=terminated,
                lifecycle_event_id=make_lifecycle_event_id(
                    s.setup_id,
                    lifecycle_transition,
                    lifecycle_reason if lifecycle_reason is not None else reason,
                    cursor,
                ),
                bar=bar_evidence(bar) if bar is not None else None,
                event_cursor=cursor,
                physical_fill=fill is not None,
                structural_close=structural,
                far_boundary_ticks=(
                    fill.fvg.far_boundary_ticks
                    if fill is not None and fill.fvg is not None
                    else None
                ),
                prior_reached_ticks=(
                    fill.prior_reached_ticks if fill is not None else None
                ),
                new_reached_ticks=(
                    fill.new_reached_ticks if fill is not None else None
                ),
                fill_depth_ticks=(
                    fill.new_penetration_ticks if fill is not None else None
                ),
                wick_crossed_far_boundary=(
                    fill.wick_crossed_far_boundary if fill is not None else None
                ),
                body_closed_through_far_boundary=(
                    fill.body_closed_through_far_boundary
                    if fill is not None
                    else None
                ),
                parent_clocks=clocks,
                remaining_window_bars_by_tf=remaining,
                open_window_timeframes=open_tfs,
                parentless_interval_started=(
                    not terminated and s.phase == "S1" and bool(open_tfs)
                ),
            ),
        )

    def _audit_invalidation(
        self,
        s: _Setup,
        *,
        kind: str,
        source_bar: Bar,
        boundary_ticks: int,
        margin: int | None,
        bar: Bar,
        out_len: int,
    ) -> None:
        assert s.parent is not None
        self._audit_emit(
            "fvg_invalidation_event",
            FvgInvalidationEventRecord(
                envelope=self._env(bar, s.setup_id),
                stamp=self._audit_stamp(
                    substep=AUDIT_SUBSTEP_PRETRADE_INVALIDATION,
                    out_len=out_len,
                    bar_id=bar.bar_id,
                    cursor=bar_cursor(bar),
                    step_ordinal=self._ordinal,
                ),
                event_id=make_audit_event_id(
                    "fvg_invalidation",
                    s.setup_id,
                    kind,
                    s.parent.fvg_id,
                    bar_cursor(bar),
                ),
                invalidation_kind=kind,
                setup_id=s.setup_id,
                parent_fvg_id=s.parent.fvg_id,
                phase=s.phase,
                source_timeframe_seconds=source_bar.timeframe_ticks,
                source_bar=bar_evidence(source_bar),
                boundary_ticks=boundary_ticks,
                close_through_margin_ticks=margin,
                strict_comparison_result=True,
            ),
        )

    def _audit_parent_window_event(
        self,
        s: _Setup,
        *,
        event_kind: str,
        parent_fvg_id: str | None,
        prior_parent_fvg_id: str | None,
        bar: Bar,
        out_len: int,
    ) -> None:
        clocks, _remaining, open_tfs = self._audit_window_snapshot(s)
        cursor = bar_cursor(bar)
        self._audit_emit(
            "parent_window_event",
            ParentWindowEventRecord(
                envelope=self._env(bar, s.setup_id),
                stamp=self._audit_stamp(
                    substep=self._audit_substep,
                    out_len=out_len,
                    bar_id=bar.bar_id,
                    cursor=cursor,
                    step_ordinal=self._ordinal,
                ),
                event_id=make_audit_event_id(
                    "parent_window",
                    s.setup_id,
                    event_kind,
                    parent_fvg_id or prior_parent_fvg_id or "none",
                    cursor,
                ),
                event_kind=event_kind,
                setup_id=s.setup_id,
                parent_fvg_id=parent_fvg_id,
                prior_parent_fvg_id=prior_parent_fvg_id,
                parent_clocks=clocks,
                open_window_timeframes=open_tfs,
                event_cursor=cursor,
            ),
        )

    def step(self, inp: IfvgStepInput) -> tuple[IfvgEmission, ...]:
        out = self._step_inner(inp)
        if self._audit_enabled:
            self._core_emitted_day += len(out)
            self._last_step_core_len = len(out)
        return out

    def _step_inner(self, inp: IfvgStepInput) -> tuple[IfvgEmission, ...]:
        if self._audit_enabled:
            self._audit_on_bar(inp.bar_1m)
            self._step_bar = inp.bar_1m
            self._step_filled_events = {
                event.fvg_id: event
                for event in inp.fill_events
                if event.kind == "filled"
            }
        self._ordinal += 1
        out: list[IfvgEmission] = []
        self._tick_parent_clocks(inp)

        self._audit_substep = AUDIT_SUBSTEP_PRETRADE_INVALIDATION
        if self._apply_invalidations(inp, out):
            return tuple(out)
        if self._apply_expiries(inp.bar_1m, out):
            return tuple(out)

        started_in_trade = self._setup is not None and self._setup.phase == "S5"
        self._audit_substep = AUDIT_SUBSTEP_FSM_TRANSITION
        if self._setup is None:
            self._scan_taps(inp, out)
        else:
            if self._apply_transitions(inp, out):
                # Resolution is terminal for this reducer step. A newly free slot
                # cannot activate on the resolution bar.
                return tuple(out)

        if self._setup is not None:
            self._audit_substep = AUDIT_SUBSTEP_CANDIDATE_INTAKE
            self._apply_intake(inp, out)
            self._audit_substep = AUDIT_SUBSTEP_PARENTLESS
            self._instrument_parentless_window(out)
        if started_in_trade:
            assert self.active_setup_count <= 1 and self.active_trade_count <= 1
        return tuple(out)

    def finalize_day(
        self,
        *,
        last_ts_utc: datetime,
        trading_day: date,
    ) -> tuple[IfvgEmission, ...]:
        """Trading-day roll is not a trade exit in v2."""
        del last_ts_utc, trading_day
        return ()

    def finalize_dataset(
        self,
        *,
        last_ts_utc: datetime,
        trading_day: date,
    ) -> tuple[IfvgEmission, ...]:
        """Close the replay stream without fabricating realized P&L."""
        s = self._setup
        if s is None:
            return ()
        out: list[IfvgEmission] = []
        cursor = f"dataset_exhaustion|{last_ts_utc.isoformat()}"
        if s.phase == "S5":
            if s.geometry is None:
                raise ValueError("open executed trade is missing immutable geometry")
            assert all(
                value is not None
                for value in (
                    s.trade_id,
                    s.decision_id,
                    s.candidate_id,
                    s.entry_family,
                    s.entry_ts_utc,
                    s.entry_session,
                    s.entry_ticks,
                    s.stop_ticks,
                    s.tp_ticks,
                )
            )
            risk = abs(s.entry_ticks - s.stop_ticks)  # type: ignore[operator]
            out.append(
                IfvgEmission(
                    kind="executed_trade",
                    record=ExecutedTradeRecord(
                        envelope=self._env_at(
                            last_ts_utc,
                            trading_day,
                            s.setup_id,
                            entry_session=s.entry_session,  # type: ignore[arg-type]
                        ),
                        trade_id=s.trade_id,  # type: ignore[arg-type]
                        decision_id=s.decision_id,  # type: ignore[arg-type]
                        candidate_id=s.candidate_id,  # type: ignore[arg-type]
                        direction=s.direction,
                        status="open_unresolved",
                        resolution="dataset_exhaustion",
                        entry_family=s.entry_family,  # type: ignore[arg-type]
                        entry_cursor=bar_cursor(s.entry_bar),  # type: ignore[arg-type]
                        resolution_cursor=None,
                        entry_ts_utc=s.entry_ts_utc,  # type: ignore[arg-type]
                        resolution_ts_utc=None,
                        entry_ticks=s.entry_ticks,  # type: ignore[arg-type]
                        stop_ticks=s.stop_ticks,  # type: ignore[arg-type]
                        target_ticks=s.tp_ticks,  # type: ignore[arg-type]
                        risk_ticks=risk,
                        bars_after_entry_to_resolution=None,
                        mfe_ticks=s.mfe_ticks,
                        mae_ticks=s.mae_ticks,
                        realized_ticks=None,
                        realized_r=None,
                        geometry=s.geometry,
                    ),
                )
            )
            self._lifecycle_at(
                s,
                from_phase="S5",
                to_phase="S0",
                transition="trade_unresolved",
                reason="dataset_exhaustion",
                cursor=cursor,
                ts_utc=last_ts_utc,
                trading_day=trading_day,
                out=out,
            )
        else:
            self._lifecycle_at(
                s,
                from_phase=s.phase,
                to_phase="S0",
                transition="setup_ended",
                reason="dataset_exhaustion_pre_entry",
                cursor=cursor,
                ts_utc=last_ts_utc,
                trading_day=trading_day,
                out=out,
            )
        if self._audit_enabled:
            self._audit_substep = AUDIT_SUBSTEP_RESOLUTION
            self._audit_substep_counts = {}
            in_trade = s.phase == "S5"
            self._audit_slot_death(
                s,
                reason=(
                    "dataset_exhaustion" if in_trade else "dataset_exhaustion_pre_entry"
                ),
                bar=None,
                cursor=cursor,
                ts_utc=last_ts_utc,
                trading_day=trading_day,
                terminated=True,
                lifecycle_transition=(
                    "trade_unresolved" if in_trade else "setup_ended"
                ),
                out_len=len(out),
            )
            self._core_emitted_day += len(out)
        self._setup = None
        return tuple(out)

    def snapshot(self) -> IfvgReducerSnapshot:
        s = self._setup
        return IfvgReducerSnapshot(
            schema_version=REDUCER_SNAPSHOT_SCHEMA_VERSION,
            profile_hash=self._cfg.profile_hash,
            ordinal=self._ordinal,
            seq_day=self._seq_day,
            seq=self._seq,
            setup=(
                IfvgSetupSnapshot(
                    setup_id=s.setup_id,
                    phase=s.phase,
                    direction=s.direction,
                    htf=s.htf,
                    tap_ts_utc=s.tap_ts_utc,
                    tap_ordinal=s.tap_ordinal,
                    parent=s.parent,
                    parent_selected_ordinal=s.parent_selected_ordinal,
                    lock_ts_utc=s.lock_ts_utc,
                    lock_ordinal=s.lock_ordinal,
                    swing_min_low=s.swing_min_low,
                    swing_max_high=s.swing_max_high,
                    sweep=s.sweep.snapshot() if s.sweep is not None else None,
                    opposing=s.opposing,
                    armed_ts_utc=s.armed_ts_utc,
                    armed_ordinal=s.armed_ordinal,
                    inversion_ts_utc=s.inversion_ts_utc,
                    inversion_ordinal=s.inversion_ordinal,
                    sweep_result=s.sweep_result,
                    entry_family=s.entry_family,
                    entry_ticks=s.entry_ticks,
                    stop_ticks=s.stop_ticks,
                    tp_ticks=s.tp_ticks,
                    entry_ts_utc=s.entry_ts_utc,
                    entry_session=s.entry_session,
                    entry_ordinal=s.entry_ordinal,
                    mfe_ticks=s.mfe_ticks,
                    mae_ticks=s.mae_ticks,
                    tap_bar=s.tap_bar,
                    parent_clocks=tuple(sorted(s.parent_clocks.items())),
                    lock_bar=s.lock_bar,
                    inversion_bar=s.inversion_bar,
                    retest_latched=s.retest_latched,
                    retest_touch_seen=s.retest_touch_seen,
                    candidate_id=s.candidate_id,
                    decision_id=s.decision_id,
                    trade_id=s.trade_id,
                    entry_bar=s.entry_bar,
                    geometry=s.geometry,
                )
                if s is not None
                else None
            ),
            executions_by_day=tuple(sorted(self._executions_by_day.items())),
        )

    @classmethod
    def from_snapshot(
        cls,
        snap: IfvgReducerSnapshot,
        config: IfvgReducerConfig,
        *,
        audit_capture_mode: str = "disabled",
    ) -> "IfvgReducer":
        if snap.schema_version != REDUCER_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"IfvgReducerSnapshot schema {snap.schema_version} != "
                f"supported {REDUCER_SNAPSHOT_SCHEMA_VERSION}"
            )
        if snap.profile_hash != config.profile_hash:
            raise ValueError("reducer snapshot profile_hash does not match active profile")
        reducer = cls(config, audit_capture_mode=audit_capture_mode)
        reducer._ordinal = snap.ordinal
        reducer._seq_day = snap.seq_day
        reducer._seq = snap.seq
        reducer._executions_by_day = dict(snap.executions_by_day)
        if snap.setup is not None:
            ss = snap.setup
            if ss.tap_bar is None:
                raise ValueError("v2 reducer snapshot is missing tap_bar evidence")
            reducer._setup = _Setup(
                setup_id=ss.setup_id,
                phase=ss.phase,
                direction=ss.direction,
                htf=ss.htf,
                tap_ts_utc=ss.tap_ts_utc,
                tap_ordinal=ss.tap_ordinal,
                tap_bar=ss.tap_bar,
                parent_clocks=dict(ss.parent_clocks),
                parent=ss.parent,
                parent_selected_ordinal=ss.parent_selected_ordinal,
                lock_ts_utc=ss.lock_ts_utc,
                lock_ordinal=ss.lock_ordinal,
                lock_bar=ss.lock_bar,
                swing_min_low=ss.swing_min_low,
                swing_max_high=ss.swing_max_high,
                sweep=(
                    SweepTracker.from_snapshot(ss.sweep)
                    if ss.sweep is not None
                    else None
                ),
                opposing=ss.opposing,
                armed_ts_utc=ss.armed_ts_utc,
                armed_ordinal=ss.armed_ordinal,
                inversion_ts_utc=ss.inversion_ts_utc,
                inversion_ordinal=ss.inversion_ordinal,
                inversion_bar=ss.inversion_bar,
                sweep_result=ss.sweep_result,
                retest_latched=ss.retest_latched,
                retest_touch_seen=ss.retest_touch_seen,
                entry_family=ss.entry_family,
                candidate_id=ss.candidate_id,
                decision_id=ss.decision_id,
                trade_id=ss.trade_id,
                entry_ticks=ss.entry_ticks,
                stop_ticks=ss.stop_ticks,
                tp_ticks=ss.tp_ticks,
                entry_ts_utc=ss.entry_ts_utc,
                entry_session=ss.entry_session,
                entry_ordinal=ss.entry_ordinal,
                entry_bar=ss.entry_bar,
                geometry=ss.geometry,
                mfe_ticks=ss.mfe_ticks,
                mae_ticks=ss.mae_ticks,
            )
        return reducer

    # ------------------------------------------------------------------
    # Identity, envelopes, lifecycle

    def _count(self, key: str, n: int = 1) -> None:
        self._funnel[key] = self._funnel.get(key, 0) + n

    def _env(
        self,
        bar: Bar,
        setup_id: str,
        *,
        entry_session: str = "none",
    ) -> RecordEnvelope:
        return self._env_at(
            bar.availability_ts_utc,
            bar.trading_day,
            setup_id,
            entry_session=entry_session,
        )

    def _env_at(
        self,
        ts_utc: datetime,
        trading_day: date,
        setup_id: str,
        *,
        entry_session: str,
    ) -> RecordEnvelope:
        cfg = self._cfg
        return RecordEnvelope(
            schema_version=IFVG_RECORD_SCHEMA_VERSION,
            strategy_id=cfg.strategy_id,
            strategy_version=cfg.strategy_version,
            profile_hash=cfg.profile_hash,
            trading_day=trading_day,
            ts_utc=ts_utc,
            setup_id=setup_id,
            profile_name=cfg.profile_name,
            qualification_mode=cfg.qualification_mode,
            section_config_hash=cfg.profile_hash,
            entry_family=cfg.entry_family,
            label_family=cfg.label_family,
            entry_session=entry_session,
            anchor_policy=cfg.anchor_policy,
            resolver_policy=cfg.resolver_policy,
            causality_parent=cfg.causality_parent,
            causality_opposing=cfg.causality_opposing,
            causality_entry=cfg.causality_entry,
            timeout_policy=cfg.timeout_policy,
        )

    def _lifecycle(
        self,
        s: _Setup,
        *,
        from_phase: str,
        to_phase: str,
        transition: str,
        reason: str,
        bar: Bar,
        out: list[IfvgEmission],
    ) -> None:
        self._lifecycle_at(
            s,
            from_phase=from_phase,
            to_phase=to_phase,
            transition=transition,
            reason=reason,
            cursor=bar_cursor(bar),
            ts_utc=bar.availability_ts_utc,
            trading_day=bar.trading_day,
            out=out,
        )

    def _lifecycle_at(
        self,
        s: _Setup,
        *,
        from_phase: str,
        to_phase: str,
        transition: str,
        reason: str,
        cursor: str,
        ts_utc: datetime,
        trading_day: date,
        out: list[IfvgEmission],
    ) -> None:
        out.append(
            IfvgEmission(
                kind="setup_lifecycle_event",
                record=SetupLifecycleEventRecord(
                    envelope=self._env_at(
                        ts_utc,
                        trading_day,
                        s.setup_id,
                        entry_session=s.entry_session or "none",
                    ),
                    lifecycle_event_id=make_lifecycle_event_id(
                        s.setup_id, transition, reason, cursor
                    ),
                    from_phase=from_phase,
                    to_phase=to_phase,
                    transition=transition,
                    reason=reason,
                    event_cursor=cursor,
                    candidate_id=s.candidate_id,
                    decision_id=s.decision_id,
                    trade_id=s.trade_id,
                ),
            )
        )

    @staticmethod
    def _gap_direction_to_trade(direction: GapDirection) -> Direction:
        return Direction.LONG if direction is GapDirection.BULLISH else Direction.SHORT

    @staticmethod
    def _trade_direction_to_gap(direction: Direction) -> GapDirection:
        return (
            GapDirection.BULLISH
            if direction is Direction.LONG
            else GapDirection.BEARISH
        )

    def _direction_enabled(self, direction: Direction) -> bool:
        return (
            self._cfg.enable_longs
            if direction is Direction.LONG
            else self._cfg.enable_shorts
        )

    # ------------------------------------------------------------------
    # Invalidation and expiry

    def _tick_parent_clocks(self, inp: IfvgStepInput) -> None:
        s = self._setup
        if s is None or s.phase != "S1":
            return
        for tf in self._cfg.parent_tf_seconds:
            count = inp.tf_bar_close_counts.get(
                tf, 1 if tf in inp.tf_bars_closed else 0
            )
            if count:
                s.parent_clocks[tf] = s.parent_clocks.get(tf, 0) + count

    def _apply_invalidations(
        self,
        inp: IfvgStepInput,
        out: list[IfvgEmission],
    ) -> bool:
        s = self._setup
        if s is None or s.phase == "S5":
            return False
        bar = inp.bar_1m
        filled = {event.fvg_id for event in inp.fill_events if event.kind == "filled"}
        if s.htf.fvg_id in filled:
            self._terminate_pretrade(
                s,
                "invalidated_htf_filled",
                bar,
                out,
                died_fvg_id=s.htf.fvg_id,
            )
            return True
        if (
            self._cfg.parent_full_fill_invalidation
            and s.parent is not None
            and s.parent.fvg_id in filled
        ):
            if s.phase == "S1":
                dead_parent_id = s.parent.fvg_id
                self._count("candidate_died_filled")
                self._lifecycle(
                    s,
                    from_phase="S1",
                    to_phase="S1",
                    transition="parent_candidate_invalidated",
                    reason="parent_filled",
                    bar=bar,
                    out=out,
                )
                if self._audit_enabled:
                    self._audit_invalidation(
                        s,
                        kind="physical_full_fill",
                        source_bar=bar,
                        boundary_ticks=s.parent.far_boundary_ticks,
                        margin=None,
                        bar=bar,
                        out_len=len(out),
                    )
                    self._audit_slot_death(
                        s,
                        reason="parent_filled",
                        bar=bar,
                        cursor=bar_cursor(bar),
                        ts_utc=bar.availability_ts_utc,
                        trading_day=bar.trading_day,
                        terminated=False,
                        lifecycle_transition="parent_candidate_invalidated",
                        died_fvg_id=dead_parent_id,
                        out_len=len(out),
                    )
                s.parent = None
                s.parent_selected_ordinal = None
                if self._audit_enabled:
                    self._audit_parent_window_event(
                        s,
                        event_kind="parent_cleared",
                        parent_fvg_id=None,
                        prior_parent_fvg_id=dead_parent_id,
                        bar=bar,
                        out_len=len(out),
                    )
            else:
                if self._audit_enabled:
                    self._audit_invalidation(
                        s,
                        kind="physical_full_fill",
                        source_bar=bar,
                        boundary_ticks=s.parent.far_boundary_ticks,
                        margin=None,
                        bar=bar,
                        out_len=len(out),
                    )
                self._terminate_pretrade(
                    s,
                    "invalidated_parent_filled",
                    bar,
                    out,
                    died_fvg_id=s.parent.fvg_id,
                )
                return True
        if (
            self._cfg.parent_structural_invalidation
            and s.parent is not None
            and (tf_bar := inp.tf_bars_closed.get(s.parent.timeframe_seconds))
            is not None
        ):
            structural = (
                body_closes_through(
                    tf_bar,
                    boundary_ticks=s.parent.gap_low_ticks,
                    beyond=Side.LOW,
                )
                if s.parent.direction is GapDirection.BULLISH
                else body_closes_through(
                    tf_bar,
                    boundary_ticks=s.parent.gap_high_ticks,
                    beyond=Side.HIGH,
                )
            )
            if structural:
                boundary = (
                    s.parent.gap_low_ticks
                    if s.parent.direction is GapDirection.BULLISH
                    else s.parent.gap_high_ticks
                )
                side = (
                    Side.LOW
                    if s.parent.direction is GapDirection.BULLISH
                    else Side.HIGH
                )
                margin = close_through_margin_ticks(
                    tf_bar, boundary_ticks=boundary, beyond=side
                )
                if s.phase == "S1":
                    dead_parent_id = s.parent.fvg_id
                    self._count("candidate_died_structural")
                    self._lifecycle(
                        s,
                        from_phase="S1",
                        to_phase="S1",
                        transition="parent_candidate_invalidated",
                        reason="parent_structural_close",
                        bar=bar,
                        out=out,
                    )
                    if self._audit_enabled:
                        self._audit_invalidation(
                            s,
                            kind="structural_body_close",
                            source_bar=tf_bar,
                            boundary_ticks=boundary,
                            margin=margin,
                            bar=bar,
                            out_len=len(out),
                        )
                        self._audit_slot_death(
                            s,
                            reason="parent_structural_close",
                            bar=bar,
                            cursor=bar_cursor(bar),
                            ts_utc=bar.availability_ts_utc,
                            trading_day=bar.trading_day,
                            terminated=False,
                            lifecycle_transition="parent_candidate_invalidated",
                            died_fvg_id=dead_parent_id,
                            structural=True,
                            out_len=len(out),
                        )
                    s.parent = None
                    s.parent_selected_ordinal = None
                    if self._audit_enabled:
                        self._audit_parent_window_event(
                            s,
                            event_kind="parent_cleared",
                            parent_fvg_id=None,
                            prior_parent_fvg_id=dead_parent_id,
                            bar=bar,
                            out_len=len(out),
                        )
                else:
                    if self._audit_enabled:
                        self._audit_invalidation(
                            s,
                            kind="structural_body_close",
                            source_bar=tf_bar,
                            boundary_ticks=boundary,
                            margin=margin,
                            bar=bar,
                            out_len=len(out),
                        )
                    self._terminate_pretrade(
                        s,
                        "invalidated_parent_structural",
                        bar,
                        out,
                        died_fvg_id=s.parent.fvg_id,
                        structural=True,
                    )
                    return True
        return False

    def _apply_expiries(
        self,
        bar: Bar,
        out: list[IfvgEmission],
    ) -> bool:
        s = self._setup
        if s is None or s.phase == "S5":
            return False
        cfg = self._cfg
        if s.phase == "S1":
            if (
                s.parent is not None
                and cfg.parent_retest_timeout_1m_bars is not None
                and s.parent_selected_ordinal is not None
                and self._ordinal - s.parent_selected_ordinal
                > cfg.parent_retest_timeout_1m_bars
            ):
                self._terminate_pretrade(s, "expired_parent_retest", bar, out)
                return True
            if s.parent is None:
                if (
                    cfg.parent_reaction_window_1m_bars_max is not None
                    and self._ordinal - s.tap_ordinal
                    > cfg.parent_reaction_window_1m_bars_max
                ):
                    self._terminate_pretrade(s, "expired_parent_search", bar, out)
                    return True
                if all(
                    s.parent_clocks.get(tf, 0)
                    > cfg.parent_reaction_window_parent_bars
                    for tf in cfg.parent_tf_seconds
                ):
                    self._terminate_pretrade(s, "expired_parent_search", bar, out)
                    return True
        elif (
            s.phase == "S2"
            and cfg.opposing_timeout_1m_bars is not None
            and s.lock_ordinal is not None
            and self._ordinal - s.lock_ordinal > cfg.opposing_timeout_1m_bars
        ):
            self._terminate_pretrade(s, "expired_opposing_wait", bar, out)
            return True
        elif (
            s.phase == "S3"
            and cfg.inversion_timeout_1m_bars is not None
            and s.armed_ordinal is not None
            and self._ordinal - s.armed_ordinal > cfg.inversion_timeout_1m_bars
        ):
            self._terminate_pretrade(s, "expired_inversion_wait", bar, out)
            return True
        elif (
            s.phase == "S4"
            and s.inversion_ordinal is not None
            and self._ordinal - s.inversion_ordinal
            > cfg.post_inversion_expiry_1m_bars_max
        ):
            self._terminate_pretrade(s, "expired_entry_wait", bar, out)
            return True
        return False

    def _instrument_parentless_window(self, out: list[IfvgEmission]) -> None:
        s = self._setup
        if (
            s is not None
            and s.phase == "S1"
            and s.parent is None
            and any(
                s.parent_clocks.get(tf, 0)
                <= self._cfg.parent_reaction_window_parent_bars
                for tf in self._cfg.parent_tf_seconds
            )
        ):
            self._count("parentless_window_live")
            if self._audit_enabled and self._step_bar is not None:
                bar = self._step_bar
                clocks, _remaining, open_tfs = self._audit_window_snapshot(s)
                self._audit_emit(
                    "parentless_step",
                    ParentlessStepRecord(
                        envelope=self._env(bar, s.setup_id),
                        stamp=self._audit_stamp(
                            substep=AUDIT_SUBSTEP_PARENTLESS,
                            out_len=len(out),
                            bar_id=bar.bar_id,
                            cursor=bar_cursor(bar),
                            step_ordinal=self._ordinal,
                        ),
                        setup_id=s.setup_id,
                        bar=bar_evidence(bar),
                        parent_clocks=clocks,
                        open_window_timeframes=open_tfs,
                    ),
                )

    def _terminate_pretrade(
        self,
        s: _Setup,
        reason: str,
        bar: Bar,
        out: list[IfvgEmission],
        *,
        died_fvg_id: str | None = None,
        structural: bool = False,
    ) -> None:
        self._count(reason)
        self._lifecycle(
            s,
            from_phase=s.phase,
            to_phase="S0",
            transition="setup_ended",
            reason=reason,
            bar=bar,
            out=out,
        )
        out.append(
            IfvgEmission(
                kind="setup_resolution",
                record=self._compat_resolution(s, reason, bar),
            )
        )
        if self._audit_enabled:
            self._audit_slot_death(
                s,
                reason=reason,
                bar=bar,
                cursor=bar_cursor(bar),
                ts_utc=bar.availability_ts_utc,
                trading_day=bar.trading_day,
                terminated=True,
                lifecycle_transition="setup_ended",
                died_fvg_id=died_fvg_id,
                structural=structural,
                out_len=len(out),
            )
        self._setup = None

    # ------------------------------------------------------------------
    # Price transitions

    def _apply_transitions(
        self,
        inp: IfvgStepInput,
        out: list[IfvgEmission],
    ) -> bool:
        s = self._setup
        if s is None:
            return False
        bar = inp.bar_1m
        if s.phase in ("S2", "S3", "S4") and s.lock_ordinal is not None:
            s.swing_min_low = (
                bar.low_ticks
                if s.swing_min_low is None
                else min(s.swing_min_low, bar.low_ticks)
            )
            s.swing_max_high = (
                bar.high_ticks
                if s.swing_max_high is None
                else max(s.swing_max_high, bar.high_ticks)
            )
            if s.sweep is not None:
                s.sweep.on_bar(bar)
        if s.phase == "S1":
            self._try_lock(inp, s, out)
        elif s.phase == "S3":
            self._try_inversion(inp, s, out)
        elif s.phase == "S4":
            self._watch_entries(inp, s, out)
        elif s.phase == "S5":
            resolved = self._walk_trade(inp, s, out)
            if not resolved:
                # Keep the counterfactual trigger stream complete while the
                # sole execution slot is occupied. These rows are explicitly
                # blocked and can never create another decision or trade.
                self._watch_entries(inp, s, out)
            return resolved
        return False

    def _scan_taps(
        self,
        inp: IfvgStepInput,
        out: list[IfvgEmission],
    ) -> None:
        bar = inp.bar_1m
        selected_view_ids: set[str] = set()
        for tf in self._cfg.htf_tf_seconds:
            states = sorted(
                (state for state in inp.htf_live if state.fvg.timeframe_seconds == tf),
                key=lambda state: (
                    state.fvg.confirmed_ts_utc,
                    state.fvg.fvg_id,
                ),
                reverse=True,
            )
            selected_view_ids.update(
                state.fvg.fvg_id
                for state in states[: self._cfg.htf_selection_max_per_timeframe]
            )
        taps = [
            state
            for state in inp.htf_live
            if state.fvg.confirmed_ts_utc < bar.availability_ts_utc
            and wick_overlaps(
                bar, state.fvg.gap_low_ticks, state.fvg.gap_high_ticks
            )
        ]
        if not taps:
            return
        taps.sort(
            key=lambda state: (
                state.fvg.timeframe_seconds,
                state.fvg.confirmed_ts_utc,
                state.fvg.fvg_id,
            ),
            reverse=True,
        )
        eligible_view = [
            state for state in taps if state.fvg.fvg_id in selected_view_ids
        ]
        top_tf = eligible_view[0].fvg.timeframe_seconds if eligible_view else None
        top_dirs = {
            state.fvg.direction
            for state in eligible_view
            if state.fvg.timeframe_seconds == top_tf
        }
        conflicted = len(top_dirs) > 1
        winner = None if conflicted or not eligible_view else eligible_view[0]
        nearest_kind, nearest_dist = self._nearest_level(inp, bar)
        for rank, state in enumerate(taps):
            gap = state.fvg
            direction = self._gap_direction_to_trade(gap.direction)
            selected = winner is state and self._direction_enabled(direction)
            if gap.fvg_id not in selected_view_ids:
                drop = "retention_not_selected"
            elif conflicted:
                drop = "conflicted"
            elif winner is not state:
                drop = "outranked"
            elif not self._direction_enabled(direction):
                drop = "direction_disabled"
            else:
                drop = None
            setup_id = (
                make_setup_id(self._cfg.profile_hash, gap.fvg_id, bar_cursor(bar))
                if selected
                else ""
            )
            self._count("htf_taps")
            if conflicted:
                self._count("taps_conflicted")
            out.append(
                IfvgEmission(
                    kind="htf_tap",
                    record=HtfTapRecord(
                        envelope=self._env(bar, setup_id),
                        htf_tf_seconds=gap.timeframe_seconds,
                        fvg=gap,
                        direction=direction,
                        penetration_ticks=penetration_ticks(bar, gap),
                        ce_reached=ce_reached(bar, gap),
                        htf_age_seconds=int(
                            (
                                bar.availability_ts_utc - gap.confirmed_ts_utc
                            ).total_seconds()
                        ),
                        remaining_fraction=state.remaining_fraction(),
                        registry_live_count=len(inp.htf_live),
                        rank=rank,
                        conflicted=conflicted,
                        nearest_level_kind=nearest_kind,
                        nearest_level_distance_ticks=nearest_dist,
                        session_engine=inp.session_engine,
                        session_doc=inp.session_doc,
                        selected=selected,
                        drop_reason=drop,
                        tap_cursor=bar_cursor(bar),
                    ),
                )
            )
            if selected:
                setup = _Setup(
                    setup_id=setup_id,
                    phase="S1",
                    direction=direction,
                    htf=gap,
                    tap_ts_utc=bar.availability_ts_utc,
                    tap_ordinal=self._ordinal,
                    tap_bar=bar,
                    parent_clocks={tf: 0 for tf in self._cfg.parent_tf_seconds},
                )
                self._setup = setup
                self._count("setups_born")
                self._lifecycle(
                    setup,
                    from_phase="S0",
                    to_phase="S1",
                    transition="setup_activated",
                    reason="htf_tap_selected",
                    bar=bar,
                    out=out,
                )
                if self._audit_enabled:
                    self._audit_parent_window_event(
                        setup,
                        event_kind="opened",
                        parent_fvg_id=None,
                        prior_parent_fvg_id=None,
                        bar=bar,
                        out_len=len(out),
                    )

    def _tap_scan_while_occupied(
        self,
        inp: IfvgStepInput,
        out: list[IfvgEmission],
    ) -> None:
        bar = inp.bar_1m
        nearest_kind, nearest_dist = self._nearest_level(inp, bar)
        for state in inp.htf_live:
            gap = state.fvg
            if gap.confirmed_ts_utc >= bar.availability_ts_utc or not wick_overlaps(
                bar, gap.gap_low_ticks, gap.gap_high_ticks
            ):
                continue
            self._count("htf_taps")
            self._count("taps_slot_occupied")
            out.append(
                IfvgEmission(
                    kind="htf_tap",
                    record=HtfTapRecord(
                        envelope=self._env(bar, ""),
                        htf_tf_seconds=gap.timeframe_seconds,
                        fvg=gap,
                        direction=self._gap_direction_to_trade(gap.direction),
                        penetration_ticks=penetration_ticks(bar, gap),
                        ce_reached=ce_reached(bar, gap),
                        htf_age_seconds=int(
                            (
                                bar.availability_ts_utc - gap.confirmed_ts_utc
                            ).total_seconds()
                        ),
                        remaining_fraction=state.remaining_fraction(),
                        registry_live_count=len(inp.htf_live),
                        rank=-1,
                        conflicted=False,
                        nearest_level_kind=nearest_kind,
                        nearest_level_distance_ticks=nearest_dist,
                        session_engine=inp.session_engine,
                        session_doc=inp.session_doc,
                        selected=False,
                        drop_reason="slot_occupied",
                        tap_cursor=bar_cursor(bar),
                    ),
                )
            )

    def _try_lock(
        self,
        inp: IfvgStepInput,
        s: _Setup,
        out: list[IfvgEmission],
    ) -> None:
        bar = inp.bar_1m
        if (
            s.parent is None
            or s.parent_selected_ordinal is None
            or s.parent_selected_ordinal >= self._ordinal
            or not wick_overlaps(
                bar, s.parent.gap_low_ticks, s.parent.gap_high_ticks
            )
        ):
            return
        s.phase = "S2"
        s.lock_ts_utc = bar.availability_ts_utc
        s.lock_ordinal = self._ordinal
        s.lock_bar = bar
        s.swing_min_low = bar.low_ticks
        s.swing_max_high = bar.high_ticks
        s.sweep = SweepTracker(
            direction=s.direction,
            pools=self._build_pools(inp),
            armed_ts=bar.availability_ts_utc,
        )
        s.sweep.on_bar(bar)
        self._count("parents_locked")
        self._lifecycle(
            s,
            from_phase="S1",
            to_phase="S2",
            transition="parent_locked",
            reason="parent_wick_retest",
            bar=bar,
            out=out,
        )
        out.append(
            IfvgEmission(
                kind="parent_lock",
                record=ParentLockRecord(
                    envelope=self._env(bar, s.setup_id),
                    parent_fvg_id=s.parent.fvg_id,
                    penetration_ticks=penetration_ticks(bar, s.parent),
                    ce_reached=ce_reached(bar, s.parent),
                    elapsed_1m_bars_since_selection=(
                        self._ordinal - s.parent_selected_ordinal
                    ),
                    lock_cursor=bar_cursor(bar),
                ),
            )
        )

    def _try_inversion(
        self,
        inp: IfvgStepInput,
        s: _Setup,
        out: list[IfvgEmission],
    ) -> None:
        bar = inp.bar_1m
        if (
            s.opposing is None
            or s.armed_ordinal is None
            or s.armed_ordinal >= self._ordinal
        ):
            return
        if s.direction is Direction.LONG:
            boundary = s.opposing.gap_high_ticks
            side = Side.HIGH
        else:
            boundary = s.opposing.gap_low_ticks
            side = Side.LOW
        if not body_closes_through(bar, boundary_ticks=boundary, beyond=side):
            return
        s.phase = "S4"
        s.inversion_ts_utc = bar.availability_ts_utc
        s.inversion_ordinal = self._ordinal
        s.inversion_bar = bar
        s.sweep_result = s.sweep.result() if s.sweep is not None else None
        semantic = (
            "manipulation_failed"
            if s.sweep_result is not None and s.sweep_result.sweep_confirmed
            else "counter_displacement_failed"
        )
        self._count("inversions")
        self._count(f"inverted_{semantic}")
        self._lifecycle(
            s,
            from_phase="S3",
            to_phase="S4",
            transition="opposing_inverted",
            reason=semantic,
            bar=bar,
            out=out,
        )
        out.append(
            IfvgEmission(
                kind="inversion",
                record=InversionRecord(
                    envelope=self._env(bar, s.setup_id),
                    opposing_fvg_id=s.opposing.fvg_id,
                    close_through_margin_ticks=close_through_margin_ticks(
                        bar, boundary_ticks=boundary, beyond=side
                    ),
                    bars_armed_to_inversion=self._ordinal - s.armed_ordinal,
                    opposing_size_ticks=s.opposing.size_ticks,
                    sweep=(
                        s.sweep_result
                        if s.sweep_result is not None
                        else SweepResult(False, (), 0, None, None, None)
                    ),
                    semantic=semantic,
                    inversion_cursor=bar_cursor(bar),
                ),
            )
        )

    # ------------------------------------------------------------------
    # Candidate -> decision -> modeled fill

    def _watch_entries(
        self,
        inp: IfvgStepInput,
        s: _Setup,
        out: list[IfvgEmission],
    ) -> None:
        bar = inp.bar_1m
        if s.inversion_ordinal is None or s.inversion_ordinal >= self._ordinal:
            return
        triggers: list[tuple[str, Fvg | None, str, bool, bool | None, bool | None]] = []
        wanted = self._trade_direction_to_gap(s.direction)
        for gap in inp.new_fvgs.get(60, ()):
            if gap.direction is wanted:
                confirmed, fully, satisfied = self._causality(
                    gap,
                    trigger_ts=s.inversion_ts_utc,
                    policy=self._cfg.causality_entry,
                )
                triggers.append(
                    (
                        "fresh_fvg_continuation",
                        gap,
                        gap.fvg_id,
                        satisfied,
                        confirmed,
                        fully,
                    )
                )
        if self._retest_triggered(bar, s):
            triggers.append(
                (
                    "ifvg_retest",
                    None,
                    f"{self._cfg.retest_trigger}|{bar_cursor(bar)}",
                    True,
                    None,
                    None,
                )
            )
        for family, entry_gap, evidence_id, causality_ok, confirmed, fully in triggers:
            self._emit_candidate(
                inp,
                s,
                family=family,
                entry_gap=entry_gap,
                evidence_id=evidence_id,
                causality_ok=causality_ok,
                causality_confirmed=confirmed,
                causality_fully=fully,
                out=out,
            )

    def _retest_triggered(self, bar: Bar, s: _Setup) -> bool:
        assert s.opposing is not None
        overlap = wick_overlaps(
            bar, s.opposing.gap_low_ticks, s.opposing.gap_high_ticks
        )
        trigger = self._cfg.retest_trigger
        if trigger == RetestTrigger.LEGACY_PLACEHOLDER_CANDIDATE_ONLY.value:
            return overlap
        if s.retest_latched:
            return False
        hit = False
        if trigger == RetestTrigger.FIRST_TOUCH.value:
            hit = overlap
        elif trigger == RetestTrigger.FIRST_CE_TOUCH.value:
            hit = overlap and ce_reached(bar, s.opposing)
        elif trigger == RetestTrigger.FIRST_FRACTIONAL_PENETRATION.value:
            hit = overlap and penetration_ticks(bar, s.opposing) > 0
        elif trigger == RetestTrigger.FIRST_REJECTION_CLOSE.value:
            hit = overlap and (
                bar.close_ticks > s.opposing.gap_high_ticks
                if s.direction is Direction.LONG
                else bar.close_ticks < s.opposing.gap_low_ticks
            )
        elif trigger == RetestTrigger.FIRST_DISPLACEMENT_AFTER_TOUCH.value:
            if overlap:
                s.retest_touch_seen = True
            hit = s.retest_touch_seen and (
                bar.close_ticks > bar.open_ticks
                if s.direction is Direction.LONG
                else bar.close_ticks < bar.open_ticks
            )
        if hit:
            s.retest_latched = True
        return hit

    def _emit_candidate(
        self,
        inp: IfvgStepInput,
        s: _Setup,
        *,
        family: str,
        entry_gap: Fvg | None,
        evidence_id: str,
        causality_ok: bool,
        causality_confirmed: bool | None = None,
        causality_fully: bool | None = None,
        out: list[IfvgEmission],
    ) -> None:
        bar = inp.bar_1m
        entry = bar.close_ticks
        if s.direction is Direction.LONG:
            swing = s.swing_min_low
            stop = (
                swing - self._cfg.sl_buffer_ticks
                if swing is not None
                else entry
            )
            risk = entry - stop
        else:
            swing = s.swing_max_high
            stop = (
                swing + self._cfg.sl_buffer_ticks
                if swing is not None
                else entry
            )
            risk = stop - entry
        offset = math.ceil(abs(risk * self._cfg.tp_r_multiple))
        target = entry + offset if s.direction is Direction.LONG else entry - offset
        parent = s.parent
        entry_to_parent = (
            interval_distance_ticks(
                entry,
                entry,
                parent.gap_low_ticks,
                parent.gap_high_ticks,
            )
            if parent is not None
            else 0
        )
        trigger_cursor = (
            entry_gap.fvg_id if entry_gap is not None else f"{evidence_id}"
        )
        candidate_id = make_candidate_id(s.setup_id, family, trigger_cursor)
        if self._audit_enabled:
            self._audit_emit(
                "entry_joint_causality",
                EntryCausalityRecord(
                    envelope=self._env(
                        bar, s.setup_id, entry_session=inp.session_doc
                    ),
                    stamp=self._audit_stamp(
                        substep=self._audit_substep,
                        out_len=len(out),
                        bar_id=bar.bar_id,
                        cursor=bar_cursor(bar),
                        step_ordinal=self._ordinal,
                    ),
                    candidate_id=candidate_id,
                    setup_id=s.setup_id,
                    entry_family=family,
                    entry_fvg_id=(
                        entry_gap.fvg_id if entry_gap is not None else None
                    ),
                    policy=self._cfg.causality_entry,
                    trigger_ts_utc=s.inversion_ts_utc,
                    confirmed_after=causality_confirmed,
                    fully_formed_after=causality_fully,
                    satisfied=causality_ok,
                ),
            )
        geometry = self._geometry(
            s,
            bar=bar,
            entry_fvg=entry_gap,
            entry=entry,
            stop=stop,
            target=target,
            swing=swing,
        )

        blocks: list[str] = []
        if not self._cfg.runnable:
            blocks.append("profile_not_runnable")
        if not self._cfg.execution_enabled:
            blocks.append("execution_disabled")
        if family != self._cfg.entry_family:
            blocks.append("entry_family_not_profile")
        if s.phase != "S4":
            blocks.append("already_in_trade")
        if not causality_ok:
            blocks.append("causality_failed")
        if inp.session_doc not in self._cfg.enabled_entry_sessions:
            blocks.append("out_of_session")
        if (
            self._cfg.entry_near_parent
            and self._cfg.entry_parent_distance_ticks_max is not None
            and entry_to_parent > self._cfg.entry_parent_distance_ticks_max
        ):
            blocks.append("entry_too_far_from_parent")
        if risk < 1:
            blocks.append("risk_lt_min")
        if family == "ifvg_retest":
            blocks.append("retest_trigger_unratified")
        if geometry is None:
            blocks.append("geometry_incomplete")
        cap = self._cfg.max_executed_trades_per_day
        if (
            cap is not None
            and self._executions_by_day.get(bar.trading_day, 0) >= cap
        ):
            blocks.append("daily_execution_cap")

        self._count(f"entry_candidates_{family}")
        for reason in blocks:
            self._count(f"candidate_blocked_{reason}")
        candidate = EntryCandidateRecord(
            envelope=self._env(
                bar, s.setup_id, entry_session=inp.session_doc
            ),
            candidate_id=candidate_id,
            direction=s.direction,
            entry_family=family,
            trigger_evidence_id=evidence_id,
            trigger_cursor=bar_cursor(bar),
            entry_fvg=entry_gap,
            entry_ticks=entry,
            proposed_stop_ticks=stop,
            risk_ticks=risk,
            proposed_target_ticks=target,
            bars_since_inversion=self._ordinal - s.inversion_ordinal,  # type: ignore[operator]
            entry_to_parent_ticks=entry_to_parent,
            in_engine_session=inp.session_engine,
            in_doc_session=inp.session_doc,
            block_reasons=tuple(blocks),
            geometry=geometry,
        )
        out.append(IfvgEmission(kind="entry_candidate", record=candidate))
        if geometry is None:
            out.append(
                IfvgEmission(
                    kind="quarantine",
                    record=QuarantineRecord(
                        envelope=candidate.envelope,
                        quarantine_id=make_lifecycle_event_id(
                            s.setup_id,
                            "quarantine",
                            "geometry_incomplete",
                            bar_cursor(bar),
                        ),
                        candidate_id=candidate_id,
                        reasons=("geometry_incomplete",),
                        evidence_cursor=bar_cursor(bar),
                    ),
                )
            )
            return
        if blocks:
            out.append(
                IfvgEmission(
                    kind="geometry_dossier",
                    record=GeometryDossierRecord(
                        envelope=candidate.envelope,
                        candidate_id=candidate_id,
                        decision_id=None,
                        trade_id=None,
                        geometry=geometry,
                    ),
                )
            )
            if (
                "out_of_session" in blocks
                and self._cfg.outside_session_policy
                == OutsideSessionPolicy.RESET_SETUP_AS_MISSED.value
                and s.phase == "S4"
            ):
                self._terminate_pretrade(s, "missed_out_of_session", bar, out)
            return

        self._assert_decision_consistency(s, entry_gap, entry, stop, risk)
        decision_id = make_decision_id(candidate_id, self._cfg.profile_hash)
        trade_id = make_trade_id(decision_id, bar_cursor(bar))
        decision = EligibleDecisionRecord(
            envelope=candidate.envelope,
            decision_id=decision_id,
            candidate_id=candidate_id,
            direction=s.direction,
            execution_profile_hash=self._cfg.profile_hash,
            entry_family=family,
            entry_cursor=bar_cursor(bar),
            entry_ticks=entry,
            stop_ticks=stop,
            risk_ticks=risk,
            target_ticks=target,
            passed_guards=(
                "profile_runnable",
                "family_active",
                "causality",
                "session",
                "positive_risk",
                "geometry_complete",
                "slot_free",
            ),
            geometry=geometry,
        )
        out.append(IfvgEmission(kind="eligible_decision", record=decision))
        out.append(
            IfvgEmission(
                kind="geometry_dossier",
                record=GeometryDossierRecord(
                    envelope=candidate.envelope,
                    candidate_id=candidate_id,
                    decision_id=decision_id,
                    trade_id=trade_id,
                    geometry=geometry,
                ),
            )
        )
        s.phase = "S5"
        s.entry_family = family
        s.candidate_id = candidate_id
        s.decision_id = decision_id
        s.trade_id = trade_id
        s.entry_ticks = entry
        s.stop_ticks = stop
        s.tp_ticks = target
        s.entry_ts_utc = bar.availability_ts_utc
        s.entry_session = inp.session_doc
        s.entry_ordinal = self._ordinal
        s.entry_bar = bar
        s.geometry = geometry
        s.mfe_ticks = 0
        s.mae_ticks = 0
        self._executions_by_day[bar.trading_day] = (
            self._executions_by_day.get(bar.trading_day, 0) + 1
        )
        self._count("eligible_decisions")
        self._count("executions_opened")
        self._lifecycle(
            s,
            from_phase="S4",
            to_phase="S5",
            transition="trade_opened",
            reason="eligible_decision_filled_at_confirmation_close",
            bar=bar,
            out=out,
        )

    def _geometry(
        self,
        s: _Setup,
        *,
        bar: Bar,
        entry_fvg: Fvg | None,
        entry: int,
        stop: int,
        target: int,
        swing: int | None,
    ) -> GeometryEvidence | None:
        if (
            s.parent is None
            or s.opposing is None
            or s.lock_bar is None
            or s.inversion_bar is None
            or swing is None
        ):
            return None
        return GeometryEvidence(
            htf=s.htf,
            parent=s.parent,
            opposing=s.opposing,
            entry_fvg=entry_fvg,
            tap_bar=bar_evidence(s.tap_bar),
            lock_bar=bar_evidence(s.lock_bar),
            inversion_bar=bar_evidence(s.inversion_bar),
            entry_bar=bar_evidence(bar),
            manipulation_swing_ticks=swing,
            sl_buffer_ticks=self._cfg.sl_buffer_ticks,
            entry_ticks=entry,
            stop_ticks=stop,
            target_ticks=target,
            feature_as_of_cursor=bar_cursor(bar),
        )

    def _assert_decision_consistency(
        self,
        s: _Setup,
        entry_gap: Fvg | None,
        entry: int,
        stop: int,
        risk: int,
    ) -> None:
        wanted = self._trade_direction_to_gap(s.direction)
        if s.htf.direction is not wanted:
            raise ValueError("HTF direction disagrees with setup direction")
        if s.parent is None or s.parent.direction is not wanted:
            raise ValueError("parent direction disagrees with setup direction")
        counter = (
            GapDirection.BEARISH
            if s.direction is Direction.LONG
            else GapDirection.BULLISH
        )
        if s.opposing is None or s.opposing.direction is not counter:
            raise ValueError("opposing direction is not opposite the setup")
        if entry_gap is not None and entry_gap.direction is not wanted:
            raise ValueError("fresh entry direction disagrees with setup direction")
        if risk <= 0:
            raise ValueError("decision risk must be positive")
        if s.direction is Direction.LONG and stop >= entry:
            raise ValueError("long stop must be strictly below entry")
        if s.direction is Direction.SHORT and stop <= entry:
            raise ValueError("short stop must be strictly above entry")

    # ------------------------------------------------------------------
    # Trade resolver

    def _walk_trade(
        self,
        inp: IfvgStepInput,
        s: _Setup,
        out: list[IfvgEmission],
    ) -> bool:
        bar = inp.bar_1m
        if (
            s.entry_ordinal is None
            or self._ordinal <= s.entry_ordinal
            or s.entry_bar is None
        ):
            return False
        if bar.availability_ts_utc <= s.entry_bar.availability_ts_utc:
            raise ValueError("resolution cursor must be strictly after entry")
        assert (
            s.entry_ticks is not None
            and s.stop_ticks is not None
            and s.tp_ticks is not None
        )
        if s.direction is Direction.LONG:
            s.mfe_ticks = max(s.mfe_ticks, bar.high_ticks - s.entry_ticks)
            s.mae_ticks = max(s.mae_ticks, s.entry_ticks - bar.low_ticks)
            hit_stop = bar.low_ticks <= s.stop_ticks
            hit_target = bar.high_ticks >= s.tp_ticks
        else:
            s.mfe_ticks = max(s.mfe_ticks, s.entry_ticks - bar.low_ticks)
            s.mae_ticks = max(s.mae_ticks, bar.high_ticks - s.entry_ticks)
            hit_stop = bar.high_ticks >= s.stop_ticks
            hit_target = bar.low_ticks <= s.tp_ticks
        if hit_stop:
            self._resolve_trade(s, "stop", bar, out)
            return True
        if hit_target:
            self._resolve_trade(s, "target", bar, out)
            return True
        return False

    def _resolve_trade(
        self,
        s: _Setup,
        resolution: str,
        bar: Bar,
        out: list[IfvgEmission],
    ) -> None:
        if s.geometry is None:
            raise ValueError("executed trade is missing immutable geometry")
        assert all(
            value is not None
            for value in (
                s.trade_id,
                s.decision_id,
                s.candidate_id,
                s.entry_family,
                s.entry_ts_utc,
                s.entry_session,
                s.entry_ticks,
                s.stop_ticks,
                s.tp_ticks,
                s.entry_ordinal,
            )
        )
        risk = abs(s.entry_ticks - s.stop_ticks)  # type: ignore[operator]
        if resolution == "stop":
            realized = -risk
        else:
            realized = abs(s.tp_ticks - s.entry_ticks)  # type: ignore[operator]
        bars_after = self._ordinal - s.entry_ordinal  # type: ignore[operator]
        out.append(
            IfvgEmission(
                kind="executed_trade",
                record=ExecutedTradeRecord(
                    envelope=self._env(
                        bar,
                        s.setup_id,
                        entry_session=s.entry_session,  # type: ignore[arg-type]
                    ),
                    trade_id=s.trade_id,  # type: ignore[arg-type]
                    decision_id=s.decision_id,  # type: ignore[arg-type]
                    candidate_id=s.candidate_id,  # type: ignore[arg-type]
                    direction=s.direction,
                    status="resolved",
                    resolution=resolution,
                    entry_family=s.entry_family,  # type: ignore[arg-type]
                    entry_cursor=bar_cursor(s.entry_bar),  # type: ignore[arg-type]
                    resolution_cursor=bar_cursor(bar),
                    entry_ts_utc=s.entry_ts_utc,  # type: ignore[arg-type]
                    resolution_ts_utc=bar.availability_ts_utc,
                    entry_ticks=s.entry_ticks,  # type: ignore[arg-type]
                    stop_ticks=s.stop_ticks,  # type: ignore[arg-type]
                    target_ticks=s.tp_ticks,  # type: ignore[arg-type]
                    risk_ticks=risk,
                    bars_after_entry_to_resolution=bars_after,
                    mfe_ticks=s.mfe_ticks,
                    mae_ticks=s.mae_ticks,
                    realized_ticks=realized,
                    realized_r=realized / risk,
                    geometry=s.geometry,
                ),
            )
        )
        self._count(f"resolved_{resolution}")
        self._lifecycle(
            s,
            from_phase="S5",
            to_phase="S0",
            transition="trade_resolved",
            reason=resolution,
            bar=bar,
            out=out,
        )
        out.append(
            IfvgEmission(
                kind="setup_resolution",
                record=self._compat_resolution(
                    s,
                    f"resolved_{'tp' if resolution == 'target' else 'sl'}",
                    bar,
                ),
            )
        )
        if self._audit_enabled:
            self._audit_substep = AUDIT_SUBSTEP_RESOLUTION
            self._audit_slot_death(
                s,
                reason="slot_freed",
                bar=bar,
                cursor=bar_cursor(bar),
                ts_utc=bar.availability_ts_utc,
                trading_day=bar.trading_day,
                terminated=True,
                lifecycle_transition="trade_resolved",
                lifecycle_reason=resolution,
                out_len=len(out),
            )
        self._setup = None

    # ------------------------------------------------------------------
    # Structure intake

    def _apply_intake(
        self,
        inp: IfvgStepInput,
        out: list[IfvgEmission],
    ) -> None:
        s = self._setup
        if s is None:
            return
        if s.tap_ordinal != self._ordinal:
            self._tap_scan_while_occupied(inp, out)
        if s.phase == "S1":
            self._intake_parent_candidates(inp, s, out)
        elif s.phase in ("S2", "S3"):
            self._intake_opposing(inp, s, out)

    def _intake_parent_candidates(
        self,
        inp: IfvgStepInput,
        s: _Setup,
        out: list[IfvgEmission],
    ) -> None:
        bar = inp.bar_1m
        wanted = self._trade_direction_to_gap(s.direction)
        arrivals = [
            gap
            for tf in self._cfg.parent_tf_seconds
            for gap in inp.new_fvgs.get(tf, ())
            if gap.direction is wanted
        ]
        arrivals.sort(
            key=lambda gap: (
                gap.timeframe_seconds,
                gap.confirmed_ts_utc,
                gap.fvg_id,
            ),
            reverse=True,
        )
        for rank, gap in enumerate(arrivals):
            clock = s.parent_clocks.get(gap.timeframe_seconds, 0)
            confirmed, fully, causal = self._causality(
                gap,
                trigger_ts=s.tap_ts_utc,
                policy=self._cfg.causality_parent,
            )
            distance = interval_distance_ticks(
                gap.gap_low_ticks,
                gap.gap_high_ticks,
                s.htf.gap_low_ticks,
                s.htf.gap_high_ticks,
            )
            selected = False
            if not causal:
                drop = "causality_failed"
            elif clock > self._cfg.parent_reaction_window_parent_bars:
                drop = "reaction_window_expired"
            elif distance > self._cfg.parent_htf_distance_ticks_max:
                drop = "distance_gt_profile"
            elif s.parent is None:
                selected, drop = True, None
            elif gap.timeframe_seconds > s.parent.timeframe_seconds or (
                gap.timeframe_seconds == s.parent.timeframe_seconds
                and (
                    gap.confirmed_ts_utc,
                    gap.fvg_id,
                )
                > (
                    s.parent.confirmed_ts_utc,
                    s.parent.fvg_id,
                )
            ):
                self._count("parents_replaced")
                selected, drop = True, None
            else:
                drop = "outranked"
            self._count("parent_candidates")
            out.append(
                IfvgEmission(
                    kind="parent_candidate",
                    record=ParentCandidateRecord(
                        envelope=self._env(bar, s.setup_id),
                        parent_tf_seconds=gap.timeframe_seconds,
                        fvg=gap,
                        distance_to_htf_ticks=distance,
                        elapsed_parent_bars_since_tap=clock,
                        elapsed_1m_bars_since_tap=self._ordinal - s.tap_ordinal,
                        confirmed_after=confirmed,
                        fully_formed_after=fully,
                        causality_satisfied=causal,
                        rank=rank,
                        selected=selected,
                        drop_reason=drop,
                    ),
                )
            )
            if selected:
                prior_parent_id = s.parent.fvg_id if s.parent is not None else None
                s.parent = gap
                s.parent_selected_ordinal = self._ordinal
                if self._audit_enabled:
                    self._audit_parent_window_event(
                        s,
                        event_kind="parent_selected",
                        parent_fvg_id=gap.fvg_id,
                        prior_parent_fvg_id=prior_parent_id,
                        bar=bar,
                        out_len=len(out),
                    )

    def _intake_opposing(
        self,
        inp: IfvgStepInput,
        s: _Setup,
        out: list[IfvgEmission],
    ) -> None:
        bar = inp.bar_1m
        counter = (
            GapDirection.BEARISH
            if s.direction is Direction.LONG
            else GapDirection.BULLISH
        )
        assert s.parent is not None
        for gap in inp.new_fvgs.get(60, ()):
            if gap.direction is not counter:
                continue
            confirmed, fully, causal = self._causality(
                gap,
                trigger_ts=s.lock_ts_utc,
                policy=self._cfg.causality_opposing,
            )
            distance = interval_distance_ticks(
                gap.gap_low_ticks,
                gap.gap_high_ticks,
                s.parent.gap_low_ticks,
                s.parent.gap_high_ticks,
            )
            self._count("opposing_candidates")
            if not causal:
                out.append(
                    self._opposing_emission(
                        s,
                        gap,
                        distance,
                        bar,
                        confirmed=confirmed,
                        fully=fully,
                        causal=False,
                        selected=False,
                        drop="causality_failed",
                    )
                )
                continue
            if distance > self._cfg.opposing_parent_distance_ticks_max:
                out.append(
                    self._opposing_emission(
                        s,
                        gap,
                        distance,
                        bar,
                        confirmed=confirmed,
                        fully=fully,
                        causal=True,
                        selected=False,
                        drop="distance_gt_profile",
                    )
                )
                continue
            # Inversion was already checked in step 3. Replacement occurs only now.
            if s.opposing is not None:
                self._count("opposing_replaced")
            s.opposing = gap
            s.armed_ts_utc = bar.availability_ts_utc
            s.armed_ordinal = self._ordinal
            if s.phase == "S2":
                s.phase = "S3"
                self._count("opposing_armed")
                self._lifecycle(
                    s,
                    from_phase="S2",
                    to_phase="S3",
                    transition="opposing_armed",
                    reason="opposing_fvg_selected",
                    bar=bar,
                    out=out,
                )
            out.append(
                self._opposing_emission(
                    s,
                    gap,
                    distance,
                    bar,
                    confirmed=confirmed,
                    fully=fully,
                    causal=True,
                    selected=True,
                    drop=None,
                )
            )

    def _opposing_emission(
        self,
        s: _Setup,
        gap: Fvg,
        distance: int,
        bar: Bar,
        *,
        confirmed: bool,
        fully: bool,
        causal: bool,
        selected: bool,
        drop: str | None,
    ) -> IfvgEmission:
        return IfvgEmission(
            kind="opposing",
            record=OpposingGapRecord(
                envelope=self._env(bar, s.setup_id),
                fvg=gap,
                distance_to_parent_ticks=distance,
                elapsed_1m_bars_since_lock=(
                    self._ordinal - s.lock_ordinal
                    if s.lock_ordinal is not None
                    else 0
                ),
                confirmed_after=confirmed,
                fully_formed_after=fully,
                causality_satisfied=causal,
                selected=selected,
                drop_reason=drop,
            ),
        )

    @staticmethod
    def _causality(
        gap: Fvg,
        *,
        trigger_ts: datetime | None,
        policy: str,
    ) -> tuple[bool, bool, bool]:
        if trigger_ts is None:
            return False, False, False
        confirmed = gap.confirmed_ts_utc > trigger_ts
        fully = gap.a_open_ts_utc >= trigger_ts
        satisfied = (
            confirmed
            if policy == CausalityPolicy.CONFIRMED_AFTER.value
            else fully
        )
        return confirmed, fully, satisfied

    # ------------------------------------------------------------------
    # Shared measurements and compatibility

    def _nearest_level(
        self,
        inp: IfvgStepInput,
        bar: Bar,
    ) -> tuple[str | None, int | None]:
        best_kind: str | None = None
        best_dist: int | None = None
        for level in inp.levels:
            if (
                level.available_from is not None
                and level.available_from > bar.availability_ts_utc
            ):
                continue
            price_ticks = round(level.price / self._cfg.tick_size)
            distance = abs(bar.close_ticks - price_ticks)
            if best_dist is None or distance < best_dist:
                best_kind, best_dist = level.name, distance
        return best_kind, best_dist

    def _build_pools(self, inp: IfvgStepInput) -> tuple[LevelPool, ...]:
        pools = [
            LevelPool(
                kind=level.name,
                price_ticks=round(level.price / self._cfg.tick_size),
                side=level.side,
                available_from=level.available_from,
            )
            for level in inp.levels
        ]
        pools.extend(
            LevelPool(
                "swing_high",
                point.price_ticks,
                Side.HIGH,
                point.confirmed_ts_utc,
            )
            for point in inp.recent_swing_highs
        )
        pools.extend(
            LevelPool(
                "swing_low",
                point.price_ticks,
                Side.LOW,
                point.confirmed_ts_utc,
            )
            for point in inp.recent_swing_lows
        )
        return tuple(pools)

    def _compat_resolution(
        self,
        s: _Setup,
        resolution: str,
        bar: Bar,
    ) -> SetupResolutionRecord:
        return SetupResolutionRecord(
            envelope=self._env(bar, s.setup_id),
            resolution=resolution,
            direction=s.direction,
            entry_family=s.entry_family,
            entry_ticks=s.entry_ticks,
            stop_ticks=s.stop_ticks,
            tp_ticks=s.tp_ticks,
            mfe_ticks=s.mfe_ticks if s.entry_ordinal is not None else None,
            mae_ticks=s.mae_ticks if s.entry_ordinal is not None else None,
            bars_in_trade=(
                self._ordinal - s.entry_ordinal
                if s.entry_ordinal is not None
                else None
            ),
            tap_ts_utc=s.tap_ts_utc,
            parent_confirmed_ts_utc=(
                s.parent.confirmed_ts_utc if s.parent is not None else None
            ),
            lock_ts_utc=s.lock_ts_utc,
            armed_ts_utc=s.armed_ts_utc,
            inversion_ts_utc=s.inversion_ts_utc,
            entry_ts_utc=s.entry_ts_utc,
            htf_fvg_id=s.htf.fvg_id,
            parent_fvg_id=s.parent.fvg_id if s.parent is not None else None,
            opposing_fvg_id=(
                s.opposing.fvg_id if s.opposing is not None else None
            ),
        )
