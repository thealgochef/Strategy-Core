"""Databento Parquet source normalized into Strategy-Core neutral events."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from heapq import heappop, heappush
from itertools import count
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from strategy_core.constants import (
    BUY_AGGRESSOR_SIDE,
    DEFAULT_TICK_SIZE,
    SESSION_TIMEZONE,
    TRADING_DAY_BOUNDARY,
)
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

#: Per-date file resolution priority for trading-day composition (mirrors the
#: research store convention: best book depth available wins).
DAY_FILE_PRIORITY = (
    ("mbp10.parquet", "mbp-10"),
    ("mbp1.parquet", "mbp-1"),
    ("trades.parquet", "trades"),
)


@dataclass(frozen=True, slots=True)
class DatabentoParquetSource:
    paths: tuple[Path, ...]
    requested_symbol: str
    schema: str
    start_ts_utc: datetime | None = None
    end_ts_utc: datetime | None = None
    front_month_only: bool = False
    batch_size: int = 65_536
    #: Optional per-path [start, end) UTC windows; when set, overrides the global
    #: start/end for that path. Length must match ``paths``.
    path_windows: tuple[tuple[datetime | None, datetime | None], ...] | None = None
    #: Warnings produced at composition time (e.g. missing prior-day file); yielded
    #: on the event stream before any market data.
    pending_warnings: tuple[DataQualityWarning, ...] = ()

    def __post_init__(self) -> None:
        if self.path_windows is not None and len(self.path_windows) != len(self.paths):
            raise ValueError("path_windows must match paths length")

    @classmethod
    def for_trading_day(
        cls,
        symbol_dir: Path | str,
        trading_day: date,
        *,
        requested_symbol: str | None = None,
        front_month_only: bool = True,
        batch_size: int = 65_536,
    ) -> DatabentoParquetSource:
        """Canonical trading-day stream: [prev-day 18:00 ET, trading-day 18:00 ET).

        Composes the window from the two per-date files under ``symbol_dir``
        (``<symbol_dir>/<YYYY-MM-DD>/{mbp10,mbp1,trades}.parquet``), DST-aware via
        ``SESSION_TIMEZONE``. The two files are partitioned at UTC midnight of
        ``trading_day`` — the physical file boundary — so rows duplicated across
        adjacent day files are never double-emitted. A missing (or schema-mismatched)
        prior-day file degrades to a single-file scan and surfaces a
        ``MISSING_PRIOR_DAY_FILE`` warning on the event stream.
        """

        root = Path(symbol_dir)
        symbol = requested_symbol or root.name
        day_resolved = cls._resolve_day_file(root, trading_day)
        if day_resolved is None:
            raise FileNotFoundError(
                f"no parquet day file for {symbol} {trading_day.isoformat()}"
            )
        day_path, day_schema = day_resolved
        prev_day = trading_day - timedelta(days=1)
        tz = ZoneInfo(SESSION_TIMEZONE)
        start = datetime.combine(prev_day, TRADING_DAY_BOUNDARY, tzinfo=tz).astimezone(UTC)
        end = datetime.combine(trading_day, TRADING_DAY_BOUNDARY, tzinfo=tz).astimezone(UTC)
        split = datetime(trading_day.year, trading_day.month, trading_day.day, tzinfo=UTC)
        prev_resolved = cls._resolve_day_file(root, prev_day)
        warnings: list[DataQualityWarning] = []
        if prev_resolved is not None and prev_resolved[1] != day_schema:
            warnings.append(
                cls._warning(
                    DataQualityCode.MISSING_PRIOR_DAY_FILE,
                    "prior-day file schema differs; trading-day window served from a single file",
                    str(day_path),
                    trading_day=trading_day.isoformat(),
                    prior_day=prev_day.isoformat(),
                    prior_schema=prev_resolved[1],
                    schema=day_schema,
                )
            )
            prev_resolved = None
        if prev_resolved is None:
            if not warnings:
                warnings.append(
                    cls._warning(
                        DataQualityCode.MISSING_PRIOR_DAY_FILE,
                        "prior-day file missing; trading-day window served from a single file",
                        str(day_path),
                        trading_day=trading_day.isoformat(),
                        prior_day=prev_day.isoformat(),
                    )
                )
            return cls(
                paths=(day_path,),
                requested_symbol=symbol,
                schema=day_schema,
                front_month_only=front_month_only,
                batch_size=batch_size,
                path_windows=((start, end),),
                pending_warnings=tuple(warnings),
            )
        return cls(
            paths=(prev_resolved[0], day_path),
            requested_symbol=symbol,
            schema=day_schema,
            front_month_only=front_month_only,
            batch_size=batch_size,
            path_windows=((start, split), (split, end)),
            pending_warnings=tuple(warnings),
        )

    @staticmethod
    def _resolve_day_file(root: Path, day: date) -> tuple[Path, str] | None:
        folder = root / day.isoformat()
        for filename, schema in DAY_FILE_PRIORITY:
            candidate = folder / filename
            if candidate.exists():
                return candidate, schema
        return None

    def _window_for(self, index: int) -> tuple[datetime | None, datetime | None]:
        if self.path_windows is not None:
            return self.path_windows[index]
        return (self.start_ts_utc, self.end_ts_utc)

    def events(self) -> Iterator[Trade | Quote | DataQualityWarning]:
        yield from self.pending_warnings
        streams = [
            iter(self._scan_file(Path(path), self._window_for(index)))
            for index, path in enumerate(self.paths)
        ]
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

        # L1 dedup: a Quote is emitted only when level-0 state (bid/ask price or
        # size) changes from the previously *emitted* top-of-book state. Applies
        # across the whole merged stream, so it holds for multi-file day windows.
        last_tob: tuple[int, int, int, int] | None = None
        while heap:
            _, _, stream_index, event = heappop(heap)
            if isinstance(event, Quote):
                tob = (
                    event.bid_price_ticks,
                    event.ask_price_ticks,
                    event.bid_size,
                    event.ask_size,
                )
                if tob != last_tob:
                    last_tob = tob
                    yield event
            else:
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

    def _scan_file(
        self, path: Path, window: tuple[datetime | None, datetime | None]
    ) -> Iterator[SourceItem]:
        import pyarrow.parquet as pq

        source = safe_source(str(path)) or "historical-parquet"
        try:
            parquet = pq.ParquetFile(path)
        except Exception as exc:
            yield self._warning(DataQualityCode.INVALID_RECORD, f"could not open historical parquet: {type(exc).__name__}", source, severity=DataQualitySeverity.ERROR)
            return
        # audit N5: schema_arrow decode can fail on a corrupt file footer; warn-and-skip.
        try:
            names = set(parquet.schema_arrow.names)
        except Exception as exc:
            yield self._warning(DataQualityCode.INVALID_RECORD, f"could not decode historical parquet: {type(exc).__name__}", source, severity=DataQualitySeverity.ERROR)
            return
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
        # audit N5: the front-month prescan and iter_batches/to_pylist decode read
        # actual data pages, so a corrupt page must warn-and-skip this file instead
        # of aborting the k-way merge. Per-row warn/skip behavior is unchanged: row
        # warnings are still yielded inline below; only decode failures land here.
        try:
            front_month_id = self._front_month_instrument_id(parquet, selected) if self.front_month_only else None
            window_start, window_end = window
            start = window_start.astimezone(UTC) if window_start is not None else None
            end = window_end.astimezone(UTC) if window_end is not None else None
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
        except Exception as exc:
            yield self._warning(DataQualityCode.INVALID_RECORD, f"could not decode historical parquet: {type(exc).__name__}", source, severity=DataQualitySeverity.ERROR)
            return

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
        """Dominant non-spread instrument by TRADE-row count (ties -> larger id).

        Matches the Trade-Lab/Quant-Lab front-month rule: spread symbols (containing
        ``-``) are excluded, only trade rows are counted (every row counts for
        schemas without an ``action`` column), and ties break toward the larger
        instrument id.
        """

        if "instrument_id" not in selected:
            return None
        has_action = "action" in selected
        counts: dict[int, int] = {}
        for batch in parquet.iter_batches(columns=selected, batch_size=self.batch_size):
            for row in batch.to_pylist():
                if has_action and not self._is_trade_action(row.get("action")):
                    continue
                if self._is_spread_symbol(row.get("raw_symbol") or row.get("symbol")):
                    continue
                instrument_id = self._optional_int(row.get("instrument_id"))
                if instrument_id is None:
                    continue
                counts[instrument_id] = counts.get(instrument_id, 0) + 1
        if not counts:
            return None
        return max(counts.items(), key=lambda item: (item[1], item[0]))[0]

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
            # audit #1: guard the int-ns branch like the str branch so a single
            # out-of-range/garbage ts_event warns-and-skips instead of aborting replay.
            # audit #2: convert with integer arithmetic to microseconds (no lossy float).
            try:
                return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=value // 1000)
            except (OverflowError, OSError, ValueError):
                return DatabentoParquetSource._warning(DataQualityCode.INVALID_TIMESTAMP, "invalid historical parquet timestamp", source)
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
