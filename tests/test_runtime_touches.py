from datetime import UTC, datetime, timedelta

from strategy_core.runtime.state import StrategyRuntime
from strategy_core.types import Direction, Level, Side, Trade


def test_touches_fire_on_completed_bar_range_intersection_not_exact_trade_price() -> None:
    runtime = StrategyRuntime(timeframes=(2,), decision_timeframe=2, requested_symbol="NQ.c.0")
    runtime.set_static_levels((Level("pdl", 100.50, Side.LOW, available_from=datetime(2026, 1, 6, 14, tzinfo=UTC)),))
    runtime.process_event(Trade(datetime(2026, 1, 6, 14, 0, tzinfo=UTC), 400, 1, "B"))
    update = runtime.process_event(Trade(datetime(2026, 1, 6, 14, 1, tzinfo=UTC), 404, 1, "B"))
    assert len(update.touches) == 1
    assert update.touches[0].direction is Direction.LONG
    assert update.touches[0].representative_price == 100.50


def test_available_from_guard_prevents_pre_session_close_self_touch() -> None:
    runtime = StrategyRuntime(timeframes=(2,), decision_timeframe=2, requested_symbol="NQ.c.0")
    available = datetime(2026, 1, 6, 14, 5, tzinfo=UTC)
    runtime.set_static_levels((Level("pdh", 100.50, Side.HIGH, available_from=available),))
    runtime.process_event(Trade(available - timedelta(minutes=2), 400, 1, "B"))
    early = runtime.process_event(Trade(available - timedelta(minutes=1), 404, 1, "B"))
    runtime.process_event(Trade(available, 400, 1, "B"))
    late = runtime.process_event(Trade(available + timedelta(minutes=1), 404, 1, "B"))
    assert early.touches == ()
    assert len(late.touches) == 1
