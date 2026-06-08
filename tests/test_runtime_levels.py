from datetime import UTC, datetime

from strategy_core.runtime.state import StrategyRuntime
from strategy_core.types import Side, Trade


def _ts(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 6, hour, minute, tzinfo=UTC)


def test_prior_day_summary_loads_pdh_pdl_with_start_availability() -> None:
    runtime = StrategyRuntime(timeframes=(2,), requested_symbol="NQ.c.0")
    runtime.load_prior_day_summary(datetime(2026, 1, 5, tzinfo=UTC).date(), high_ticks=68100, low_ticks=67900)
    runtime.process_event(Trade(_ts(14), 68000, 1, "B"))
    levels = {level.name: level for level in runtime.snapshot().levels}
    assert levels["pdh"].side is Side.HIGH
    assert levels["pdl"].side is Side.LOW
    assert levels["pdh"].available_from is not None


def test_asia_and_london_ranges_use_strategy_core_sessions_not_chicago_closed_window() -> None:
    runtime = StrategyRuntime(timeframes=(2,), requested_symbol="NQ.c.0")
    runtime.process_event(Trade(datetime(2026, 1, 6, 0, 30, tzinfo=UTC), 68000, 1, "B"))  # Asia ET
    runtime.process_event(Trade(datetime(2026, 1, 6, 12, 30, tzinfo=UTC), 68100, 1, "B"))  # London ET
    runtime.process_event(Trade(datetime(2026, 1, 6, 22, 30, tzinfo=UTC), 68200, 1, "B"))  # ET 17:30 gap, not CT closed
    levels = {level.name for level in runtime.snapshot().levels}
    assert {"asia_high", "asia_low", "london_high", "london_low"} <= levels
    assert runtime.snapshot().trading_day is not None
