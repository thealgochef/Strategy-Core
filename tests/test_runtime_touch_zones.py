"""audit #3 regression: runtime touch detection merges ALL levels, then gates.

Proves that the touch path builds zones from every current level (canonical
merge-all semantics — since B3/S-B3a that derivation lives in the touch plugin's
``on_bar_closed``, matching the snapshot's zone derivation) and that
``detect_touches`` gates each *merged* zone on its MAX availability -- rather than
the old behavior of pre-filtering levels by availability before ``build_zones``
(which could change zone composition near an availability boundary).
"""

from datetime import UTC, datetime

from strategy_core.constants import ZONE_PROXIMITY_PTS
from strategy_core.runtime.state import StrategyRuntime
from strategy_core.types import Direction, Level, Side, Trade


def _ts(minute: int) -> datetime:
    # 14:xx UTC == 09:xx ET (NY session), so no asia/london range levels are
    # generated -- the two static levels are the only thing build_zones sees.
    return datetime(2026, 1, 6, 14, minute, tzinfo=UTC)


def test_merged_zone_gated_on_max_availability_fires_once_at_mean_price() -> None:
    """Two HIGH levels 1.5 pts apart (< ZONE_PROXIMITY_PTS) with DIFFERENT
    availability merge into ONE zone: representative_price = their mean, and
    available_from = the LATER (MAX) of the two constituents.

    A decision bar straddling that mean must (a) NOT fire before the later
    constituent is available, (b) fire exactly once at the MEAN price afterwards,
    and (c) never re-fire for the same cluster the same day.
    """
    # Within ZONE_PROXIMITY_PTS so the two levels merge into a single zone.
    assert abs(102.00 - 100.50) <= ZONE_PROXIMITY_PTS

    day_start = datetime(2026, 1, 6, 13, 0, tzinfo=UTC)  # pdh available at day start
    later = _ts(10)  # session_high only available 10 minutes into the session

    runtime = StrategyRuntime(timeframes=(2,), decision_timeframe=2, requested_symbol="NQ.c.0")
    runtime.set_static_levels(
        (
            Level("pdh", 100.50, Side.HIGH, available_from=day_start),
            Level("session_high", 102.00, Side.HIGH, available_from=later),
        )
    )

    # Decision bar 1 closes at 14:02 (< later). Its range [100.50, 101.50] straddles
    # the merged mean 101.25, but the zone is gated on its MAX availability (14:10).
    # The range deliberately also covers 100.50 (the pdh price): the OLD pre-filter
    # code would, at this close, see only the available pdh, build a pdh-ONLY zone
    # (rep 100.50, available at day start) and fire a premature single-constituent
    # touch here -- exactly the divergence this test guards against.
    runtime.process_event(Trade(_ts(1), 402, 1, "B"))  # 100.50 pts
    before = runtime.process_event(Trade(_ts(2), 406, 1, "B"))  # 101.50 pts -> bar straddles 101.25

    # The runtime composed exactly ONE merged zone at the mean, gated on the MAX avail.
    zones = runtime.snapshot().zones
    assert len(zones) == 1
    assert zones[0].names == ("pdh", "session_high")
    assert zones[0].representative_price == 101.25
    assert zones[0].available_from == later

    # (a) No touch before the merged zone's MAX availability, despite the straddle.
    assert before.touches == ()

    # (b) Bar 2 closes at 14:12 (>= later): exactly ONE touch, at the MEAN price
    # (101.25, not a single-constituent 100.50/102.00). HIGH zone -> SHORT.
    runtime.process_event(Trade(_ts(11), 402, 1, "B"))
    fired = runtime.process_event(Trade(_ts(12), 406, 1, "B"))
    assert len(fired.touches) == 1
    touch = fired.touches[0]
    assert touch.representative_price == 101.25
    assert touch.representative_price not in (100.50, 102.00)
    assert touch.direction is Direction.SHORT
    assert touch.level_type == "pdh"

    # (c) A later bar straddling the same merged zone the same day must NOT re-fire
    # (first-touch-per-cluster-per-day dedup — plugin-owned ``_fired_keys`` since S-B3a).
    runtime.process_event(Trade(_ts(13), 402, 1, "B"))
    again = runtime.process_event(Trade(_ts(14), 406, 1, "B"))
    assert again.touches == ()
    # Exactly one touch in total -- the OLD pre-filter path would have logged a
    # second, distinct-keyed pdh-only touch at 100.50 (see bar-1 comment).
    assert len(runtime.snapshot().touches) == 1
