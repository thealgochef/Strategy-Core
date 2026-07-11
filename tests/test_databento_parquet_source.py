from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from strategy_core.data.databento_parquet import DatabentoParquetSource
from strategy_core.data.events import DataQualityWarning
from strategy_core.types import Quote, Trade


def _write(path: Path, rows: list[dict]) -> Path:
    pq.write_table(pa.Table.from_pylist(rows), path)
    return path


def test_trades_parquet_normalizes_to_strategy_core_trades(tmp_path: Path) -> None:
    path = _write(tmp_path / "trades.parquet", [{"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "price": 17000.0, "size": 2, "side": "B", "sequence": 1}])
    events = list(DatabentoParquetSource(paths=(path,), requested_symbol="NQ.c.0", schema="trades").events())
    assert isinstance(events[0], Trade)
    assert events[0].price_ticks == 68000
    assert events[0].event_ts_utc.tzinfo is not None


def test_mbp10_trade_rows_emit_trades_and_quotes_do_not_increment_bars(tmp_path: Path) -> None:
    path = _write(tmp_path / "mbp10.parquet", [
        {"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "action": "T", "price": 17000.0, "size": 2, "side": "B", "bid_px_00": 16999.75, "ask_px_00": 17000.25, "sequence": 1},
        {"ts_event": datetime(2026, 1, 6, 14, 1, tzinfo=UTC), "action": "A", "price": 17000.25, "size": 1, "side": "B", "bid_px_00": 17000.0, "ask_px_00": 17000.5, "sequence": 2},
    ])
    events = list(DatabentoParquetSource(paths=(path,), requested_symbol="NQ.c.0", schema="mbp-10").events())
    assert sum(isinstance(event, Trade) for event in events) == 1
    assert sum(isinstance(event, Quote) for event in events) == 2


def test_multiple_files_merge_in_canonical_order(tmp_path: Path) -> None:
    ts = datetime(2026, 1, 6, 14, tzinfo=UTC)
    p1 = _write(tmp_path / "a.parquet", [{"ts_event": ts, "price": 17000.25, "size": 1, "side": "A", "sequence": 1}])
    p2 = _write(tmp_path / "b.parquet", [{"ts_event": ts, "price": 17000.50, "size": 1, "side": "A", "sequence": 1}])
    events = [event for event in DatabentoParquetSource(paths=(p1, p2), requested_symbol="NQ.c.0", schema="trades").events() if isinstance(event, Trade)]
    assert [event.price_ticks for event in events] == [68002, 68001]


def test_invalid_rows_produce_path_safe_warning(tmp_path: Path) -> None:
    path = _write(tmp_path / "bad.parquet", [{"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "price": 17000.10, "size": 1, "side": "B"}])
    events = list(DatabentoParquetSource(paths=(path,), requested_symbol="NQ.c.0", schema="trades").events())
    warnings = [event for event in events if isinstance(event, DataQualityWarning)]
    assert warnings
    assert str(tmp_path) not in str(warnings[0])


def test_front_month_filter_drops_spreads_and_non_dominant_instruments(tmp_path: Path) -> None:
    # Dominance is by TRADE-ROW COUNT (the TL/QL rule), not summed size: id 1 has two
    # rows and wins despite id 3's larger single trade.
    path = _write(tmp_path / "mixed.parquet", [
        {"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "price": 17000.0, "size": 1, "side": "B", "instrument_id": 1, "raw_symbol": "NQZ6", "sequence": 1},
        {"ts_event": datetime(2026, 1, 6, 14, 1, tzinfo=UTC), "price": 17000.0, "size": 1, "side": "B", "instrument_id": 1, "raw_symbol": "NQZ6", "sequence": 2},
        {"ts_event": datetime(2026, 1, 6, 14, 2, tzinfo=UTC), "price": 17000.25, "size": 50, "side": "B", "instrument_id": 2, "raw_symbol": "NQZ6-NQH7", "sequence": 3},
        {"ts_event": datetime(2026, 1, 6, 14, 3, tzinfo=UTC), "price": 17000.50, "size": 50, "side": "B", "instrument_id": 3, "raw_symbol": "NQH7", "sequence": 4},
    ])
    events = [event for event in DatabentoParquetSource(paths=(path,), requested_symbol="NQ.c.0", schema="trades", front_month_only=True).events() if isinstance(event, Trade)]
    assert len(events) == 2
    assert all(event.price_ticks == 68000 for event in events)


def test_mbp1_action_trade_rows_emit_trades_like_mbp10(tmp_path: Path) -> None:
    # D-P-17: action-bearing TOB schemas (mbp-1/tbbo) classify T rows as trades — the
    # mbp-10 rule. The same row still emits its Quote iff level-0 state changed, with
    # the row's Trade item before its Quote item.
    base = datetime(2026, 3, 2, 14, tzinfo=UTC)
    rows = [
        {"ts_event": base, "action": "A", "price": 17000.0, "size": 1, "side": "B", "bid_px_00": 16999.75, "ask_px_00": 17000.25, "sequence": 1},
        # trade with unchanged book -> Trade emitted, Quote suppressed by TOB dedup
        {"ts_event": base.replace(minute=1), "action": "T", "price": 17000.25, "size": 2, "side": "B", "bid_px_00": 16999.75, "ask_px_00": 17000.25, "sequence": 2},
        # trade that moves the book -> Trade then Quote from the same row
        {"ts_event": base.replace(minute=2), "action": "T", "price": 17000.25, "size": 1, "side": "A", "bid_px_00": 17000.0, "ask_px_00": 17000.5, "sequence": 3},
    ]
    for filename, schema in (("mbp1.parquet", "mbp-1"), ("tbbo.parquet", "tbbo")):
        path = _write(tmp_path / filename, rows)
        events = list(DatabentoParquetSource(paths=(path,), requested_symbol="NQ.c.0", schema=schema).events())
        assert [type(event).__name__ for event in events] == ["Quote", "Trade", "Trade", "Quote"]
        trades = [event for event in events if isinstance(event, Trade)]
        assert [(t.price_ticks, t.size, t.side) for t in trades] == [(68001, 2, "B"), (68001, 1, "A")]


def test_tob_schema_without_action_column_stays_quotes_only(tmp_path: Path) -> None:
    # D-P-17 guard: no action column (the bbo/cbbo shape) -> quotes-only, unchanged.
    base = datetime(2026, 3, 2, 14, tzinfo=UTC)
    rows = [
        {"ts_event": base, "bid_px_00": 16999.75, "ask_px_00": 17000.25, "sequence": 1},
        {"ts_event": base.replace(minute=1), "bid_px_00": 17000.0, "ask_px_00": 17000.5, "sequence": 2},
    ]
    for filename, schema in (("mbp1.parquet", "mbp-1"), ("bbo.parquet", "bbo")):
        path = _write(tmp_path / filename, rows)
        events = list(DatabentoParquetSource(paths=(path,), requested_symbol="NQ.c.0", schema=schema).events())
        assert [type(event).__name__ for event in events] == ["Quote", "Quote"]


def test_front_month_count_tie_breaks_to_larger_instrument_id(tmp_path: Path) -> None:
    path = _write(tmp_path / "tie.parquet", [
        {"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "price": 17000.0, "size": 9, "side": "B", "instrument_id": 1, "raw_symbol": "NQZ6", "sequence": 1},
        {"ts_event": datetime(2026, 1, 6, 14, 1, tzinfo=UTC), "price": 17000.50, "size": 1, "side": "B", "instrument_id": 3, "raw_symbol": "NQH7", "sequence": 2},
    ])
    events = [event for event in DatabentoParquetSource(paths=(path,), requested_symbol="NQ.c.0", schema="trades", front_month_only=True).events() if isinstance(event, Trade)]
    assert len(events) == 1
    assert events[0].price_ticks == 68002
