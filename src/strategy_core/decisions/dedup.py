"""Single-sourced zone-identity key for cross-bar first-touch dedup (PLAN §7 / B2).

The once-per-zone-per-day suppression compares a zone's identity against a set of
already-fired keys. Historically that key was computed inline by
``StrategyRuntime._zone_key``; B2 hoisted it here so the runtime and the plugin could
not drift (invariant I3). Since S-B3a the dedup set is PLUGIN-owned
(``TouchReversalPlugin._fired_keys``) and this key's only consumer is the plugin — the
runtime keeps no dedup bookkeeping. The body is VERBATIM the original:
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

    Verbatim port of the original ``StrategyRuntime._zone_key``; consumed by the touch
    plugin's own ``_fired_keys`` dedup (premark + record) since S-B3a.
    """
    return (trading_day, zone.names, zone.representative_price, zone.side.value)
