"""Databento Parquet source normalized into Strategy-Core neutral events."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from heapq import heappop, heappush
from itertools import count
from pathlib import Path
from typing import Any

from strategy_core.constants import BUY_AGGRESSOR_SIDE, DEFAULT_TICK_SIZE
from strategy_core.data.events import (
    DataQualityCode,
    DataQualitySeverity,
    DataQualityWarning,
    safe_source,
)
from strategy_core.data.ordering import side_signed_price_ticks
from strategy_core.types import Quote, Trade

__all__ = ["DatabentoParquetSource"]

TRADE_REQUIRED = frozenset(("ts_event", "price", "size"))
MBP10_REQUIRED = frozenset(("ts_event", "action", "price", "size"))
TOB_ALIASES = (
    ("bid_price", "bid_px", "bid", "bid_px_00"),
    ("ask_price", "ask_px", "ask", "ask_px_00"),
)
TRADE_SELECTED = (
    "ts_event",
    "ts_recv",
    "sequence",
    "seq",
    "instrument_id",
    "raw_symbol",
    "symbol",
    "action",
    "side",
    "price",
    "size",
    "bid_price",
    "bid_px",
    "bid",
    "bid_px_00",
    "bid_size",
    "bid_sz",
    "bid_sz_00",
    "ask_price",
    "ask_px",
    "ask",
    "ask_px_00",
    "ask_size",
    "ask_sz",
    "ask_sz_00",
)

SortKey = tuple[datetime, int, int, int]
SourceItem = tuple[SortKey, Trade | Quote] | DataQualityWarning


@dataclass(frozen=True, slots=True)
class DatabentoParquetSource:
    paths: tuple[Path, ...]
    requested_symbol: str
    schema: str
    start_ts_utc: datetime | None = None
    end_ts_utc: datetime | None = None
    front_month_only: bool = False
    batch_size: int = 65_536

    def events(self) -> Iterator[Trade | Quote | DataQualityWarning]:
        streams = [iter(self._scan_file(Path(path))) for path in self.paths]
        if not streams:
            return
        heap: list[tuple[SortKey, int, int, Trade | Quote]] = []
        tie = count()
        primed = [False] * len(streams)
        exhausted = [False] * len(streams)

        def ready() -> bool:
            return all(is_primed or is_exhausted for is_primed, is_exhausted in zip(primed, exhausted, strict=True))

        def prime(index: int) -> Iterator[DataQualityWarning]:
            while not primed[index] and not exhausted[index]:
                try:
                    item = next(streams[index])
                except StopIteration:
                    exhausted[index] = True
                    break
                if isinstance(item, DataQualityWarning):
                    yield item
                    continue
                key, event = item
                heappush(heap, (key, next(tie), index, event))
                primed[index] = True

        while not ready():
            progressed = False
            for stream_index in range(len(streams)):
                if primed[stream_index] or exhausted[stream_index]:
                    continue
                for warning in prime(stream_index):
                    yield warning
                    progressed = True
                    break
                if primed[stream_index] or exhausted[stream_index]:
                    progressed = True
                    break
            if not progressed:
                break

        while heap:
            _, _, stream_index, event = heappop(heap)
            yield event
            primed[stream_index] = False
            for warning in prime(stream_index):
                yield warning
            while not ready():
                for idx in range(len(streams)):
                    if not primed[idx] and not exhausted[idx]:
                        for warning in prime(idx):
                            yield warning
                        break
                else:
                    break

    def _scan_file(self, path: Path) -> Iterator[SourceItem]:
        import pyarrow.parquet as pq

        source = safe_source(str(path)) or "historical-parquet"
        try:
            parquet = pq.ParquetFile(path)
        except Exception as exc:
            yield self._warning(DataQualityCode.INVALID_RECORD, f"could not open historical parquet: {type(exc).__name__}", source, severity=DataQualitySeverity.ERROR)
            return
        names = set(parquet.schema_arrow.names)
        schema = self.schema.lower()
        is_trade_schema = schema in {"trades", "trade"}
        is_mbp10 = schema in {"mbp-10", "mbp10", "cmbp-10", "cmbp10"}
        is_tob = schema in {"mbp-1", "cmbp-1", "bbo", "cbbo", "tbbo"}
        if is_trade_schema:
            missing = TRADE_REQUIRED - names
        elif is_mbp10:
            missing = MBP10_REQUIRED - names
        elif is_tob:
            missing = self._missing_tob(names)
        else:
            yield self._warning(DataQualityCode.UNSUPPORTED_SCHEMA, "unsupported historical parquet schema", source, severity=DataQualitySeverity.ERROR)
            return
        if missing:
            yield self._warning(DataQualityCode.MISSING_REQUIRED_COLUMN, "missing required historical parquet fields", source, severity=DataQualitySeverity.ERROR, missing=sorted(missing))
            return
        selected = [name for name in TRADE_SELECTED if name in names]
        front_month_id = self._front_month_instrument_id(parquet, selected) if self.front_month_only else None
        start = self.start_ts_utc.astimezone(UTC) if self.start_ts_utc is not None else None
        end = self.end_ts_utc.astimezone(UTC) if self.end_ts_utc is not None else None
        for batch in parquet.iter_batches(columns=selected, batch_size=self.batch_size):
            events: list[tuple[SortKey, Trade | Quote]] = []
            for row in batch.to_pylist():
                if self.front_month_only and self._is_off_front_month(row, front_month_id):
                    continue
                normalized = self._normalize_row(row, schema=schema, source=source, is_trade_schema=is_trade_schema, is_mbp10=is_mbp10, is_tob=is_tob)
                for item in normalized:
                    if isinstance(item, DataQualityWarning):
                        yield item
                        continue
                    key, event = item
                    if start is not None and event.event_ts_utc < start:
                        continue
                    if end is not None and event.event_ts_utc >= end:
                        continue
                    events.append((key, event))
            yield from sorted(events, key=lambda item: item[0])

    def _normalize_row(self, row: dict[str, Any], *, schema: str, source: str, is_trade_schema: bool, is_mbp10: bool, is_tob: bool) -> tuple[SourceItem, ...]:
        items: list[SourceItem] = []
        if is_trade_schema or (is_mbp10 and self._is_trade_action(row.get("action"))):
            items.append(self._normalize_trade(row, schema=schema, source=source))
        if is_tob or (is_mbp10 and self._has_top_of_book(row)):
            items.append(self._normalize_quote(row, schema=schema, source=source))
        return tuple(items)

    def _normalize_trade(self, row: dict[str, Any], *, schema: str, source: str) -> SourceItem:
        ts = self._timestamp(row.get("ts_event"), source=source)
        if isinstance(ts, DataQualityWarning):
            return ts
        price_ticks = self._price_ticks(row.get("price"), source=source)
        if isinstance(price_ticks, DataQualityWarning):
            return price_ticks
        size = row.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            return self._warning(DataQualityCode.INVALID_RECORD, "invalid historical parquet record", source, event_ts_utc=ts)
        side = None if row.get("side") is None else str(row.get("side")).upper()
        trade = Trade(event_ts_utc=ts, price_ticks=price_ticks, size=size, side=side)
        sequence = self._optional_int(row.get("sequence")) or self._optional_int(row.get("seq")) or 0
        key = (ts, sequence, side_signed_price_ticks(trade, buy_side=BUY_AGGRESSOR_SIDE), size)
        return key, trade

    def _normalize_quote(self, row: dict[str, Any], *, schema: str, source: str) -> SourceItem:
        _ = schema
        ts = self._timestamp(row.get("ts_event"), source=source)
        if isinstance(ts, DataQualityWarning):
            return ts
        bid = self._price_ticks(self._first(row, TOB_ALIASES[0]), source=source)
        ask = self._price_ticks(self._first(row, TOB_ALIASES[1]), source=source)
        if isinstance(bid, DataQualityWarning):
            return bid
        if isinstance(ask, DataQualityWarning):
            return ask
        quote = Quote(
            event_ts_utc=ts,
            bid_price_ticks=bid,
            ask_price_ticks=ask,
            bid_size=self._optional_int(self._first(row, ("bid_size", "bid_sz", "bid_sz_00"))) or 0,
            ask_size=self._optional_int(self._first(row, ("ask_size", "ask_sz", "ask_sz_00"))) or 0,
        )
        sequence = self._optional_int(row.get("sequence")) or self._optional_int(row.get("seq")) or 0
        return (ts, sequence, 0, 0), quote

    def _front_month_instrument_id(self, parquet: Any, selected: list[str]) -> int | None:
        counts: dict[int, int] = {}
        if "instrument_id" not in selected:
            return None
        for batch in parquet.iter_batches(columns=selected, batch_size=self.batch_size):
            for row in batch.to_pylist():
                if self._is_spread_symbol(row.get("raw_symbol") or row.get("symbol")):
                    continue
                instrument_id = self._optional_int(row.get("instrument_id"))
                if instrument_id is None:
                    continue
                size = self._optional_int(row.get("size")) or 1
                counts[instrument_id] = counts.get(instrument_id, 0) + max(size, 1)
        return max(counts.items(), key=lambda item: item[1])[0] if counts else None

    def _is_off_front_month(self, row: dict[str, Any], front_month_id: int | None) -> bool:
        if self._is_spread_symbol(row.get("raw_symbol") or row.get("symbol")):
            return True
        if front_month_id is None:
            return False
        return self._optional_int(row.get("instrument_id")) != front_month_id

    @staticmethod
    def _is_spread_symbol(value: Any) -> bool:
        return isinstance(value, str) and "-" in value

    @staticmethod
    def _is_trade_action(value: Any) -> bool:
        return str(value).upper() in {"T", "TRADE"}

    @staticmethod
    def _has_top_of_book(row: dict[str, Any]) -> bool:
        return any(name in row and row.get(name) is not None for aliases in TOB_ALIASES for name in aliases)

    @staticmethod
    def _missing_tob(names: set[str]) -> set[str]:
        missing = set()
        if "ts_event" not in names:
            missing.add("ts_event")
        if not any(name in names for name in TOB_ALIASES[0]):
            missing.add("bid")
        if not any(name in names for name in TOB_ALIASES[1]):
            missing.add("ask")
        return missing

    @staticmethod
    def _timestamp(value: Any, *, source: str) -> datetime | DataQualityWarning:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return DatabentoParquetSource._warning(DataQualityCode.INVALID_TIMESTAMP, "invalid historical parquet timestamp", source)
            return value.astimezone(UTC)
        if isinstance(value, int) and not isinstance(value, bool):
            return datetime.fromtimestamp(value / 1_000_000_000, tz=UTC)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return DatabentoParquetSource._warning(DataQualityCode.INVALID_TIMESTAMP, "invalid historical parquet timestamp", source)
            if parsed.tzinfo is None:
                return DatabentoParquetSource._warning(DataQualityCode.INVALID_TIMESTAMP, "invalid historical parquet timestamp", source)
            return parsed.astimezone(UTC)
        return DatabentoParquetSource._warning(DataQualityCode.INVALID_TIMESTAMP, "invalid historical parquet timestamp", source)

    @staticmethod
    def _price_ticks(value: Any, *, source: str) -> int | DataQualityWarning:
        try:
            price = Decimal(str(value))
            tick = Decimal(str(DEFAULT_TICK_SIZE))
            ticks = price / tick
        except (InvalidOperation, ValueError, TypeError):
            return DatabentoParquetSource._warning(DataQualityCode.INVALID_PRICE, "invalid historical parquet price", source)
        if ticks != ticks.to_integral_value():
            return DatabentoParquetSource._warning(DataQualityCode.INVALID_PRICE, "invalid historical parquet price", source)
        return int(ticks)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _first(row: dict[str, Any], names: tuple[str, ...]) -> Any:
        for name in names:
            if row.get(name) is not None:
                return row.get(name)
        return None

    @staticmethod
    def _warning(code: DataQualityCode, message: str, source: str, *, severity: DataQualitySeverity = DataQualitySeverity.WARNING, event_ts_utc: datetime | None = None, **metadata: Any) -> DataQualityWarning:
        return DataQualityWarning(code=code, message=message, severity=severity, source=source, event_ts_utc=event_ts_utc, metadata=metadata)
