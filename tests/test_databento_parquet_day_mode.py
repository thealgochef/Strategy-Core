"""W1 Part 1: trading-day composition, TOB dedup, tie-break, naive-ts rejection."""

from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from strategy_core.data.databento_parquet import DatabentoParquetSource
from strategy_core.data.events import DataQualityCode, DataQualityWarning
from strategy_core.types import Quote, Trade


def _write(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)
    return path


def _trade_row(ts: datetime, price: float, *, size: int = 1, side: str = "B", seq: int = 0) -> dict:
    return {"ts_event": ts, "price": price, "size": size, "side": side, "sequence": seq}


def _trades(events: list) -> list[Trade]:
    return [event for event in events if isinstance(event, Trade)]


def _quotes(events: list) -> list[Quote]:
    return [event for event in events if isinstance(event, Quote)]


def test_tob_dedup_emits_quotes_only_on_level0_change(tmp_path: Path) -> None:
    base = datetime(2026, 1, 6, 14, tzinfo=UTC)
    rows = [
        {"ts_event": base, "action": "A", "price": 17000.0, "size": 1, "side": "B", "bid_px_00": 17000.0, "ask_px_00": 17000.5, "bid_sz_00": 5, "ask_sz_00": 5, "sequence": 1},
        # identical level-0 state -> suppressed
        {"ts_event": base.replace(second=1), "action": "A", "price": 17000.0, "size": 1, "side": "B", "bid_px_00": 17000.0, "ask_px_00": 17000.5, "bid_sz_00": 5, "ask_sz_00": 5, "sequence": 2},
        # size-only change -> emitted
        {"ts_event": base.replace(second=2), "action": "A", "price": 17000.0, "size": 1, "side": "B", "bid_px_00": 17000.0, "ask_px_00": 17000.5, "bid_sz_00": 6, "ask_sz_00": 5, "sequence": 3},
        # trade row with unchanged book -> Trade emitted, Quote suppressed
        {"ts_event": base.replace(second=3), "action": "T", "price": 17000.5, "size": 2, "side": "B", "bid_px_00": 17000.0, "ask_px_00": 17000.5, "bid_sz_00": 6, "ask_sz_00": 5, "sequence": 4},
        # price change -> emitted
        {"ts_event": base.replace(second=4), "action": "A", "price": 17000.25, "size": 1, "side": "B", "bid_px_00": 17000.25, "ask_px_00": 17000.5, "bid_sz_00": 6, "ask_sz_00": 5, "sequence": 5},
    ]
    path = _write(tmp_path / "mbp10.parquet", rows)
    events = list(DatabentoParquetSource(paths=(path,), requested_symbol="NQ", schema="mbp-10").events())
    assert len(_trades(events)) == 1
    assert len(_quotes(events)) == 3


def test_day_mode_two_file_window_and_midnight_partition(tmp_path: Path) -> None:
    # Trading day 2026-02-18 (EST): window [2026-02-17 23:00 UTC, 2026-02-18 23:00 UTC),
    # files partitioned at UTC midnight 2026-02-18.
    root = tmp_path / "NQ"
    duplicated = _trade_row(datetime(2026, 2, 18, 0, 0, 1, tzinfo=UTC), 17001.0, seq=10)
    _write(root / "2026-02-17" / "trades.parquet", [
        _trade_row(datetime(2026, 2, 17, 22, 59, 59, tzinfo=UTC), 16990.0, seq=1),  # before window
        _trade_row(datetime(2026, 2, 17, 23, 0, tzinfo=UTC), 16991.0, seq=2),       # window start (incl)
        _trade_row(datetime(2026, 2, 17, 23, 30, tzinfo=UTC), 16992.0, seq=3),
        duplicated,  # after split -> dropped from prev file
    ])
    _write(root / "2026-02-18" / "trades.parquet", [
        _trade_row(datetime(2026, 2, 17, 23, 59, 59, tzinfo=UTC), 16993.0, seq=9),  # stray pre-midnight row -> dropped
        duplicated,  # same row in its proper file -> emitted exactly once overall
        _trade_row(datetime(2026, 2, 18, 22, 59, 59, tzinfo=UTC), 17002.0, seq=11),  # last in window
        _trade_row(datetime(2026, 2, 18, 23, 0, tzinfo=UTC), 17003.0, seq=12),       # window end (excl)
    ])
    source = DatabentoParquetSource.for_trading_day(root, date(2026, 2, 18))
    events = list(source.events())
    assert not [e for e in events if isinstance(e, DataQualityWarning)]
    prices = [trade.price_ticks / 4 for trade in _trades(events)]
    assert prices == [16991.0, 16992.0, 17001.0, 17002.0]


