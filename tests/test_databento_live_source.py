import asyncio
from datetime import UTC, datetime

import strategy_core
from strategy_core.data.databento_live import DatabentoLiveSource, normalize_provider_message
from strategy_core.data.events import DataQualityWarning
from strategy_core.types import Quote, Trade


def test_importing_strategy_core_does_not_require_databento_sdk() -> None:
    assert strategy_core.ENGINE_VERSION.startswith("strategy_core_engine_")


def test_fake_provider_messages_normalize_trade_and_quote() -> None:
    trade = normalize_provider_message({"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "price": 17000.0, "size": 2, "side": "B"}, requested_symbol="NQ.c.0", schema="trades")
    quote = normalize_provider_message({"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "bid_px": 17000.0, "ask_px": 17000.25}, requested_symbol="NQ.c.0", schema="mbp-1")
    assert isinstance(trade, Trade)
    assert isinstance(quote, Quote)
    assert trade.price_ticks == 68000


def test_fake_provider_messages_keep_explicit_tick_fields_as_ticks() -> None:
    trade = normalize_provider_message(
        {"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "price_ticks": 68000, "size": 1},
        requested_symbol="NQ.c.0",
        schema="trades",
    )
    quote = normalize_provider_message(
        {
            "ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC),
            "bid_price_ticks": 67999,
            "ask_price_ticks": 68001,
        },
        requested_symbol="NQ.c.0",
        schema="mbp-1",
    )

    assert isinstance(trade, Trade)
    assert isinstance(quote, Quote)
    assert trade.price_ticks == 68000
    assert quote.bid_price_ticks == 67999
    assert quote.ask_price_ticks == 68001


def test_plain_integer_price_fields_convert_to_ticks_not_presumed_ticks() -> None:
    trade = normalize_provider_message(
        {"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "price": 170000, "size": 1},
        requested_symbol="NQ.c.0",
        schema="trades",
    )

    assert isinstance(trade, Trade)
    assert trade.price_ticks == 680000


def test_live_source_invalid_trade_size_emits_warning_not_trade() -> None:
    source = DatabentoLiveSource(api_key="x", requested_symbol="NQ.c.0", queue_maxsize=10)
    source.start_fake()
    source.provider_callback(
        {"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "price": 17000.0, "size": 0},
        schema="trades",
    )

    items = asyncio.run(source.collect_available())

    assert not any(isinstance(item, Trade) for item in items)
    assert any(isinstance(item, DataQualityWarning) for item in items)


def test_live_source_queue_overflow_emits_warning_and_never_exposes_api_key() -> None:
    source = DatabentoLiveSource(api_key="x", requested_symbol="NQ.c.0", queue_maxsize=1)
    source.start_fake()
    source.provider_callback({"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "price": 17000.0, "size": 1}, schema="trades")
    source.provider_callback({"ts_event": datetime(2026, 1, 6, 14, 1, tzinfo=UTC), "price": 17000.25, "size": 1}, schema="trades")
    items = asyncio.run(source.collect_available())
    assert any(isinstance(item, DataQualityWarning) for item in items)
    assert "SECRET" not in str(items)
