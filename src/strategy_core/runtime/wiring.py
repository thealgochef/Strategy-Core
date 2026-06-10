"""Plugin attachment for StrategyRuntime construction — the touch strategy is THE path.

ONE helper, called by every production construction site (Trade-Lab's ``StrategyCoreService``
and the runtime's own default-attach), so all sites wire the touch strategy identically. As
of B3 the plugin is the production strategy path: there is no flag and no None path, so this
UNCONDITIONALLY builds the registered ``touch_reversal`` plugin + its default section.

The default section matches the runtime's default RESEARCH scheme + ``ZONE_PROXIMITY_PTS``
proximity, so the plugin's ``self._levels`` — the SOLE level fold since S-B3a (the
runtime's redundant copy is deleted) — is built with the same scheme the runtime
classifies sessions and builds candles with. Importing this module registers the
``touch_reversal`` plugin (the ``@register`` side effect) — intended, since it is the
production strategy.
"""

from __future__ import annotations

from typing import Any

from strategy_core.strategies.registry import get_strategy
from strategy_core.strategies.touch_reversal import plugin as _tr_plugin  # noqa: F401 -- registers
from strategy_core.strategies.touch_reversal.section import default_touch_reversal_section

__all__ = ["touch_reversal_kwargs"]


def touch_reversal_kwargs() -> dict[str, Any]:
    """Return the StrategyRuntime kwargs attaching the touch plugin + its default section.

    Spread into the construction call: ``StrategyRuntime(..., **touch_reversal_kwargs())``.
    """
    return {
        "plugin": get_strategy("touch_reversal")(),
        "strategy_section": default_touch_reversal_section(),
    }
