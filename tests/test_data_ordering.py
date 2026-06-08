from datetime import UTC, datetime

from strategy_core.data.ordering import canonical_event_sort_key, side_signed_price_ticks, sort_events
from strategy_core.types import Trade


def _trade(price_ticks: int, side: str | None, *, size: int = 1, seq: int = 1) -> Trade:
    return Trade(datetime(2026, 1, 6, 14, 0, tzinfo=UTC), price_ticks, size, side)


def test_side_signed_price_orders_buy_sweeps_ascending_and_sell_sweeps_descending() -> None:
    assert side_signed_price_ticks(_trade(100, "B")) == 100
    assert side_signed_price_ticks(_trade(100, "A")) == -100
    buy_events = [_trade(102, "B"), _trade(100, "B"), _trade(101, "B")]
    sell_events = [_trade(100, "A"), _trade(102, "A"), _trade(101, "A")]
    assert [event.price_ticks for event in sort_events(buy_events, sequence=lambda _: 7)] == [100, 101, 102]
    assert [event.price_ticks for event in sort_events(sell_events, sequence=lambda _: 7)] == [102, 101, 100]


def test_canonical_sort_key_uses_ts_sequence_side_signed_price_and_size() -> None:
    event = _trade(101, "B", size=4)
    assert canonical_event_sort_key(event, sequence=9) == (event.event_ts_utc, 9, 101, 4)
