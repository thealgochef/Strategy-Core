"""Confirmed fractal swing points — the "recent extremes" liquidity pools.

A bar is a HIGH pivot iff its high is STRICTLY greater than the highs of the
``strength`` bars on BOTH sides (ties produce no pivot — deterministic and
conservative); LOW mirrored. A pivot is CONFIRMED only when the ``strength``-th
bar after it closes: ``SwingPoint.confirmed_ts_utc`` is that bar's close and is
the availability instant for pool eligibility — the same zero-lookahead
discipline as ``Level.available_from`` (a running extreme has no honest
availability; only a confirmed pivot does).

Streaming-only by design (the reducer folds it per execution bar); cross-day
continuity is the snapshot seam, mirroring ``structures/fvg.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from strategy_core.types import Bar, Side

__all__ = [
    "SwingPoint",
    "SwingTracker",
    "SwingSnapshot",
    "SWING_SNAPSHOT_SCHEMA_VERSION",
]

SWING_SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SwingPoint:
    """One confirmed fractal pivot."""

    side: Side
    price_ticks: int
    pivot_ts_utc: datetime
    confirmed_ts_utc: datetime
    pivot_bar_id: str


@dataclass(frozen=True, slots=True)
class SwingSnapshot:
    """Cross-day carry: kept confirmed points + the trailing unconfirmed window."""

    schema_version: int
    strength: int
    max_kept: int
    swings: tuple[SwingPoint, ...]
    tail: tuple[Bar, ...]  # the last <= 2*strength bars (candidates not yet decidable)


@dataclass(slots=True)
class SwingTracker:
    """Rolling ``2*strength + 1`` window; the middle bar is judged when the
    window fills. Confirmed points are kept newest-last, bounded by
    ``max_kept`` per side jointly (oldest evicted first)."""

    strength: int = 3
    max_kept: int = 64
    _window: list[Bar] = field(default_factory=list)
    _swings: list[SwingPoint] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.strength < 1:
            raise ValueError(f"strength must be >= 1 (got {self.strength})")
        if self.max_kept < 1:
            raise ValueError(f"max_kept must be >= 1 (got {self.max_kept})")

    def on_bar_closed(self, bar: Bar) -> tuple[SwingPoint, ...]:
        """Fold one execution bar; returns the pivots CONFIRMED at this close
        (0, 1, or 2 — a bar can pivot on both sides)."""
        self._window.append(bar)
        span = 2 * self.strength + 1
        if len(self._window) > span:
            del self._window[0]
        if len(self._window) < span:
            return ()
        pivot = self._window[self.strength]
        before = self._window[: self.strength]
        after = self._window[self.strength + 1 :]
        confirmed: list[SwingPoint] = []
        if all(pivot.high_ticks > b.high_ticks for b in before) and all(
            pivot.high_ticks > b.high_ticks for b in after
        ):
            confirmed.append(
                SwingPoint(
                    side=Side.HIGH,
                    price_ticks=pivot.high_ticks,
                    pivot_ts_utc=pivot.close_ts_utc,
                    confirmed_ts_utc=bar.close_ts_utc,
                    pivot_bar_id=pivot.bar_id,
                )
            )
        if all(pivot.low_ticks < b.low_ticks for b in before) and all(
            pivot.low_ticks < b.low_ticks for b in after
        ):
            confirmed.append(
                SwingPoint(
                    side=Side.LOW,
                    price_ticks=pivot.low_ticks,
                    pivot_ts_utc=pivot.close_ts_utc,
                    confirmed_ts_utc=bar.close_ts_utc,
                    pivot_bar_id=pivot.bar_id,
                )
            )
        if confirmed:
            self._swings.extend(confirmed)
            overflow = len(self._swings) - self.max_kept
            if overflow > 0:
                del self._swings[:overflow]
        return tuple(confirmed)

    def recent(self, *, side: Side, before: datetime, limit: int) -> tuple[SwingPoint, ...]:
        """Newest-first confirmed points on ``side`` with
        ``confirmed_ts_utc <= before`` (pool-eligibility filter)."""
        picked = [
            s for s in reversed(self._swings) if s.side is side and s.confirmed_ts_utc <= before
        ]
        return tuple(picked[:limit])

    def snapshot(self) -> SwingSnapshot:
        return SwingSnapshot(
            schema_version=SWING_SNAPSHOT_SCHEMA_VERSION,
            strength=self.strength,
            max_kept=self.max_kept,
            swings=tuple(self._swings),
            tail=tuple(self._window[-2 * self.strength :]),
        )

    @classmethod
    def from_snapshot(cls, snap: SwingSnapshot) -> SwingTracker:
        if snap.schema_version != SWING_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"SwingSnapshot schema {snap.schema_version} != "
                f"supported {SWING_SNAPSHOT_SCHEMA_VERSION}"
            )
        tracker = cls(strength=snap.strength, max_kept=snap.max_kept)
        tracker._window = list(snap.tail)
        tracker._swings = list(snap.swings)
        return tracker
