"""Typed research emissions for ``ifvg_smc`` — QL serializes these verbatim.

Design rules (IFVG window rulings):

* Every record rides one :class:`RecordEnvelope` (schema/strategy/profile/day/
  instant/setup identity) so a flattened row is self-describing and joinable.
* DROPPED CANDIDATES ARE THE SAME TABLE: candidate-stage records carry
  ``selected`` + ``drop_reason`` instead of living in a shadow table — the
  scored-but-not-selected rows that make selection policy measurable offline.
* CAUSALITY IS DERIVABLE, NEVER BAKED: structure records carry the raw per-joint
  timestamps (``a_open_ts_utc`` / ``confirmed_ts_utc`` vs the stage trigger) AND
  the two convenience booleans, so ``confirmed_after`` / ``fully_formed_after``
  families are row filters downstream.
* Stdlib only, frozen ``slots`` dataclasses; QL flattens via
  ``dataclasses.asdict``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping

from strategy_core.structures.fvg import Fvg
from strategy_core.structures.sweeps import SweepResult
from strategy_core.types import Direction

__all__ = [
    "IFVG_RECORD_SCHEMA_VERSION",
    "RecordEnvelope",
    "DayFunnelRecord",
    "HtfTapRecord",
    "ParentCandidateRecord",
    "ParentLockRecord",
    "OpposingGapRecord",
    "InversionRecord",
    "EntryCandidateRecord",
    "SetupResolutionRecord",
    "IfvgEmission",
]

#: Bumped on ANY shape change of the records below; QL stamps it per row and
#: fails closed on unknown versions (capture-cache trust discipline).
IFVG_RECORD_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class RecordEnvelope:
    """Identity every emission carries."""

    schema_version: int
    strategy_id: str
    strategy_version: str
    profile_hash: str
    trading_day: date
    ts_utc: datetime
    setup_id: str  # "" for pre-setup records (e.g. conflicted taps)


@dataclass(frozen=True, slots=True)
class DayFunnelRecord:
    """Tier-1 per-day counters (stage passes + every drop reason)."""

    envelope: RecordEnvelope
    counters: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class HtfTapRecord:
    """One live HTF gap wick-tapped by a 1m bar (every tap emits, winner or not)."""

    envelope: RecordEnvelope
    htf_tf_seconds: int
    fvg: Fvg
    direction: Direction
    penetration_ticks: int
    ce_reached: bool
    htf_age_seconds: int
    remaining_fraction: float
    registry_live_count: int
    rank: int  # 0 = the would-be winner under 4H>1H, newest-wins
    conflicted: bool
    nearest_level_kind: str | None
    nearest_level_distance_ticks: int | None
    session_engine: str
    session_doc: str
    selected: bool
    drop_reason: str | None  # conflicted | slot_occupied | outranked


@dataclass(frozen=True, slots=True)
class ParentCandidateRecord:
    """A same-direction parent-TF FVG arriving while the setup searches (S1)."""

    envelope: RecordEnvelope
    parent_tf_seconds: int
    fvg: Fvg
    distance_to_htf_ticks: int
    elapsed_1m_bars_since_tap: int
    confirmed_after: bool  # fvg.confirmed_ts >  tap_ts (doc-default causality)
    fully_formed_after: bool  # fvg.a_open_ts   >= tap_ts (ICT-clean causality)
    rank: int
    selected: bool
    drop_reason: str | None  # outranked | replaced_by_newer | distance_gt_capture


@dataclass(frozen=True, slots=True)
class ParentLockRecord:
    """The 1m retest that locked the selected parent (S1 -> S2)."""

    envelope: RecordEnvelope
    parent_fvg_id: str
    penetration_ticks: int
    ce_reached: bool
    elapsed_1m_bars_since_selection: int


@dataclass(frozen=True, slots=True)
class OpposingGapRecord:
    """A counter-direction 1m FVG arming (or replacing) the manipulation slot."""

    envelope: RecordEnvelope
    fvg: Fvg
    distance_to_parent_ticks: int
    elapsed_1m_bars_since_lock: int
    confirmed_after: bool  # vs lock_ts
    fully_formed_after: bool
    selected: bool
    drop_reason: str | None  # replaced_by_newer | distance_gt_capture


@dataclass(frozen=True, slots=True)
class InversionRecord:
    """The 1m body close back through the armed opposing gap (S3 -> S4)."""

    envelope: RecordEnvelope
    opposing_fvg_id: str
    close_through_margin_ticks: int
    bars_armed_to_inversion: int
    opposing_size_ticks: int
    sweep: SweepResult


@dataclass(frozen=True, slots=True)
class EntryCandidateRecord:
    """An entry signal under either family (both are always watched; the
    non-selected family emits ``selected=False`` — explicit family pooling)."""

    envelope: RecordEnvelope
    entry_family: str  # "fresh_fvg_continuation" | "ifvg_retest"
    entry_fvg: Fvg | None  # the fresh 1m gap (fresh family only)
    entry_ticks: int
    stop_ticks: int
    risk_ticks: int
    tp_ticks: int
    bars_since_inversion: int
    entry_to_parent_ticks: int
    in_engine_session: str
    in_doc_session: str
    selected: bool
    drop_reason: str | None  # family_not_selected | risk_lt_min | already_in_trade


@dataclass(frozen=True, slots=True)
class SetupResolutionRecord:
    """Terminal record per setup: trade outcome, expiry, or invalidation.

    ``resolution`` ∈ resolved_tp | resolved_sl | resolved_eod |
    expired_parent_search | expired_lock_wait | expired_armed |
    expired_entry_wait | invalidated_htf_filled | invalidated_parent_filled |
    invalidated_parent_structural. The full stage-timestamp chain makes every
    doc §12 audit question answerable by joining on ``setup_id``.
    """

    envelope: RecordEnvelope
    resolution: str
    direction: Direction
    entry_family: str | None
    entry_ticks: int | None
    stop_ticks: int | None
    tp_ticks: int | None
    mfe_ticks: int | None  # running favorable excursion (in-trade phases only)
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
    """Kind-tagged wrapper so a heterogeneous emission stream stays typed."""

    kind: str  # "htf_tap" | "parent_candidate" | "parent_lock" | "opposing" |
    #            "inversion" | "entry_candidate" | "resolution" | "funnel"
    record: object
