"""A3 equivalence: the TouchReversalPlugin wrapper mirrors detect_touches exactly.

PLAN §7 Step A3 acceptance: the plugin's touch output equals a direct ``detect_touches``
call on the SAME bars + the SAME zones derived the identical way. This is the proof that
wrapping ``build_zones → detect_touches`` behind the §2.2 plugin protocol is byte-faithful
(the plugin is "call-site-only" — it moves no math).

This file is the ONLY place that imports the plugin, so its ``@register`` side effect
fires only here — the runtime registry stays empty for every other import path.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from strategy_core.constants import (
    DEFAULT_TICK_SIZE,
    RESEARCH_SESSION_SCHEME,
    TRADE_LAB_CT_SESSION_SCHEME,
    ZONE_PROXIMITY_PTS,
)
from strategy_core.contract.schema import (
    ContractError,
    FeatureWindows,
    LevelScheme,
    SessionScheme,
    SessionWindow,
    TouchRule,
)
from strategy_core.decisions.touch import detect_touches
from strategy_core.decisions.zones import build_zones
from strategy_core.strategies.registry import get_strategy
from strategy_core.strategies.touch_reversal.plugin import (  # noqa: F401 -- import registers the plugin
    TouchReversalPlugin,
    _runtime_scheme_from_section,
)
from strategy_core.strategies.touch_reversal.section import (
    TouchReversalSection,
    _contract_scheme_from_runtime,
)
from strategy_core.types import Bar, CloseReason, Direction, Level, Side


class _Ctx:
    """Minimal PlatformContext stub — only ``tick_size`` is exercised by the touch path."""

    tick_size = DEFAULT_TICK_SIZE
    point_value = 20.0

    def closed_bars(self, label: str):
        return ()

    def current_bar(self, label: str):
        return None

    def trade_price_at(self, ts_utc):
        return None

    def session_at(self, ts_utc):
        return None

    def quotes_in_window(self, start_ts_utc, end_ts_utc):
        return ()


def _section() -> TouchReversalSection:
    """A valid v3 touch section (contract-form), sourced from the canonical constants."""
    return TouchReversalSection(
        session_scheme=SessionScheme(
            timezone="US/Eastern",
            trading_day_boundary="18:00",
            sessions={
                "asia": SessionWindow(start="19:00", end="02:45", crosses_midnight=True),
                "london": SessionWindow(start="03:00", end="08:00"),
                "ny": SessionWindow(start="09:00", end="17:00"),
            },
        ),
        level_scheme=LevelScheme(
            pdh_pdl_source="prior_day_full",
            session_levels=("asia_high", "asia_low", "london_high", "london_low", "pdh", "pdl"),
            available_from_guard=True,
        ),
        touch_rule=TouchRule(
            type="bar_intersect",
            bar_type="tick",
            zone_proximity_pts=ZONE_PROXIMITY_PTS,
            zone_representative_price="mean_of_constituent_levels",
            scope="first_touch_per_zone_per_day",
            direction_from_side={"LOW": "LONG", "HIGH": "SHORT"},
        ),
        feature_windows=FeatureWindows(
            interaction_window_minutes=5,
            approach_window_minutes=90,
            within_band_pts=2.0,
            level_proximity_pts=0.5,
            large_trade_threshold=10,
            mid_price_source="trade_price",
        ),
        interaction_features=(
            "int_time_beyond_level",
            "int_time_within_2pts",
            "int_absorption_ratio",
        ),
        approach_features=(
            "app_large_trade_vol_pct",
            "app_avg_trade_size",
            "app_max_spread",
        ),
    )


def _bar(timeframe_ticks: int, low_ticks: int, high_ticks: int, day: date, close_ts: datetime) -> Bar:
    return Bar(
        timeframe_ticks=timeframe_ticks,
        trading_day=day,
        bar_index=0,
        bar_id="b0",
        open_ts_utc=close_ts,
        close_ts_utc=close_ts,
        open_ticks=low_ticks,
        high_ticks=high_ticks,
        low_ticks=low_ticks,
        close_ticks=high_ticks,
        volume=2,
        trade_count=timeframe_ticks,
        is_complete=True,
        is_partial=False,
        close_reason=CloseReason.COMPLETE,
    )


def test_plugin_touch_output_equals_direct_detect_touches() -> None:
    """The plugin's on_bar_closed touches == a direct detect_touches on the same bars+zones."""
    day = date(2026, 1, 6)
    close_ts = datetime(2026, 1, 6, 14, 2, tzinfo=UTC)
    # Two UNGATED levels (available_from=None → no look-ahead gate): a LOW at 100.0 and a
    # HIGH at 110.0. Gap 10 > ZONE_PROXIMITY_PTS so they form two separate zones.
    levels = (
        Level("pdl", 100.0, Side.LOW, None),
        Level("pdh", 110.0, Side.HIGH, None),
    )

    plugin = get_strategy("touch_reversal")()
    plugin.configure(_section(), _Ctx())
    plugin.set_static_levels(levels)

    tf = plugin.required_bars()[0].size
    # Bar range [99.0, 101.0] points straddles the LOW zone's rep price 100.0, not 110.0.
    low_ticks = round(99.0 / DEFAULT_TICK_SIZE)
    high_ticks = round(101.0 / DEFAULT_TICK_SIZE)
    bar = _bar(tf, low_ticks, high_ticks, day, close_ts)

    step = plugin.on_bar_closed(bar, _Ctx())
    plugin_touches = tuple(setup.touch for setup in step.setups)

    # Direct call on the SAME bar and the SAME zones, derived the identical way.
    direct_zones = build_zones(list(levels), zone_proximity_pts=ZONE_PROXIMITY_PTS)
    direct_touches = tuple(
        detect_touches((bar,), direct_zones, tick_size=DEFAULT_TICK_SIZE, trading_day=day)
    )

    # Byte-identical touches (Touch is a frozen dataclass; == compares all fields).
    assert plugin_touches == direct_touches
    assert len(plugin_touches) == 1
    assert plugin_touches[0].representative_price == 100.0
    assert plugin_touches[0].direction is Direction.LONG  # LOW touch → LONG
    # The plugin's decisions mirror the same touches one-for-one.
    assert tuple(decision.touch for decision in step.decisions) == direct_touches


