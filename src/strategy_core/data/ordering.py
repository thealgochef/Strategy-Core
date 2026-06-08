"""Canonical Databento trade-bar event ordering.

The v3 order is ``(ts_event, sequence, side_signed_price, size)``. Buy-aggressor
sweeps sort ascending by price; sell-aggressor sweeps sort descending because their
side-signed price is negative.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import TypeVar

from strategy_core.constants import BUY_AGGRESSOR_SIDE
from strategy_core.types import Quote, Trade

__all__ = ["canonical_event_sort_key", "side_signed_price_ticks", "sort_events"]

T = TypeVar("T", Trade, Quote)


def side_signed_price_ticks(event: Trade, *, buy_side: str = BUY_AGGRESSOR_SIDE) -> int:
    """Return side-signed integer price used by canonical sweep ordering."""

    side = None if event.side is None else str(event.side).upper()
    return event.price_ticks if side == buy_side.upper() else -event.price_ticks


def canonical_event_sort_key(
    event: Trade | Quote,
    *,
    sequence: int | None = None,
) -> tuple[datetime, int, int, int]:
    """Return ``(ts_event, sequence, side_signed_price, size)`` for an event."""

    if isinstance(event, Trade):
        return (
            event.event_ts_utc,
            0 if sequence is None else int(sequence),
            side_signed_price_ticks(event),
            event.size,
        )
    return (event.event_ts_utc, 0 if sequence is None else int(sequence), 0, 0)


def sort_events(
    events: Iterable[T],
    *,
    sequence: Callable[[T], int | None] | None = None,
) -> list[T]:
    """Sort ``events`` by the canonical key with optional per-event sequence lookup."""

    def key(event: T) -> tuple[datetime, int, int, int]:
        return canonical_event_sort_key(event, sequence=None if sequence is None else sequence(event))

    return sorted(events, key=key)
