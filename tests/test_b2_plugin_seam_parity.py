"""Plugin-path behavioral regression: cross-bar first-touch suppression.

(Originally the B2 seam off-vs-on parity test. B3 removed the hardwired None path, so there
is no comparator runtime any more; this is repurposed into a plugin-path BEHAVIOR test that
preserves the one coverage the off-vs-on test uniquely had: a zone that fires on an early
decision bar and is straddled again by later bars must fire EXACTLY once across the day —
cross-bar first-touch suppression, which the single-bar A3 equivalence test cannot reach.)

The runtime auto-attaches the registered ``touch_reversal`` plugin (B3 default), so a bare
construction exercises the production path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from strategy_core.constants import DEFAULT_TICK_SIZE
from strategy_core.runtime.state import StrategyRuntime
from strategy_core.types import Level, Side, Trade

#: Must equal the plugin's declared decision bar so the runtime's decision_timeframe gate fires.
DECISION_TF = 147


def _trade_stream(n_bars: int) -> list[Trade]:
    """n_bars * DECISION_TF trades in the NY session, one trading day, prices alternating
    99.0 / 101.0 ticks so EVERY 147-tick bar's range [99.0, 101.0] straddles the 100.0 zone."""
    base = datetime(2026, 1, 6, 14, 30, tzinfo=UTC)  # 09:30 ET, NY session, trading_day 2026-01-06
    low_ticks = round(99.0 / DEFAULT_TICK_SIZE)  # 396
    high_ticks = round(101.0 / DEFAULT_TICK_SIZE)  # 404
    return [
        Trade(
            event_ts_utc=base + timedelta(seconds=i),
            price_ticks=low_ticks if i % 2 == 0 else high_ticks,
            size=1,
            side="B",
        )
        for i in range(n_bars * DECISION_TF)
    ]


def test_plugin_path_cross_bar_first_touch_suppression() -> None:
    # Bare construction auto-attaches the default touch_reversal plugin (B3).
    runtime = StrategyRuntime(
        requested_symbol="NQ",
        timeframes=(DECISION_TF,),
        decision_timeframe=DECISION_TF,
    )
    assert runtime._plugin is not None and runtime._plugin.strategy_id == "touch_reversal"
    # The plugin's declared decision bar agrees with the runtime's decision_timeframe gate.
    assert runtime._plugin.required_bars()[0].size == runtime.decision_timeframe == DECISION_TF

    # One ungated LOW zone at rep 100.0; seeded via set_static_levels (propagates to the plugin).
    runtime.set_static_levels((Level("pdl", 100.0, Side.LOW, None),))

    # Drive 3 decision bars; bar 1 fires the zone, bars 2 & 3 re-straddle it.
    total_touches = sum(len(runtime.process_event(trade).touches) for trade in _trade_stream(n_bars=3))

    # The re-straddled zone fired EXACTLY once across the 3 bars (cross-bar suppression).
    assert total_touches == 1
    snap = runtime.snapshot()
    assert len(snap.touches) == 1
    assert len(snap.zones) == 1 and snap.zones[0].touched is True
