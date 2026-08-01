"""Shared identity, provenance, and validity primitives for deterministic context.

This module is intentionally strategy-neutral.  The IFVG observer supplies the
feature/config identities, while the bounded structure, displacement, and liquidity
trackers use the same immutable envelope.  No outcome or execution type is imported
here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum, StrEnum
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid5

__all__ = [
    "AnchorStatus",
    "ContextIdentity",
    "ContextRecord",
    "MissingReason",
    "canonical_json",
    "canonical_sha256",
    "context_uuid",
    "record_provenance",
]


class MissingReason(StrEnum):
    INSUFFICIENT_CONFIRMED_SWINGS = "insufficient_confirmed_swings"
    INSUFFICIENT_OBSERVATIONS = "insufficient_observations"
    INSUFFICIENT_PAIRS = "insufficient_pairs"
    SOURCE_GAP = "source_gap"
    SOURCE_BAR_MISSING = "source_bar_missing"
    SOURCE_PARTITION_UNAVAILABLE = "source_partition_unavailable"
    SOURCE_UNAVAILABLE = "source_unavailable"
    ZERO_RANGE = "zero_range"
    ZERO_MEAN_TRUE_RANGE = "zero_mean_true_range"
    ZERO_LOCAL_RANGE = "zero_local_range"
    NO_BREAK = "no_break"
    NO_ACTIVE_POOL = "no_active_pool"
    NO_QUALIFYING_SWEEP = "no_qualifying_sweep"
    NOT_APPLICABLE = "not_applicable"
    STATE_VERSION_MISMATCH = "state_version_mismatch"


class AnchorStatus(StrEnum):
    RATIFIED = "ratified"
    EXPERIMENTAL_Q40_OPEN = "experimental_q40_open"


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    return value


def canonical_json(value: Any) -> str:
    """Canonical JSON used by every context hash and deterministic identifier."""

    return json.dumps(
        _canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


_CONTEXT_NAMESPACE = UUID("542d88f4-b509-59a6-a46a-e3cfc0d45888")


def context_uuid(*parts: object) -> UUID:
    """Stable UUIDv5 over unambiguous canonical components."""

    return uuid5(_CONTEXT_NAMESPACE, canonical_json(parts))


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextIdentity:
    schema_version: int
    feature_set_version: str
    feature_formula_version: str
    feature_schema_hash: str
    context_config_hash: str
    strategy_core_commit: str
    strategy_core_source_tree_hash: str
    symbol: str
    tick_size: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextRecord:
    """Common point-in-time provenance envelope from the frozen contract."""

    schema_version: int
    feature_set_version: str
    feature_formula_version: str
    feature_schema_hash: str
    context_config_hash: str
    strategy_core_commit: str
    strategy_core_source_tree_hash: str
    symbol: str
    tick_size: str
    as_of_ts: datetime
    as_of_cursor: str
    source_close_ts: datetime | None
    source_confirmed_ts: datetime | None
    valid: bool
    warmup_complete: bool
    source_available: bool
    missing_reason: MissingReason | None

    def to_dict(self) -> dict[str, Any]:
        return json.loads(canonical_json(self))


def record_provenance(
    identity: ContextIdentity,
    *,
    as_of_ts: datetime,
    as_of_cursor: str,
    source_close_ts: datetime | None,
    source_confirmed_ts: datetime | None,
    valid: bool,
    warmup_complete: bool,
    source_available: bool,
    missing_reason: MissingReason | None,
) -> dict[str, Any]:
    """Keyword payload for a :class:`ContextRecord` subclass constructor."""

    return {
        "schema_version": identity.schema_version,
        "feature_set_version": identity.feature_set_version,
        "feature_formula_version": identity.feature_formula_version,
        "feature_schema_hash": identity.feature_schema_hash,
        "context_config_hash": identity.context_config_hash,
        "strategy_core_commit": identity.strategy_core_commit,
        "strategy_core_source_tree_hash": identity.strategy_core_source_tree_hash,
        "symbol": identity.symbol,
        "tick_size": identity.tick_size,
        "as_of_ts": as_of_ts,
        "as_of_cursor": as_of_cursor,
        "source_close_ts": source_close_ts,
        "source_confirmed_ts": source_confirmed_ts,
        "valid": valid,
        "warmup_complete": warmup_complete,
        "source_available": source_available,
        "missing_reason": missing_reason,
    }
