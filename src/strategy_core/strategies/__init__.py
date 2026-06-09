"""The strategy-plugin SDK package (PLAN §2, §6.2 Tier 2).

This package hosts the thin-waist plugin boundary (``protocols``), the single-sourced
``registry`` (decision 9.2: an in-package registry module — not entry-points — so the
SHA-pinned Trade-Lab and the unpinned Quant-Lab resolve plugins identically), and one
sub-package per strategy under ``strategy_core/strategies/<id>/`` (decision 9.5).

This ``__init__`` is intentionally SIDE-EFFECT-FREE: it imports nothing, so

* importing ``strategy_core`` (or this package) never registers a plugin — a plugin
  registers itself as an import side-effect (``@register``), and the platform must stay
  strategy-agnostic with the runtime registry EMPTY in Phase A; and
* the registry (A2) and plugins (A3) import the protocol types from the ``protocols``
  submodule directly, so the package ``__init__`` cannot create an import cycle.

Consumers import the surface explicitly, e.g.::

    from strategy_core.strategies.protocols import StrategyPlugin, BarSpec
    from strategy_core.strategies.registry import register, get_strategy
    from strategy_core.strategies.touch_reversal.plugin import TouchReversalPlugin  # registers
"""

from __future__ import annotations
