"""Flag-gated plugin attachment for StrategyRuntime construction (B2 PART 2).

ONE helper, called by EVERY construction site (production + the go-live gate), so all
sites wire the plugin identically. With the flag OFF (the default) it returns ``{}`` —
the caller constructs the verbatim None path, byte-identical to PART 1 (W1) — and it
imports NOTHING from the strategies package, so ``import strategy_core`` leaves the
registry empty (W2). With the flag ON it lazily imports the touch plugin (the
``@register`` side effect runs ONLY here, never at module scope — W2) and returns the
``plugin`` + ``strategy_section`` kwargs.

The section is the canonical default (matching the runtime's default RESEARCH scheme +
``ZONE_PROXIMITY_PTS`` proximity), so the plugin's ``self._levels`` is built identically to
the runtime's ``level_state`` (W5). TRANSIENT with the flag — removed at B3.
"""

from __future__ import annotations

from typing import Any

from strategy_core.config import plugin_routing_enabled

__all__ = ["touch_reversal_kwargs"]


def touch_reversal_kwargs() -> dict[str, Any]:
    """Return the StrategyRuntime kwargs that attach the touch plugin when the flag is ON.

    OFF (default) -> ``{}`` (None path, byte-identical; no plugin import → registry stays
    empty). ON -> ``{"plugin": TouchReversalPlugin(), "strategy_section": <default section>}``.
    Spread into the construction call: ``StrategyRuntime(..., **touch_reversal_kwargs())``.
    """
    if not plugin_routing_enabled():
        return {}
    # Lazy imports — the plugin's @register runs ONLY on this flag-ON branch (W2).
    from strategy_core.strategies.registry import get_strategy
    from strategy_core.strategies.touch_reversal import plugin as _tr_plugin  # noqa: F401 -- registers
    from strategy_core.strategies.touch_reversal.section import default_touch_reversal_section

    return {
        "plugin": get_strategy("touch_reversal")(),
        "strategy_section": default_touch_reversal_section(),
    }