def test_day_mode_dst_transition_window(tmp_path: Path) -> None:
    # US spring-forward 2026-03-08. Trading day 2026-03-09: 18:00 ET is EDT (UTC-4)
    # on BOTH ends -> window [2026-03-08 22:00 UTC, 2026-03-09 22:00 UTC).
    root = tmp_path / "NQ"
    _write(root / "2026-03-08" / "trades.parquet", [
        _trade_row(datetime(2026, 3, 8, 21, 59, 59, tzinfo=UTC), 17000.0, seq=1),  # 17:59:59 EDT -> out
        _trade_row(datetime(2026, 3, 8, 22, 0, tzinfo=UTC), 17001.0, seq=2),       # 18:00 EDT -> in
    ])
    _write(root / "2026-03-09" / "trades.parquet", [
        _trade_row(datetime(2026, 3, 9, 21, 59, 59, tzinfo=UTC), 17002.0, seq=3),  # in
        _trade_row(datetime(2026, 3, 9, 22, 0, tzinfo=UTC), 17003.0, seq=4),       # 18:00 EDT next day -> out
    ])
    events = list(DatabentoParquetSource.for_trading_day(root, date(2026, 3, 9)).events())
    prices = [trade.price_ticks / 4 for trade in _trades(events)]
    assert prices == [17001.0, 17002.0]


def test_day_mode_missing_prior_day_warns_and_serves_single_file(tmp_path: Path) -> None:
    root = tmp_path / "NQ"
    _write(root / "2026-02-18" / "trades.parquet", [
        _trade_row(datetime(2026, 2, 17, 23, 30, tzinfo=UTC), 17000.0, seq=1),
        _trade_row(datetime(2026, 2, 18, 23, 30, tzinfo=UTC), 17001.0, seq=2),  # past window end -> out
    ])
    events = list(DatabentoParquetSource.for_trading_day(root, date(2026, 2, 18)).events())
    assert isinstance(events[0], DataQualityWarning)
    assert events[0].code is DataQualityCode.MISSING_PRIOR_DAY_FILE
    prices = [trade.price_ticks / 4 for trade in _trades(events)]
    assert prices == [17000.0]


def test_day_mode_missing_day_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        DatabentoParquetSource.for_trading_day(tmp_path / "NQ", date(2026, 2, 18))


def test_merge_tie_break_is_side_signed_deterministic(tmp_path: Path) -> None:
    ts = datetime(2026, 1, 6, 14, tzinfo=UTC)
    # Same ts+sequence across two files: sell-aggressor sweeps sort descending by
    # price (side-signed negative), buy-aggressor ascending.
    p1 = _write(tmp_path / "a.parquet", [
        _trade_row(ts, 17000.25, side="A", seq=7),
        _trade_row(ts.replace(minute=1), 17000.25, side="B", seq=8),
    ])
    p2 = _write(tmp_path / "b.parquet", [
        _trade_row(ts, 17000.75, side="A", seq=7),
        _trade_row(ts.replace(minute=1), 17000.75, side="B", seq=8),
    ])
    events = _trades(list(DatabentoParquetSource(paths=(p1, p2), requested_symbol="NQ", schema="trades").events()))
    prices = [trade.price_ticks / 4 for trade in events]
    assert prices == [17000.75, 17000.25, 17000.25, 17000.75]


