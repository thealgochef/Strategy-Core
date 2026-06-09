"""SC-owned runtime feature flags (B2; TRANSIENT — removed at B3).

One switch, default OFF, env-overridable, read through ONE resolver that every
construction site calls. No per-strategy or multi-value config — it exists only to let
the plugin seam (B2 PART 1) be wired on behind a flag without flipping the default; B3
deletes it when the plugin path becomes the default and the hardwired block is removed.
"""

from __future__ import annotations

import os

__all__ = ["PLUGIN_ROUTING_ENV", "plugin_routing_enabled"]

#: Env var that overrides the (False) default. Truthy values: "1" / "true" / "yes".
PLUGIN_ROUTING_ENV = "SC_PLUGIN_ROUTING"

_TRUTHY = {"1", "true", "yes"}


def plugin_routing_enabled() -> bool:
    """Whether ``StrategyRuntime`` construction routes the touch strategy through the
    plugin seam (B2). Default ``False``; ``True`` iff ``SC_PLUGIN_ROUTING`` is set to a
    truthy value (``"1"``/``"true"``/``"yes"``, case-insensitive, surrounding whitespace
    ignored). Every construction site reads the flag ONLY through this resolver.
    """
    return os.environ.get(PLUGIN_ROUTING_ENV, "").strip().lower() in _TRUTHY
