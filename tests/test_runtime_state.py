from datetime import UTC, datetime

from strategy_core.runtime.state import StrategyRuntime
from strategy_core.types import Quote, Trade


def _ts(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 6, hour, minute, tzinfo=UTC)


def test_empty_runtime_snapshot_is_serializable_and_path_free() -> None:
    runtime = StrategyRuntime(timeframes=(2,), requested_symbol="NQ.c.0")
    snapshot = runtime.snapshot()
    payload = snapshot.to_dict()
    assert payload["feed_status"]["state"] == "disconnected"
    assert payload["current_bars"] == []
    assert "/" not in str(payload)
    assert "api_key" not in str(payload).lower()


def test_quote_updates_context_without_incrementing_bars() -> None:
    runtime = StrategyRuntime(timeframes=(2,), requested_symbol="NQ.c.0")
    update = runtime.process_event(Quote(_ts(14), bid_price_ticks=68000, ask_price_ticks=68001))
    snapshot = runtime.snapshot()
    assert update.current_bars == ()
    assert update.closed_bars == ()
    assert snapshot.last_quote is not None
    assert snapshot.feed_status.last_event_ts_utc == _ts(14)


def test_trades_advance_bars_and_session_state_uses_strategy_core_et_scheme() -> None:
    runtime = StrategyRuntime(timeframes=(2,), requested_symbol="NQ.c.0")
    first = runtime.process_event(Trade(_ts(14), 68000, 1, "B"))
    second = runtime.process_event(Trade(_ts(14, 1), 68004, 2, "B"))
    assert first.current_bars[0].trade_count == 1
    assert len(second.closed_bars) == 1
    assert second.closed_bars[0].trade_count == 2
    snapshot = runtime.snapshot()
    assert snapshot.session == "ny"
    assert snapshot.trading_day.isoformat() == "2026-01-06"
