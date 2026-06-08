import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from strategy_core.runtime.live import LiveRuntime, LiveState
from strategy_core.types import Trade


class _Feed:
    def __init__(self, items) -> None:
        self.started = False
        self.stopped = False
        self._items = items

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def events(self) -> AsyncIterator[object]:
        for item in self._items:
            yield item


def test_live_runtime_processes_feed_items_and_disconnects_cleanly() -> None:
    processed = []
    updates = []
    feed = _Feed([Trade(datetime(2026, 1, 6, 14, tzinfo=UTC), 68000, 1, "B")])
    live = LiveRuntime(
        feed,
        process_item=lambda item: processed.append(item) or "update",
        on_update=lambda update: updates.append(update),
    )

    async def run() -> None:
        await live.start()
        assert live.status().state is LiveState.RUNNING
        assert feed.started is True
        await live.wait_finished()
        assert live.status().state is LiveState.DISCONNECTED
        await live.stop()

    asyncio.run(run())

    assert feed.stopped is True
    assert len(processed) == 1
    assert updates == ["update"]
    assert live.status().events_processed == 1


def test_live_runtime_start_failure_stops_partial_feed_and_records_error() -> None:
    class _FailingFeed(_Feed):
        async def start(self) -> None:
            self.started = True
            raise RuntimeError("provider failed api_key=secret")

    feed = _FailingFeed([])
    live = LiveRuntime(feed, process_item=lambda item: None)

    async def run() -> None:
        try:
            await live.start()
        except RuntimeError:
            pass

    asyncio.run(run())

    assert feed.started is True
    assert feed.stopped is True
    status = live.status()
    assert status.state is LiveState.FAILED
    assert status.last_error == "RuntimeError"
    assert "secret" not in (status.last_message or "").lower()
