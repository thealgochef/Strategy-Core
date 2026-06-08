import asyncio
import time
from datetime import UTC, datetime

from strategy_core.runtime.replay import ReplayConfig, ReplayRuntime, ReplayState
from strategy_core.runtime.state import StrategyRuntime
from strategy_core.types import Trade


class _Source:
    def __init__(self, items):
        self._items = items
    def events(self):
        yield from self._items

class _FailingSource:
    def events(self):
        raise RuntimeError("boom /tmp/data api_key=secret")
        yield


class _BlockingSource:
    def __init__(self, item, *, delay_seconds: float = 0.2):
        self._item = item
        self._delay_seconds = delay_seconds

    def events(self):
        time.sleep(self._delay_seconds)
        yield self._item


def test_replay_emits_fixture_events_in_order_immediate_mode() -> None:
    runtime = StrategyRuntime(timeframes=(2,), requested_symbol="NQ.c.0")
    source = _Source([
        Trade(datetime(2026, 1, 6, 14, 0, tzinfo=UTC), 68000, 1, "B"),
        Trade(datetime(2026, 1, 6, 14, 1, tzinfo=UTC), 68001, 1, "B"),
    ])
    replay = ReplayRuntime(runtime, source)
    asyncio.run(replay.start(ReplayConfig(speed=0)))
    assert replay.status().state is ReplayState.COMPLETED
    assert replay.status().events_processed == 2
    assert len(runtime.snapshot().recent_closed_bars) == 1


def test_replay_source_exception_transitions_failed_with_sanitized_error() -> None:
    replay = ReplayRuntime(StrategyRuntime(timeframes=(2,)), _FailingSource())
    asyncio.run(replay.start(ReplayConfig(speed=0)))
    status = replay.status()
    assert status.state is ReplayState.FAILED
    assert status.last_error == "RuntimeError"
    assert "secret" not in status.last_message.lower()
    assert "/tmp" not in status.last_message


def test_replay_runtime_accepts_custom_processor_and_update_callback() -> None:
    trade = Trade(datetime(2026, 1, 6, 14, 0, tzinfo=UTC), 68000, 1, "B")
    processed = []
    updates = []
    replay = ReplayRuntime(
        None,
        _Source([trade]),
        process_item=lambda item: processed.append(item) or "update",
        on_update=lambda update: updates.append(update),
    )

    asyncio.run(replay.start(ReplayConfig(speed=0)))

    assert replay.status().state is ReplayState.COMPLETED
    assert replay.status().events_processed == 1
    assert processed == [trade]
    assert updates == ["update"]


def test_replay_fetches_blocking_source_items_off_event_loop_and_honors_stop() -> None:
    async def scenario() -> None:
        trade = Trade(datetime(2026, 1, 6, 14, 0, tzinfo=UTC), 68000, 1, "B")
        replay = ReplayRuntime(StrategyRuntime(timeframes=(2,)), _BlockingSource(trade))

        started = time.perf_counter()
        task = asyncio.create_task(replay.start(ReplayConfig(speed=0)))
        await asyncio.sleep(0.05)
        assert time.perf_counter() - started < 0.15

        await replay.stop()
        await task

        status = replay.status()
        assert status.state is ReplayState.STOPPED
        assert status.events_processed == 0

    asyncio.run(scenario())
