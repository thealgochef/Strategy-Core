"""Deterministic IFVG v2 one-setup/one-trade reducer."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
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
    IFVG_RECORD_SCHEMA_VERSION,
    EligibleDecisionRecord,
    EntryCandidateRecord,
    ExecutedTradeRecord,
    GeometryDossierRecord,
    GeometryEvidence,
    HtfTapRecord,
    IfvgEmission,
    InversionRecord,
    OpposingGapRecord,
    ParentCandidateRecord,
    ParentLockRecord,
    QuarantineRecord,
    RecordEnvelope,
    SetupLifecycleEventRecord,
    SetupResolutionRecord,
    bar_cursor,
    bar_evidence,
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


class IfvgReducer:
    def __init__(self, config: IfvgReducerConfig) -> None:
        self._cfg = config
        self._ordinal = 0
        self._setup: _Setup | None = None
        self._seq_day: date | None = None
        self._seq = 0
        self._funnel: dict[str, int] = {}
        self._executions_by_day: dict[date, int] = {}

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

    def step(self, inp: IfvgStepInput) -> tuple[IfvgEmission, ...]:
        self._ordinal += 1
        out: list[IfvgEmission] = []
        self._tick_parent_clocks(inp)

        if self._apply_invalidations(inp, out):
            return tuple(out)
        if self._apply_expiries(inp.bar_1m, out):
            return tuple(out)

        started_in_trade = self._setup is not None and self._setup.phase == "S5"
        if self._setup is None:
            self._scan_taps(inp, out)
        else:
            if self._apply_transitions(inp, out):
                # Resolution is terminal for this reducer step. A newly free slot
                # cannot activate on the resolution bar.
                return tuple(out)

        if self._setup is not None:
            self._apply_intake(inp, out)
            self._instrument_parentless_window()
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
    ) -> "IfvgReducer":
        if snap.schema_version != REDUCER_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"IfvgReducerSnapshot schema {snap.schema_version} != "
                f"supported {REDUCER_SNAPSHOT_SCHEMA_VERSION}"
            )
        if snap.profile_hash != config.profile_hash:
            raise ValueError("reducer snapshot profile_hash does not match active profile")
        reducer = cls(config)
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
            self._terminate_pretrade(s, "invalidated_htf_filled", bar, out)
            return True
        if (
            self._cfg.parent_full_fill_invalidation
            and s.parent is not None
            and s.parent.fvg_id in filled
        ):
            if s.phase == "S1":
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
                s.parent = None
                s.parent_selected_ordinal = None
            else:
                self._terminate_pretrade(s, "invalidated_parent_filled", bar, out)
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
                if s.phase == "S1":
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
                    s.parent = None
                    s.parent_selected_ordinal = None
                else:
                    self._terminate_pretrade(
                        s, "invalidated_parent_structural", bar, out
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

    def _instrument_parentless_window(self) -> None:
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

    def _terminate_pretrade(
        self,
        s: _Setup,
        reason: str,
        bar: Bar,
        out: list[IfvgEmission],
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
        triggers: list[tuple[str, Fvg | None, str, bool]] = []
        wanted = self._trade_direction_to_gap(s.direction)
        for gap in inp.new_fvgs.get(60, ()):
            if gap.direction is wanted:
                confirmed, fully, satisfied = self._causality(
                    gap,
                    trigger_ts=s.inversion_ts_utc,
                    policy=self._cfg.causality_entry,
                )
                del confirmed, fully
                triggers.append(
                    (
                        "fresh_fvg_continuation",
                        gap,
                        gap.fvg_id,
                        satisfied,
                    )
                )
        if self._retest_triggered(bar, s):
            triggers.append(
                (
                    "ifvg_retest",
                    None,
                    f"{self._cfg.retest_trigger}|{bar_cursor(bar)}",
                    True,
                )
            )
        for family, entry_gap, evidence_id, causality_ok in triggers:
            self._emit_candidate(
                inp,
                s,
                family=family,
                entry_gap=entry_gap,
                evidence_id=evidence_id,
                causality_ok=causality_ok,
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
                s.parent = gap
                s.parent_selected_ordinal = self._ordinal

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
