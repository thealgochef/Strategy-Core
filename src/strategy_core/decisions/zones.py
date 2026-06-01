"""Zone construction: greedy merge of nearby key levels into zones.

Single-sourced from the canonical research training path. ``build_zones`` is a
byte-for-byte port of ``_build_zones`` in the dashboard utility builder, the
function that produced the zones the trained model's touches/labels were built
on. Reproduce it exactly -- same sort, same chained ``<=`` proximity compare
against the *last* level in the open group, same mean representative price, same
strict-majority side rule (ties resolve to LOW), same empty-case ``[]``.

Ported from:
``Claude-Quant-Lab/src/alpha_lab/agents/data_infra/ml/dashboard_utility_builder.py``
lines 382-411 (``_build_zones``).
"""

from __future__ import annotations

from strategy_core.constants import ZONE_PROXIMITY_PTS
from strategy_core.types import Level, Side, Zone

__all__ = ["build_zones"]


def build_zones(
    levels: list[Level], *, zone_proximity_pts: float = ZONE_PROXIMITY_PTS
) -> list[Zone]:
    """Merge levels within ``zone_proximity_pts`` points into zones.

    Greedy single-pass merge over price-sorted levels: a level joins the current
    open group when its price is within ``zone_proximity_pts`` of the group's
    *last appended* level (not the group minimum), otherwise it opens a new
    group. Each group becomes a :class:`~strategy_core.types.Zone` whose
    ``representative_price`` is the mean of its level prices, ``names`` is the
    constituent level names in group (price-sorted) order, and ``side`` is the
    strict-majority side (``HIGH`` only when HIGH levels strictly outnumber the
    rest, so ties resolve to ``LOW``). Zones are returned in ascending price
    order. Empty input yields ``[]``.

    Mirrors ``_build_zones`` exactly
    (``dashboard_utility_builder.py:382-411``); the only adaptation is plain
    :class:`Level`/:class:`Zone` dataclasses and the :class:`Side` enum in place
    of the research path's dicts and ``"HIGH"``/``"LOW"`` strings.

    Parameters
    ----------
    levels:
        Key levels (PDH/PDL/session highs/lows) to cluster. Order-independent;
        the function sorts by price.
    zone_proximity_pts:
        Maximum points between consecutive sorted levels for them to merge.
        Defaults to the canonical ``ZONE_PROXIMITY_PTS`` (3.0).

    Returns
    -------
    list[Zone]
        Merged zones in ascending ``representative_price`` order.
    """
    # _build_zones:384-385 -- empty input is the empty list, not a single zone.
    if not levels:
        return []

    # _build_zones:387 -- sort ascending by price; stable, mirrors the dict sort.
    sorted_levels = sorted(levels, key=lambda l: l.price)
    # _build_zones:388 -- seed the first group with the lowest-priced level.
    groups: list[list[Level]] = [[sorted_levels[0]]]

    # _build_zones:390-394 -- chained merge. The compare is against the LAST
    # level appended to the open group (groups[-1][-1]), NOT the group minimum,
    # so a run of small consecutive gaps chains into one zone even when its total
    # span exceeds zone_proximity_pts. Preserve this exactly.
    for lvl in sorted_levels[1:]:
        if lvl.price - groups[-1][-1].price <= zone_proximity_pts:
            groups[-1].append(lvl)
        else:
            groups.append([lvl])

    zones: list[Zone] = []
    for group in groups:
        # _build_zones:398-399 -- representative price is the arithmetic mean.
        prices = [l.price for l in group]
        rep_price = sum(prices) / len(prices)
        # _build_zones:400 -- names in group (price-sorted) order, as a tuple.
        names = tuple(l.name for l in group)
        # _build_zones:402-403 -- strict-majority side; ties (high_count not
        # strictly greater than half) resolve to LOW.
        high_count = sum(1 for l in group if l.side == Side.HIGH)
        side = Side.HIGH if high_count > len(group) / 2 else Side.LOW
        zones.append(
            Zone(
                representative_price=rep_price,
                names=names,
                side=side,
                touched=False,
            )
        )

    # _build_zones:411 -- zones in the same ascending price order as the groups.
    return zones
