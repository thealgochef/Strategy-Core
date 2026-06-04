"""Decision layer: pure, scalar, config-driven strategy functions.

Single-sourced from the canonical research training path: zone construction,
touch detection + first-touch scope, ET session classification, the interaction
and approach feature formulas, MAE-first outcome resolution, and the honest
decision-time outcome orchestration. No pandas, no IO.
"""

from __future__ import annotations

from strategy_core.decisions.honest_entry import (
    HonestEntryDrop,
    resolve_honest_outcome,
)
from strategy_core.decisions.outcomes import (
    OutcomeResult,
    classify_mae_first,
    resolve_outcome,
)

__all__ = [
    "resolve_honest_outcome",
    "HonestEntryDrop",
    "resolve_outcome",
    "classify_mae_first",
    "OutcomeResult",
]
