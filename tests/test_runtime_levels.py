from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from strategy_core.runtime.levels import StrategyLevelState
from strategy_core.runtime.state import StrategyRuntime
from strategy_core.types import Side, Trade

_ET = ZoneInfo("US/Eastern")


def _ts(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 6, hour, minute, tzinfo=UTC)


def _et_trade(year: int, month: int, day: int, hour: int, minute: int, price_ticks: int) -> Trade:
    ts = datetime(year, month, day, hour, minute, tzinfo=_ET).astimezone(UTC)
    return Trade(ts, price_ticks, 1, "B")


def test_prior_day_summary_loads_pdh_pdl_with_start_availability() -> None:
    runtime = StrategyRuntime(timeframes=(2,), requested_symbol="NQ.c.0")
    runtime.load_prior_day_summary(datetime(2026, 1, 5, tzinfo=UTC).date(), high_ticks=68100, low_ticks=67900)
    runtime.process_event(Trade(_ts(14), 68000, 1, "B"))
    levels = {level.name: level for level in runtime.snapshot().levels}
    assert levels["pdh"].side is Side.HIGH
    assert levels["pdl"].side is Side.LOW
    assert levels["pdh"].available_from is not None


def test_two_day_stream_banks_pdh_pdl_organically() -> None:
    """W1 P2b: the trading-day roll banks the completed day's extremes; day 2 emits
    pdh/pdl with no external seed."""
    state = StrategyLevelState()
    # Trading day 2025-07-15 (rolls at 18:00 ET on 7/14): high 68400, low 68000.
    state.process_trade(_et_trade(2025, 7, 14, 19, 0, 68400))
    state.process_trade(_et_trade(2025, 7, 15, 10, 0, 68000))
    assert {level.name for level in state.levels()}.isdisjoint({"pdh", "pdl"})
    # First trade after 18:00 ET on 7/15 rolls to trading day 2025-07-16.
    levels = {level.name: level for level in state.process_trade(_et_trade(2025, 7, 15, 19, 30, 68200))}
    assert levels["pdh"].price == 68400 * 0.25
    assert levels["pdl"].price == 68000 * 0.25
    assert levels["pdh"].side is Side.HIGH
    assert levels["pdl"].side is Side.LOW


def test_explicit_prior_day_load_wins_over_organic_banking() -> None:
    """W1 P2b: an external seed for the same completed day is never overwritten by
    the roll — the explicitly loaded extremes win."""
    state = StrategyLevelState()
    state.process_trade(_et_trade(2025, 7, 14, 19, 0, 68400))
    state.load_prior_day_summary(
        datetime(2025, 7, 15, tzinfo=UTC).date(), high_ticks=70000, low_ticks=60000
    )
    levels = {level.name: level for level in state.process_trade(_et_trade(2025, 7, 15, 19, 30, 68200))}
    assert levels["pdh"].price == 70000 * 0.25
    assert levels["pdl"].price == 60000 * 0.25


def test_asia_and_london_ranges_use_strategy_core_sessions_not_chicago_closed_window() -> None:
    runtime = StrategyRuntime(timeframes=(2,), requested_symbol="NQ.c.0")
    runtime.process_event(Trade(datetime(2026, 1, 6, 0, 30, tzinfo=UTC), 68000, 1, "B"))  # Asia ET
    runtime.process_event(Trade(datetime(2026, 1, 6, 12, 30, tzinfo=UTC), 68100, 1, "B"))  # London ET
    runtime.process_event(Trade(datetime(2026, 1, 6, 22, 30, tzinfo=UTC), 68200, 1, "B"))  # ET 17:30 gap, not CT closed
    levels = {level.name for level in runtime.snapshot().levels}
    assert {"asia_high", "asia_low", "london_high", "london_low"} <= levels
    assert runtime.snapshot().trading_day is not None


def test_friday_bank_serves_monday_pdh_pdl_across_the_weekend_gap() -> None:
    """W2 P1f rider: the emission lookup resolves the MOST RECENT banked day with
    key < the current trading day, so a Friday bank serves Monday across the
    weekend gap (verified: no fix needed — this pins the behavior)."""
    state = StrategyLevelState()
    # Trading day Friday 2025-07-11 (rolls at 18:00 ET on Thu 7/10): high/low banked.
    state.process_trade(_et_trade(2025, 7, 10, 19, 0, 68400))
    state.process_trade(_et_trade(2025, 7, 11, 10, 0, 68000))
    assert {level.name for level in state.levels()}.isdisjoint({"pdh", "pdl"})
    # First trade of Monday's trading day (Sunday 19:00 ET) rolls across the
    # weekend; Friday is the most recent banked day and must emit as pdh/pdl.
    levels = {
        level.name: level
        for level in state.process_trade(_et_trade(2025, 7, 13, 19, 0, 68200))
    }
    assert levels["pdh"].price == 68400 * 0.25
    assert levels["pdl"].price == 68000 * 0.25
    assert levels["pdh"].side is Side.HIGH
    assert levels["pdl"].side is Side.LOW
