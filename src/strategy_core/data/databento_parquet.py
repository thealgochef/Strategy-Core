"""Databento Parquet source normalized into Strategy-Core neutral events."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from heapq import heappop, heappush
from itertools import count
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

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
from strategy_core.types import Quote, Trade

__all__ = ["DatabentoParquetSource"]

TRADE_REQUIRED = frozenset(("ts_event", "price", "size"))
MBP10_REQUIRED = frozenset(("ts_event", "action", "price", "size"))
TOB_ALIASES = (
    ("bid_price", "bid_px", "bid", "bid_px_00"),
    ("ask_price", "ask_px", "ask", "ask_px_00"),
)
BID_SIZE_ALIASES = ("bid_size", "bid_sz", "bid_sz_00")
ASK_SIZE_ALIASES = ("ask_size", "ask_sz", "ask_sz_00")
#: W3A-READER P2: the decode reads only columns the normalization consumes
#: (the retired row-wise path also decoded ts_recv and discarded it).
DECODE_SELECTED = (
    "ts_event",
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

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ONE_US = timedelta(microseconds=1)
#: datetime-representable bounds in epoch microseconds — values outside warn-and-skip
#: (the row-wise int branch raised OverflowError into a per-row warning the same way).
_MIN_DT_US = (datetime.min.replace(tzinfo=UTC) - _EPOCH) // _ONE_US
_MAX_DT_US = (datetime.max.replace(tzinfo=UTC) - _EPOCH) // _ONE_US
_TS_UNIT_TO_US = {"s": 1_000_000, "ms": 1_000, "us": 1}


def _pandas_or_none() -> Any:
    """Lazy pandas, mirroring pyarrow ``as_py``: timestamp[ns] cells surface as
    ns-precision ``pd.Timestamp`` when pandas is importable, µs-floor ``datetime``
    otherwise. The vectorized path must construct the same objects."""

    try:
        import pandas
    except ImportError:  # pragma: no cover - pandas present in all current envs
        return None
    return pandas


def _us_datetimes(us_values: np.ndarray) -> list[datetime]:
    return [_EPOCH + timedelta(microseconds=us) for us in us_values.tolist()]


@dataclass(slots=True)
class _DecodedBatch:
    """One parquet batch decoded to canonical-order emission arrays.

    Arrays are aligned and already in the per-batch emission order: stable sort by
    ``(ts, sequence, side_signed_price, size)`` with the row-wise path's original
    item order (row order; a trade item before its row's quote item) breaking ties.
    ``ts_sort`` is the native-precision integer timestamp (ns for ns-unit columns —
    the canonical order is ns-precise there — µs otherwise); ``make_ts`` converts a
    subset of it into the exact objects the row-wise decode emitted.
    """

    is_quote: np.ndarray
    ts_sort: np.ndarray
    seq: np.ndarray
    ssp: np.ndarray
    size: np.ndarray
    price_ticks: np.ndarray
    side: list[str | None]
    bid_ticks: np.ndarray
    ask_ticks: np.ndarray
    bid_size: np.ndarray
    ask_size: np.ndarray
    make_ts: Callable[[np.ndarray], list]

    def emit_deduped(
        self, last_tob: tuple[int, int, int, int] | None
    ) -> tuple[list[Trade | Quote], tuple[int, int, int, int] | None]:
        """Materialize events with L1 TOB dedup applied BEFORE construction.

        A quote is emitted only when its level-0 state differs from the previous
        quote's in stream order (``last_tob`` carries across batches and files);
        suppressed quotes are never constructed. Trades always emit.
        """

        emit = np.ones(self.is_quote.shape[0], dtype=bool)
        quote_pos = np.flatnonzero(self.is_quote)
        if quote_pos.size:
            tob = (
                self.bid_ticks[quote_pos],
                self.ask_ticks[quote_pos],
                self.bid_size[quote_pos],
                self.ask_size[quote_pos],
            )
            changed = np.zeros(quote_pos.size, dtype=bool)
            for field in tob:
                changed[1:] |= field[1:] != field[:-1]
            if last_tob is None:
                changed[0] = True
            else:
                changed[0] = any(
                    int(field[0]) != prev for field, prev in zip(tob, last_tob, strict=True)
                )
            emit[quote_pos] = changed
            last_tob = tuple(int(field[-1]) for field in tob)
        idx = np.flatnonzero(emit)
        ts_objects = self.make_ts(self.ts_sort[idx])
        quote_flags = self.is_quote[idx].tolist()
        price = self.price_ticks[idx].tolist()
        size = self.size[idx].tolist()
        bid = self.bid_ticks[idx].tolist()
        ask = self.ask_ticks[idx].tolist()
        bid_size = self.bid_size[idx].tolist()
        ask_size = self.ask_size[idx].tolist()
        positions = idx.tolist()
        events: list[Trade | Quote] = []
        for out, pos in enumerate(positions):
            if quote_flags[out]:
                events.append(
                    Quote(
                        event_ts_utc=ts_objects[out],
                        bid_price_ticks=bid[out],
                        ask_price_ticks=ask[out],
                        bid_size=bid_size[out],
                        ask_size=ask_size[out],
                    )
                )
            else:
                events.append(
                    Trade(
                        event_ts_utc=ts_objects[out],
                        price_ticks=price[out],
                        size=size[out],
                        side=self.side[pos],
                    )
                )
        return events, last_tob

    def emit_keyed(self) -> list[tuple[SortKey, Trade | Quote]]:
        """Materialize ALL events with their canonical sort keys (no dedup) for the
        generic k-way merge path; dedup happens at the merge layer there."""

        ts_objects = self.make_ts(self.ts_sort)
        quote_flags = self.is_quote.tolist()
        seq = self.seq.tolist()
        ssp = self.ssp.tolist()
        price = self.price_ticks.tolist()
        size = self.size.tolist()
        bid = self.bid_ticks.tolist()
        ask = self.ask_ticks.tolist()
        bid_size = self.bid_size.tolist()
        ask_size = self.ask_size.tolist()
        out: list[tuple[SortKey, Trade | Quote]] = []
        for pos, ts in enumerate(ts_objects):
            if quote_flags[pos]:
                event: Trade | Quote = Quote(
                    event_ts_utc=ts,
                    bid_price_ticks=bid[pos],
                    ask_price_ticks=ask[pos],
                    bid_size=bid_size[pos],
                    ask_size=ask_size[pos],
                )
                out.append(((ts, seq[pos], 0, 0), event))
            else:
                event = Trade(
                    event_ts_utc=ts, price_ticks=price[pos], size=size[pos], side=self.side[pos]
                )
                out.append(((ts, seq[pos], ssp[pos], size[pos]), event))
        return out


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

    def _sequential_windows(self) -> bool:
        """True when per-path windows are pairwise ordered and non-overlapping —
        every event of path i precedes every event of path i+1, so the k-way merge
        degenerates to concatenation. Single-path sources are trivially sequential.
        The trading-day composition (split at UTC midnight) always qualifies."""

        if len(self.paths) <= 1:
            return True
        if self.path_windows is None:
            return False
        for (_, prev_end), (next_start, _) in zip(
            self.path_windows, self.path_windows[1:], strict=False
        ):
            if prev_end is None or next_start is None or prev_end > next_start:
                return False
        return True

    def events(self) -> Iterator[Trade | Quote | DataQualityWarning]:
        yield from self.pending_warnings
        if self._sequential_windows():
            yield from self._events_sequential()
        else:
            yield from self._events_merged()

    def _events_sequential(self) -> Iterator[Trade | Quote | DataQualityWarning]:
        """Vectorized fast path for ordered-disjoint (or single-path) sources.

        Files stream in order; the L1 TOB dedup state carries across batches and
        files (identical to deduping the merged stream), and suppressed quotes are
        never constructed.
        """

        last_tob: tuple[int, int, int, int] | None = None
        for index, path in enumerate(self.paths):
            for item in self._decode_batches(Path(path), self._window_for(index)):
                if isinstance(item, DataQualityWarning):
                    yield item
                    continue
                events, last_tob = item.emit_deduped(last_tob)
                yield from events

    def _events_merged(self) -> Iterator[Trade | Quote | DataQualityWarning]:
        """Generic k-way merge for multi-path sources whose windows may overlap:
        canonical-key interleave with the global tie counter, L1 TOB dedup applied
        across the merged stream."""

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
        """Adapter for the merge path: vectorized decode re-expressed as the
        row-wise scan's ``(key, event)`` item stream (warnings inline)."""

        for item in self._decode_batches(path, window):
            if isinstance(item, DataQualityWarning):
                yield item
            else:
                yield from item.emit_keyed()

    # ── W3A-READER P2: vectorized decode core ─────────────────────────────────

    def _decode_batches(
        self, path: Path, window: tuple[datetime | None, datetime | None]
    ) -> Iterator[DataQualityWarning | _DecodedBatch]:
        """Column-pruned pyarrow read; classification, validation, window bounds and
        canonical per-batch ordering as numpy masks. Semantics mirror the row-wise
        scan exactly: same batch boundaries (same ``iter_batches`` slicing over the
        same row groups), same per-batch ``[row warnings in row order] + [events
        stable-sorted by canonical key]`` emission, same warn-and-skip rules."""

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
        selected = [name for name in DECODE_SELECTED if name in names]
        # audit N5: the front-month prescan and iter_batches decode read actual data
        # pages, so a corrupt page must warn-and-skip this file instead of aborting
        # the k-way merge. Per-row warn/skip behavior is unchanged: row warnings are
        # still yielded inline below; only decode failures land here.
        try:
            window_start, window_end = window
            start = window_start.astimezone(UTC) if window_start is not None else None
            end = window_end.astimezone(UTC) if window_end is not None else None
            # W1 P1: prune row groups by ts_event statistics so a narrow window
            # (e.g. the prior-day hour of a trading-day composition) never decodes
            # the whole file. Conservative: groups without usable stats are kept;
            # the exact per-row window filter below is unchanged.
            row_groups = self._window_row_groups(parquet, start, end)
            front_month_id = (
                self._front_month_instrument_id(parquet, selected, row_groups)
                if self.front_month_only
                else None
            )
            ts_kind, ts_scale = self._ts_column_kind(parquet.schema_arrow.field("ts_event").type)
            start_us = None if start is None else (start - _EPOCH) // _ONE_US
            end_us = None if end is None else (end - _EPOCH) // _ONE_US
            for batch in parquet.iter_batches(
                columns=selected, batch_size=self.batch_size, row_groups=row_groups
            ):
                warnings, decoded = self._decode_batch(
                    batch,
                    source=source,
                    is_trade_schema=is_trade_schema,
                    is_mbp10=is_mbp10,
                    is_tob=is_tob,
                    front_month_id=front_month_id,
                    ts_kind=ts_kind,
                    ts_scale=ts_scale,
                    start_us=start_us,
                    end_us=end_us,
                )
                yield from warnings
                if decoded is not None:
                    yield decoded
        except Exception as exc:
            yield self._warning(DataQualityCode.INVALID_RECORD, f"could not decode historical parquet: {type(exc).__name__}", source, severity=DataQualitySeverity.ERROR)
            return

    @staticmethod
    def _ts_column_kind(arrow_type: Any) -> tuple[str, int]:
        """Classify the ts_event column: ``("ns", 1)`` (ns-precision objects),
        ``("us", scale)`` (µs-domain datetimes; covers tz-aware s/ms/us units and
        raw-integer ns columns via the int branch's ``// 1000``), ``("naive", 0)``
        (every row warns INVALID_TIMESTAMP) or ``("scalar", 0)`` (per-cell
        fallback through ``_timestamp`` — string-typed and exotic columns)."""

        import pyarrow as pa

        if pa.types.is_timestamp(arrow_type):
            if arrow_type.tz is None:
                return ("naive", 0)
            if arrow_type.unit == "ns":
                return ("ns", 1)
            scale = _TS_UNIT_TO_US.get(arrow_type.unit)
            if scale is not None:
                return ("us", scale)
            return ("scalar", 0)
        if pa.types.is_integer(arrow_type):
            return ("int", 0)
        return ("scalar", 0)

    def _ts_arrays(
        self, column: Any, ts_kind: str, ts_scale: int, source: str
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, Callable[[np.ndarray], list]]:
        """Return ``(ts_us, ts_sort, valid, make_ts)`` for the batch's ts column.

        ``ts_us`` is the µs-floor epoch timestamp used by the window masks (the
        row-wise path window-filtered the constructed objects; for whole-µs bounds
        the floor-µs compare is exactly equivalent, ns-precision included).
        ``ts_sort`` is the native-precision sort integer; ``make_ts`` rebuilds the
        exact objects the row-wise ``as_py``/``_timestamp`` decode produced."""

        import pyarrow.compute as pc

        rows = len(column)
        if ts_kind == "naive":
            zeros = np.zeros(rows, dtype=np.int64)
            return zeros, zeros, np.zeros(rows, dtype=bool), _us_datetimes
        if ts_kind in {"ns", "us"}:
            valid = pc.is_valid(column).to_numpy(zero_copy_only=False)
            raw = column.to_numpy(zero_copy_only=False).view("i8").astype(np.int64, copy=False)
            raw = np.where(valid, raw, 0)
            if ts_kind == "ns":
                ts_us = raw // 1000
                pandas = _pandas_or_none()
                if pandas is not None:
                    def make_ts(values: np.ndarray) -> list:
                        return list(pandas.DatetimeIndex(values, tz="UTC"))
                else:  # pragma: no cover - pandas present in all current envs
                    def make_ts(values: np.ndarray) -> list:
                        return _us_datetimes(values // 1000)
                return ts_us, raw, valid, make_ts
            in_range = (raw >= _MIN_DT_US // ts_scale) & (raw <= _MAX_DT_US // ts_scale)
            valid &= in_range
            ts_us = np.where(in_range, raw, 0) * ts_scale
            return ts_us, ts_us, valid, _us_datetimes
        if ts_kind == "int":
            valid = pc.is_valid(column).to_numpy(zero_copy_only=False)
            raw = self._int64_values(column)
            ts_us = np.where(valid, raw, 0) // 1000
            in_range = (ts_us >= _MIN_DT_US) & (ts_us <= _MAX_DT_US)
            valid &= in_range
            ts_us = np.where(in_range, ts_us, 0)
            return ts_us, ts_us, valid, _us_datetimes
        # scalar fallback (string-typed and exotic ts columns): per-cell _timestamp.
        cells = column.to_pylist()
        ts_us = np.zeros(rows, dtype=np.int64)
        valid = np.zeros(rows, dtype=bool)
        for index, cell in enumerate(cells):
            converted = self._timestamp(cell, source=source)
            if isinstance(converted, DataQualityWarning):
                continue
            valid[index] = True
            ts_us[index] = (converted - _EPOCH) // _ONE_US
        return ts_us, ts_us, valid, _us_datetimes

    @staticmethod
    def _int64_values(column: Any) -> np.ndarray:
        """Integer column to int64 values (nulls as 0 — mask separately)."""

        import pyarrow as pa
        import pyarrow.compute as pc

        return pc.fill_null(pc.cast(column, pa.int64()), 0).to_numpy(zero_copy_only=False)

    def _grid_ticks(self, column: Any, rows: int) -> tuple[np.ndarray, np.ndarray]:
        """Price column → ``(ticks int64, valid)`` under the exact-grid rule.

        Float/int columns vectorize (a finite double is a multiple of the tick in
        the row-wise ``Decimal(str(value))`` sense iff ``value / tick`` is integral
        in binary floating point — division by 0.25 is exact); anything else falls
        back to per-cell ``_price_ticks``. Nulls, NaN and non-finite values are
        invalid (the row-wise path warned INVALID_PRICE for those too)."""

        import pyarrow as pa
        import pyarrow.compute as pc

        if column is None:
            return np.zeros(rows, dtype=np.int64), np.zeros(rows, dtype=bool)
        column_type = column.type
        if pa.types.is_floating(column_type) or pa.types.is_integer(column_type):
            values = pc.cast(column, pa.float64()).to_numpy(zero_copy_only=False)
            with np.errstate(invalid="ignore", over="ignore"):
                ticks = values / DEFAULT_TICK_SIZE
                valid = np.isfinite(ticks) & (ticks == np.floor(ticks))
            safe = np.where(valid, ticks, 0)
            return safe.astype(np.int64), valid
        ticks_out = np.zeros(rows, dtype=np.int64)
        valid = np.zeros(rows, dtype=bool)
        for index, cell in enumerate(column.to_pylist()):
            converted = self._price_ticks(cell, source="")
            if isinstance(converted, DataQualityWarning):
                continue
            ticks_out[index] = converted
            valid[index] = True
        return ticks_out, valid

    def _strict_size(self, column: Any, rows: int) -> tuple[np.ndarray, np.ndarray]:
        """Trade size under the strict row-wise rule: integer cells only (bools and
        non-int types never qualify), positive. Returns ``(size int64, valid)``."""

        import pyarrow as pa

        if column is None or not pa.types.is_integer(column.type):
            return np.zeros(rows, dtype=np.int64), np.zeros(rows, dtype=bool)
        import pyarrow.compute as pc

        valid = pc.is_valid(column).to_numpy(zero_copy_only=False)
        values = self._int64_values(column)
        return values, valid & (values > 0)

    def _optional_size(self, columns: list[Any], rows: int) -> np.ndarray:
        """Quote depth via ``_optional_int(_first(...)) or 0`` semantics: first
        non-null alias wins; unconvertible cells and nulls become 0; float cells
        truncate toward zero (non-finite → 0); bool columns never qualify."""

        import pyarrow as pa
        import pyarrow.compute as pc

        usable = [col for col in columns if not pa.types.is_boolean(col.type)]
        if not usable:
            return np.zeros(rows, dtype=np.int64)
        simple = all(
            pa.types.is_integer(col.type) or pa.types.is_floating(col.type) for col in usable
        )
        if simple:
            merged = usable[0] if len(usable) == 1 else pc.coalesce(*usable)
            values = pc.cast(merged, pa.float64()).to_numpy(zero_copy_only=False)
            finite = np.isfinite(values)
            return np.where(finite, np.trunc(np.where(finite, values, 0)), 0).astype(np.int64)
        cell_rows = zip(*(col.to_pylist() for col in usable), strict=True)
        out = np.zeros(rows, dtype=np.int64)
        for index, cells in enumerate(cell_rows):
            first = next((cell for cell in cells if cell is not None), None)
            out[index] = self._optional_int(first) or 0
        return out

    @staticmethod
    def _upper_text(column: Any) -> Any:
        """Uppercased string array for a text-ish column (bytes cells decode), or
        None when the column cannot be read as text."""

        import pyarrow as pa
        import pyarrow.compute as pc

        try:
            return pc.utf8_upper(pc.cast(column, pa.string()))
        except Exception:
            cells = [
                None if cell is None else DatabentoParquetSource._as_text(cell)
                for cell in column.to_pylist()
            ]
            return pc.utf8_upper(pa.array(cells, type=pa.string()))

    def _effective_sequence(self, batch_columns: dict[str, Any], rows: int) -> np.ndarray:
        """``_optional_int(sequence) or _optional_int(seq) or 0`` vectorized,
        falsiness included: a null OR ZERO ``sequence`` falls through to ``seq``."""

        import pyarrow as pa
        import pyarrow.compute as pc

        result = np.zeros(rows, dtype=np.int64)
        chosen = np.zeros(rows, dtype=bool)
        for name in ("sequence", "seq"):
            column = batch_columns.get(name)
            if column is None or pa.types.is_boolean(column.type):
                continue
            try:
                values = self._int64_values(column)
                valid = pc.is_valid(column).to_numpy(zero_copy_only=False)
            except Exception:
                cells = column.to_pylist()
                converted = [self._optional_int(cell) for cell in cells]
                values = np.array([0 if c is None else c for c in converted], dtype=np.int64)
                valid = np.array([c is not None for c in converted], dtype=bool)
            take = ~chosen & valid & (values != 0)
            result[take] = values[take]
            chosen |= take
        return result

    def _spread_mask(self, batch_columns: dict[str, Any], rows: int) -> np.ndarray:
        """Vectorized ``_is_spread_symbol(row.get("raw_symbol") or row.get("symbol"))``:
        falsy (null/empty) raw_symbol falls through to symbol; spread = contains '-'."""

        import pyarrow as pa
        import pyarrow.compute as pc

        def text_column(name: str) -> Any:
            column = batch_columns.get(name)
            if column is None:
                return None
            try:
                return pc.cast(column, pa.string())
            except Exception:
                return pa.array(
                    [None if cell is None else self._as_text(cell) for cell in column.to_pylist()],
                    type=pa.string(),
                )

        raw = text_column("raw_symbol")
        sym = text_column("symbol")
        if raw is None and sym is None:
            return np.zeros(rows, dtype=bool)
        if raw is None:
            merged = sym
        elif sym is None:
            merged = pc.if_else(pc.equal(raw, ""), pa.nulls(rows, pa.string()), raw)
        else:
            falsy = pc.or_kleene(pc.is_null(raw), pc.equal(raw, ""))
            merged = pc.if_else(pc.fill_null(falsy, True), sym, raw)
        contains = pc.fill_null(pc.match_substring(merged, "-"), False)
        return contains.to_numpy(zero_copy_only=False)

    def _decode_batch(
        self,
        batch: Any,
        *,
        source: str,
        is_trade_schema: bool,
        is_mbp10: bool,
        is_tob: bool,
        front_month_id: int | None,
        ts_kind: str,
        ts_scale: int,
        start_us: int | None,
        end_us: int | None,
    ) -> tuple[list[DataQualityWarning], _DecodedBatch | None]:
        import pyarrow.compute as pc

        rows = batch.num_rows
        if rows == 0:
            return [], None
        columns = {name: batch.column(index) for index, name in enumerate(batch.schema.names)}

        ts_us, ts_sort, ts_valid, make_ts = self._ts_arrays(
            columns["ts_event"], ts_kind, ts_scale, source
        )

        keep = np.ones(rows, dtype=bool)
        if self.front_month_only:
            keep &= ~self._spread_mask(columns, rows)
            if front_month_id is not None:
                instrument = columns.get("instrument_id")
                if instrument is None:
                    keep &= False
                else:
                    inst_valid = pc.is_valid(instrument).to_numpy(zero_copy_only=False)
                    inst = self._int64_values(instrument)
                    keep &= inst_valid & (inst == front_month_id)

        side_values: list[str | None]
        side_column = columns.get("side")
        if side_column is not None:
            side_upper = self._upper_text(side_column)
            buy_mask = pc.fill_null(
                pc.equal(side_upper, BUY_AGGRESSOR_SIDE.upper()), False
            ).to_numpy(zero_copy_only=False)
            side_values = side_upper.to_pylist()
        else:
            buy_mask = np.zeros(rows, dtype=bool)
            side_values = [None] * rows

        if is_trade_schema:
            trade_rows = keep.copy()
        elif is_mbp10 or (is_tob and "action" in columns):
            # INGEST (D-P-17): action-bearing TOB schemas (mbp-1/tbbo) carry every
            # trade print as an action='T' row — classify them exactly like mbp-10
            # so mbp1.parquet store days are trade+quote first-class. bbo/cbbo files
            # have no action column and keep their quotes-only behavior.
            import pyarrow as pa

            action_upper = self._upper_text(columns["action"])
            trade_rows = keep & pc.fill_null(
                pc.is_in(action_upper, value_set=pa.array(["T", "TRADE"])), False
            ).to_numpy(zero_copy_only=False)
        else:
            trade_rows = np.zeros(rows, dtype=bool)

        if is_tob:
            quote_rows = keep.copy()
        elif is_mbp10:
            has_tob = np.zeros(rows, dtype=bool)
            for group in TOB_ALIASES:
                for name in group:
                    column = columns.get(name)
                    if column is not None:
                        has_tob |= pc.is_valid(column).to_numpy(zero_copy_only=False)
            quote_rows = keep & has_tob
        else:
            quote_rows = np.zeros(rows, dtype=bool)

        window = np.ones(rows, dtype=bool)
        if start_us is not None:
            window &= ts_us >= start_us
        if end_us is not None:
            window &= ts_us < end_us

        sequence = self._effective_sequence(columns, rows)

        warnings: list[DataQualityWarning] = []
        trade_warn = np.zeros(rows, dtype=bool)
        quote_warn = np.zeros(rows, dtype=bool)
        price_ticks = np.zeros(rows, dtype=np.int64)
        size_values = np.zeros(rows, dtype=np.int64)
        trade_emit = np.zeros(rows, dtype=bool)
        if trade_rows.any():
            price_ticks, price_valid = self._grid_ticks(columns.get("price"), rows)
            size_values, size_valid = self._strict_size(columns.get("size"), rows)
            trade_ok = ts_valid & price_valid & size_valid
            trade_warn = trade_rows & ~trade_ok
            trade_emit = trade_rows & trade_ok & window

        bid_ticks = np.zeros(rows, dtype=np.int64)
        ask_ticks = np.zeros(rows, dtype=np.int64)
        bid_sizes = np.zeros(rows, dtype=np.int64)
        ask_sizes = np.zeros(rows, dtype=np.int64)
        quote_emit = np.zeros(rows, dtype=bool)
        if quote_rows.any():
            import pyarrow as pa

            def merged_price(aliases: tuple[str, ...]) -> Any:
                present = [columns[name] for name in aliases if name in columns]
                if not present:
                    return None
                if len(present) == 1:
                    return present[0]
                try:
                    return pc.coalesce(*(pc.cast(col, pa.float64()) for col in present))
                except Exception:
                    return pa.array(
                        [
                            next((cell for cell in cells if cell is not None), None)
                            for cells in zip(*(c.to_pylist() for c in present), strict=True)
                        ]
                    )

            bid_ticks, bid_valid = self._grid_ticks(merged_price(TOB_ALIASES[0]), rows)
            ask_ticks, ask_valid = self._grid_ticks(merged_price(TOB_ALIASES[1]), rows)
            bid_sizes = self._optional_size(
                [columns[n] for n in BID_SIZE_ALIASES if n in columns], rows
            )
            ask_sizes = self._optional_size(
                [columns[n] for n in ASK_SIZE_ALIASES if n in columns], rows
            )
            quote_ok = ts_valid & bid_valid & ask_valid
            quote_warn = quote_rows & ~quote_ok
            quote_emit = quote_rows & quote_ok & window

        if trade_warn.any() or quote_warn.any():
            # Row order, trade item before the same row's quote item — exactly the
            # row-wise loop's yield order. INVALID_RECORD (bad size) carries the ts.
            for row in np.flatnonzero(trade_warn | quote_warn).tolist():
                if trade_warn[row]:
                    if not ts_valid[row]:
                        warnings.append(self._warning(DataQualityCode.INVALID_TIMESTAMP, "invalid historical parquet timestamp", source))
                    elif not price_valid[row]:
                        warnings.append(self._warning(DataQualityCode.INVALID_PRICE, "invalid historical parquet price", source))
                    else:
                        row_ts = make_ts(ts_sort[np.array([row])])[0]
                        warnings.append(self._warning(DataQualityCode.INVALID_RECORD, "invalid historical parquet record", source, event_ts_utc=row_ts))
                if quote_warn[row]:
                    if not ts_valid[row]:
                        warnings.append(self._warning(DataQualityCode.INVALID_TIMESTAMP, "invalid historical parquet timestamp", source))
                    else:
                        warnings.append(self._warning(DataQualityCode.INVALID_PRICE, "invalid historical parquet price", source))

        trade_idx = np.flatnonzero(trade_emit)
        quote_idx = np.flatnonzero(quote_emit)
        total = trade_idx.size + quote_idx.size
        if total == 0:
            return warnings, None

        zeros_q = np.zeros(quote_idx.size, dtype=np.int64)
        zeros_t = np.zeros(trade_idx.size, dtype=np.int64)
        signed = np.where(buy_mask[trade_idx], price_ticks[trade_idx], -price_ticks[trade_idx])
        cat_ts = np.concatenate((ts_sort[trade_idx], ts_sort[quote_idx]))
        cat_seq = np.concatenate((sequence[trade_idx], sequence[quote_idx]))
        cat_ssp = np.concatenate((signed, zeros_q))
        cat_size = np.concatenate((size_values[trade_idx], zeros_q))
        # Emission index = 2*row for the trade item, 2*row+1 for the quote item:
        # the stable tie-break reproducing the row-wise insertion order exactly.
        cat_emit = np.concatenate((trade_idx * 2, quote_idx * 2 + 1))
        order = np.lexsort((cat_emit, cat_size, cat_ssp, cat_seq, cat_ts))

        is_quote = np.concatenate(
            (np.zeros(trade_idx.size, dtype=bool), np.ones(quote_idx.size, dtype=bool))
        )[order]
        side_for_trades = [side_values[row] for row in trade_idx.tolist()]
        cat_side = side_for_trades + [None] * quote_idx.size
        decoded = _DecodedBatch(
            is_quote=is_quote,
            ts_sort=cat_ts[order],
            seq=cat_seq[order],
            ssp=cat_ssp[order],
            size=cat_size[order],
            price_ticks=np.concatenate((price_ticks[trade_idx], zeros_q))[order],
            side=[cat_side[position] for position in order.tolist()],
            bid_ticks=np.concatenate((zeros_t, bid_ticks[quote_idx]))[order],
            ask_ticks=np.concatenate((zeros_t, ask_ticks[quote_idx]))[order],
            bid_size=np.concatenate((zeros_t, bid_sizes[quote_idx]))[order],
            ask_size=np.concatenate((zeros_t, ask_sizes[quote_idx]))[order],
            make_ts=make_ts,
        )
        return warnings, decoded


    @staticmethod
    def _window_row_groups(
        parquet: Any, start: datetime | None, end: datetime | None
    ) -> list[int] | None:
        """Row groups whose ts_event range can intersect [start, end); None = all.

        Conservative by construction: any group whose statistics are absent or
        unreadable is kept. Returning ``None`` keeps the default full scan.
        """

        if start is None and end is None:
            return None
        try:
            ts_index = parquet.schema_arrow.names.index("ts_event")
        except ValueError:
            return None
        metadata = parquet.metadata
        groups: list[int] = []
        for group_index in range(metadata.num_row_groups):
            try:
                stats = metadata.row_group(group_index).column(ts_index).statistics
            except Exception:
                groups.append(group_index)
                continue
            if stats is None or not stats.has_min_max:
                groups.append(group_index)
                continue
            group_min, group_max = stats.min, stats.max
            if not isinstance(group_min, datetime) or not isinstance(group_max, datetime):
                groups.append(group_index)
                continue
            if group_min.tzinfo is None or group_max.tzinfo is None:
                groups.append(group_index)
                continue
            if start is not None and group_max < start:
                continue
            if end is not None and group_min >= end:
                continue
            groups.append(group_index)
        return groups

    def _front_month_instrument_id(
        self, parquet: Any, selected: list[str], row_groups: list[int] | None
    ) -> int | None:
        """Dominant non-spread instrument by TRADE-row count (ties -> larger id).

        Matches the Trade-Lab/Quant-Lab front-month rule: spread symbols (containing
        ``-``) are excluded, only trade rows are counted (every row counts for
        schemas without an ``action`` column), and ties break toward the larger
        instrument id. Vectorized (pyarrow compute) and restricted to the scanned
        row groups so the prescan never decodes more than the window does.
        """

        if "instrument_id" not in selected:
            return None
        import pyarrow as pa
        import pyarrow.compute as pc

        columns = [
            name
            for name in ("action", "instrument_id", "raw_symbol", "symbol")
            if name in selected
        ]
        if row_groups is None:
            table = parquet.read(columns=columns)
        elif not row_groups:
            return None
        else:
            table = parquet.read_row_groups(row_groups, columns=columns)
        if table.num_rows == 0:
            return None
        mask = None
        if "action" in columns:
            action = pc.utf8_lower(pc.cast(table["action"], pa.string()))
            mask = pc.is_in(action, value_set=pa.array(["t", "trade"]))
        for symbol_column in ("raw_symbol", "symbol"):
            if symbol_column in columns:
                not_spread = pc.invert(
                    pc.match_substring(pc.cast(table[symbol_column], pa.string()), "-")
                )
                not_spread = pc.fill_null(not_spread, True)
                mask = not_spread if mask is None else pc.and_kleene(mask, not_spread)
        instruments = table["instrument_id"]
        if mask is not None:
            instruments = instruments.filter(pc.fill_null(mask, False))
        instruments = instruments.drop_null().combine_chunks()
        if len(instruments) == 0:
            return None
        value_counts = pc.value_counts(instruments)
        ranked = [
            (count.as_py(), value.as_py())
            for value, count in zip(
                value_counts.field("values"), value_counts.field("counts"), strict=True
            )
            if value.as_py() is not None
        ]
        if not ranked:
            return None
        return max(ranked)[1]

    @staticmethod
    def _as_text(value: Any) -> str | None:
        """Decode parquet string-ish cells; mixed columns surface as bytes."""

        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

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
    def _warning(code: DataQualityCode, message: str, source: str, *, severity: DataQualitySeverity = DataQualitySeverity.WARNING, event_ts_utc: datetime | None = None, **metadata: Any) -> DataQualityWarning:
        return DataQualityWarning(code=code, message=message, severity=severity, source=source, event_ts_utc=event_ts_utc, metadata=metadata)
