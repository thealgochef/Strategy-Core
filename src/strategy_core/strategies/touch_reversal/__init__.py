"""The ``touch_reversal`` strategy plugin package (archetype 1, PLAN §4 / §6.2 Tier 2).

Importing this package imports ``plugin``, whose ``@register`` decorator populates the
registry (PLAN §5.2: "importing the package is what populates the table"). This is the
EXPLICIT opt-in that registers ``strategy_id="touch_reversal"`` — no ``import strategy_core``
or ``import strategy_core.strategies`` path reaches here, so the runtime registry stays
EMPTY in Phase A until a consumer (or the A3 test) imports this package.
"""

from __future__ import annotations

from strategy_core.strategies.touch_reversal.plugin import (
    FixedPointsBarrier,
    TouchReversalPlugin,
)
from strategy_core.strategies.touch_reversal.section import TouchReversalSection

__all__ = ["TouchReversalPlugin", "TouchReversalSection", "FixedPointsBarrier"]
