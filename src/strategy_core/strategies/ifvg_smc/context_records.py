"""Typed v1 IFVG context records, separate from immutable v2 strategy records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID

from strategy_core.structures.context import ContextRecord
from strategy_core.structures.displacement import DisplacementWindowSummary
from strategy_core.structures.equal_levels import (
    EqualLevelPoolLifecycleEvent,
    EqualLevelSweepLink,
    NearestPoolReference,
)
from strategy_core.structures.market_structure import (
    MarketStructureState,
    MtfConfluenceSnapshot,
    StructureTransitionDelta,
)

_COMMON_PROVENANCE_KEYS = {
    "schema_version",
    "feature_set_version",
    "feature_formula_version",
    "feature_schema_hash",
    "context_config_hash",
    "strategy_core_commit",
    "strategy_core_source_tree_hash",
    "symbol",
    "tick_size",
}

_EVENT_PROVENANCE_KEYS = _COMMON_PROVENANCE_KEYS | {
    "as_of_ts",
    "as_of_cursor",
    "source_close_ts",
    "source_confirmed_ts",
    "valid",
    "warmup_complete",
    "source_available",
    "missing_reason",
}


def _compact_record(
    record: ContextRecord,
    inherited: Mapping[str, Any],
) -> dict[str, Any]:
    """Serialize a nested live record without repeating event provenance."""

    payload = record.to_dict()
    for key in _COMMON_PROVENANCE_KEYS:
        payload.pop(key, None)
    for key in _EVENT_PROVENANCE_KEYS - _COMMON_PROVENANCE_KEYS:
        if key in payload and payload[key] == inherited.get(key):
            payload.pop(key)
    return payload


def _compact_pool_lifecycle(
    record: EqualLevelPoolLifecycleEvent,
    inherited: Mapping[str, Any],
) -> dict[str, Any]:
    lifecycle = record.to_dict()
    payload = _compact_record(record, inherited)
    pool = payload.get("pool")
    if isinstance(pool, dict):
        for key in _COMMON_PROVENANCE_KEYS:
            pool.pop(key, None)
        for key in _EVENT_PROVENANCE_KEYS - _COMMON_PROVENANCE_KEYS:
            if key in pool and pool[key] == lifecycle.get(key):
                pool.pop(key)
    return payload

__all__ = [
    "CaptureKind",
    "ContextStateSnapshot",
    "IfvgContextCapture",
    "IfvgContextEvent",
]


class CaptureKind(StrEnum):
    HTF_TAP = "htf_tap"
    PARENT_CANDIDATE = "parent_candidate"
    PARENT_REPLACEMENT = "parent_replacement"
    PARENT_LOCK = "parent_lock"
    OPPOSING_CANDIDATE = "opposing_candidate"
    OPPOSING_REPLACEMENT = "opposing_replacement"
    INVERSION = "inversion"
    ENTRY_CANDIDATE = "entry_candidate"
    ELIGIBLE_DECISION = "eligible_decision"
    EXECUTED_TRADE_LINK = "executed_trade_link"


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextStateSnapshot(ContextRecord):
    context_state_id: UUID
    state_payload_hash: str
    setup_id: str
    setup_direction: str
    mtf_snapshot_id: UUID
    local_structure_state_id: UUID
    active_pool_state_hash: str
    mtf_snapshot: MtfConfluenceSnapshot
    nearest_context: Mapping[str, NearestPoolReference | None]
    containing_pool_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class IfvgContextCapture(ContextRecord):
    context_capture_id: UUID
    capture_kind: CaptureKind
    context_state_id: UUID
    setup_id: str
    candidate_id: str | None
    decision_id: str | None
    trade_id: str | None
    evidence_id: str
    evidence_cursor: str
    displacement_window_ids: tuple[UUID, ...]
    structure_delta_ids: tuple[UUID, ...]
    opposing_leg_sweep_link_ids: tuple[UUID, ...]
    selected_opposing_leg_sweep_link_id: UUID | None
    frozen_from_capture_id: UUID | None


@dataclass(frozen=True, slots=True)
class IfvgContextEvent:
    """One additive transition event for offline normalization or live transport."""

    capture: IfvgContextCapture
    state: ContextStateSnapshot
    structure_states: tuple[MarketStructureState, ...] = ()
    structure_deltas: tuple[StructureTransitionDelta, ...] = ()
    displacement_windows: tuple[DisplacementWindowSummary, ...] = ()
    pool_lifecycle_events: tuple[EqualLevelPoolLifecycleEvent, ...] = ()
    sweep_links: tuple[EqualLevelSweepLink, ...] = ()

    @property
    def context_capture_id(self) -> UUID:
        return self.capture.context_capture_id

    def to_dict(self) -> dict[str, Any]:
        capture_full = self.capture.to_dict()
        provenance = {
            key: capture_full[key] for key in sorted(_EVENT_PROVENANCE_KEYS)
        }
        capture = {
            key: value
            for key, value in capture_full.items()
            if key not in _EVENT_PROVENANCE_KEYS
        }
        state = _compact_record(self.state, provenance)
        # Capture and state are one event and therefore share setup identity.
        state.pop("setup_id", None)
        state.pop("mtf_snapshot", None)
        mtf = _compact_record(self.state.mtf_snapshot, provenance)
        mtf.pop("states", None)
        mtf.pop("local_state", None)
        return {
            "provenance": provenance,
            "capture": capture,
            "state": state,
            "mtf_snapshot": mtf,
            "structure_states": [
                _compact_record(item, provenance) for item in self.structure_states
            ],
            "structure_deltas": [
                _compact_record(item, provenance) for item in self.structure_deltas
            ],
            "displacement_windows": [
                _compact_record(item, provenance) for item in self.displacement_windows
            ],
            "pool_lifecycle_events": [
                _compact_pool_lifecycle(item, provenance)
                for item in self.pool_lifecycle_events
            ],
            "sweep_links": [
                _compact_record(item, provenance) for item in self.sweep_links
            ],
        }

    def serialized_size(self) -> int:
        return len(
            json.dumps(
                self.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )
