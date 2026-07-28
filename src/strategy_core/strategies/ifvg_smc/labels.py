"""Honest r-relative IFVG outcomes via the SHARED kernel — no new scan code.

The ifvg trade shape is per-decision: stop at the manipulation swing (already
buffered into ``stop_ticks`` by the reducer), target at ``r_multiple`` times the
risk. The kernel (:func:`strategy_core.decisions.outcomes.resolve_outcome`)
already takes per-call point barriers, so an r-relative pair is just
``tp_points = r * risk_points`` / ``sl_points = risk_points`` — the barrier
math happens HERE, the scan stays single-sourced in the kernel (MAE-first,
both-breach resolves to the loss).

Entry reference: ``confirmation_close`` — the entry bar's close, the price the
reducer recorded at the signal instant. ``forward_bars`` must be STRICTLY after
the entry bar's close (the caller slices, exactly like the touch adapters); the
end of the slice IS the label window (trading-day end offline).

Label vocabulary is mapped to the ifvg family: ``tradeable_reversal`` -> ``win``,
``trap_reversal``/``aggressive_blowthrough`` -> ``loss`` (with the trap split
retained in ``kernel_label``), ``no_resolution`` -> ``eod_timeout``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from strategy_core.constants import NO_RESOLUTION, TRADEABLE_REVERSAL
from strategy_core.decisions.outcomes import OutcomeResult, resolve_outcome
from strategy_core.types import Bar, Direction

__all__ = ["IfvgOutcome", "resolve_ifvg_outcome"]


@dataclass(frozen=True, slots=True)
class IfvgOutcome:
    """One label-family column set for one entry candidate."""

    label: str  # "win" | "loss" | "eod_timeout"
    kernel_label: str  # the kernel's 3-class + no_resolution vocabulary
    r_multiple: float
    risk_points: float
    mfe_r: float
    mae_r: float
    bars_to_resolution: int  # -1 when unresolved (eod_timeout)


def resolve_ifvg_outcome(
    *,
    entry_ticks: int,
    stop_ticks: int,
    direction: Direction,
    forward_bars_1m: Sequence[Bar],
    tick_size: float,
    r_multiple: float = 1.0,
) -> IfvgOutcome:
    """Resolve one entry against its forward window through the shared kernel.

    ``stop_ticks`` already carries the reducer's buffer; ``trap_mfe_min`` is 0
    for the base family (the trap/blowthrough split is a touch-strategy concept;
    ifvg keeps the binary win/loss with the kernel vocabulary preserved for
    downstream splits).
    """
    risk_ticks = (
        entry_ticks - stop_ticks if direction is Direction.LONG else stop_ticks - entry_ticks
    )
    if risk_ticks < 1:
        raise ValueError(f"risk must be >= 1 tick (got {risk_ticks})")
    risk_points = risk_ticks * tick_size
    result: OutcomeResult = resolve_outcome(
        entry_points=entry_ticks * tick_size,
        direction=direction,
        forward_bars=forward_bars_1m,
        tick_size=tick_size,
        tp_points=r_multiple * risk_points,
        sl_points=risk_points,
        trap_mfe_min=0.0,
    )
    if result.label == TRADEABLE_REVERSAL:
        label = "win"
    elif result.label == NO_RESOLUTION:
        label = "eod_timeout"
    else:
        label = "loss"
    return IfvgOutcome(
        label=label,
        kernel_label=result.label,
        r_multiple=r_multiple,
        risk_points=risk_points,
        mfe_r=result.max_mfe / risk_points,
        mae_r=result.max_mae / risk_points,
        bars_to_resolution=result.bars_to_resolution,
    )
