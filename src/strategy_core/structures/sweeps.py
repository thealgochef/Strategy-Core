"""Liquidity-pool sweep evaluation for a counter-displacement leg.

Armed when the IFVG reducer locks a parent (the manipulation leg starts
there), fed every execution bar through the inversion, then finalized: did the
leg RAID a liquidity pool (trade strictly beyond a session high/low, PDH/PDL,
prev-session level, or confirmed swing) on the side stops rest on?

``sweep_confirmed`` is a MEASUREMENT the records carry (the A-06R ruling: only
sweep-confirmed counter-legs may be called manipulation; the rest are counted
as counter-displacement) — never a gate. Pools are filtered at arm time by the
same availability discipline as touches: a pool whose ``available_from`` is
after the arm instant does not exist yet for this leg.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from strategy_core.types import Bar, Direction, Side

__all__ = [
    "LevelPool",
    "SweepResult",
    "SweepTracker",
    "SweepTrackerSnapshot",
    "strict_pool_reclaim_distance",
    "strict_pool_sweep_depth",
]


def strict_pool_sweep_depth(
    pool_type: str,
    *,
    lower_bound_ticks: int,
    upper_bound_ticks: int,
    bar: Bar,
) -> int | None:
    """Canonical strict bound penetration for EQH/EQL and legacy-compatible raids."""

    normalized = pool_type.lower()
    if normalized == "eqh":
        return (
            bar.high_ticks - upper_bound_ticks
            if bar.high_ticks > upper_bound_ticks
            else None
        )
    if normalized == "eql":
        return (
            lower_bound_ticks - bar.low_ticks
            if bar.low_ticks < lower_bound_ticks
            else None
        )
    raise ValueError(f"unknown equal-level pool type: {pool_type!r}")


def strict_pool_reclaim_distance(
    pool_type: str,
    *,
    lower_bound_ticks: int,
    upper_bound_ticks: int,
    close_ticks: int,
) -> int | None:
    """Strict completed-close reclaim; ``None`` means reclaim has not occurred."""

    normalized = pool_type.lower()
    if normalized == "eqh":
        return upper_bound_ticks - close_ticks if close_ticks < upper_bound_ticks else None
    if normalized == "eql":
        return close_ticks - lower_bound_ticks if close_ticks > lower_bound_ticks else None
    raise ValueError(f"unknown equal-level pool type: {pool_type!r}")


@dataclass(frozen=True, slots=True)
class LevelPool:
    """One liquidity pool in integer ticks (levels arrive in points; the caller
    converts on the tick grid once, at arm time)."""

    kind: str  # "pdh" | "pdl" | "asia_high" | ... | "prev_ny_low" | "swing_high" | "swing_low"
    price_ticks: int
    side: Side
    available_from: datetime | None = None


@dataclass(frozen=True, slots=True)
class SweepResult:
    """Finalized sweep block for the records (InversionRecord)."""

    sweep_confirmed: bool
    swept_kinds: tuple[str, ...]
    max_penetration_ticks: int
    nearest_unswept_distance_ticks: int | None
    sweep_ts_utc: datetime | None
    leg_extreme_ticks: int | None


class SweepTracker:
    """Fold execution bars over the armed pool set; read :meth:`result` at
    inversion (or at reset — partial legs are still measurable)."""

    def __init__(
        self,
        *,
        direction: Direction,
        pools: tuple[LevelPool, ...],
        armed_ts: datetime,
    ) -> None:
        # A LONG setup's counter-leg presses DOWN into sell-side liquidity
        # (LOW pools); SHORT mirrored. Off-side and not-yet-available pools are
        # excluded here so the reducer can pass the raw pool set.
        want = Side.LOW if direction is Direction.LONG else Side.HIGH
        self._direction = direction
        self._pools = tuple(
            p
            for p in pools
            if p.side is want and (p.available_from is None or p.available_from <= armed_ts)
        )
        self._armed_ts = armed_ts
        self._leg_extreme: int | None = None
        self._first_sweep_ts: datetime | None = None

    @property
    def pools(self) -> tuple[LevelPool, ...]:
        return self._pools

    def on_bar(self, bar: Bar) -> None:
        """Update the running leg extreme; record the first instant any pool
        was traded strictly through (a touch AT the level is not a raid)."""
        if self._direction is Direction.LONG:
            probe = bar.low_ticks
            self._leg_extreme = probe if self._leg_extreme is None else min(self._leg_extreme, probe)
        else:
            probe = bar.high_ticks
            self._leg_extreme = probe if self._leg_extreme is None else max(self._leg_extreme, probe)
        if self._first_sweep_ts is None and any(
            self._is_swept(pool) for pool in self._pools
        ):
            self._first_sweep_ts = bar.close_ts_utc

    def _is_swept(self, pool: LevelPool) -> bool:
        if self._leg_extreme is None:
            return False
        if self._direction is Direction.LONG:
            return self._leg_extreme < pool.price_ticks
        return self._leg_extreme > pool.price_ticks

    def result(self) -> SweepResult:
        swept = tuple(p for p in self._pools if self._is_swept(p))
        unswept = tuple(p for p in self._pools if not self._is_swept(p))
        max_pen = 0
        for pool in swept:
            pen = (
                pool.price_ticks - self._leg_extreme  # type: ignore[operator]
                if self._direction is Direction.LONG
                else self._leg_extreme - pool.price_ticks  # type: ignore[operator]
            )
            max_pen = max(max_pen, pen)
        nearest: int | None = None
        if self._leg_extreme is not None:
            for pool in unswept:
                dist = (
                    self._leg_extreme - pool.price_ticks
                    if self._direction is Direction.LONG
                    else pool.price_ticks - self._leg_extreme
                )
                nearest = dist if nearest is None else min(nearest, dist)
        return SweepResult(
            sweep_confirmed=bool(swept),
            swept_kinds=tuple(p.kind for p in swept),
            max_penetration_ticks=max_pen,
            nearest_unswept_distance_ticks=nearest,
            sweep_ts_utc=self._first_sweep_ts,
            leg_extreme_ticks=self._leg_extreme,
        )

    def snapshot(self) -> SweepTrackerSnapshot:
        """Cross-day carry for an in-flight leg (reducer day-seed seam)."""
        return SweepTrackerSnapshot(
            direction=self._direction,
            pools=self._pools,
            armed_ts=self._armed_ts,
            leg_extreme_ticks=self._leg_extreme,
            first_sweep_ts_utc=self._first_sweep_ts,
        )

    @classmethod
    def from_snapshot(cls, snap: SweepTrackerSnapshot) -> SweepTracker:
        tracker = cls(direction=snap.direction, pools=snap.pools, armed_ts=snap.armed_ts)
        tracker._pools = snap.pools  # already side/availability-filtered at original arm
        tracker._leg_extreme = snap.leg_extreme_ticks
        tracker._first_sweep_ts = snap.first_sweep_ts_utc
        return tracker


@dataclass(frozen=True, slots=True)
class SweepTrackerSnapshot:
    direction: Direction
    pools: tuple[LevelPool, ...]
    armed_ts: datetime
    leg_extreme_ticks: int | None
    first_sweep_ts_utc: datetime | None
