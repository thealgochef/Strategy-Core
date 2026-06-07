"""Fidelity tests for ``build_zones`` against canonical ``_build_zones``.

Each case pins a behavior that must match
``dashboard_utility_builder.py:382-411`` byte-for-byte: the ``<=`` proximity
boundary, the strict-majority (ties->LOW) side rule, the mean representative
price, and -- critically -- the chained merge that compares against the LAST
level in the open group rather than the group minimum.
"""

from __future__ import annotations

from strategy_core.constants import ZONE_PROXIMITY_PTS
from strategy_core.decisions.zones import build_zones
from strategy_core.types import Level, Side, Zone


def _high(name: str, price: float) -> Level:
    return Level(name=name, price=price, side=Side.HIGH)


def _low(name: str, price: float) -> Level:
    return Level(name=name, price=price, side=Side.LOW)


def test_empty_returns_empty_list() -> None:
    """_build_zones:384-385 -- no levels yields the empty list."""
    assert build_zones([]) == []


def test_single_level_one_zone() -> None:
    """A lone level becomes one zone carrying its own price/name/side."""
    zones = build_zones([_high("PDH", 100.0)])
    assert zones == [
        Zone(representative_price=100.0, names=("PDH",), side=Side.HIGH, touched=False)
    ]
    assert zones[0].touched is False


def test_two_levels_within_proximity_merge() -> None:
    """Gap 2.0 (< 3.0) -- the two levels merge into a single zone."""
    zones = build_zones([_high("a", 100.0), _high("b", 102.0)])
    assert len(zones) == 1
    assert zones[0].names == ("a", "b")
    assert zones[0].representative_price == 101.0


def test_two_levels_beyond_proximity_do_not_merge() -> None:
    """Gap 3.01 (> 3.0) -- the levels stay separate, ascending order."""
    zones = build_zones([_high("a", 100.0), _high("b", 103.01)])
    assert len(zones) == 2
    assert [z.names for z in zones] == [("a",), ("b",)]
    assert zones[0].representative_price == 100.0
    assert zones[1].representative_price == 103.01


def test_exactly_proximity_apart_merges_inclusive_boundary() -> None:
    """Gap exactly 3.0 merges -- the compare is ``<=`` not ``<``."""
    zones = build_zones([_high("a", 100.0), _high("b", 103.0)])
    assert len(zones) == 1
    assert zones[0].names == ("a", "b")
    assert zones[0].representative_price == 101.5


def test_majority_side_tie_resolves_to_low() -> None:
    """high_count == len/2 is NOT strictly greater -> side is LOW (ties->LOW)."""
    zones = build_zones([_high("h", 100.0), _low("l", 101.0)])
    assert len(zones) == 1
    assert zones[0].side == Side.LOW


def test_majority_side_high_wins_when_strictly_greater() -> None:
    """Two HIGH vs one LOW in one zone -> strict majority HIGH."""
    zones = build_zones([_high("h1", 100.0), _high("h2", 101.0), _low("l", 102.0)])
    assert len(zones) == 1
    assert zones[0].side == Side.HIGH


def test_representative_price_is_the_mean() -> None:
    """rep_price = sum(prices)/len(prices) over the merged group."""
    zones = build_zones([_high("a", 100.0), _high("b", 101.0), _high("c", 103.0)])
    assert len(zones) == 1
    # All three chain (gaps 1.0 then 2.0, each <= 3.0); mean of 100,101,103.
    assert zones[0].representative_price == (100.0 + 101.0 + 103.0) / 3


def test_chain_merge_spans_more_than_proximity_total() -> None:
    """Consecutive gaps each <= 3.0 chain into ONE zone even when the total span
    exceeds 3.0, because the compare is against the LAST level, not the first.
    100 -> 102.5 (2.5) -> 105.0 (2.5): total span 5.0 > 3.0, but still one zone.
    """
    zones = build_zones([_low("a", 100.0), _low("b", 102.5), _low("c", 105.0)])
    assert len(zones) == 1
    assert zones[0].names == ("a", "b", "c")
    assert zones[0].representative_price == (100.0 + 102.5 + 105.0) / 3


def test_chain_break_when_step_exceeds_proximity() -> None:
    """A single gap > 3.0 breaks the chain into two zones at that point."""
    zones = build_zones([_low("a", 100.0), _low("b", 102.0), _high("c", 106.0), _high("d", 108.0)])
    assert [z.names for z in zones] == [("a", "b"), ("c", "d")]
    assert zones[0].side == Side.LOW
    assert zones[1].side == Side.HIGH


def test_input_order_independent_sorted_by_price() -> None:
    """Unsorted input is sorted by price; output is ascending, names in order."""
    zones = build_zones([_high("hi", 110.0), _low("lo", 100.0)])
    assert [z.representative_price for z in zones] == [100.0, 110.0]
    assert [z.names for z in zones] == [("lo",), ("hi",)]


def test_default_proximity_matches_constant() -> None:
    """The default kwarg is the canonical ZONE_PROXIMITY_PTS (3.0)."""
    levels = [_high("a", 100.0), _high("b", 100.0 + ZONE_PROXIMITY_PTS)]
    assert len(build_zones(levels)) == 1
    assert len(build_zones(levels, zone_proximity_pts=ZONE_PROXIMITY_PTS)) == 1
