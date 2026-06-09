"""B2 PART 1 seam parity: the plugin PATH is byte-identical to the None path.

PLAN §7 Step B2 (routing half). Two `StrategyRuntime`s over the SAME config — one with
`plugin=None` (the verbatim hardwired fold), one with the registered `touch_reversal`
plugin — are driven by the IDENTICAL multi-bar trade stream and must emit byte-identical
`RuntimeUpdate`s at every trade, INCLUDING the cross-bar first-touch suppression the A3
single-bar test cannot reach (a zone that fires on an early decision bar and is straddled
again by a later bar must fire EXACTLY once).

This is the only place a `StrategyRuntime` is constructed with a plugin/section — the
production/TL construction is unchanged (that is B2-wire, PART 2).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from strategy_core.constants import (
    DEFAULT_TICK_SIZE,
    RESEARCH_SESSION_SCHEME,
    ZONE_PROXIMITY_PTS,
)
from strategy_core.contract.schema import (
    FeatureWindows,
    InferencePolicy,
    LabelPolicy,
    LevelScheme,
    SessionScheme,
    SessionWindow,
    TouchRule,
)
from strategy_core.runtime.state import StrategyRuntime
from strategy_core.strategies.registry import get_strategy
from strategy_core.strategies.touch_reversal.plugin import (  # noqa: F401 -- import registers the plugin
    TouchReversalPlugin,
)
from strategy_core.strategies.touch_reversal.section import TouchReversalSection
from strategy_core.types import Level, Side, Trade

#: Must equal the plugin's _DECISION_TIMEFRAME so the runtime gate and the plugin gate agree.
DECISION_TF = 147


def _section() -> TouchReversalSection:
    """A valid v3 touch section whose session_scheme converts to RESEARCH_SESSION_SCHEME (I4a)
    and whose zone_proximity_pts equals build_zones' default (I4b)."""
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
        label_policy=LabelPolicy(
            resolution="mae_first",
            entry_reference="realistic_at_decision",
            decision_offset_minutes=5,
            tp_points=15.0,
            sl_points=30.0,
            trap_mfe_min=5.0,
            forward_bar_type="tick",
            forward_cutoff="17:00_US/Eastern_ny_close",
            no_resolution_dropped=True,
        ),
        inference=InferencePolicy(
            eligible_class="tradeable_reversal",
            eligible_session="ny",
            confidence_gate=0.70,
        ),
    )


def _trade_stream(n_bars: int) -> list[Trade]:
    """n_bars * DECISION_TF trades in the NY session, one trading day, prices alternating
    99.0 / 101.0 ticks so EVERY 147-tick bar's range [99.0, 101.0] straddles the 100.0 zone."""
    base = datetime(2026, 1, 6, 14, 30, tzinfo=UTC)  # 09:30 ET, NY session, trading_day 2026-01-06
    low_ticks = round(99.0 / DEFAULT_TICK_SIZE)   # 396
    high_ticks = round(101.0 / DEFAULT_TICK_SIZE)  # 404
    n = n_bars * DECISION_TF
    return [
        Trade(
            event_ts_utc=base + timedelta(seconds=i),
            price_ticks=low_ticks if i % 2 == 0 else high_ticks,
            size=1,
            side="B",
        )
        for i in range(n)
    ]


def test_plugin_path_byte_identical_to_none_path_across_multiple_bars() -> None:
    levels = (Level("pdl", 100.0, Side.LOW, None),)  # one ungated LOW zone at rep 100.0
    section = _section()
    plugin = get_strategy("touch_reversal")()

    runtime_b = StrategyRuntime(
        requested_symbol="NQ",
        timeframes=(DECISION_TF,),
        decision_timeframe=DECISION_TF,
        plugin=plugin,
        strategy_section=section,
    )
    runtime_a = StrategyRuntime(
        requested_symbol="NQ",
        timeframes=(DECISION_TF,),
        decision_timeframe=DECISION_TF,
    )
    # Seed the SAME static level into A's level_state, B's level_state, and the plugin's
    # own level_state (configured in B's __init__), so all three produce identical zones.
    runtime_a.set_static_levels(levels)
    runtime_b.set_static_levels(levels)
    plugin.set_static_levels(levels)

    # ---- Byte-identity preconditions (I4) ----
    # decision-timeframe agreement: runtime loop gates on decision_timeframe; on_bar_closed
    # gates on the plugin's _DECISION_TIMEFRAME — a mismatch silently emits no plugin touches.
    assert plugin.required_bars()[0].size == runtime_b.decision_timeframe == DECISION_TF
    # I4a: the plugin's configured scheme == the runtime's level_state scheme.
    assert runtime_b._plugin._levels._scheme == runtime_a.level_state._scheme == RESEARCH_SESSION_SCHEME
    # I4b: section proximity == build_zones' default (used by _zones_for_detection).
    assert section.touch_rule.zone_proximity_pts == ZONE_PROXIMITY_PTS
    # I4c: ctx.tick_size == the runtime's tick_size.
    assert runtime_b._ctx.tick_size == runtime_b.tick_size == DEFAULT_TICK_SIZE

    # ---- Drive both runtimes with the identical stream; compare every update ----
    trades = _trade_stream(n_bars=3)  # 3 decision bars; bar 1 fires, bars 2 & 3 re-straddle
    a_touch_total = 0
    b_touch_total = 0
    for trade in trades:
        ua = runtime_a.process_event(trade)
        ub = runtime_b.process_event(trade)
        # Full field-for-field byte identity: touches, snapshot zones (incl. each zone's
        # `touched` flag), levels, bars, feed status, last quote.
        assert ua.to_dict() == ub.to_dict(), f"plugin path diverged at {trade.event_ts_utc}"
        a_touch_total += len(ua.touches)
        b_touch_total += len(ub.touches)

    # The re-straddled zone fired EXACTLY once on BOTH paths (cross-bar suppression).
    assert a_touch_total == b_touch_total == 1

    # Final snapshots identical; the zone is touched and was never re-fired.
    assert runtime_a.snapshot().to_dict() == runtime_b.snapshot().to_dict()
    snap_b = runtime_b.snapshot()
    assert len(snap_b.touches) == 1
    assert len(snap_b.zones) == 1 and snap_b.zones[0].touched is True
