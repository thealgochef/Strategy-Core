"""First-touch detection: a bar's range straddling a zone's representative price.

Single-sourced from the canonical research training path. Ported EXACTLY from
``_detect_touches`` in Claude-Quant-Lab
``src/alpha_lab/agents/data_infra/ml/dashboard_utility_builder.py:414-440``.

The canonical detector iterates ET bars in order; for each zone not yet touched it
fires when the bar's ``[low, high]`` *closed* interval contains the zone's
representative price (``bar_low <= rep <= bar_high``, line 429). The first such bar
flips the zone's ``touched`` flag so the zone never fires again (line 425, 430).
Low-side zones imply LONG, high-side imply SHORT (line 431).

Fidelity note (phase-7 parity item): the canonical detector uses the bar's *index*
timestamp (``bar_ts`` from ``bars_et.iterrows()``, line 420/433) as the touch
timestamp. The research bars are indexed by their **open** time, whereas here we
record ``bar.close_ts_utc``. Whether the canonical index is the open or the close
of the bar is an open vs. close bar-timestamp question that must be reconciled in
phase 7.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from strategy_core.constants import DIRECTION_FROM_SIDE
from strategy_core.types import Bar, Direction, Side, Touch, Zone

__all__ = ["is_touch", "detect_touches"]


def is_touch(
    bar_low_points: float, bar_high_points: float, zone_rep_points: float
) -> bool:
    """Return whether a bar's range straddles a zone's representative price.

    Closed interval, exactly as canonical
    ``dashboard_utility_builder.py:429``::

        if bar_low <= rep <= bar_high:

    so a touch on either boundary (``rep == bar_low`` or ``rep == bar_high``) fires.
    """
    return bar_low_points <= zone_rep_points <= bar_high_points


def detect_touches(
    bars: Sequence[Bar],
    zones: list[Zone],
    *,
    tick_size: float,
    trading_day: date,
    direction_from_side: Mapping[Side, Direction] = DIRECTION_FROM_SIDE,
) -> list[Touch]:
    """Detect first-touch events over ``bars`` in order.

    Ported from ``dashboard_utility_builder.py:414-440`` (``_detect_touches``).

    Iterate ``bars`` IN ORDER. For each bar, convert its high/low ticks to points
    (the decision layer compares in points). For each zone not yet touched, if the
    bar straddles the zone's representative price (``is_touch``), flip the zone's
    ``touched`` flag (mutable first-touch state, canonical line 430), map the zone
    side to a trade direction (canonical line 431), and append a ``Touch``. A zone
    fires only on its FIRST straddling bar and never again (canonical line 425
    guard). Multiple zones may fire on the same bar.

    ``level_type`` is the zone's first constituent level name (``zone["names"][0]``,
    canonical line 436). Touches are returned in detection order.
    """
    touches: list[Touch] = []

    for bar in bars:
        low_points = bar.low_ticks * tick_size
        high_points = bar.high_ticks * tick_size

        for zone in zones:
            if zone.touched:
                continue

            if is_touch(low_points, high_points, zone.representative_price):
                zone.touched = True
                direction = direction_from_side[zone.side]
                touches.append(
                    Touch(
                        bar_ts_utc=bar.close_ts_utc,
                        representative_price=zone.representative_price,
                        direction=direction,
                        level_type=zone.names[0],
                        trading_day=trading_day,
                    )
                )

    return touches