def test_bytes_action_and_side_cells_are_decoded(tmp_path: Path) -> None:
    """Mixed-type parquet columns surface as bytes; action/side/symbol decode must
    tolerate them (the TL catalog fixtures and some real dumps carry them)."""
    path = _write(tmp_path / "mbp10.parquet", [
        {"ts_event": datetime(2026, 1, 6, 14, tzinfo=UTC), "action": b"T", "price": 17000.0, "size": 1, "side": b"B", "bid_px_00": None, "ask_px_00": None, "sequence": 1},
        {"ts_event": datetime(2026, 1, 6, 14, 1, tzinfo=UTC), "action": b"A", "price": 17000.25, "size": 1, "side": b"B", "bid_px_00": 17000.0, "ask_px_00": 17000.5, "sequence": 2},
    ])
    events = list(DatabentoParquetSource(paths=(path,), requested_symbol="NQ", schema="mbp-10").events())
    trades = _trades(events)
    assert len(trades) == 1
    assert trades[0].side == "B"
    assert len(_quotes(events)) == 1


def test_naive_timestamp_rejected_with_warning(tmp_path: Path) -> None:
    path = _write(tmp_path / "trades.parquet", [
        {"ts_event": datetime(2026, 1, 6, 14), "price": 17000.0, "size": 1, "side": "B", "sequence": 1},
    ])
    events = list(DatabentoParquetSource(paths=(path,), requested_symbol="NQ", schema="trades").events())
    assert not _trades(events)
    warnings = [event for event in events if isinstance(event, DataQualityWarning)]
    assert warnings
    assert warnings[0].code is DataQualityCode.INVALID_TIMESTAMP


def test_single_file_global_window_still_applies(tmp_path: Path) -> None:
    path = _write(tmp_path / "trades.parquet", [
        _trade_row(datetime(2026, 1, 6, 13, tzinfo=UTC), 17000.0, seq=1),
        _trade_row(datetime(2026, 1, 6, 14, tzinfo=UTC), 17001.0, seq=2),
        _trade_row(datetime(2026, 1, 6, 15, tzinfo=UTC), 17002.0, seq=3),
    ])
    source = DatabentoParquetSource(
        paths=(path,),
        requested_symbol="NQ",
        schema="trades",
        start_ts_utc=datetime(2026, 1, 6, 14, tzinfo=UTC),
        end_ts_utc=datetime(2026, 1, 6, 15, tzinfo=UTC),
    )
    prices = [trade.price_ticks / 4 for trade in _trades(list(source.events()))]
    assert prices == [17001.0]


def test_day_file_priority_prefers_mbp10_over_mbp1(tmp_path: Path) -> None:
    # INGEST: overlap days carry both files; mbp10.parquet keeps serving the day.
    root = tmp_path / "NQ"
    base = datetime(2026, 2, 18, 14, tzinfo=UTC)
    _write(root / "2026-02-18" / "mbp10.parquet", [
        {"ts_event": base, "action": "T", "price": 17000.0, "size": 1, "side": "B", "bid_px_00": 16999.75, "ask_px_00": 17000.25, "sequence": 1},
    ])
    _write(root / "2026-02-18" / "mbp1.parquet", [
        {"ts_event": base, "action": "T", "price": 15000.0, "size": 1, "side": "B", "bid_px_00": 14999.75, "ask_px_00": 15000.25, "sequence": 1},
    ])
    source = DatabentoParquetSource.for_trading_day(root, date(2026, 2, 18))
    assert source.schema == "mbp-10"
    assert [t.price_ticks for t in _trades(list(source.events()))] == [68000]


def test_day_file_priority_falls_back_to_mbp1_when_alone(tmp_path: Path) -> None:
    root = tmp_path / "NQ"
    base = datetime(2026, 3, 2, 14, tzinfo=UTC)
    _write(root / "2026-03-02" / "mbp1.parquet", [
        {"ts_event": base, "action": "T", "price": 17000.0, "size": 1, "side": "B", "bid_px_00": 16999.75, "ask_px_00": 17000.25, "sequence": 1},
    ])
    source = DatabentoParquetSource.for_trading_day(root, date(2026, 3, 2))
    assert source.schema == "mbp-1"
    assert [t.price_ticks for t in _trades(list(source.events()))] == [68000]
