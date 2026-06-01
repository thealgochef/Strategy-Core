"""MAE-first outcome labeling for level-touch events.

Single-sourced from the canonical research training path's labeler,
``dashboard_utility_labeling.py:44-108`` (``label_touch_event``), with the
same MAE-first ladder cross-referenced (and already aligned) against Trade-Lab's
streaming ``outcome_tracker.py:160-191`` (``_classify``).

The 3-class scheme (dashboard_utility_labeling.py:4-11):

* ``tradeable_reversal`` (0):     MFE >= ``tp_points`` before MAE >= ``sl_points``.
* ``trap_reversal`` (1):          MAE >= ``sl_points`` and MFE >= ``trap_mfe_min``.
* ``aggressive_blowthrough`` (2): MAE >= ``sl_points`` and MFE <  ``trap_mfe_min``.
* ``no_resolution``:              neither threshold hit within the forward bars.

Resolution order: MAE is checked FIRST (conservative). A single bar whose range
breaches both the stop and the target therefore resolves to the LOSS, not the win
-- this is the guard that keeps training labels honest and is matched exactly here
(dashboard_utility_labeling.py:82-97).

Entry reference is the level price itself (``representative_price`` in research),
passed here as ``entry_points``. Prices are compared in POINTS; ``forward_bars``
carry integer ticks, so the resolver converts via ``tick_size``.

This module deliberately holds NO session/RTH-cutoff logic: the canonical labeler
receives ``forward_bars`` already truncated at the 16:15 RTH cutoff by its caller
(the builder/adapter), and so does ``resolve_outcome`` -- it scans whatever bars it
is given.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from strategy_core.constants import (
    AGGRESSIVE_BLOWTHROUGH,
    LABEL_ENCODING,
    NO_RESOLUTION,
    TRADEABLE_REVERSAL,
    TRAP_REVERSAL,
)
from strategy_core.types import Bar, Direction

__all__ = ["classify_mae_first", "OutcomeResult", "resolve_outcome"]


def classify_mae_first(
    max_mfe: float,
    max_mae: float,
    *,
    tp_points: float,
    sl_points: float,
    trap_mfe_min: float,
    forced: bool = False,
) -> str | None:
    """Apply the MAE-first ladder to running MFE/MAE extremes; the shared kernel.

    Ported from ``dashboard_utility_labeling.py:82-97`` (per-bar ladder) plus the
    ``forced`` (RTH-cutoff) branch from ``outcome_tracker.py:183-189``.

    MAE is checked FIRST so a bar that breaches both the stop and the target
    resolves to the LOSS (``trap_reversal`` / ``aggressive_blowthrough``), never the
    win. Within the loss branch, MFE >= ``trap_mfe_min`` splits a *trap* (it did
    move favorably first) from an *aggressive blowthrough*.

    Args:
        max_mfe: Running maximum favorable excursion (points).
        max_mae: Running maximum adverse excursion (points).
        tp_points: Take-profit threshold (points).
        sl_points: Stop-loss threshold (points).
        trap_mfe_min: Minimum MFE for the loss to count as a trap vs a blowthrough.
        forced: If True (RTH cutoff), resolve even when neither threshold is hit,
            using the same trap/blowthrough split as the SL branch.

    Returns:
        The resolved label string, or ``None`` if unresolved (and not ``forced``).
    """
    # Adverse FIRST (conservative): both-breach -> loss, never the win.
    if max_mae >= sl_points:
        return TRAP_REVERSAL if max_mfe >= trap_mfe_min else AGGRESSIVE_BLOWTHROUGH

    # Then favorable.
    if max_mfe >= tp_points:
        return TRADEABLE_REVERSAL

    # RTH cutoff: force a loss-side resolution with the same trap/blowthrough split.
    if forced:
        return TRAP_REVERSAL if max_mfe >= trap_mfe_min else AGGRESSIVE_BLOWTHROUGH

    return None


@dataclass(frozen=True, slots=True)
class OutcomeResult:
    """Result of resolving one touch event against its forward bars.

    Mirrors the dict returned by ``dashboard_utility_labeling.py:101-108`` (minus
    ``resolution_ts``, which is a caller concern): ``max_mfe``/``max_mae`` are
    rounded to 4 decimals, ``label_encoded`` is ``None`` for ``no_resolution`` (the
    label is absent from ``LABEL_ENCODING``), and ``bars_to_resolution`` is ``-1``
    when never resolved.
    """

    label: str
    label_encoded: int | None
    max_mfe: float
    max_mae: float
    bars_to_resolution: int


def resolve_outcome(
    entry_points: float,
    direction: Direction,
    forward_bars: Sequence[Bar],
    tick_size: float,
    *,
    tp_points: float,
    sl_points: float,
    trap_mfe_min: float,
) -> OutcomeResult:
    """Scan forward bars for MFE/MAE and resolve via the MAE-first ladder.

    Ported from ``dashboard_utility_labeling.py:62-108`` (``label_touch_event``).
    The entry reference is the level price (``entry_points``), matching training.

    Per bar (dashboard_utility_labeling.py:71-80), for a LONG the favorable
    excursion is ``high - entry`` and the adverse is ``entry - low``; for a SHORT
    the two are mirrored (``entry - low`` favorable, ``high - entry`` adverse). The
    running maxima feed ``classify_mae_first`` with ``forced=False`` (this resolver
    never forces; that is the streaming RTH-cutoff path's job).

    ``forward_bars`` must already be the post-touch bars truncated at the RTH cutoff
    -- that filtering is the ADAPTER's job (the canonical builder slices them before
    calling ``label_touch_event``). This function does NOT apply the 16:15 cutoff.

    Args:
        entry_points: Entry/level price in points.
        direction: ``Direction.LONG`` or ``Direction.SHORT``.
        forward_bars: Post-touch bars (touch bar excluded), already RTH-truncated.
        tick_size: Points per tick, to convert bar tick prices to points.
        tp_points: Take-profit threshold (points).
        sl_points: Stop-loss threshold (points).
        trap_mfe_min: Trap-vs-blowthrough MFE threshold (points).

    Returns:
        An ``OutcomeResult`` with the label, its encoding, the rounded MFE/MAE
        extremes, and the zero-based index of the resolving bar (``-1`` if none).
    """
    max_mfe = 0.0
    max_mae = 0.0
    label = NO_RESOLUTION
    bars_to_resolution = -1

    is_long = direction == Direction.LONG

    for i, bar in enumerate(forward_bars):
        high = bar.high_ticks * tick_size
        low = bar.low_ticks * tick_size

        if is_long:
            bar_mfe = high - entry_points
            bar_mae = entry_points - low
        else:  # SHORT
            bar_mfe = entry_points - low
            bar_mae = high - entry_points

        max_mfe = max(max_mfe, bar_mfe)
        max_mae = max(max_mae, bar_mae)

        decided = classify_mae_first(
            max_mfe,
            max_mae,
            tp_points=tp_points,
            sl_points=sl_points,
            trap_mfe_min=trap_mfe_min,
            forced=False,
        )
        if decided is not None:
            label = decided
            bars_to_resolution = i
            break

    label_encoded = LABEL_ENCODING.get(label)

    return OutcomeResult(
        label=label,
        label_encoded=label_encoded,
        max_mfe=round(max_mfe, 4),
        max_mae=round(max_mae, 4),
        bars_to_resolution=bars_to_resolution,
    )