def test_on_bar_closed_processes_the_handed_bar_no_internal_gate() -> None:
    """B2 PART 2: the plugin no longer self-gates on its declared decision timeframe — the
    RUNTIME gates which bars reach on_bar_closed (so the plugin path is byte-identical for any
    runtime decision_timeframe, not only 147). A straddling bar of a DIFFERENT timeframe still
    produces the touch when handed directly to on_bar_closed."""
    plugin = get_strategy("touch_reversal")()
    plugin.configure(_section(), _Ctx())
    plugin.set_static_levels((Level("pdl", 100.0, Side.LOW, None),))
    decision_tf = plugin.required_bars()[0].size
    bar = _bar(decision_tf + 1, round(99.0 / DEFAULT_TICK_SIZE), round(101.0 / DEFAULT_TICK_SIZE),
               date(2026, 1, 6), datetime(2026, 1, 6, 14, 2, tzinfo=UTC))
    step = plugin.on_bar_closed(bar, _Ctx())
    assert len(step.touches) == 1  # processed despite tf != the declared decision bar
    assert step.touches[0].representative_price == 100.0


def test_registry_resolves_touch_reversal_and_fails_closed() -> None:
    """get_strategy resolves the registered plugin and fail-closes on an unknown id (A2)."""
    assert get_strategy("touch_reversal") is TouchReversalPlugin
    with pytest.raises(ContractError):
        get_strategy("does_not_exist")


def test_section_forbids_unknown_keys() -> None:
    """TouchReversalSection is extra='forbid' — an unknown key fails closed (A3)."""
    section = _section()
    assert section.touch_rule.zone_proximity_pts == ZONE_PROXIMITY_PTS
    with pytest.raises(ValidationError):
        TouchReversalSection.model_validate({**section.model_dump(), "bogus_key": 1})


def test_plugin_declarations_match_engine_constants() -> None:
    """feature_spec/label_policy declare the six features and the fixed-points barrier (A3)."""
    spec = TouchReversalPlugin.feature_spec()
    assert spec.names == (
        "int_time_beyond_level",
        "int_time_within_2pts",
        "int_absorption_ratio",
        "app_large_trade_vol_pct",
        "app_avg_trade_size",
        "app_max_spread",
    )
    policy = TouchReversalPlugin.label_policy()
    assert policy.barrier_mode == "fixed_points"
    # tp=15 / sl=30 anchored to constants.py (NOT a bundle's per-model value).
    assert policy.barrier.tp_points == 15.0
    assert policy.barrier.sl_points == 30.0
    # The barrier projects fixed points off the entry, direction-aware.
    assert policy.barrier.stop_price(100.0, Direction.LONG) == 70.0
    assert policy.barrier.target_price(100.0, Direction.LONG) == 115.0


def test_session_scheme_round_trips_drop_nothing() -> None:
    """E3: contract<->runtime scheme adaptation drops nothing in either direction.

    The research scheme (closed_window=None) round-trips identically as before, and
    the CT scheme's 16:00-18:00 closed window — the recorded pre-E3 round-trip gap —
    now survives ``_contract_scheme_from_runtime`` -> ``_runtime_scheme_from_section``.
    """
    for runtime_scheme in (RESEARCH_SESSION_SCHEME, TRADE_LAB_CT_SESSION_SCHEME):
        contract_form = _contract_scheme_from_runtime(runtime_scheme)
        assert _runtime_scheme_from_section(contract_form) == runtime_scheme

    ct_contract = _contract_scheme_from_runtime(TRADE_LAB_CT_SESSION_SCHEME)
    assert ct_contract.closed_window is not None
    assert (ct_contract.closed_window.start, ct_contract.closed_window.end) == (
        "16:00",
        "18:00",
    )
    assert _contract_scheme_from_runtime(RESEARCH_SESSION_SCHEME).closed_window is None
