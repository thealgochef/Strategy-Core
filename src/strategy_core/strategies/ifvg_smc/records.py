"""Append-only IFVG v2 records and deterministic identities."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping

from strategy_core.structures.fvg import Fvg
from strategy_core.structures.sweeps import SweepResult
from strategy_core.types import Bar, Direction

__all__ = [
    "IFVG_RECORD_SCHEMA_VERSION",
    "IFVG_AUDIT_RECORD_SCHEMA_VERSION",
    "AUDIT_SUBSTEP_CONTEXT_FILL",
    "AUDIT_SUBSTEP_PRETRADE_INVALIDATION",
    "AUDIT_SUBSTEP_FSM_TRANSITION",
    "AUDIT_SUBSTEP_CANDIDATE_INTAKE",
    "AUDIT_SUBSTEP_PARENTLESS",
    "AUDIT_SUBSTEP_RESOLUTION",
    "AuditStamp",
    "FvgFillEventRecord",
    "EntryCausalityRecord",
    "ParentSlotDeathRecord",
    "FvgInvalidationEventRecord",
    "ParentWindowEventRecord",
    "ParentlessStepRecord",
    "make_audit_event_id",
    "RecordEnvelope",
    "BarEvidence",
    "CausalityEvidence",
    "GeometryEvidence",
    "DayFunnelRecord",
    "HtfTapRecord",
    "ParentCandidateRecord",
    "ParentLockRecord",
    "OpposingGapRecord",
    "InversionRecord",
    "SetupLifecycleEventRecord",
    "EntryCandidateRecord",
    "EligibleDecisionRecord",
    "ExecutedTradeRecord",
    "CandidateLabelRecord",
    "GeometryDossierRecord",
    "QuarantineRecord",
    "SetupResolutionRecord",
    "IfvgEmission",
    "bar_cursor",
    "bar_evidence",
    "make_setup_id",
    "make_candidate_id",
    "make_decision_id",
    "make_trade_id",
    "make_lifecycle_event_id",
]

IFVG_RECORD_SCHEMA_VERSION = 2

_IDENTITY_NAMESPACE = uuid.UUID("e6bf46f5-e6c8-4fd3-bf90-5747cbd9ea99")


def _uuid5(kind: str, *parts: object) -> str:
    if any(part is None or str(part) == "" for part in parts):
        raise ValueError(f"{kind} identity components must be non-empty")
    payload = json.dumps(
        [kind, *(str(part) for part in parts)],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(_IDENTITY_NAMESPACE, payload))


def make_setup_id(profile_hash: str, htf_fvg_id: str, tap_cursor: str) -> str:
    return _uuid5("setup", profile_hash, htf_fvg_id, tap_cursor)


def make_candidate_id(setup_id: str, entry_family: str, trigger_cursor: str) -> str:
    return _uuid5("candidate", setup_id, entry_family, trigger_cursor)


def make_decision_id(candidate_id: str, execution_profile_hash: str) -> str:
    return _uuid5("decision", candidate_id, execution_profile_hash)


def make_trade_id(decision_id: str, entry_cursor: str) -> str:
    return _uuid5("trade", decision_id, entry_cursor)


def make_lifecycle_event_id(
    setup_id: str,
    transition: str,
    reason: str,
    event_cursor: str,
) -> str:
    return _uuid5("lifecycle", setup_id, transition, reason, event_cursor)


def bar_cursor(bar: Bar) -> str:
    """Stable logical-candle cursor for bar-resolution replay."""
    return (
        f"{bar.availability_ts_utc.isoformat()}|{bar.timeframe_ticks}|"
        f"{bar.trading_day.isoformat()}|{bar.bar_id}"
    )


@dataclass(frozen=True, slots=True)
class BarEvidence:
    bar_id: str
    timeframe_seconds: int
    trading_day: date
    logical_open_ts_utc: datetime
    logical_close_ts_utc: datetime
    first_print_ts_utc: datetime
    last_print_ts_utc: datetime
    open_ticks: int
    high_ticks: int
    low_ticks: int
    close_ticks: int
    cursor: str


def bar_evidence(bar: Bar) -> BarEvidence:
    return BarEvidence(
        bar_id=bar.bar_id,
        timeframe_seconds=bar.timeframe_ticks,
        trading_day=bar.trading_day,
        logical_open_ts_utc=bar.logical_open_ts_utc or bar.open_ts_utc,
        logical_close_ts_utc=bar.availability_ts_utc,
        first_print_ts_utc=bar.open_ts_utc,
        last_print_ts_utc=bar.close_ts_utc,
        open_ticks=bar.open_ticks,
        high_ticks=bar.high_ticks,
        low_ticks=bar.low_ticks,
        close_ticks=bar.close_ticks,
        cursor=bar_cursor(bar),
    )


@dataclass(frozen=True, slots=True)
class CausalityEvidence:
    joint: str
    policy: str
    trigger_logical_close_ts_utc: datetime
    evidence_a_open_ts_utc: datetime
    evidence_confirmed_ts_utc: datetime
    trigger_cursor: str
    evidence_cursor: str
    confirmed_after: bool
    fully_formed_after: bool
    satisfied: bool


@dataclass(frozen=True, slots=True)
class GeometryEvidence:
    htf: Fvg
    parent: Fvg
    opposing: Fvg
    entry_fvg: Fvg | None
    tap_bar: BarEvidence
    lock_bar: BarEvidence
    inversion_bar: BarEvidence
    entry_bar: BarEvidence
    manipulation_swing_ticks: int
    sl_buffer_ticks: int
    entry_ticks: int
    stop_ticks: int
    target_ticks: int
    feature_as_of_cursor: str


@dataclass(frozen=True, slots=True)
class RecordEnvelope:
    schema_version: int
    strategy_id: str
    strategy_version: str
    profile_hash: str
    trading_day: date
    ts_utc: datetime
    setup_id: str
    profile_name: str = ""
    qualification_mode: str = ""
    section_config_hash: str = ""
    entry_family: str = ""
    label_family: str = ""
    entry_session: str = "none"
    anchor_policy: str = ""
    resolver_policy: str = ""
    causality_parent: str = ""
    causality_opposing: str = ""
    causality_entry: str = ""
    timeout_policy: str = ""


@dataclass(frozen=True, slots=True)
class DayFunnelRecord:
    envelope: RecordEnvelope
    counters: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class HtfTapRecord:
    envelope: RecordEnvelope
    htf_tf_seconds: int
    fvg: Fvg
    direction: Direction
    penetration_ticks: int
    ce_reached: bool
    htf_age_seconds: int
    remaining_fraction: float
    registry_live_count: int
    rank: int
    conflicted: bool
    nearest_level_kind: str | None
    nearest_level_distance_ticks: int | None
    session_engine: str
    session_doc: str
    selected: bool
    drop_reason: str | None
    tap_cursor: str = ""


@dataclass(frozen=True, slots=True)
class ParentCandidateRecord:
    envelope: RecordEnvelope
    parent_tf_seconds: int
    fvg: Fvg
    distance_to_htf_ticks: int
    elapsed_parent_bars_since_tap: int
    elapsed_1m_bars_since_tap: int
    confirmed_after: bool
    fully_formed_after: bool
    causality_satisfied: bool
    rank: int
    selected: bool
    drop_reason: str | None


@dataclass(frozen=True, slots=True)
class ParentLockRecord:
    envelope: RecordEnvelope
    parent_fvg_id: str
    penetration_ticks: int
    ce_reached: bool
    elapsed_1m_bars_since_selection: int
    lock_cursor: str = ""


@dataclass(frozen=True, slots=True)
class OpposingGapRecord:
    envelope: RecordEnvelope
    fvg: Fvg
    distance_to_parent_ticks: int
    elapsed_1m_bars_since_lock: int
    confirmed_after: bool
    fully_formed_after: bool
    causality_satisfied: bool
    selected: bool
    drop_reason: str | None


@dataclass(frozen=True, slots=True)
class InversionRecord:
    envelope: RecordEnvelope
    opposing_fvg_id: str
    close_through_margin_ticks: int
    bars_armed_to_inversion: int
    opposing_size_ticks: int
    sweep: SweepResult
    semantic: str
    inversion_cursor: str = ""


@dataclass(frozen=True, slots=True)
class SetupLifecycleEventRecord:
    envelope: RecordEnvelope
    lifecycle_event_id: str
    from_phase: str
    to_phase: str
    transition: str
    reason: str
    event_cursor: str
    candidate_id: str | None = None
    decision_id: str | None = None
    trade_id: str | None = None


@dataclass(frozen=True, slots=True)
class EntryCandidateRecord:
    """Counterfactual trigger. It never represents an execution."""

    envelope: RecordEnvelope
    candidate_id: str
    direction: Direction
    entry_family: str
    trigger_evidence_id: str
    trigger_cursor: str
    entry_fvg: Fvg | None
    entry_ticks: int
    proposed_stop_ticks: int
    risk_ticks: int
    proposed_target_ticks: int
    bars_since_inversion: int
    entry_to_parent_ticks: int
    in_engine_session: str
    in_doc_session: str
    block_reasons: tuple[str, ...]
    geometry: GeometryEvidence | None

    @property
    def stop_ticks(self) -> int:
        return self.proposed_stop_ticks

    @property
    def tp_ticks(self) -> int:
        return self.proposed_target_ticks

    @property
    def selected(self) -> bool:
        """Deprecated v1 readback; absent from serialized v2 rows."""
        return not self.block_reasons

    @property
    def drop_reason(self) -> str | None:
        """Deprecated v1 readback; v2 preserves ordered block reasons."""
        return self.block_reasons[0] if self.block_reasons else None


@dataclass(frozen=True, slots=True)
class EligibleDecisionRecord:
    envelope: RecordEnvelope
    decision_id: str
    candidate_id: str
    direction: Direction
    execution_profile_hash: str
    entry_family: str
    entry_cursor: str
    entry_ticks: int
    stop_ticks: int
    risk_ticks: int
    target_ticks: int
    passed_guards: tuple[str, ...]
    geometry: GeometryEvidence

    @property
    def tp_ticks(self) -> int:
        return self.target_ticks


@dataclass(frozen=True, slots=True)
class ExecutedTradeRecord:
    envelope: RecordEnvelope
    trade_id: str
    decision_id: str
    candidate_id: str
    direction: Direction
    status: str  # resolved | open_unresolved
    resolution: str | None  # target | stop | dataset_exhaustion
    entry_family: str
    entry_cursor: str
    resolution_cursor: str | None
    entry_ts_utc: datetime
    resolution_ts_utc: datetime | None
    entry_ticks: int
    stop_ticks: int
    target_ticks: int
    risk_ticks: int
    bars_after_entry_to_resolution: int | None
    mfe_ticks: int
    mae_ticks: int
    realized_ticks: int | None
    realized_r: float | None
    geometry: GeometryEvidence


@dataclass(frozen=True, slots=True)
class CandidateLabelRecord:
    envelope: RecordEnvelope
    candidate_label_id: str
    candidate_id: str
    label_family: str
    r_multiple: float
    label: str
    bars_after_entry_to_resolution: int | None
    mfe_r: float
    mae_r: float
    censored: bool
    censor_reason: str | None


@dataclass(frozen=True, slots=True)
class GeometryDossierRecord:
    envelope: RecordEnvelope
    candidate_id: str
    decision_id: str | None
    trade_id: str | None
    geometry: GeometryEvidence


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    envelope: RecordEnvelope
    quarantine_id: str
    candidate_id: str
    reasons: tuple[str, ...]
    evidence_cursor: str


@dataclass(frozen=True, slots=True)
class SetupResolutionRecord:
    """Read-only v1 compatibility record; never an executed-trade input."""

    envelope: RecordEnvelope
    resolution: str
    direction: Direction
    entry_family: str | None
    entry_ticks: int | None
    stop_ticks: int | None
    tp_ticks: int | None
    mfe_ticks: int | None
    mae_ticks: int | None
    bars_in_trade: int | None
    tap_ts_utc: datetime
    parent_confirmed_ts_utc: datetime | None
    lock_ts_utc: datetime | None
    armed_ts_utc: datetime | None
    inversion_ts_utc: datetime | None
    entry_ts_utc: datetime | None
    htf_fvg_id: str
    parent_fvg_id: str | None
    opposing_fvg_id: str | None


@dataclass(frozen=True, slots=True)
class IfvgEmission:
    kind: str
    record: object


# ── FSM audit channel (parallel to the v2 emission trace; never in-band) ─────
#
# Audit records ride a SEPARATE per-step-drained channel so the v2 trace —
# whose QL-assigned ``trace_ordinal`` and column union are content-hashed in
# accepted artifacts — is byte-identical with the channel on or off. Every
# audit record carries an :class:`AuditStamp` fixing one total order across
# both channels.

IFVG_AUDIT_RECORD_SCHEMA_VERSION = 1

AUDIT_SUBSTEP_CONTEXT_FILL = "01_context_fill_maintenance"
AUDIT_SUBSTEP_PRETRADE_INVALIDATION = "02_pretrade_invalidation"
AUDIT_SUBSTEP_FSM_TRANSITION = "03_fsm_transition"
AUDIT_SUBSTEP_CANDIDATE_INTAKE = "04_candidate_intake"
AUDIT_SUBSTEP_PARENTLESS = "05_parentless_instrumentation"
AUDIT_SUBSTEP_RESOLUTION = "06_resolution"


def make_audit_event_id(kind: str, *parts: object) -> str:
    return _uuid5(f"audit_{kind}", *parts)


@dataclass(frozen=True, slots=True)
class AuditStamp:
    """Cross-channel ordering contract carried by EVERY audit record.

    ``core_trace_ordinal_before``/``_after`` are DAY-LOCAL ordinals of the
    core (non-funnel) emissions bracketing this record — the audit row sits
    strictly between core rows ``before`` and ``after`` (``before`` is ``-1``
    when no core row precedes it that day). QL adds the day's chain offset to
    obtain global ``trace_ordinal`` brackets. Verifier ordering:
    ``source_step_ordinal → reducer_substep → reducer_substep_ordinal →
    audit_seq``; timestamps are a display fallback only. Ties are a test
    failure.
    """

    audit_schema_version: int
    source_step_ordinal: int
    source_bar_id: str
    source_bar_cursor: str
    reducer_substep: str
    reducer_substep_ordinal: int
    core_trace_ordinal_before: int
    core_trace_ordinal_after: int
    audit_seq: int


@dataclass(frozen=True, slots=True)
class FvgFillEventRecord:
    """One registry maintenance outcome (touch/fill/eviction) with setup
    linkage resolved from live state at the emission moment — never recovered
    later by timestamp matching."""

    envelope: RecordEnvelope
    stamp: AuditStamp
    event_kind: str  # first_touch | filled | evicted_age | evicted_cap
    fvg: Fvg
    bar: BarEvidence  # the 1m execution bar of the emission step
    prior_reached_ticks: int | None
    new_reached_ticks: int | None
    prior_penetration_ticks: int
    new_penetration_ticks: int
    far_boundary_ticks: int
    fill_depth_ticks: int
    remaining_fraction_after: float
    wick_crossed_far_boundary: bool | None  # None: cap eviction has no bar
    body_closed_through_far_boundary: bool | None
    age_seconds: int
    age_trading_days: int
    registry_live_count_after: int
    setup_id: str | None
    fvg_role: str  # htf | parent | opposing | entry | registry_only
    selected_for_setup: bool
    setup_phase_before: str
    setup_phase_after: str
    linked_slot_death_event_id: str | None
    linked_setup_resolution_event_id: str | None


@dataclass(frozen=True, slots=True)
class EntryCausalityRecord:
    """The entry-joint causality counterfactual, candidate-keyed (exact join
    to the v2 ``entry_candidate`` row; that schema is untouched)."""

    envelope: RecordEnvelope
    stamp: AuditStamp
    candidate_id: str
    setup_id: str
    entry_family: str
    entry_fvg_id: str | None  # None for the retest family (no entry gap)
    policy: str
    trigger_ts_utc: datetime | None
    confirmed_after: bool | None  # None when the family has no entry gap
    fully_formed_after: bool | None
    satisfied: bool


@dataclass(frozen=True, slots=True)
class ParentSlotDeathRecord:
    """Provisional-parent death (S1) or setup-terminal death at any stage,
    with the fill-depth and window-clock evidence the lifecycle row lacks."""

    envelope: RecordEnvelope
    stamp: AuditStamp
    event_id: str
    setup_id: str
    phase: str  # phase at death
    death_reason: str
    death_ts_utc: datetime
    parent_fvg_id: str | None  # None: parentless expiry / no parent at death
    died_fvg_id: str | None  # gap whose fill caused death (htf or parent)
    setup_terminated: bool  # False only for S1 provisional-parent death
    lifecycle_event_id: str | None  # join key to the v2 lifecycle row
    bar: BarEvidence | None  # None: dataset-exhaustion death has no bar
    event_cursor: str
    physical_fill: bool
    structural_close: bool
    far_boundary_ticks: int | None
    prior_reached_ticks: int | None
    new_reached_ticks: int | None
    fill_depth_ticks: int | None
    wick_crossed_far_boundary: bool | None
    body_closed_through_far_boundary: bool | None
    parent_clocks: tuple[tuple[int, int], ...]
    remaining_window_bars_by_tf: tuple[tuple[int, int], ...]
    open_window_timeframes: tuple[int, ...]
    parentless_interval_started: bool


@dataclass(frozen=True, slots=True)
class FvgInvalidationEventRecord:
    """Structural-vs-physical parent invalidation evidence. Emitted at both
    branches even while the artifact shows zero structural terminal deaths —
    the contract supports the active rule."""

    envelope: RecordEnvelope
    stamp: AuditStamp
    event_id: str
    invalidation_kind: str  # physical_full_fill | structural_body_close
    setup_id: str
    parent_fvg_id: str
    phase: str
    source_timeframe_seconds: int
    source_bar: BarEvidence  # parent-TF bar for structural; 1m bar otherwise
    boundary_ticks: int
    close_through_margin_ticks: int | None  # structural only
    strict_comparison_result: bool


@dataclass(frozen=True, slots=True)
class ParentWindowEventRecord:
    """Parent reaction-window timeline: opened / parent_selected /
    parent_cleared, with the clocks snapshot at the event."""

    envelope: RecordEnvelope
    stamp: AuditStamp
    event_id: str
    event_kind: str  # opened | parent_selected | parent_cleared
    setup_id: str
    parent_fvg_id: str | None  # None for opened / cleared-to-empty
    prior_parent_fvg_id: str | None  # replacement evidence
    parent_clocks: tuple[tuple[int, int], ...]
    open_window_timeframes: tuple[int, ...]
    event_cursor: str


@dataclass(frozen=True, slots=True)
class ParentlessStepRecord:
    """One counted parentless S1 bar — 1:1 with each
    ``parentless_window_live`` increment, so interval derivation reconciles
    exactly by construction. QL groups consecutive steps into intervals."""

    envelope: RecordEnvelope
    stamp: AuditStamp
    setup_id: str
    bar: BarEvidence
    parent_clocks: tuple[tuple[int, int], ...]
    open_window_timeframes: tuple[int, ...]
