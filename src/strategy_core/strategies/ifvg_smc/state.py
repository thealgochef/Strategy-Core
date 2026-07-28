"""Cross-day carry for ``ifvg_smc`` — the day-seed seam the QL cache chain trusts.

One :class:`IfvgDaySeed` is everything ``run_day`` needs to continue exactly
where the prior day ended: per-timeframe FVG registry snapshots (INCLUDING the
detector tails — cross-boundary triplets are load-bearing, census E3), the
swing tracker, and the in-flight reducer state (owner default: a pre-entry
setup CARRIES across the 18:00 roll). Levels are deliberately absent: the level
timeline is the driver's input (QL's Phase-A artifact, seeded via the
``prior_day``/``prior_day_session_extremes`` walks).

``seed_hash`` is the trust stamp: a per-day capture cache is valid only if the
seed ENTERING that day hashes identically (the ``prev_full_hl`` lesson,
generalized). Canonical form: dataclasses to sorted-key JSON with dates/
datetimes as isoformat — deterministic across sessions and platforms.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum

from strategy_core.structures.fvg import FvgRegistrySnapshot
from strategy_core.structures.swings import SwingSnapshot

from .reducer import IfvgReducerSnapshot

__all__ = ["IFVG_SEED_SCHEMA_VERSION", "IfvgDaySeed", "seed_hash"]

IFVG_SEED_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class IfvgDaySeed:
    """State at the END of ``source_day`` == the state ENTERING the next day."""

    schema_version: int
    profile_hash: str
    source_day: date
    registries: tuple[FvgRegistrySnapshot, ...]  # one per configured timeframe
    swings: SwingSnapshot
    reducer: IfvgReducerSnapshot | None


def _canon(obj: object) -> object:
    """Recursive canonicalization for hashing (dataclass -> dict, ts -> iso)."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _canon(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [_canon(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _canon(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    return obj


def seed_hash(seed: IfvgDaySeed) -> str:
    payload = json.dumps(_canon(seed), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
