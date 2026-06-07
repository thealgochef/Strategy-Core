"""Tests for ``strategy_core.decisions.touch``.

Mirrors the canonical first-touch semantics of
``dashboard_utility_builder.py:414-440`` (``_detect_touches``): closed-interval
straddle, first-touch-per-zone, low->LONG / high->SHORT, boundary touches fire.

Deterministic: fixed timezone-aware UTC datetimes, no ``now()``/random.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from strategy_core.decisions.touch import detect_touches, is_touch
from strategy_core.types import CloseReason, Direction, Side, Zone

TICK_SIZE = 0.25
TRADING_DAY = date(2025, 6, 2)
_BASE_TS = datetime(2025, 6, 2, 13, 30, tzinfo=timezone.utc)


def _bar(
    bar_index: int,
    low_ticks: int,
    high_ticks: int,
    *,
    close_offset_minutes: int = 0,
):
    """Build a ``Bar`` with the high/low needed for touch tests.

    Open/close/volume fields are filler; only ``low_ticks``/``high_ticks`` and
    ``close_ts_utc`` matter to the detector.
    """
    # Import locally so the test module's only hard dependency is the engine API.
    from strategy_core.types import Bar

    close_ts = datetime(2025, 6, 2, 13, 30 + bar_index + close_offset_minutes, tzinfo=timezone.utc)
    return Bar(
        timeframe_ticks=100,
        trading_day=TRADING_DAY,
        bar_index=bar_index,
        bar_id=f"bar-{bar_index}",
        open_ts_utc=_BASE_TS,
        close_ts_utc=close_ts,
        open_ticks=low_ticks,
        high_ticks=high_ticks,
        low_ticks=low_ticks,
        close_ticks=high_ticks,
        volume=10,
        trade_count=5,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
    )


# ── is_touch (closed interval, canonical line 429) ──────────────────────────


def test_is_touch_inside_interval():
    assert is_touch(100.0, 110.0, 105.0) is True


def test_is_touch_below_interval():
    assert is_touch(100.0, 110.0, 99.0) is False


def test_is_touch_above_interval():
    assert is_touch(100.0, 110.0, 111.0) is False


def test_is_touch_lower_boundary_fires():
    # rep == bar_low -> closed interval includes it.
    assert is_touch(100.0, 110.0, 100.0) is True


def test_is_touch_upper_boundary_fires():
    # rep == bar_high -> closed interval includes it.
    assert is_touch(100.0, 110.0, 110.0) is True


# ── detect_touches ──────────────────────────────────────────────────────────


def test_straddling_bar_fires_one_touch():
    # rep 105.0 == 420 ticks * 0.25; bar spans [100.0, 110.0].
    zone = Zone(representative_price=105.0, names=("PDL",), side=Side.LOW)
    bars = [_bar(0, low_ticks=400, high_ticks=440)]  # [100.0, 110.0]

    touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)

    assert len(touches) == 1
    t = touches[0]
    assert t.representative_price == 105.0
    assert t.direction == Direction.LONG
    assert t.level_type == "PDL"
    assert t.trading_day == TRADING_DAY
    assert t.bar_ts_utc == bars[0].close_ts_utc
    # First-touch state flipped on the zone.
    assert zone.touched is True


def test_zone_fires_only_on_first_straddling_bar():
    zone = Zone(representative_price=105.0, names=("PDL",), side=Side.LOW)
    bars = [
        _bar(0, low_ticks=400, high_ticks=440),  # straddles -> fires
        _bar(1, low_ticks=400, high_ticks=440),  # straddles again -> ignored
    ]

    touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)

    assert len(touches) == 1
    # The single touch came from the FIRST bar.
    assert touches[0].bar_ts_utc == bars[0].close_ts_utc


def test_zone_fires_on_first_straddle_even_if_earlier_bar_misses():
    zone = Zone(representative_price=105.0, names=("PDL",), side=Side.LOW)
    bars = [
        _bar(0, low_ticks=400, high_ticks=410),  # [100.0, 102.5] -> miss
        _bar(1, low_ticks=400, high_ticks=440),  # [100.0, 110.0] -> fires
        _bar(2, low_ticks=400, high_ticks=440),  # straddles -> ignored
    ]

    touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)

    assert len(touches) == 1
    assert touches[0].bar_ts_utc == bars[1].close_ts_utc


def test_multiple_zones_fire_on_same_bar_in_order():
    low_zone = Zone(representative_price=101.0, names=("PDL",), side=Side.LOW)
    high_zone = Zone(representative_price=109.0, names=("PDH",), side=Side.HIGH)
    bars = [_bar(0, low_ticks=400, high_ticks=440)]  # [100.0, 110.0] straddles both

    touches = detect_touches(
        bars, [low_zone, high_zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY
    )

    assert len(touches) == 2
    # Detection order follows the zone list order.
    assert touches[0].level_type == "PDL"
    assert touches[0].direction == Direction.LONG
    assert touches[1].level_type == "PDH"
    assert touches[1].direction == Direction.SHORT
    assert low_zone.touched is True
    assert high_zone.touched is True


def test_low_side_maps_to_long():
    zone = Zone(representative_price=105.0, names=("L",), side=Side.LOW)
    bars = [_bar(0, low_ticks=400, high_ticks=440)]
    touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
    assert touches[0].direction == Direction.LONG


def test_high_side_maps_to_short():
    zone = Zone(representative_price=105.0, names=("H",), side=Side.HIGH)
    bars = [_bar(0, low_ticks=400, high_ticks=440)]
    touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
    assert touches[0].direction == Direction.SHORT


def test_boundary_touch_rep_equals_bar_high_fires():
    # rep 110.0 == bar_high (440 ticks * 0.25) exactly -> fires (closed interval).
    zone = Zone(representative_price=110.0, names=("PDH",), side=Side.HIGH)
    bars = [_bar(0, low_ticks=400, high_ticks=440)]  # [100.0, 110.0]

    touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)

    assert len(touches) == 1
    assert touches[0].representative_price == 110.0


def test_boundary_touch_rep_equals_bar_low_fires():
    # rep 100.0 == bar_low (400 ticks * 0.25) exactly -> fires.
    zone = Zone(representative_price=100.0, names=("PDL",), side=Side.LOW)
    bars = [_bar(0, low_ticks=400, high_ticks=440)]  # [100.0, 110.0]

    touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)

    assert len(touches) == 1
    assert touches[0].representative_price == 100.0


def test_no_touch_returns_empty_list():
    zone = Zone(representative_price=200.0, names=("PDH",), side=Side.HIGH)
    bars = [_bar(0, low_ticks=400, high_ticks=440)]  # [100.0, 110.0], rep far above

    touches = detect_touches(bars, [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)

    assert touches == []
    assert zone.touched is False


def test_empty_bars_returns_empty_list():
    zone = Zone(representative_price=105.0, names=("PDL",), side=Side.LOW)
    touches = detect_touches([], [zone], tick_size=TICK_SIZE, trading_day=TRADING_DAY)
    assert touches == []


def test_custom_direction_mapping_is_honored():
    # The mapping is injectable; pass an explicit one matching the default.
    zone = Zone(representative_price=105.0, names=("PDL",), side=Side.LOW)
    bars = [_bar(0, low_ticks=400, high_ticks=440)]
    mapping = {Side.LOW: Direction.LONG, Side.HIGH: Direction.SHORT}
    touches = detect_touches(
        bars,
        [zone],
        tick_size=TICK_SIZE,
        trading_day=TRADING_DAY,
        direction_from_side=mapping,
    )
    assert touches[0].direction == Direction.LONG
