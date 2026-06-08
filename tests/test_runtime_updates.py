from datetime import UTC, datetime

from strategy_core.runtime.state import FeedStatus, StrategyRuntime
from strategy_core.types import Trade


def test_runtime_update_to_dict_is_neutral_and_serializable() -> None:
    runtime = StrategyRuntime(timeframes=(1,), requested_symbol="NQ.c.0")
    update = runtime.process_event(Trade(datetime(2026, 1, 6, 14, tzinfo=UTC), 68000, 3, "B"))
    payload = update.to_dict()
    assert payload["closed_bars"][0]["bar_id"] == "1t:2026-01-06:0"
    assert payload["feed_status"]["state"] == "replaying"


def test_feed_status_redacts_paths_and_secrets() -> None:
    status = FeedStatus(state="failed", mode="replay", last_message="/tmp/data api_key=secret")
    assert "<path>" in status.to_dict()["last_message"]
    assert "secret" not in status.to_dict()["last_message"].lower()
