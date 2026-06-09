"""Single-sourced zone-identity key for cross-bar first-touch dedup (PLAN §7 / B2).

The once-per-zone-per-day suppression compares a zone's identity against a set of
already-fired keys. Historically that key was computed inline by
``StrategyRuntime._zone_key`` (``runtime/state.py``). B2 routes the touch fold through a
plugin whose ``on_bar_closed`` must pre-mark its zones from the SAME set using the SAME
key, so the key is hoisted here as ONE function both the runtime and the plugin call —
they cannot drift (invariant I3).

The body is VERBATIM the prior ``StrategyRuntime._zone_key`` (state.py:333-335):
``(trading_day, zone.names, zone.representative_price, zone.side.value)``.
"""

from __future__ import annotations

from datetime import date

from strategy_core.types import Zone

__all__ = ["ZoneKey", "zone_key"]

#: The cross-bar dedup key: (trading_day, zone names, representative price, side value).
ZoneKey = tuple[date, tuple[str, ...], float, str]


def zone_key(trading_day: date, zone: Zone) -> ZoneKey:
    """Compute a zone's cross-bar first-touch identity key.

    Verbatim port of ``StrategyRuntime._zone_key`` so the runtime and the touch plugin
    compute byte-identical keys against the shared ``_touched_zone_keys`` set.
    """
    return (trading_day, zone.names, zone.representative_price, zone.side.value)
