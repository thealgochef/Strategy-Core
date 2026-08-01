"""IFVG v2 counterfactual labels and integer-tick barrier helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from strategy_core.constants import NO_RESOLUTION, TRADEABLE_REVERSAL
from strategy_core.decisions.outcomes import OutcomeResult, resolve_outcome
from strategy_core.types import Bar, Direction

__all__ = [
    "IfvgOutcome",
    "target_ticks_for_r",
    "resolve_ifvg_outcome",
]


def target_ticks_for_r(
    entry_ticks: int,
    stop_ticks: int,
    direction: Direction,
    r_multiple: float,
) -> int:
    """Conservative target snapped away from entry on the integer tick grid."""
    if r_multiple <= 0:
        raise ValueError(f"r_multiple must be positive (got {r_multiple})")
    risk_ticks = (
        entry_ticks - stop_ticks
        if direction is Direction.LONG
        else stop_ticks - entry_ticks
    )
    if risk_ticks < 1:
        raise ValueError(f"risk must be >= 1 tick (got {risk_ticks})")
    offset = math.ceil(abs(risk_ticks * r_multiple))
    return (
        entry_ticks + offset
        if direction is Direction.LONG
        else entry_ticks - offset
    )


@dataclass(frozen=True, slots=True)
class IfvgOutcome:
    label: str
    kernel_label: str
    r_multiple: float
    risk_points: float
    target_ticks: int
    mfe_r: float
    mae_r: float
    #: Generic shared-kernel compatibility: zero-based, -1 if unresolved.
    bars_to_resolution: int
    #: IFVG v2 meaning: first eligible forward bar is 1, None if unresolved.
    bars_after_entry_to_resolution: int | None
    resolution_bar_id: str | None


def resolve_ifvg_outcome(
    *,
    entry_ticks: int,
    stop_ticks: int,
    direction: Direction,
    forward_bars_1m: Sequence[Bar],
    tick_size: float,
    r_multiple: float = 1.0,
    entry_bar: Bar | None = None,
) -> IfvgOutcome:
    """Resolve a candidate label with entry-bar exclusion and stop-first order.

    Candidate-label censoring is defined by the caller's supplied forward
    window. It is separate from the executed-trade lifecycle.
    """
    risk_ticks = (
        entry_ticks - stop_ticks
        if direction is Direction.LONG
        else stop_ticks - entry_ticks
    )
    if risk_ticks < 1:
        raise ValueError(f"risk must be >= 1 tick (got {risk_ticks})")
    target_ticks = target_ticks_for_r(
        entry_ticks, stop_ticks, direction, r_multiple
    )
    if entry_bar is not None:
        entry_available = entry_bar.availability_ts_utc
        eligible = tuple(
            bar
            for bar in forward_bars_1m
            if bar.availability_ts_utc > entry_available
        )
    else:
        eligible = tuple(forward_bars_1m)
    risk_points = risk_ticks * tick_size
    target_points = abs(target_ticks - entry_ticks) * tick_size
    result: OutcomeResult = resolve_outcome(
        entry_points=entry_ticks * tick_size,
        direction=direction,
        forward_bars=eligible,
        tick_size=tick_size,
        tp_points=target_points,
        sl_points=risk_points,
        trap_mfe_min=0.0,
    )
    if result.label == TRADEABLE_REVERSAL:
        label = "win"
    elif result.label == NO_RESOLUTION:
        label = "censored"
    else:
        label = "loss"
    one_based = (
        result.bars_to_resolution + 1
        if result.bars_to_resolution >= 0
        else None
    )
    resolution_bar_id = (
        eligible[result.bars_to_resolution].bar_id
        if result.bars_to_resolution >= 0
        else None
    )
    return IfvgOutcome(
        label=label,
        kernel_label=result.label,
        r_multiple=r_multiple,
        risk_points=risk_points,
        target_ticks=target_ticks,
        mfe_r=result.max_mfe / risk_points,
        mae_r=result.max_mae / risk_points,
        bars_to_resolution=result.bars_to_resolution,
        bars_after_entry_to_resolution=one_based,
        resolution_bar_id=resolution_bar_id,
    )
