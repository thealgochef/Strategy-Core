"""Bounded deterministic equal-high/equal-low pools and exact sweep links."""

from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

from strategy_core.structures.context import (
    ContextIdentity,
    ContextRecord,
    context_uuid,
    record_provenance,
)
from strategy_core.structures.market_structure import (
    ConfirmedSwingEvidence,
)
from strategy_core.structures.sweeps import (
    strict_pool_reclaim_distance,
    strict_pool_sweep_depth,
)
from strategy_core.types import Bar, BarKind, Direction, Side

__all__ = [
    "EqualLevelPool",
    "EqualLevelPoolLifecycleEvent",
    "EqualLevelPoolTracker",
    "EqualLevelPoolTrackerSnapshot",
    "EqualLevelSweepLink",
    "NearestPoolReference",
    "PoolType",
    "interval_distance_ticks",
]

EQUAL_LEVEL_SNAPSHOT_SCHEMA_VERSION = 3


class PoolType(StrEnum):
    EQH = "eqh"
    EQL = "eql"


def interval_distance_ticks(price_ticks: int, lower: int, upper: int) -> int:
    if price_ticks < lower:
        return lower - price_ticks
    if price_ticks > upper:
        return price_ticks - upper
    return 0


@dataclass(frozen=True, slots=True, kw_only=True)
class EqualLevelPool(ContextRecord):
    pool_id: UUID
    pool_type: PoolType
    source_timeframe: str
    source_timeframe_seconds: int
    lower_bound_ticks: int
    upper_bound_ticks: int
    representative_price_ticks: int
    member_swing_ids: tuple[UUID, ...]
    swing_count: int
    first_pivot_ts: datetime
    latest_pivot_ts: datetime
    confirmation_ts: datetime
    last_update_ts: datetime
    last_update_cursor: str
    absolute_separation_ticks: int
    atr14_ticks: float | None
    local_range20_ticks: int | None
    separation_normalized_by_atr: float | None
    separation_normalized_by_local_range: float | None
    active: bool
    swept: bool
    sweep_link_id: UUID | None
    sweep_ts: datetime | None
    reclaimed: bool
    reclaim_ts: datetime | None
    invalidation_reason: str | None
    expiration_reason: str | None
    tolerance_policy: str
    lifecycle_version: int


@dataclass(frozen=True, slots=True, kw_only=True)
class EqualLevelSweepLink(ContextRecord):
    sweep_link_id: UUID
    pool_id: UUID
    pool_type: PoolType
    source_timeframe: str
    source_timeframe_seconds: int
    sweep_bar_id: str
    sweep_cursor: str
    sweep_ts: datetime
    sweep_depth_ticks: int
    sweep_depth_normalized: float | None
    reclaimed_after_sweep: bool
    reclaim_bar_id: str | None
    reclaim_ts: datetime | None
    reclaim_latency_bars: int | None
    reclaim_close_distance_ticks: int | None
    reclaim_close_distance_normalized: float | None
    setup_id: str | None
    opposing_fvg_id: str | None
    parent_lock_cursor: str | None
    inversion_cursor: str | None
    qualifies_opposing_leg: bool
    distance_at_lock_ticks: int | None = None
    distance_at_lock_normalized: float | None = None


_SweepLinkSeed = tuple[
    datetime,
    str,
    datetime | None,
    datetime | None,
    UUID,
    UUID,
    PoolType,
    str,
    int,
    str,
    str,
    datetime,
    int,
    float | None,
    bool,
    str | None,
    datetime | None,
    int | None,
    int | None,
    float | None,
    str | None,
    str | None,
    str | None,
    str | None,
    bool,
    int | None,
    float | None,
]


def _sweep_link_seed(link: EqualLevelSweepLink) -> _SweepLinkSeed:
    return (
        link.as_of_ts,
        link.as_of_cursor,
        link.source_close_ts,
        link.source_confirmed_ts,
        link.sweep_link_id,
        link.pool_id,
        link.pool_type,
        link.source_timeframe,
        link.source_timeframe_seconds,
        link.sweep_bar_id,
        link.sweep_cursor,
        link.sweep_ts,
        link.sweep_depth_ticks,
        link.sweep_depth_normalized,
        link.reclaimed_after_sweep,
        link.reclaim_bar_id,
        link.reclaim_ts,
        link.reclaim_latency_bars,
        link.reclaim_close_distance_ticks,
        link.reclaim_close_distance_normalized,
        link.setup_id,
        link.opposing_fvg_id,
        link.parent_lock_cursor,
        link.inversion_cursor,
        link.qualifies_opposing_leg,
        link.distance_at_lock_ticks,
        link.distance_at_lock_normalized,
    )


def _sweep_link_from_seed(
    seed: _SweepLinkSeed,
    *,
    identity: ContextIdentity,
) -> EqualLevelSweepLink:
    (
        as_of_ts,
        as_of_cursor,
        source_close_ts,
        source_confirmed_ts,
        sweep_link_id,
        pool_id,
        pool_type,
        source_timeframe,
        source_timeframe_seconds,
        sweep_bar_id,
        sweep_cursor,
        sweep_ts,
        sweep_depth_ticks,
        sweep_depth_normalized,
        reclaimed_after_sweep,
        reclaim_bar_id,
        reclaim_ts,
        reclaim_latency_bars,
        reclaim_close_distance_ticks,
        reclaim_close_distance_normalized,
        setup_id,
        opposing_fvg_id,
        parent_lock_cursor,
        inversion_cursor,
        qualifies_opposing_leg,
        distance_at_lock_ticks,
        distance_at_lock_normalized,
    ) = seed
    return EqualLevelSweepLink(
        **record_provenance(
            identity,
            as_of_ts=as_of_ts,
            as_of_cursor=as_of_cursor,
            source_close_ts=source_close_ts,
            source_confirmed_ts=source_confirmed_ts,
            valid=True,
            warmup_complete=True,
            source_available=True,
            missing_reason=None,
        ),
        sweep_link_id=sweep_link_id,
        pool_id=pool_id,
        pool_type=pool_type,
        source_timeframe=source_timeframe,
        source_timeframe_seconds=source_timeframe_seconds,
        sweep_bar_id=sweep_bar_id,
        sweep_cursor=sweep_cursor,
        sweep_ts=sweep_ts,
        sweep_depth_ticks=sweep_depth_ticks,
        sweep_depth_normalized=sweep_depth_normalized,
        reclaimed_after_sweep=reclaimed_after_sweep,
        reclaim_bar_id=reclaim_bar_id,
        reclaim_ts=reclaim_ts,
        reclaim_latency_bars=reclaim_latency_bars,
        reclaim_close_distance_ticks=reclaim_close_distance_ticks,
        reclaim_close_distance_normalized=reclaim_close_distance_normalized,
        setup_id=setup_id,
        opposing_fvg_id=opposing_fvg_id,
        parent_lock_cursor=parent_lock_cursor,
        inversion_cursor=inversion_cursor,
        qualifies_opposing_leg=qualifies_opposing_leg,
        distance_at_lock_ticks=distance_at_lock_ticks,
        distance_at_lock_normalized=distance_at_lock_normalized,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class EqualLevelPoolLifecycleEvent(ContextRecord):
    lifecycle_event_id: UUID
    event_type: str
    pool: EqualLevelPool
    member_swing_id: UUID | None


@dataclass(frozen=True, slots=True)
class NearestPoolReference:
    pool_id: UUID
    pool_type: PoolType
    source_timeframe: str
    source_timeframe_seconds: int
    lower_bound_ticks: int
    upper_bound_ticks: int
    representative_price_ticks: int
    distance_ticks: int
    distance_normalized_by_atr: float | None
    swing_count: int
    age_minutes: float
    span_minutes: float
    width_ticks: int
    width_normalized_by_atr: float | None
    creation_separation_ticks: int
    creation_separation_normalized_by_atr: float | None
    creation_separation_normalized_by_local_range: float | None


@dataclass(slots=True)
class _EqualSwing:
    swing_id: UUID
    source_timeframe: str
    source_timeframe_seconds: int
    side: Side
    price_ticks: int
    pivot_ts: datetime
    confirmation_ts: datetime
    availability_cursor: str


_EqualSwingSeed = tuple[UUID, str, int, Side, int, datetime, datetime, str]


def _equal_swing(swing: ConfirmedSwingEvidence) -> _EqualSwing:
    return _EqualSwing(
        swing_id=swing.swing_id,
        source_timeframe=swing.source_timeframe,
        source_timeframe_seconds=swing.source_timeframe_seconds,
        side=swing.side,
        price_ticks=swing.price_ticks,
        pivot_ts=swing.pivot_ts,
        confirmation_ts=swing.confirmation_ts,
        availability_cursor=swing.availability_cursor,
    )


def _equal_swing_seed(swing: _EqualSwing) -> _EqualSwingSeed:
    return (
        swing.swing_id,
        swing.source_timeframe,
        swing.source_timeframe_seconds,
        swing.side,
        swing.price_ticks,
        swing.pivot_ts,
        swing.confirmation_ts,
        swing.availability_cursor,
    )


def _equal_swing_from_seed(seed: _EqualSwingSeed) -> _EqualSwing:
    return _EqualSwing(*seed)


@dataclass(slots=True)
class _PoolState:
    pool_id: UUID
    pool_type: PoolType
    timeframe: str
    timeframe_seconds: int
    members: list[_EqualSwing]
    lower: int
    upper: int
    representative: int
    confirmation_ts: datetime
    confirmation_cursor: str
    last_update_ts: datetime
    last_update_cursor: str
    separation: int
    creation_atr: float | None
    creation_range: int | None
    active: bool = True
    swept: bool = False
    sweep_link_id: UUID | None = None
    sweep_ts: datetime | None = None
    reclaimed: bool = False
    reclaim_ts: datetime | None = None
    invalidation_reason: str | None = None
    lifecycle_version: int = 1


@dataclass(frozen=True, slots=True)
class _PoolStateSnapshot:
    pool_id: UUID
    pool_type: PoolType
    timeframe: str
    timeframe_seconds: int
    members: tuple[_EqualSwingSeed, ...]
    lower: int
    upper: int
    representative: int
    confirmation_ts: datetime
    confirmation_cursor: str
    last_update_ts: datetime
    last_update_cursor: str
    separation: int
    creation_atr: float | None
    creation_range: int | None
    active: bool
    swept: bool
    sweep_link_id: UUID | None
    sweep_ts: datetime | None
    reclaimed: bool
    reclaim_ts: datetime | None
    invalidation_reason: str | None
    lifecycle_version: int


def _pool_state_snapshot(pool: _PoolState) -> _PoolStateSnapshot:
    return _PoolStateSnapshot(
        pool_id=pool.pool_id,
        pool_type=pool.pool_type,
        timeframe=pool.timeframe,
        timeframe_seconds=pool.timeframe_seconds,
        members=tuple(_equal_swing_seed(item) for item in pool.members),
        lower=pool.lower,
        upper=pool.upper,
        representative=pool.representative,
        confirmation_ts=pool.confirmation_ts,
        confirmation_cursor=pool.confirmation_cursor,
        last_update_ts=pool.last_update_ts,
        last_update_cursor=pool.last_update_cursor,
        separation=pool.separation,
        creation_atr=pool.creation_atr,
        creation_range=pool.creation_range,
        active=pool.active,
        swept=pool.swept,
        sweep_link_id=pool.sweep_link_id,
        sweep_ts=pool.sweep_ts,
        reclaimed=pool.reclaimed,
        reclaim_ts=pool.reclaim_ts,
        invalidation_reason=pool.invalidation_reason,
        lifecycle_version=pool.lifecycle_version,
    )


def _pool_state_from_snapshot(
    snapshot: _PoolStateSnapshot,
) -> _PoolState:
    return _PoolState(
        pool_id=snapshot.pool_id,
        pool_type=snapshot.pool_type,
        timeframe=snapshot.timeframe,
        timeframe_seconds=snapshot.timeframe_seconds,
        members=[_equal_swing_from_seed(item) for item in snapshot.members],
        lower=snapshot.lower,
        upper=snapshot.upper,
        representative=snapshot.representative,
        confirmation_ts=snapshot.confirmation_ts,
        confirmation_cursor=snapshot.confirmation_cursor,
        last_update_ts=snapshot.last_update_ts,
        last_update_cursor=snapshot.last_update_cursor,
        separation=snapshot.separation,
        creation_atr=snapshot.creation_atr,
        creation_range=snapshot.creation_range,
        active=snapshot.active,
        swept=snapshot.swept,
        sweep_link_id=snapshot.sweep_link_id,
        sweep_ts=snapshot.sweep_ts,
        reclaimed=snapshot.reclaimed,
        reclaim_ts=snapshot.reclaim_ts,
        invalidation_reason=snapshot.invalidation_reason,
        lifecycle_version=snapshot.lifecycle_version,
    )


@dataclass(frozen=True, slots=True)
class EqualLevelPoolTrackerSnapshot:
    schema_version: int
    tolerance_policy: str
    atr_period: int
    local_range_period: int
    max_active_per_timeframe: int
    max_members: int
    max_unmatched_per_side: int
    max_tombstones_per_timeframe: int
    source_bars: tuple[tuple[int, tuple[Bar, ...]], ...]
    pools: tuple[_PoolStateSnapshot, ...]
    unmatched: tuple[tuple[int, Side, tuple[_EqualSwingSeed, ...]], ...]
    tombstones: tuple[tuple[int, tuple[UUID, ...]], ...]
    links: tuple[_SweepLinkSeed, ...]
    link_probe_ordinals: tuple[tuple[UUID, int], ...]
    probe_ordinal: int


def _cursor(bar: Bar) -> str:
    return (
        f"{bar.availability_ts_utc.isoformat()}|{bar.timeframe_ticks}|"
        f"{bar.trading_day.isoformat()}|{bar.bar_id}"
    )


class EqualLevelPoolTracker:
    def __init__(
        self,
        *,
        identity: ContextIdentity,
        tolerance_policy: str = "instrument_tick_grid_one_tick_span_v1",
        atr_period: int = 14,
        local_range_period: int = 20,
        max_active_per_timeframe: int = 64,
        max_members: int = 16,
        max_unmatched_per_side: int = 64,
        max_tombstones_per_timeframe: int = 64,
    ) -> None:
        if tolerance_policy not in {
            "instrument_tick_grid_v1",
            "instrument_tick_grid_one_tick_span_v1",
        }:
            raise ValueError("unsupported equal-level tick-grid tolerance policy")
        self.identity = identity
        self.tolerance_policy = tolerance_policy
        self.atr_period = atr_period
        self.local_range_period = local_range_period
        self.max_active_per_timeframe = max_active_per_timeframe
        self.max_members = max_members
        self.max_unmatched_per_side = max_unmatched_per_side
        self.max_tombstones_per_timeframe = max_tombstones_per_timeframe
        self._bars: dict[int, list[Bar]] = {}
        self._pools: dict[UUID, _PoolState] = {}
        self._unmatched: dict[tuple[int, Side], list[_EqualSwing]] = {}
        self._membership: set[UUID] = set()
        self._tombstones: dict[int, list[UUID]] = {}
        self._links: dict[UUID, EqualLevelSweepLink] = {}
        self._link_probe_ordinals: dict[UUID, int] = {}
        self._scale_cache: dict[int, tuple[float | None, int | None]] = {}
        self._active_ids: set[UUID] = set()
        self._accepting_index: dict[tuple[int, PoolType, int], set[UUID]] = {}
        self._unmatched_index: dict[tuple[int, Side, int], set[UUID]] = {}
        self._unmatched_by_id: dict[UUID, _EqualSwing] = {}
        self._eqh_boundaries: list[tuple[int, str, UUID]] = []
        self._eql_boundaries: list[tuple[int, str, UUID]] = []
        self._unreclaimed_link_ids: set[UUID] = set()
        self._probe_ordinal = 0
        self._lifecycle: list[EqualLevelPoolLifecycleEvent] = []
        self._new_links: list[EqualLevelSweepLink] = []

    def on_source_bar(self, bar: Bar) -> None:
        if bar.kind is not BarKind.TIME or not bar.is_complete:
            return
        bars = self._bars.setdefault(bar.timeframe_ticks, [])
        if bars and (bar.availability_ts_utc, bar.bar_id) <= (
            bars[-1].availability_ts_utc,
            bars[-1].bar_id,
        ):
            raise ValueError("equal-level source bars must be strictly ordered")
        bars.append(bar)
        self._scale_cache.pop(bar.timeframe_ticks, None)
        keep = max(self.atr_period, self.local_range_period) + 1
        if len(bars) > keep:
            del bars[: len(bars) - keep]

    def _scales(self, timeframe_seconds: int) -> tuple[float | None, int | None]:
        cached = self._scale_cache.get(timeframe_seconds)
        if cached is not None:
            return cached
        bars = self._bars.get(timeframe_seconds, [])
        atr: float | None = None
        if len(bars) >= self.atr_period:
            selected = bars[-self.atr_period :]
            offset = len(bars) - len(selected)
            true_ranges: list[int] = []
            for index, bar in enumerate(selected):
                global_index = offset + index
                previous = bars[global_index - 1].close_ticks if global_index > 0 else bar.close_ticks
                true_ranges.append(
                    max(
                        bar.high_ticks - bar.low_ticks,
                        abs(bar.high_ticks - previous),
                        abs(bar.low_ticks - previous),
                    )
                )
            atr = sum(true_ranges) / len(true_ranges)
        local_range: int | None = None
        if len(bars) >= self.local_range_period:
            selected = bars[-self.local_range_period :]
            local_range = max(item.high_ticks for item in selected) - min(
                item.low_ticks for item in selected
            )
        scales = (atr, local_range)
        self._scale_cache[timeframe_seconds] = scales
        return scales

    def _add_active_index(self, pool: _PoolState) -> None:
        self._active_ids.add(pool.pool_id)
        self._accepting_index.setdefault(
            (pool.timeframe_seconds, pool.pool_type, pool.representative),
            set(),
        ).add(pool.pool_id)
        target = (
            self._eqh_boundaries
            if pool.pool_type is PoolType.EQH
            else self._eql_boundaries
        )
        boundary = pool.upper if pool.pool_type is PoolType.EQH else pool.lower
        insort(target, (boundary, str(pool.pool_id), pool.pool_id))

    def _remove_active_index(self, pool: _PoolState) -> None:
        self._active_ids.discard(pool.pool_id)
        key = (pool.timeframe_seconds, pool.pool_type, pool.representative)
        ids = self._accepting_index.get(key)
        if ids is not None:
            ids.discard(pool.pool_id)
            if not ids:
                del self._accepting_index[key]
        target = (
            self._eqh_boundaries
            if pool.pool_type is PoolType.EQH
            else self._eql_boundaries
        )
        boundary = pool.upper if pool.pool_type is PoolType.EQH else pool.lower
        target.remove((boundary, str(pool.pool_id), pool.pool_id))

    def _index_unmatched(self, swing: _EqualSwing) -> None:
        self._unmatched_by_id[swing.swing_id] = swing
        self._unmatched_index.setdefault(
            (swing.source_timeframe_seconds, swing.side, swing.price_ticks),
            set(),
        ).add(swing.swing_id)

    def _unindex_unmatched(self, swing: _EqualSwing) -> None:
        self._unmatched_by_id.pop(swing.swing_id, None)
        key = (swing.source_timeframe_seconds, swing.side, swing.price_ticks)
        ids = self._unmatched_index.get(key)
        if ids is not None:
            ids.discard(swing.swing_id)
            if not ids:
                del self._unmatched_index[key]

    def on_confirmed_swing(self, swing: ConfirmedSwingEvidence) -> UUID | None:
        if (
            not swing.valid
            or swing.swing_id in self._membership
            or swing.swing_id in self._unmatched_by_id
        ):
            return None
        return self._on_equal_swing(_equal_swing(swing))

    def _on_equal_swing(self, swing: _EqualSwing) -> UUID | None:
        pool_type = PoolType.EQH if swing.side is Side.HIGH else PoolType.EQL
        candidate_ids: set[UUID] = set()
        for price in range(swing.price_ticks - 1, swing.price_ticks + 2):
            candidate_ids.update(
                self._accepting_index.get(
                    (swing.source_timeframe_seconds, pool_type, price),
                    (),
                )
            )
        accepting = [
            self._pools[pool_id]
            for pool_id in candidate_ids
            if pool_id in self._active_ids
            and (
                pool := self._pools[pool_id]
            ).timeframe_seconds == swing.source_timeframe_seconds
            and pool.pool_type is pool_type
            and len(pool.members) < self.max_members
            and max(pool.upper, swing.price_ticks) - min(pool.lower, swing.price_ticks) <= 1
        ]
        if accepting:
            accepting.sort(
                key=lambda pool: (
                    abs(swing.price_ticks - pool.representative),
                    -pool.last_update_ts.timestamp(),
                    str(pool.pool_id),
                )
            )
            pool = accepting[0]
            self._remove_active_index(pool)
            pool.members.append(swing)
            pool.lower = min(pool.lower, swing.price_ticks)
            pool.upper = max(pool.upper, swing.price_ticks)
            pool.representative = self._representative(pool.members)
            pool.last_update_ts = swing.confirmation_ts
            pool.last_update_cursor = swing.availability_cursor
            pool.lifecycle_version += 1
            self._add_active_index(pool)
            self._membership.add(swing.swing_id)
            self._emit_lifecycle("updated", pool, swing.swing_id, swing.confirmation_ts, swing.availability_cursor)
            return pool.pool_id

        key = (swing.source_timeframe_seconds, swing.side)
        unmatched = self._unmatched.setdefault(key, [])
        compatible_ids: set[UUID] = set()
        for price in range(swing.price_ticks - 1, swing.price_ticks + 2):
            compatible_ids.update(
                self._unmatched_index.get(
                    (swing.source_timeframe_seconds, swing.side, price),
                    (),
                )
            )
        compatible = [
            self._unmatched_by_id[swing_id]
            for swing_id in compatible_ids
        ]
        if compatible:
            compatible.sort(
                key=lambda candidate: (
                    abs(candidate.price_ticks - swing.price_ticks),
                    -candidate.confirmation_ts.timestamp(),
                    str(candidate.swing_id),
                )
            )
            first = compatible[0]
            unmatched.remove(first)
            self._unindex_unmatched(first)
            members = sorted(
                (first, swing),
                key=lambda item: (item.confirmation_ts, item.availability_cursor, str(item.swing_id)),
            )
            pool_id = context_uuid(
                self.identity.feature_formula_version,
                swing.source_timeframe_seconds,
                pool_type,
                members[0].swing_id,
                members[1].swing_id,
            )
            self._evict_for_capacity(swing.source_timeframe_seconds, swing.confirmation_ts, swing.availability_cursor)
            atr, local_range = self._scales(swing.source_timeframe_seconds)
            pool = _PoolState(
                pool_id=pool_id,
                pool_type=pool_type,
                timeframe=swing.source_timeframe,
                timeframe_seconds=swing.source_timeframe_seconds,
                members=list(members),
                lower=min(item.price_ticks for item in members),
                upper=max(item.price_ticks for item in members),
                representative=self._representative(members),
                confirmation_ts=members[1].confirmation_ts,
                confirmation_cursor=members[1].availability_cursor,
                last_update_ts=members[1].confirmation_ts,
                last_update_cursor=members[1].availability_cursor,
                separation=abs(members[1].price_ticks - members[0].price_ticks),
                creation_atr=atr,
                creation_range=local_range,
            )
            self._pools[pool_id] = pool
            self._add_active_index(pool)
            self._membership.update(item.swing_id for item in members)
            self._emit_lifecycle("created", pool, swing.swing_id, swing.confirmation_ts, swing.availability_cursor)
            return pool_id
        unmatched.append(swing)
        self._index_unmatched(swing)
        unmatched.sort(key=lambda item: (item.confirmation_ts, item.availability_cursor, str(item.swing_id)))
        if len(unmatched) > self.max_unmatched_per_side:
            evicted = unmatched[: len(unmatched) - self.max_unmatched_per_side]
            del unmatched[: len(unmatched) - self.max_unmatched_per_side]
            for item in evicted:
                self._unindex_unmatched(item)
        return None

    @staticmethod
    def _representative(members: list[_EqualSwing] | tuple[_EqualSwing, ...]) -> int:
        ordered_prices = sorted(item.price_ticks for item in members)
        count = len(ordered_prices)
        median_x2 = (
            2 * ordered_prices[count // 2]
            if count % 2
            else ordered_prices[count // 2 - 1] + ordered_prices[count // 2]
        )
        return min(
            members,
            key=lambda item: (
                abs(2 * item.price_ticks - median_x2),
                item.confirmation_ts,
                str(item.swing_id),
            ),
        ).price_ticks

    def _active_for_tf(self, timeframe_seconds: int) -> list[_PoolState]:
        return [
            self._pools[pool_id]
            for pool_id in self._active_ids
            if self._pools[pool_id].timeframe_seconds == timeframe_seconds
        ]

    def _evict_for_capacity(self, timeframe_seconds: int, ts: datetime, cursor: str) -> None:
        active = self._active_for_tf(timeframe_seconds)
        if len(active) < self.max_active_per_timeframe:
            return
        victim = min(
            active,
            key=lambda pool: (
                pool.last_update_ts,
                pool.confirmation_ts,
                str(pool.pool_id),
            ),
        )
        self._remove_active_index(victim)
        victim.active = False
        victim.invalidation_reason = "capacity_evicted"
        victim.lifecycle_version += 1
        self._add_tombstone(victim)
        self._emit_lifecycle("capacity_evicted", victim, None, ts, cursor)

    def _add_tombstone(self, pool: _PoolState) -> None:
        tombstones = self._tombstones.setdefault(pool.timeframe_seconds, [])
        if pool.pool_id not in tombstones:
            tombstones.append(pool.pool_id)
        while len(tombstones) > self.max_tombstones_per_timeframe:
            evicted_id = tombstones.pop(0)
            evicted = self._pools.get(evicted_id)
            if evicted is not None and not evicted.active:
                if evicted.sweep_link_id is not None:
                    self._links.pop(evicted.sweep_link_id, None)
                    self._link_probe_ordinals.pop(evicted.sweep_link_id, None)
                    self._unreclaimed_link_ids.discard(evicted.sweep_link_id)
                self._membership.difference_update(
                    item.swing_id for item in evicted.members
                )
                del self._pools[evicted_id]

    def on_probe_bar(self, bar: Bar) -> tuple[EqualLevelSweepLink, ...]:
        if bar.kind is not BarKind.TIME or bar.timeframe_ticks != 60 or not bar.is_complete:
            return ()
        self._probe_ordinal += 1
        if (
            not self._unreclaimed_link_ids
            and not self._eqh_boundaries
            and not self._eql_boundaries
        ):
            return ()
        # Existing swept pools may reclaim on this close.
        for link_id in tuple(sorted(self._unreclaimed_link_ids, key=str)):
            link = self._links.get(link_id)
            if link is None:
                self._unreclaimed_link_ids.discard(link_id)
                continue
            pool = self._pools.get(link.pool_id)
            if pool is None:
                self._unreclaimed_link_ids.discard(link_id)
                continue
            distance = strict_pool_reclaim_distance(
                pool.pool_type,
                lower_bound_ticks=pool.lower,
                upper_bound_ticks=pool.upper,
                close_ticks=bar.close_ticks,
            )
            if distance is not None:
                atr, _local = self._scales(pool.timeframe_seconds)
                updated = replace(
                    link,
                    reclaimed_after_sweep=True,
                    reclaim_bar_id=bar.bar_id,
                    reclaim_ts=bar.availability_ts_utc,
                    reclaim_latency_bars=(
                        self._probe_ordinal - self._link_probe_ordinals[link.sweep_link_id]
                    ),
                    reclaim_close_distance_ticks=distance,
                    reclaim_close_distance_normalized=(distance / atr if atr else None),
                    as_of_ts=bar.availability_ts_utc,
                    as_of_cursor=_cursor(bar),
                    source_close_ts=bar.availability_ts_utc,
                )
                self._links[link_id] = updated
                self._unreclaimed_link_ids.discard(link_id)
                pool.reclaimed = True
                pool.reclaim_ts = bar.availability_ts_utc
                pool.lifecycle_version += 1
                self._new_links.append(updated)
                self._emit_lifecycle("reclaimed", pool, None, bar.availability_ts_utc, _cursor(bar))

        high_stop = bisect_left(self._eqh_boundaries, (bar.high_ticks, ""))
        low_start = bisect_right(self._eql_boundaries, (bar.low_ticks, "\U0010ffff"))
        swept_ids = {
            item[2] for item in self._eqh_boundaries[:high_stop]
        } | {
            item[2] for item in self._eql_boundaries[low_start:]
        }
        for pool in sorted(
            (self._pools[pool_id] for pool_id in swept_ids),
            key=lambda item: (item.timeframe_seconds, item.pool_type, str(item.pool_id)),
        ):
            if pool.confirmation_ts >= bar.availability_ts_utc:
                continue
            depth = strict_pool_sweep_depth(
                pool.pool_type,
                lower_bound_ticks=pool.lower,
                upper_bound_ticks=pool.upper,
                bar=bar,
            )
            if depth is None:
                continue
            atr, _local = self._scales(pool.timeframe_seconds)
            link_id = context_uuid(
                self.identity.feature_formula_version,
                self.identity.feature_schema_hash,
                pool.pool_id,
                bar.bar_id,
            )
            reclaim_distance = strict_pool_reclaim_distance(
                pool.pool_type,
                lower_bound_ticks=pool.lower,
                upper_bound_ticks=pool.upper,
                close_ticks=bar.close_ticks,
            )
            reclaimed = reclaim_distance is not None
            link = EqualLevelSweepLink(
                **record_provenance(
                    self.identity,
                    as_of_ts=bar.availability_ts_utc,
                    as_of_cursor=_cursor(bar),
                    source_close_ts=bar.availability_ts_utc,
                    source_confirmed_ts=pool.confirmation_ts,
                    valid=True,
                    warmup_complete=True,
                    source_available=True,
                    missing_reason=None,
                ),
                sweep_link_id=link_id,
                pool_id=pool.pool_id,
                pool_type=pool.pool_type,
                source_timeframe=pool.timeframe,
                source_timeframe_seconds=pool.timeframe_seconds,
                sweep_bar_id=bar.bar_id,
                sweep_cursor=_cursor(bar),
                sweep_ts=bar.availability_ts_utc,
                sweep_depth_ticks=depth,
                sweep_depth_normalized=depth / atr if atr else None,
                reclaimed_after_sweep=reclaimed,
                reclaim_bar_id=bar.bar_id if reclaimed else None,
                reclaim_ts=bar.availability_ts_utc if reclaimed else None,
                reclaim_latency_bars=0 if reclaimed else None,
                reclaim_close_distance_ticks=reclaim_distance,
                reclaim_close_distance_normalized=(
                    reclaim_distance / atr if reclaim_distance is not None and atr else None
                ),
                setup_id=None,
                opposing_fvg_id=None,
                parent_lock_cursor=None,
                inversion_cursor=None,
                qualifies_opposing_leg=False,
            )
            self._links[link_id] = link
            self._link_probe_ordinals[link_id] = self._probe_ordinal
            if not reclaimed:
                self._unreclaimed_link_ids.add(link_id)
            self._remove_active_index(pool)
            pool.active = False
            pool.swept = True
            pool.sweep_link_id = link_id
            pool.sweep_ts = bar.availability_ts_utc
            pool.reclaimed = reclaimed
            pool.reclaim_ts = bar.availability_ts_utc if reclaimed else None
            pool.invalidation_reason = "swept"
            pool.lifecycle_version += 1
            self._add_tombstone(pool)
            self._new_links.append(link)
            self._emit_lifecycle("swept", pool, None, bar.availability_ts_utc, _cursor(bar))
        return self.drain_new_links()

    def drain_new_links(self) -> tuple[EqualLevelSweepLink, ...]:
        out = tuple(self._new_links)
        self._new_links.clear()
        return out

    def drain_lifecycle(self) -> tuple[EqualLevelPoolLifecycleEvent, ...]:
        out = tuple(self._lifecycle)
        self._lifecycle.clear()
        return out

    def _emit_lifecycle(
        self,
        event_type: str,
        pool: _PoolState,
        member_swing_id: UUID | None,
        ts: datetime,
        cursor: str,
    ) -> None:
        record = self._pool_record(pool, as_of_ts=ts, as_of_cursor=cursor)
        self._lifecycle.append(
            EqualLevelPoolLifecycleEvent(
                **record_provenance(
                    self.identity,
                    as_of_ts=ts,
                    as_of_cursor=cursor,
                    source_close_ts=record.source_close_ts,
                    source_confirmed_ts=pool.confirmation_ts,
                    valid=True,
                    warmup_complete=True,
                    source_available=True,
                    missing_reason=None,
                ),
                lifecycle_event_id=context_uuid(
                    self.identity.feature_formula_version,
                    pool.pool_id,
                    pool.lifecycle_version,
                    event_type,
                    cursor,
                ),
                event_type=event_type,
                pool=record,
                member_swing_id=member_swing_id,
            )
        )

    def _pool_record(self, pool: _PoolState, *, as_of_ts: datetime, as_of_cursor: str) -> EqualLevelPool:
        latest_atr, _local = self._scales(pool.timeframe_seconds)
        first_pivot = min(item.pivot_ts for item in pool.members)
        latest_pivot = max(item.pivot_ts for item in pool.members)
        return EqualLevelPool(
            **record_provenance(
                self.identity,
                as_of_ts=as_of_ts,
                as_of_cursor=as_of_cursor,
                source_close_ts=(
                    self._bars[pool.timeframe_seconds][-1].availability_ts_utc
                    if self._bars.get(pool.timeframe_seconds)
                    else None
                ),
                source_confirmed_ts=pool.confirmation_ts,
                valid=True,
                warmup_complete=True,
                source_available=True,
                missing_reason=None,
            ),
            pool_id=pool.pool_id,
            pool_type=pool.pool_type,
            source_timeframe=pool.timeframe,
            source_timeframe_seconds=pool.timeframe_seconds,
            lower_bound_ticks=pool.lower,
            upper_bound_ticks=pool.upper,
            representative_price_ticks=pool.representative,
            member_swing_ids=tuple(item.swing_id for item in pool.members),
            swing_count=len(pool.members),
            first_pivot_ts=first_pivot,
            latest_pivot_ts=latest_pivot,
            confirmation_ts=pool.confirmation_ts,
            last_update_ts=pool.last_update_ts,
            last_update_cursor=pool.last_update_cursor,
            absolute_separation_ticks=pool.separation,
            atr14_ticks=pool.creation_atr,
            local_range20_ticks=pool.creation_range,
            separation_normalized_by_atr=(pool.separation / pool.creation_atr if pool.creation_atr else None),
            separation_normalized_by_local_range=(pool.separation / pool.creation_range if pool.creation_range else None),
            active=pool.active,
            swept=pool.swept,
            sweep_link_id=pool.sweep_link_id,
            sweep_ts=pool.sweep_ts,
            reclaimed=pool.reclaimed,
            reclaim_ts=pool.reclaim_ts,
            invalidation_reason=pool.invalidation_reason,
            expiration_reason=None,
            tolerance_policy=self.tolerance_policy,
            lifecycle_version=pool.lifecycle_version,
        )

    def active_pool_records(self, *, as_of_ts: datetime, as_of_cursor: str) -> tuple[EqualLevelPool, ...]:
        return tuple(
            self._pool_record(pool, as_of_ts=as_of_ts, as_of_cursor=as_of_cursor)
            for pool in sorted(
                (
                    self._pools[pool_id]
                    for pool_id in self._active_ids
                    if self._pools[pool_id].confirmation_ts <= as_of_ts
                ),
                key=lambda item: (item.timeframe_seconds, item.pool_type, str(item.pool_id)),
            )
        )

    def active_pool_versions(self, *, as_of_ts: datetime) -> tuple[tuple[str, int], ...]:
        """Compact state-hash projection in the same canonical pool order."""

        return tuple(
            (str(pool.pool_id), pool.lifecycle_version)
            for pool in sorted(
                (
                    self._pools[pool_id]
                    for pool_id in self._active_ids
                    if self._pools[pool_id].confirmation_ts <= as_of_ts
                ),
                key=lambda item: (
                    item.timeframe_seconds,
                    item.pool_type,
                    str(item.pool_id),
                ),
            )
        )

    def nearest_context(
        self,
        *,
        price_ticks: int,
        setup_direction: Direction | str,
        as_of_ts: datetime,
        as_of_cursor: str,
    ) -> tuple[Mapping[str, NearestPoolReference | None], int]:
        del as_of_cursor  # provenance is created only for the selected references
        pools = [
            self._pools[pool_id]
            for pool_id in self._active_ids
            if self._pools[pool_id].confirmation_ts <= as_of_ts
        ]
        containing = sum(pool.lower <= price_ticks <= pool.upper for pool in pools)
        direction = setup_direction.value if isinstance(setup_direction, Direction) else str(setup_direction)
        long_setup = direction.lower() == "long"

        def choose(candidates: list[_PoolState]) -> NearestPoolReference | None:
            if not candidates:
                return None
            pool = min(
                candidates,
                key=lambda item: (
                    interval_distance_ticks(price_ticks, item.lower, item.upper),
                    -item.timeframe_seconds,
                    str(item.pool_id),
                ),
            )
            atr, _local = self._scales(pool.timeframe_seconds)
            distance = interval_distance_ticks(price_ticks, pool.lower, pool.upper)
            first_pivot = min(item.pivot_ts for item in pool.members)
            latest_pivot = max(item.pivot_ts for item in pool.members)
            width = pool.upper - pool.lower
            return NearestPoolReference(
                pool_id=pool.pool_id,
                pool_type=pool.pool_type,
                source_timeframe=pool.timeframe,
                source_timeframe_seconds=pool.timeframe_seconds,
                lower_bound_ticks=pool.lower,
                upper_bound_ticks=pool.upper,
                representative_price_ticks=pool.representative,
                distance_ticks=distance,
                distance_normalized_by_atr=distance / atr if atr else None,
                swing_count=len(pool.members),
                age_minutes=(as_of_ts - pool.confirmation_ts).total_seconds() / 60,
                span_minutes=(latest_pivot - first_pivot).total_seconds() / 60,
                width_ticks=width,
                width_normalized_by_atr=width / atr if atr else None,
                creation_separation_ticks=pool.separation,
                creation_separation_normalized_by_atr=(
                    pool.separation / pool.creation_atr if pool.creation_atr else None
                ),
                creation_separation_normalized_by_local_range=(
                    pool.separation / pool.creation_range
                    if pool.creation_range
                    else None
                ),
            )

        non_containing = [
            pool
            for pool in pools
            if not pool.lower <= price_ticks <= pool.upper
        ]
        above = [pool for pool in non_containing if pool.lower > price_ticks]
        below = [pool for pool in non_containing if pool.upper < price_ticks]
        supporting = above if long_setup else below
        opposing = below if long_setup else above
        return MappingProxyType(
            {
                "nearest_eqh": choose([pool for pool in pools if pool.pool_type is PoolType.EQH]),
                "nearest_eql": choose([pool for pool in pools if pool.pool_type is PoolType.EQL]),
                "nearest_thesis_supporting": choose(supporting),
                "nearest_thesis_opposing": choose(opposing),
            }
        ), containing

    def pool_at(self, pool_id: UUID) -> EqualLevelPool | None:
        pool = self._pools.get(pool_id)
        if pool is None:
            return None
        return self._pool_record(pool, as_of_ts=pool.last_update_ts, as_of_cursor=pool.last_update_cursor)

    def link_at(self, link_id: UUID) -> EqualLevelSweepLink | None:
        return self._links.get(link_id)

    def atr_at(self, timeframe_seconds: int) -> float | None:
        return self._scales(timeframe_seconds)[0]

    def snapshot(self) -> EqualLevelPoolTrackerSnapshot:
        unreclaimed_link_ids = tuple(
            sorted(
                self._unreclaimed_link_ids.intersection(self._links),
                key=str,
            )
        )
        return EqualLevelPoolTrackerSnapshot(
            schema_version=EQUAL_LEVEL_SNAPSHOT_SCHEMA_VERSION,
            tolerance_policy=self.tolerance_policy,
            atr_period=self.atr_period,
            local_range_period=self.local_range_period,
            max_active_per_timeframe=self.max_active_per_timeframe,
            max_members=self.max_members,
            max_unmatched_per_side=self.max_unmatched_per_side,
            max_tombstones_per_timeframe=self.max_tombstones_per_timeframe,
            source_bars=tuple((tf, tuple(bars)) for tf, bars in sorted(self._bars.items())),
            pools=tuple(
                _pool_state_snapshot(self._pools[key])
                for key in sorted(self._pools, key=str)
            ),
            unmatched=tuple(
                (tf, side, tuple(_equal_swing_seed(item) for item in items))
                for (tf, side), items in sorted(self._unmatched.items(), key=lambda item: (item[0][0], item[0][1].value))
            ),
            tombstones=tuple((tf, tuple(ids)) for tf, ids in sorted(self._tombstones.items())),
            links=tuple(
                _sweep_link_seed(self._links[key])
                for key in unreclaimed_link_ids
            ),
            link_probe_ordinals=tuple(
                (key, self._link_probe_ordinals[key])
                for key in unreclaimed_link_ids
            ),
            probe_ordinal=self._probe_ordinal,
        )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: EqualLevelPoolTrackerSnapshot,
        *,
        identity: ContextIdentity,
    ) -> EqualLevelPoolTracker:
        if snapshot.schema_version != EQUAL_LEVEL_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("equal-level snapshot version mismatch")
        tracker = cls(
            identity=identity,
            tolerance_policy=snapshot.tolerance_policy,
            atr_period=snapshot.atr_period,
            local_range_period=snapshot.local_range_period,
            max_active_per_timeframe=snapshot.max_active_per_timeframe,
            max_members=snapshot.max_members,
            max_unmatched_per_side=snapshot.max_unmatched_per_side,
            max_tombstones_per_timeframe=snapshot.max_tombstones_per_timeframe,
        )
        tracker._bars = {tf: list(bars) for tf, bars in snapshot.source_bars}
        tracker._pools = {
            pool.pool_id: _pool_state_from_snapshot(pool)
            for pool in snapshot.pools
        }
        tracker._unmatched = {
            (tf, side): [_equal_swing_from_seed(item) for item in items]
            for tf, side, items in snapshot.unmatched
        }
        for items in tracker._unmatched.values():
            for swing in items:
                tracker._index_unmatched(swing)
        tracker._membership = {
            item.swing_id
            for pool in tracker._pools.values()
            for item in pool.members
        }
        tracker._tombstones = {tf: list(ids) for tf, ids in snapshot.tombstones}
        restored_links = (
            _sweep_link_from_seed(item, identity=identity) for item in snapshot.links
        )
        tracker._links = {link.sweep_link_id: link for link in restored_links}
        tracker._link_probe_ordinals = dict(snapshot.link_probe_ordinals)
        for pool in tracker._pools.values():
            if pool.active:
                tracker._add_active_index(pool)
        tracker._unreclaimed_link_ids = {
            link_id
            for link_id, link in tracker._links.items()
            if not link.reclaimed_after_sweep
        }
        tracker._probe_ordinal = snapshot.probe_ordinal
        return tracker
